"""Local immutable-source utilities; never decrypt credentials."""
import contextlib
import hashlib
import json
import sqlite3
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[2]
LIMITS={'model':1,'reads':0,'login':0,'new_tasks':0,'import':0,'publish':0,'key':0,'run':0}

def require(value,message):
    if not value:raise RuntimeError(message)

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def uuid(value):
    from uuid import UUID
    try:return isinstance(value,str) and str(UUID(value))==value
    except (ValueError,AttributeError):return False

class ReadOnly:
    def __init__(self,root):self.root=Path(root)
    @contextlib.contextmanager
    def connect(self):
        db=sqlite3.connect((self.root/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True)
        try:yield db
        finally:db.close()
    def get(self,kind,item):
        with self.connect() as db:row=db.execute('SELECT value FROM objects WHERE kind=? AND id=?',(kind,item)).fetchone()
        return json.loads(row[0]) if row else None
    def list(self,kind):
        with self.connect() as db:return [json.loads(row[0]) for row in db.execute('SELECT value FROM objects WHERE kind=?',(kind,))]

def capture(store):
    with store.connect() as db:
        objects={k+':'+i:digest(json.loads(v)) for k,i,v in db.execute('SELECT kind,id,value FROM objects')}
        secrets={i:hashlib.sha256(bytes(v)).hexdigest() for i,v in db.execute('SELECT id,value FROM secrets')}
    files={}
    for path in store.root.rglob('*'):
        if not path.is_file() or path.parent==store.root and path.name in {'flowcraft.sqlite3','flowcraft.sqlite3-shm','flowcraft.sqlite3-wal','server.pid','server.out.log','server.err.log'}:continue
        require(path.resolve().is_relative_to(store.root.resolve()),'Asset link outside data root')
        files[str(path.relative_to(store.root))]=sha(path)
    return {'objects':objects,'secrets':secrets,'files':files}

def known_apps(store):
    result=set()
    for kind in ('environment','task','app_runtime_credential','workflow_publication','app_runtime_key_creation','runtime_key_previous_binding'):
        for row in store.list(kind):
            for key in ('app_id','dify_app_id','service_app_id'):
                if uuid(row.get(key)):result.add(row[key])
            for run in row.get('runs',[]):
                if uuid(run.get('app_id')):result.add(run['app_id'])
                value=run.get('result')
                if isinstance(value,dict) and uuid(value.get('app_id')):result.add(value['app_id'])
    return result
