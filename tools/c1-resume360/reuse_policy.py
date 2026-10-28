"""Reuse only the preserved blank task; never erase its failed candidate or cost."""
import copy
from guard import require

def validate_start(task,budget,limits,fixture,environment_id,provider_id):
 require(isinstance(task,dict) and task.get('revision')==3 and task.get('status')=='requirements','Existing Task is not the approved blank revision')
 require(task.get('name')==fixture['task_name'] and task.get('app_type')=='workflow' and task.get('environment_id')==environment_id,'Existing Task identity changed')
 require(task.get('intake_required') is True and task.get('plan_review_required') is True and not task.get('requirements_confirmed') and not task.get('configuration_confirmed'),'Admission gates changed')
 require(len(task.get('requirements',{}))==8 and all(v=='' for v in task['requirements'].values()),'Existing requirements are not blank')
 require(not any(task.get(k) for k in ('active_interview_id','intake_review','workflow_plan','artifact','dify_app_id','runs','planning_runs')),'Existing Task is no longer idle/blank')
 expected=copy.deepcopy(fixture['configuration']);expected['assistant_provider_id']=provider_id
 require({k:v for k,v in task.get('configuration',{}).items() if k!='resource_plan'}=={k:v for k,v in expected.items() if k!='resource_plan'},'Original fixed configuration changed')
 attempts=task.get('interview_attempts',[])
 require(len(attempts)==1 and attempts[0].get('applied') is False and not attempts[0].get('response_truncated'),'Original failed interview missing')
 require(isinstance(budget,dict) and len(budget.get('entries',[]))==1 and budget['entries'][0].get('status')=='settled' and budget['entries'][0].get('call_status')=='returned','Original settled model ledger missing')
 require(isinstance(limits,dict) and limits.get('max_started_runs')==4 and limits.get('max_total_minutes')==20 and limits.get('max_reported_cost_usd') is None,'Original execution limits changed')
 cases=task.get('test_cases',[])
 require(len(cases)==2,'Original cases missing')
 for actual,wanted in zip(cases,fixture['cases']):
  require(all(actual.get(k)==wanted.get(k) for k in ('name','input','expectation')),'Original case source changed')
 return True

def preserve_task(old,current):
 require(all(current.get(k)==old.get(k) for k in ('id','name','app_type','created_at')),'Existing Task identity overwritten')
 require(current.get('revision',0)>=old['revision'],'Task revision moved backwards')
 for key in ('messages','versions','interview_attempts','runs','planning_runs','intake_history'):
  prefix=old.get(key,[]);require(current.get(key,[])[:len(prefix)]==prefix,'Original Task history overwritten')

def preserve_budget(old,current):
 require(all(current.get(k)==v for k,v in old.items() if k!='entries'),'Original budget policy changed')
 prefix=old.get('entries',[])
 require(current.get('entries',[])[:len(prefix)]==prefix,'Original settled ledger changed')
 require(len(current.get('entries',[]))<=len(prefix)+5,'New model ledger count exceeded')
