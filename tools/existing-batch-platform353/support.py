import contextlib,hashlib,json,sqlite3
from pathlib import Path
from boundary import require
from data_guard import capture

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
class ReadOnly:
 def __init__(self,root):self.root=Path(root)
 @contextlib.contextmanager
 def connect(self):
  db=sqlite3.connect((self.root/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True)
  try:yield db
  finally:db.close()
 def get(self,kind,item):
  with self.connect() as db:r=db.execute('SELECT value FROM objects WHERE kind=? AND id=?',(kind,item)).fetchone()
  return json.loads(r[0]) if r else None
 def list(self,kind):
  with self.connect() as db:return [json.loads(v) for v, in db.execute('SELECT value FROM objects WHERE kind=? ORDER BY rowid DESC',(kind,))]
 def secret(self,item,key):
  require(key=='console_token','Read-only freeze may inspect console summary only')
  with self.connect() as db:r=db.execute('SELECT value FROM secrets WHERE id=?',(item+':'+key,)).fetchone()
  return self.cipher.decrypt(bytes(r[0])).decode('utf-8') if r else None
 def has_secret(self,item,key):
  with self.connect() as db:return db.execute('SELECT 1 FROM secrets WHERE id=?',(item+':'+key,)).fetchone() is not None

def check_consumed(project,plan):
 for folder,files in plan['consumed_files'].items():
  for name,value in files.items():
   path=(project/'work'/folder/name).resolve();require(path.is_relative_to((project/'work'/folder).resolve()) and sha(path)==value,'Consumed file changed')

def current(plan,store):
 require(capture(store)==plan['protected_data'],'Production snapshot changed')
 task=store.get('task',plan['task_id']);env=store.get('environment',plan['environment_id']);proof=store.get('publication_dispatch_evidence',plan['evidence_id'])
 require(task and sha_value(task)==plan['task_sha256'] and task['revision']==plan['revision'] and task.get('dify_app_id')==plan['app_id'],'Existing Task changed')
 require(proof and sha_value(proof)==plan['evidence_sha256'],'Registered evidence changed')
 require(env and sha_value(env)==plan['environment_sha256'],'Connection changed')
 require(len(store.list('task'))==17 and not store.list('publication_recovery'),'Unexpected Task count or prior recovery declaration')
 require(not any(r.get('status')=='pending' for t in store.list('task') for r in t.get('runs',[])),'Pending Task operation')
 require(store.get('workflow_publication',plan['old_publication_id'])['state']=='unknown','Original unknown changed')
 require(all(not store.get('app_runtime_credential',plan['environment_id']+':app-runtime:'+plan['app_id']) for _ in [0]),'Target already has local runtime binding')
 return task,env,proof

def sha_value(value):
 from boundary import digest
 return digest(value)
