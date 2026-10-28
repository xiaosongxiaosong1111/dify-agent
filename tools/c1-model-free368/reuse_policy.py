"""Reuse only the preserved blank task; never erase its failed candidate or cost."""
import copy
from guard import require

def validate_start(task,budget,limits,fixture,environment_id,provider_id):
 require(isinstance(task,dict) and task.get('revision')==13 and task.get('status')=='draft_ready','Existing saved Task revision changed')
 require(task.get('name')==fixture['task_name'] and task.get('app_type')=='workflow' and task.get('environment_id')==environment_id,'Existing Task identity changed')
 require(task.get('intake_required') is True and task.get('plan_review_required') is True and task.get('requirements_confirmed') is True and task.get('configuration_confirmed') is True and not task.get('plan_stale'),'Current saved confirmations changed')
 require(task.get('plan_source')=='manual' and isinstance(task.get('workflow_plan'),dict) and isinstance(task.get('artifact'),dict) and task['artifact'].get('revision')==13 and not task.get('dify_app_id') and not task.get('active_interview_id'),'Saved model candidate/static artifact source changed')
 runs=task.get('planning_runs',[]);require(len(runs)==2 and runs[-1].get('status')=='paused' and task['workflow_plan']==runs[-1].get('last_candidate'),'Retained complete model source changed')
 expected=copy.deepcopy(fixture['configuration']);expected['assistant_provider_id']=provider_id
 require({k:v for k,v in task.get('configuration',{}).items() if k!='resource_plan'}=={k:v for k,v in expected.items() if k!='resource_plan'},'Original fixed configuration changed')
 attempts=task.get('interview_attempts',[]);require(len(attempts)==3 and all(a.get('applied') is False and not a.get('response_truncated') for a in attempts),'Original failed interviews missing')
 require(isinstance(budget,dict) and len(budget.get('entries',[]))==6 and all(e.get('status')=='settled' and e.get('call_status')=='returned' for e in budget['entries']),'Original six settled entries missing')
 require(isinstance(limits,dict) and limits.get('max_started_runs')==4 and limits.get('max_total_minutes')==20 and limits.get('max_reported_cost_usd') is None,'Original execution limits changed')
 cases=task.get('test_cases',[]);require(len(cases)==2,'Original cases missing')
 for actual,wanted in zip(cases,fixture['cases']):require(all(actual.get(k)==wanted.get(k) for k in ('name','input','expectation')),'Current case source changed')
 observed=[r for r in task.get('runs',[]) if r.get('kind')=='run'];require(len(observed)==2 and all(r['status']=='success' and r['evaluation']['status']=='passed' and r.get('diagnostics') and r['diagnostics'][-1]['source_graph']['matched'] for r in observed),'Original observed runs changed')
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
 require(len(current.get('entries',[]))<=len(prefix),'New model ledger count exceeded')
