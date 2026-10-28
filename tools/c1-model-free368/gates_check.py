"""Admission/review negatives in disposable fixtures; never live resource authority."""
import copy,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1];sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
import execute
from guard import digest
from support import sha,ReadOnly
from reviews import Reviews,require_reviewed_content
from submit_review import submit
checks=[]

def reject(name,fn):
 try:fn()
 except (RuntimeError,ValueError,OSError,KeyError,HTTPException):checks.append(name);return
 raise AssertionError('Accepted '+name)

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False),'utf-8')

with tempfile.TemporaryDirectory(dir=PROJECT/'work',prefix='model-free-gates-') as folder:
 root=Path(folder)/'work/c1-model-free368';root.mkdir(parents=True)
 for name in execute.FROZEN-{'plan.json'}:(root/name).write_bytes((ROOT/name).read_bytes())
 plan={'schema_version':1,'batch_id':'c1-model-free368','target_task_id':'aa827c91-b683-4a34-9e7f-fa0789f5c252','explicit_regrant':{'from_batch':'c1-planning365','model':0,'reads':28,'import':1,'publish':1,'key':1,'run':2,'new_model_slots':0,'new_reads':0,'new_login':1},'limits':execute.LIMITS,'local_preparation':{'resource_note_only_configuration_change':True,'test_text_literal_sync_only':True,'same_model_plan_revalidated':True,'no_model_generation':True},'wall_seconds':1800,'max_each_model_estimate_usd':'0.055','max_new_model_estimate_usd':'0'}
 write(root/'plan.json',plan)
 def manifest():write(root/'manifest.json',{'schema_version':1,'batch_id':plan['batch_id'],'files':{n:sha(root/n) for n in execute.FROZEN}})
 manifest();assert execute.validated(root)==plan;checks.append('exact zero-model frozen scope')
 reject('missing direct approval',lambda:execute.approved(root,plan))
 approval={'authorization_source':'direct_human_reply','decision':'approve','batch_id':plan['batch_id'],'plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json'),'limits':execute.LIMITS,'new_independent_scope':True,'old_reservations_preserved':True,'model_estimate_book_upper_usd':'0.755473652','target_task_id':plan['target_task_id'],'explicit_regrant':plan['explicit_regrant'],'question_ref':'SYNTHETIC_SCHEMA_ONLY','reply':'synthetic scope schema, not actual permission'}
 for key,value in [('authorization_source','agent_delegated'),('decision','deny'),('batch_id','old365'),('plan_sha256','0'*64),('manifest_sha256','0'*64),('limits',execute.LIMITS|{'model':1}),('new_independent_scope',False),('old_reservations_preserved',False),('model_estimate_book_upper_usd','0'),('target_task_id','other'),('explicit_regrant',{}),('question_ref',' '),('reply',' ')]:
  write(root/'approval.json',approval|{key:value});reject('approval '+key,lambda:execute.approved(root,plan))
 write(root/'approval.json',approval);assert execute.approved(root,plan)==approval
 for key,value in [('limits',execute.LIMITS|{'model':1}),('limits',execute.LIMITS|{'reads':29}),('limits',execute.LIMITS|{'import':2}),('limits',execute.LIMITS|{'run':3}),('limits',execute.LIMITS|{'login':2}),('limits',execute.LIMITS|{'model':False}),('local_preparation',{}),('local_preparation',{'resource_note_only_configuration_change':1,'test_text_literal_sync_only':True,'same_model_plan_revalidated':True,'no_model_generation':True}),('wall_seconds',1801),('max_new_model_estimate_usd','0.01'),('explicit_regrant',{}),('target_task_id','other')]:
  write(root/'plan.json',plan|{key:value});manifest();reject('scope '+key+str(value),lambda:execute.validated(root))
 write(root/'plan.json',plan);manifest();write(root/'approval.json',approval|{'plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json')})
 original=(root/'boundary.py').read_bytes();(root/'boundary.py').write_bytes(b'tampered');reject('transport boundary tamper',lambda:execute.validated(root));(root/'boundary.py').write_bytes(original);manifest();write(root/'approval.json',approval|{'manifest_sha256':sha(root/'manifest.json')})
 record={'batch_id':plan['batch_id'],'state':'admission_started','phase':'preflight','plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json'),'approval_sha256':sha(root/'approval.json')}
 execute.claim(root,record);reject('one exclusive attempt',lambda:execute.claim(root,record))
 with patch.object(execute,'ROOT',root),patch.object(execute,'PROJECT',Path(folder)),patch.object(execute,'current',lambda *a:None):
  execute.authorize_worker(plan,record|{'model_requests':[]});checks.append('worker admission with empty model history')
  reject('worker starts once',lambda:execute.authorize_worker(plan,record))
 reject('source entry cannot execute live',execute.main)
 admission_project=Path(folder)/'admission';admission_root=admission_project/'work/c1-model-free368';admission_root.mkdir(parents=True)
 for reason in ('source','runtime'):
  def source_check(*a):
   if reason=='source':raise RuntimeError('Synthetic source drift')
  def readiness(*a):raise execute.NotReady('Synthetic service is not ready')
  with patch.object(execute,'ROOT',admission_root),patch.object(execute,'PROJECT',admission_project),patch.object(execute,'validated',lambda _: {'playwright_path':str(admission_project)}),patch.object(execute,'approved',lambda *a:None),patch.object(execute,'current',source_check),patch.object(execute,'runtime_check',readiness),patch.object(sys,'argv',['execute.py','live','--playwright',str(admission_project)]):
   reject('admission stops before consumption on '+reason,execute.main)
  assert not (admission_root/'attempt.json').exists() and not (admission_root/'worker-started.json').exists()
 graph={'schema_version':1,'nodes':[{'id':'public'}]};task={'id':'public-task','revision':14,'workflow_plan':graph,'planning_runs':[{'last_candidate':copy.deepcopy(graph)}]}
 host=SimpleNamespace(get_task=lambda _:copy.deepcopy(task));out=Path(folder)/'review';out.mkdir();state={'task_id':task['id']};reviews=Reviews(out,host,state,False,lambda:None);reviews.prepare('reviewed_model_plan');assert reviews.poll('reviewed_model_plan')['ready'];saved=state['reviews']['reviewed_model_plan'];assert saved['semantic_reviewed'] is False and saved['model_generated'] is False and saved['human_signoff'] is False;checks.append('synthetic saved-source comparison never claims new generation or semantic review')
 reject('review consumes once',lambda:reviews.prepare('reviewed_model_plan'))
 metadata_only=copy.deepcopy(task);metadata_only.update(revision=15,configuration_confirmed=True,artifact={'revision':15})
 require_reviewed_content(metadata_only,state);checks.append('planned confirmation and artifact metadata do not invalidate reviewed content')
 for field,value in [('requirements',{'goal':'changed'}),('configuration',{'model':'different'}),('workflow_plan',{'changed':True}),('test_cases',[{'changed':True}]),('environment_id','other'),('materials',[{'id':'new'}]),('app_type','advanced-chat')]:
  changed=copy.deepcopy(task);changed[field]=value;reject('reviewed content drift before dispatch '+field,lambda:require_reviewed_content(changed,state))
 for change in ('task','source','actor','note','retained'):
  out=Path(folder)/('review-'+change);out.mkdir();t=copy.deepcopy(task);h=SimpleNamespace(get_task=lambda _,t=t:copy.deepcopy(t));r=Reviews(out,h,{'task_id':t['id']},False,lambda:None);r.prepare('reviewed_model_plan');ack=out/'review-reviewed_model_plan.json';a=json.loads(ack.read_text('utf-8'))
  if change=='task':t['revision']+=1
  elif change=='source':source=out/'review-source-reviewed_model_plan.json';v=json.loads(source.read_text('utf-8'));v['verification']='tampered';write(source,v)
  elif change=='actor':a['actor']='human'
  elif change=='note':a['note']='password=PUBLIC_SYNTHETIC_ONLY'
  else:t['planning_runs'][-1]['last_candidate']={'different':True}
  write(ack,a);reject('review drift '+change,lambda:r.poll('reviewed_model_plan'))
 out=Path(folder)/'different-retained';out.mkdir();t=copy.deepcopy(task);t['planning_runs'][-1]['last_candidate']={'different':True};h=SimpleNamespace(get_task=lambda _:copy.deepcopy(t));r=Reviews(out,h,{'task_id':t['id']},False,lambda:None);r.prepare('reviewed_model_plan');reject('saved plan differs from retained model before review',lambda:r.poll('reviewed_model_plan'))
 out=Path(folder)/'reject';out.mkdir();source={'stage':'reviewed_model_plan','task':task};write(out/'review-source-reviewed_model_plan.json',source);decision=submit(out,'reviewed_model_plan',digest(source),'合成明确拒绝，非实际语义或资源批准。','reject');assert decision['state']=='rejected_stopped' and (out/'stop.json').exists();checks.append('explicit root rejection produces stop marker')
 # Check the inherited actual public sources read-only; no external calls or data changes.
 from inheritance import inherited
 from guard import capture
 live=ReadOnly(PROJECT/'data');snapshot=capture(live);actual=live.get('task',plan['target_task_id']);proof=inherited(plan|{'protected_data':snapshot},actual,PROJECT);assert proof['new_model_call'] is False and proof['resource_authorized'] is False;checks.append('actual retained two-text model source remains matched read-only')
 changed=copy.deepcopy(actual);changed['revision']+=1;reject('inherited source drift',lambda:inherited(plan|{'protected_data':snapshot},changed,PROJECT));assert capture(live)==snapshot
 print(json.dumps({'state':'passed','gates':len(checks),'checks':checks,'physical_http':0,'production_store_constructed':False},ensure_ascii=False))
