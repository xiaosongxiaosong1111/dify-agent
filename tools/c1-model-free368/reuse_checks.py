"""Exercise source and ledger preservation using temporary copies of the public case."""
import copy,json,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1];sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
from app.storage import Store
from support import ReadOnly
from guard import capture,guarded_store
from boundary import ModelFreeBoundary
from reuse_policy import validate_start
checks=[]

def reject(name,fn):
 try:fn()
 except RuntimeError:checks.append(name);return
 raise AssertionError('Accepted '+name)

source=ReadOnly(PROJECT/'data');tid='aa827c91-b683-4a34-9e7f-fa0789f5c252';eid='202bfb35-2f92-47c1-bc1b-eac32082181d';pid='9513f594-c256-46b7-882a-35d9871bf9d0'
task=source.get('task',tid);budget=source.get('task_budget',tid);limits=source.get('execution_limits',tid);env=source.get('environment',eid);provider=source.get('provider',pid);fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'))
with tempfile.TemporaryDirectory(dir=PROJECT/'work',prefix='model-free-store-') as folder:
 base=Store(Path(folder));base.put('task',tid,task);base.put('task_budget',tid,budget);base.put('execution_limits',tid,limits);other=str(uuid.uuid4());base.put('task',other,{'id':other,'name':'public other Task'});base.set_secret(pid,'api_key','PUBLIC_REDACTION_ONLY');base.set_secret(eid,'console_token','PUBLIC_OLD_AUTH')
 old=capture(base);b=ModelFreeBoundary(env,provider,fixture,{'phase':'reconnect'},[]);b.owner=tid;b.owner_configured=True;Guarded=guarded_store(Store,old,env,provider,b,fixture,task,budget);store=Guarded(base.root)
 assert validate_start(task,budget,limits,fixture,eid,pid);checks.append('exact saved revision13 and six old entries admitted')
 for key,value in [('revision',14),('status','planning'),('requirements_confirmed',False),('configuration_confirmed',False),('plan_stale',True),('workflow_plan',{}),('dify_app_id','unexpected')]:
  t=copy.deepcopy(task);t[key]=value;reject('preflight drift '+key,lambda:validate_start(t,budget,limits,fixture,eid,pid))
 for key in ('messages','versions','interview_attempts','runs','planning_runs','intake_history'):
  t=copy.deepcopy(task);t[key]=[];reject('cannot erase old '+key,lambda:store.put('task',tid,t));assert base.get('task',tid)==task
 reject('cannot overwrite other Task',lambda:store.put('task',other,{'id':other,'name':'changed'}))
 reject('cannot create replacement Task',lambda:store.put('task',str(uuid.uuid4()),task))
 reject('cannot change original run cap',lambda:store.put('execution_limits',tid,limits|{'max_started_runs':5}))
 for change in ('append','remove','cost','status','policy'):
  updated=copy.deepcopy(budget)
  if change=='append':updated['entries'].append({'id':'forbidden-model-reservation'})
  elif change=='remove':updated['entries'].pop()
  elif change=='cost':updated['entries'][0]['charged_usd']='0'
  elif change=='status':updated['entries'][0]['status']='unknown'
  else:updated['limit_usd']='0'
  reject('zero new model ledger '+change,lambda:store.put('task_budget',tid,updated));assert base.get('task_budget',tid)==budget
 assert store.secret(pid,'api_key')=='PUBLIC_REDACTION_ONLY';checks.append('selected existing key readable only for local diagnostic redaction')
 reject('unrelated credential read',lambda:store.secret('other-provider','api_key'))
 reject('auth cannot commit before original workspace proof',lambda:store.set_secret(eid,'console_token','PUBLIC_NEW_AUTH'))
 b.workspace_verified=True;reject('auth cannot commit without observed returned token',lambda:store.set_secret(eid,'console_token','PUBLIC_NEW_AUTH'))
 b.login_tokens={'console_token':'PUBLIC_NEW_AUTH','csrf_token':'PUBLIC_NEW_CSRF'};store.set_secret(eid,'console_token','PUBLIC_NEW_AUTH');assert store.secret(eid,'console_token')=='PUBLIC_NEW_AUTH';checks.append('observed auth token commits only with workspace proof')
 reject('saved password remains immutable',lambda:store.set_secret(eid,'console_login_password','PUBLIC_NEW_PASSWORD'))
 t=copy.deepcopy(task);t['messages'].append({'role':'assistant','source':'system','content':'public local progress'});t['revision']=14;store.put('task',tid,t);assert base.get('task',tid)['runs']==task['runs'];checks.append('normal new local revision keeps original runs and history')
 print(json.dumps({'state':'passed','checks':len(checks),'physical_http':0,'production_store_constructed':False}))
