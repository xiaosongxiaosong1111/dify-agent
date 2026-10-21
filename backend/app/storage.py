"""Local persistent store. Credentials never enter task snapshots."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from cryptography.fernet import Fernet


class _ScopedConnection(sqlite3.Connection):
    """Keep SQLite commit/rollback behavior and release its handle at scope exit."""
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "flowcraft.sqlite3"
        self.lock = threading.RLock()
        key_file = root / ".credential-key"
        if not key_file.exists():
            with key_file.open("xb") as handle:
                handle.write(Fernet.generate_key())
        self.cipher = Fernet(key_file.read_bytes())
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS objects (kind TEXT NOT NULL, id TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(kind,id))")
            conn.execute("CREATE TABLE IF NOT EXISTS secrets (id TEXT PRIMARY KEY, value BLOB NOT NULL)")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15, factory=_ScopedConnection)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except BaseException:
            conn.close()
            raise
        return conn

    def get(self, kind: str, item_id: str):
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM objects WHERE kind=? AND id=?", (kind, item_id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str):
        with self.connect() as conn:
            rows = conn.execute("SELECT value FROM objects WHERE kind=? ORDER BY rowid DESC", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put(self, kind: str, item_id: str, value: dict):
        with self.lock, self.connect() as conn:
            conn.execute("INSERT INTO objects(kind,id,value) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value", (kind, item_id, json.dumps(value, ensure_ascii=False)))

    def put_many(self, records):
        """Commit related task and operation records in one transaction."""
        with self.lock, self.connect() as conn:
            for kind, item_id, value in records:
                conn.execute("INSERT INTO objects(kind,id,value) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value", (kind,item_id,json.dumps(value,ensure_ascii=False)))

    def put_with_secrets(self, kind: str, item_id: str, value: dict, secrets: dict[str, str]):
        """Commit matched connection metadata and encrypted credentials atomically."""
        encrypted = {key: self.cipher.encrypt(token.encode()) if token else None for key, token in secrets.items()}
        with self.lock, self.connect() as conn:
            conn.execute("INSERT INTO objects(kind,id,value) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value", (kind, item_id, json.dumps(value, ensure_ascii=False)))
            for key, token in encrypted.items():
                if token is None:
                    conn.execute("DELETE FROM secrets WHERE id=?", (item_id + ":" + key,))
                else:
                    conn.execute("INSERT INTO secrets(id,value) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (item_id + ":" + key, token))

    def put_many_with_secrets(self, records, item_id: str, secrets: dict[str, str]):
        """Atomically commit an explicit connection receipt and its encrypted tokens."""
        encrypted = {key: self.cipher.encrypt(value.encode()) if value else None for key, value in secrets.items()}
        with self.lock, self.connect() as conn:
            for kind, ident, value in records:
                conn.execute("INSERT INTO objects(kind,id,value) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value", (kind, ident, json.dumps(value, ensure_ascii=False)))
            for key, value in encrypted.items():
                if value is None: conn.execute("DELETE FROM secrets WHERE id=?", (item_id + ':' + key,))
                else: conn.execute("INSERT INTO secrets(id,value) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (item_id + ':' + key, value))

    def delete(self, kind: str, item_id: str):
        with self.lock, self.connect() as conn:
            conn.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, item_id))
            conn.execute("DELETE FROM secrets WHERE id LIKE ?", (item_id + ":%",))

    def set_secret(self, item_id: str, key: str, value: str):
        if value:
            with self.lock, self.connect() as conn:
                conn.execute("INSERT INTO secrets(id,value) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (item_id + ":" + key, self.cipher.encrypt(value.encode())))

    def secret(self, item_id: str, key: str):
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM secrets WHERE id=?", (item_id + ":" + key,)).fetchone()
        return self.cipher.decrypt(row[0]).decode() if row else ""

    def has_secret(self, item_id: str, key: str):
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM secrets WHERE id=?", (item_id + ":" + key,)).fetchone() is not None
