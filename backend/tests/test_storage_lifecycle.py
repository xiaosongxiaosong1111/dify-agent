import gc,json,sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import storage
from app.storage import Store

@pytest.fixture
def connections(monkeypatch):
    original=sqlite3.connect;opened=[]
    def connect(*args,**kwargs):
        parent=kwargs.get('factory',sqlite3.Connection)
        class Observed(parent):
            scope_closed=False
            def close(self):
                result=super().close();self.scope_closed=True;return result
        kwargs['factory']=Observed;conn=original(*args,**kwargs);opened.append(conn);return conn
    monkeypatch.setattr(storage.sqlite3,'connect',connect)
    return opened

def test_all_store_operations_close_connections_without_gc_and_preserve_existing_key(tmp_path,connections):
    was_enabled=gc.isenabled();gc.disable()
    try:
        store=Store(tmp_path);key=(tmp_path/'.credential-key').read_bytes()
        store.put('task','one',{'text':'原文字'});store.put_many([('task','two',{'n':2}),('operation','op',{'state':'saved'})])
        store.put_with_secrets('provider','model',{'name':'公开测试'}, {'api_key':'isolated-fake-key'})
        assert store.get('task','one')=={'text':'原文字','state_sequence':1} and len(store.list('task'))==2
        assert store.has_secret('model','api_key') and store.secret('model','api_key')=='isolated-fake-key'
        store.set_secret('model','second','isolated-second');store.put_with_secrets('provider','model',{'name':'更新'}, {'second':''})
        assert not store.has_secret('model','second')
        reopened=Store(tmp_path);assert reopened.secret('model','api_key')=='isolated-fake-key' and (tmp_path/'.credential-key').read_bytes()==key
        store.delete('provider','model');assert store.get('provider','model') is None and not store.has_secret('model','api_key')
        assert connections and all(conn.scope_closed for conn in connections)
        for conn in connections:
            with pytest.raises(sqlite3.ProgrammingError,match='closed'):conn.execute('SELECT 1')
        # Even strong references to all handles cannot prevent moving the DB on Windows.
        moved=tmp_path/'released.sqlite3';assert moved.resolve().parent==tmp_path.resolve()
        store.path.rename(moved)
        with closing(sqlite3.connect(moved)) as conn:assert conn.execute('SELECT count(*) FROM objects WHERE kind=?',('task',)).fetchone()[0]==2
    finally:
        if was_enabled:gc.enable()

def test_partial_batch_error_rolls_back_every_change_and_closes(tmp_path,connections):
    store=Store(tmp_path);store.put('task','one',{'original':True})
    with pytest.raises(TypeError):store.put_many([('task','one',{'changed':True}),('task','bad',{'not_json':object()})])
    assert store.get('task','one')=={'original':True,'state_sequence':1} and store.get('task','bad') is None
    assert all(c.scope_closed for c in connections)

def test_secret_and_metadata_transaction_failure_keeps_original_ciphertext(tmp_path,connections):
    store=Store(tmp_path);store.put_with_secrets('provider','one',{'name':'旧设置'},{'api_key':'old-fake-value'})
    with store.connect() as conn:
        before=conn.execute('SELECT value FROM secrets WHERE id=?',('one:api_key',)).fetchone()[0]
        conn.execute("CREATE TRIGGER reject_fixture BEFORE INSERT ON secrets WHEN NEW.id='one:blocked' BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
    with pytest.raises(sqlite3.IntegrityError):store.put_with_secrets('provider','one',{'name':'新设置'},{'api_key':'new-fake-value','blocked':'reject'})
    assert store.get('provider','one')=={'name':'旧设置'} and store.secret('one','api_key')=='old-fake-value' and not store.has_secret('one','blocked')
    with store.connect() as conn:assert conn.execute('SELECT value FROM secrets WHERE id=?',('one:api_key',)).fetchone()[0]==before
    assert all(c.scope_closed for c in connections)

def test_failed_commit_still_rolls_back_and_closes_handle(tmp_path,connections):
    store=Store(tmp_path);conn=store.connect()
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute('PRAGMA foreign_keys=ON');conn.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)');conn.execute('CREATE TABLE child(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)');conn.execute('INSERT INTO child VALUES(1)')
    assert conn.scope_closed
    with store.connect() as check:assert check.execute('SELECT count(*) FROM child').fetchone()[0]==0

@pytest.mark.parametrize('error',[sqlite3.OperationalError('fixture setup failure'),KeyboardInterrupt()],ids=['sqlite-error','interrupted'])
def test_setup_failure_or_interrupt_closes_before_returning(tmp_path,monkeypatch,error):
    store=Store(tmp_path);original=sqlite3.connect;opened=[]
    class Broken(storage._ScopedConnection):
        def execute(self,sql,*args):
            if sql=='PRAGMA journal_mode=WAL':raise error
            return super().execute(sql,*args)
    def connect(*args,**kwargs):
        kwargs['factory']=Broken;value=original(*args,**kwargs);opened.append(value);return value
    monkeypatch.setattr(storage.sqlite3,'connect',connect)
    with pytest.raises(type(error)):store.connect()
    with pytest.raises(sqlite3.ProgrammingError,match='closed'):opened[0].execute('SELECT 1')

def test_parallel_independent_writes_keep_matching_encrypted_values_and_no_open_handles(tmp_path,connections):
    store=Store(tmp_path)
    def write(index):
        key=f'entry-{index}';value=f'isolated-{index}'
        store.put_with_secrets('provider',key,{'index':index},{'api_key':value})
        assert store.get('provider',key)=={'index':index} and store.secret(key,'api_key')==value
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(write,range(24)))
    assert len(store.list('provider'))==24 and all(c.scope_closed for c in connections)
