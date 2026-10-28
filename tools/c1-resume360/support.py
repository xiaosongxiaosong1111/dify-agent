import contextlib,hashlib,json,sqlite3
from pathlib import Path
from guard import require,capture,digest

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
 def has_secret(self,item,key):
  with self.connect() as db:return db.execute('SELECT 1 FROM secrets WHERE id=?',(item+':'+key,)).fetchone() is not None

def current(project,plan):
 store=ReadOnly(project/'data');require(capture(store)==plan['protected_data'],'Protected production snapshot changed')
 require(len(store.list('task'))==18,'Original Task count changed')
 for task in store.list('task'):require(task.get('status') not in ('interviewing','planning','running','importing') and not task.get('active_interview_id') and not any(r.get('status')=='pending' for r in task.get('runs',[])),'Existing task not idle')
 for folder,files in plan['consumed_files'].items():
  for name,value in files.items():
   path=(project/'work'/folder/name).resolve();require(path.is_relative_to((project/'work'/folder).resolve()) and sha(path)==value,'Consumed receipt changed')
 env=store.get('environment',plan['environment_id']);provider=store.get('provider',plan['provider_id']);require(env and digest(env)==plan['environment_sha256'] and provider and digest(provider)==plan['provider_sha256'],'Connection or model/pricing changed')
 from reuse_policy import validate_start
 validate_start(store.get('task',plan['target_task_id']),store.get('task_budget',plan['target_task_id']),store.get('execution_limits',plan['target_task_id']),json.loads((Path(__file__).resolve().parent/'fixture.json').read_text('utf-8')),env['id'],provider['id'])
 return env,provider
