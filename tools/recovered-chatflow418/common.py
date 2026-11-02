"""Local immutable-source utilities; never decrypt credentials."""
import contextlib
import hashlib
import json
import sqlite3
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[2]
LIMITS={'model':3,'reads':0,'login':0,'new_tasks':0,'import':0,'publish':0,'key':0,'run':0}

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

SEED={'task_id':'89b0763f-2fac-4974-8e47-df59955c8853','task_sha256':'74c6633f392dc5325f72ced27fdfdbd58842c0f6b0bd9afac8c67918bcae3bee','response_sha256':'036cdbb3e3f3fb1ff6ef40f647d749e384ffc377dc8c05795b25de4ae20ef629','attempt_sha256':'ff6259301cd8b236f0761cb623d2f5965f7498e50bd0245b5ec536d9317927de'}

def saved_seed():
    root=PROJECT/'work/autonomous-chatflow416'
    task=ReadOnly(root/'live-output/data').get('task',SEED['task_id'])
    raw=(root/'live-output/model-response-vague_interview.txt').read_text('utf-8')
    require(digest(task)==SEED['task_sha256'] and sha(root/'live-output/model-response-vague_interview.txt')==SEED['response_sha256'] and sha(root/'attempt.json')==SEED['attempt_sha256'],'Saved first-candidate source changed')
    require(task['revision']==2 and task['app_type']=='advanced-chat' and task['status']=='requirements' and not any(task.get(k) for k in ('materials','workflow_plan','agent_plan','artifact','dify_app_id','runs','dsl_reference','dsl_overlay')),'Only the original empty initial draft')
    attempts=task.get('interview_attempts',[])
    require(len(attempts)==1 and attempts[0]['response_excerpt']==raw and attempts[0]['applied'] is False and attempts[0]['response_truncated'] is False,'Complete unapplied source only')
    return task,raw
