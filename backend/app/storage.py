"""Local persistent store. Credentials never enter task snapshots."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
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

    def task_summaries(self):
        """Return only sidebar fields; do not decode task bodies in Python."""
        fields=('id','name','app_type','revision','status','updated_at')
        with self.connect() as conn:
            rows=conn.execute("""SELECT json_extract(value,'$.id'),json_extract(value,'$.name'),
                json_extract(value,'$.app_type'),json_extract(value,'$.revision'),
                json_extract(value,'$.status'),json_extract(value,'$.updated_at'),json_type(value,'$.revision')
                FROM objects WHERE kind=? ORDER BY rowid DESC""",('task',)).fetchall()
        result=[]
        for row in rows:
            item=dict(zip(fields,row[:6]))
            if row[6]!='integer':item['revision']=None
            result.append(item)
        return result

    @contextmanager
    def _writing(self):
        with self.lock:
            states=[]
            with self.connect() as conn:
                # Serialize read/increment/write across Store instances too.
                conn.execute("BEGIN IMMEDIATE")
                yield conn,states
            # A rolled-back transaction must not publish successful sequence IDs.
            for value,sequence in states:value['state_sequence']=sequence

    def _put_object(self,conn,states,kind,item_id,value):
        prepared=value
        if kind=='task':
            prior=conn.execute("SELECT json_extract(value,'$.state_sequence'),json_type(value,'$.state_sequence') FROM objects WHERE kind=? AND id=?",(kind,item_id)).fetchone()
            sequence=0
            if prior and prior[1] is not None:
                if prior[1]!='integer' or prior[0]<0 or prior[0]>=9007199254740991:raise ValueError('任务状态序号无法核对或超出范围，原记录保持；请核对本机数据。')
                sequence=prior[0]
            sequence+=1;prepared={**value,'state_sequence':sequence};states.append((value,sequence))
        conn.execute("INSERT INTO objects(kind,id,value) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value", (kind,item_id,json.dumps(prepared,ensure_ascii=False)))

    def put(self, kind: str, item_id: str, value: dict):
        with self._writing() as (conn,states):
            self._put_object(conn,states,kind,item_id,value)

    def put_many(self, records):
        """Commit related task and operation records in one transaction."""
        with self._writing() as (conn,states):
            for kind, item_id, value in records:
                self._put_object(conn,states,kind,item_id,value)

    def put_with_secrets(self, kind: str, item_id: str, value: dict, secrets: dict[str, str]):
        """Commit matched connection metadata and encrypted credentials atomically."""
        encrypted = {key: self.cipher.encrypt(token.encode()) if token else None for key, token in secrets.items()}
        with self._writing() as (conn,states):
            self._put_object(conn,states,kind,item_id,value)
            for key, token in encrypted.items():
                if token is None:
                    conn.execute("DELETE FROM secrets WHERE id=?", (item_id + ":" + key,))
                else:
                    conn.execute("INSERT INTO secrets(id,value) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (item_id + ":" + key, token))

    def put_many_with_secrets(self, records, item_id: str, secrets: dict[str, str]):
        """Atomically commit an explicit connection receipt and its encrypted tokens."""
        encrypted = {key: self.cipher.encrypt(value.encode()) if value else None for key, value in secrets.items()}
        with self._writing() as (conn,states):
            for kind, ident, value in records:
                self._put_object(conn,states,kind,ident,value)
            for key, value in encrypted.items():
                if value is None: conn.execute("DELETE FROM secrets WHERE id=?", (item_id + ':' + key,))
                else: conn.execute("INSERT INTO secrets(id,value) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (item_id + ':' + key, value))

    def put_many_with_secret_sets(self, records, secret_sets):
        """Commit related records and credentials for multiple owners atomically."""
        encrypted = [(owner + ':' + name, self.cipher.encrypt(value.encode()))
                     for owner, values in secret_sets.items() for name, value in values.items()]
        with self._writing() as (conn,states):
            for kind, ident, value in records:
                self._put_object(conn,states,kind,ident,value)
            for ident, value in encrypted:
                conn.execute("INSERT INTO secrets(id,value) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (ident, value))

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
