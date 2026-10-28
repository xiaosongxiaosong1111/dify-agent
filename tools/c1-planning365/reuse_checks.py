"""Exercise the real guarded Store with disposable old failure/ledger history."""
import copy,json,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
from app.storage import Store
from guard import Boundary,capture,guarded_store
from reuse_policy import validate_start,preserve_task,preserve_budget
fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));checks=[]
def reject(name,fn):
 try:fn()
 except RuntimeError:checks.append(name);return
 raise AssertionError('Accepted '+name)
with tempfile.TemporaryDirectory(dir=PROJECT/'work',prefix='c1-reuse-checks-') as folder:
 base=Store(Path(folder));tid,eid,pid,other=[str(uuid.uuid4()) for _ in range(4)]
 config=copy.deepcopy(fixture['configuration']);config['assistant_provider_id']=pid
 task={'id':tid,'name':fixture['task_name'],'app_type':'workflow','created_at':'public-old-time','revision':7,'status':'requirements','environment_id':eid,'configuration':config,'requirements':{key:'公开未决'+key for key in fixture['requirements']},'test_cases':copy.deepcopy(fixture['cases']),'intake_required':True,'plan_review_required':True,'requirements_confirmed':False,'configuration_confirmed':False,'messages':[{'role':'user','content':'公开旧需求'}],'versions':[{'id':'public-old-version','revision':1}],'interview_attempts':[{'applied':False,'response_truncated':False,'response_excerpt':'public old rejected candidate'}],'runs':[],'planning_runs':[]}
 task['intake_review']={'source':'saved_model_candidate','origin_revision':7,'review':{'checks':[{'topic':key,'status':'complete'} for key in [*fixture['requirements'],'retrieval']],'questions':[]}}
 task['interview_attempts']*=3
 budget={'id':tid,'policy_revision':0,'limit_usd':None,'created_at':'public-old-time','entries':[{'id':'public-old-entry','status':'settled','call_status':'returned','charged_usd':'0.004333872','usage':{'prompt_tokens':8624,'completion_tokens':1581}}],'policy_history':[]}
 budget['entries']*=4
 limits={'id':tid,'max_started_runs':4,'max_total_minutes':20,'max_reported_cost_usd':None}
 env={'id':eid,'base_url':'https://public-dify.invalid','service_app_id':None,'capabilities':{}}
 provider={'id':pid,'base_url':'https://api.deepseek.com','model':'deepseek-flash'}
 base.put('task',tid,task);base.put('task_budget',tid,budget);base.put('execution_limits',tid,limits);base.put('task',other,{'id':other,'name':'unrelated public Task'})
 old=capture(base);b=Boundary(env,provider,fixture,{},[]);b.owner=tid;b.owner_configured=True
 Guarded=guarded_store(Store,old,env,provider,b,fixture,task,budget);guard=Guarded(base.root)
 assert validate_start(task,budget,limits,fixture,eid,pid);checks.append('preserved unresolved interview admitted')
 for field,value in [('revision',4),('status','planning'),('app_type','advanced-chat'),('requirements',{'goal':'new'}),('intake_required',False),('workflow_plan',{'nodes':[]}),('interview_attempts',[])]:
  changed=copy.deepcopy(task);changed[field]=value
  reject('preflight drift '+field,lambda:validate_start(changed,budget,limits,fixture,eid,pid))
 changed=copy.deepcopy(task);changed['configuration']['temperature']=.9
 reject('preflight changed configuration',lambda:validate_start(changed,budget,limits,fixture,eid,pid))
 changed=copy.deepcopy(task);changed['test_cases'][1]['input']={'query':'different'}
 reject('preflight changed case',lambda:validate_start(changed,budget,limits,fixture,eid,pid))
 reject('preflight changed settled budget',lambda:validate_start(task,budget|{'entries':[]},limits,fixture,eid,pid))
 reject('preflight changed run limit',lambda:validate_start(task,budget,limits|{'max_started_runs':5},fixture,eid,pid))
 for field in ('messages','versions','interview_attempts'):
  changed=copy.deepcopy(task);changed[field]=[]
  reject('actual Store cannot erase '+field,lambda:guard.put('task',tid,changed));assert base.get('task',tid)==task
 reject('actual Store cannot overwrite other Task',lambda:guard.put('task',other,{'id':other,'name':'changed'}))
 reject('actual Store cannot create a replacement Task',lambda:guard.put('task',str(uuid.uuid4()),task))
 reject('actual Store cannot change original limits',lambda:guard.put('execution_limits',tid,limits|{'max_started_runs':5}))
 for change in ('delete','cost','usage','status','policy'):
  changed=copy.deepcopy(budget)
  if change=='delete':changed['entries']=[]
  elif change=='policy':changed['limit_usd']='1'
  else:changed['entries'][0][{'cost':'charged_usd','usage':'usage','status':'status'}[change]]='tampered'
  reject('actual Store protects old ledger '+change,lambda:guard.put('task_budget',tid,changed));assert base.get('task_budget',tid)==budget
 changed=copy.deepcopy(task);changed['messages'].append({'role':'user','content':'公开新说明'});changed['revision']=8
 guard.put('task',tid,changed);assert base.get('task',tid)==changed;checks.append('normal append preserves old failure and versions')
 changed_budget=copy.deepcopy(budget);changed_budget['entries'].append({'id':'new','status':'reserved'})
 guard.put('task_budget',tid,changed_budget);assert base.get('task_budget',tid)['entries'][0]==budget['entries'][0];checks.append('new reservation keeps settled original cost')
 for _ in range(2):changed_budget['entries'].append({'id':str(uuid.uuid4())})
 reject('new ledger cap counts three additional entries only',lambda:guard.put('task_budget',tid,changed_budget))
 print(json.dumps({'state':'passed','checks':len(checks),'physical_http':0,'production_store_constructed':False}))
