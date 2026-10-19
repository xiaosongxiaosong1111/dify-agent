import asyncio,copy
import pytest
from fastapi import HTTPException
from test_api import client
from test_runtime_repair import ready
from app import main
from app.run_diagnostics import source_hash

def repeated(client):
 task=ready(client);run=task['runs'][-1];run['input']={'query':'example'};run['diagnostics'][-1]['source_hash']=source_hash(run)
 other=copy.deepcopy(run);other['id']='failed-again';other['diagnostics'][-1]['id']='second-diagnostic';other['diagnostics'][-1]['source_hash']=source_hash(other);task['runs'].append(other);main.save_task(task);return task

def read(client,task):return client.get(f"/api/tasks/{task['id']}/failure-watch").json()
def decide(client,task,action='run',**patch):
 token=read(client,task)['paused_groups'][0]['evidence_token']
 return client.post(f"/api/tasks/{task['id']}/failure-watch/decision",json={'revision':task['revision'],'evidence_token':token,'action':action,'acknowledge_review':True,'note':'核对依赖后继续一次',**patch})
def require(task,action='run',**kw):
 return main.failure_watch.require(task,action,inputs={'query':'example'},**kw)

def test_two_failures_block_without_content_echo_or_task_changes(client):
 task=repeated(client);before=copy.deepcopy(task);state=read(client,task)
 assert state['paused_groups'][0]['consecutive_failures']==2
 assert state['paused_groups'][0]['run_ids']==['failed-re-run','failed-again']
 assert 'example' not in str(state) and "name 're'" not in str(state)
 with pytest.raises(HTTPException,match='相同输入'):require(task)
 assert main.get_task(task['id'])==before and not main.store.list('failure_decision')

def test_once_permission_cannot_be_reused_by_reading_same_diagnostics(client):
 task=repeated(client);assert decide(client,task).status_code==200
 require(task);assert read(client,task)['paused_groups'][0]['permission']['status']=='used'
 with pytest.raises(HTTPException):require(task)
 task['runs'][-1]['diagnostics'][-1]['id']='read-again';task['runs'][-1]['diagnostics'][-1]['created_at']=main.now();main.save_task(task)
 assert decide(client,task).status_code==409
 with pytest.raises(HTTPException):require(task)

def test_latest_decision_replaces_ready_choice_but_not_consumed_permission(client):
 task=repeated(client);assert decide(client,task,'change_plan').status_code==200
 assert decide(client,task,'model_repair').status_code==200
 with pytest.raises(HTTPException):require(task)
 main.failure_watch.require(task,'model_repair',run_id='failed-again')
 assert read(client,task)['paused_groups'][0]['permission']['status']=='used'
 assert decide(client,task,'run').status_code==409

def test_new_same_failure_pauses_again_but_stale_decision_cannot_apply(client):
 task=repeated(client);old=read(client,task)['paused_groups'][0]['evidence_token'];assert decide(client,task).status_code==200;require(task)
 third=copy.deepcopy(task['runs'][-1]);third['id']='third';third['diagnostics'][-1]['source_hash']=source_hash(third);task['runs'].append(third);main.save_task(task)
 state=read(client,task);assert state['paused_groups'][0]['consecutive_failures']==3 and state['paused_groups'][0]['permission'] is None
 assert decide(client,task,evidence_token=old).status_code==409
 assert decide(client,task).status_code==200

def test_failure_history_survives_revision_and_app_changes_when_proof_is_valid(client):
 task=repeated(client);task['revision']+=1;task['artifact']['revision']=task['revision'];task['dify_app_id']='new-app';run=task['runs'][-1];run['revision']=task['revision'];run['app_id']='new-app';report=run['diagnostics'][-1];report.update(source_revision=task['revision'],captured_at_revision=task['revision'],app_id='new-app',source_hash=source_hash(run));main.save_task(task)
 assert read(client,task)['paused_groups'][0]['consecutive_failures']==2

@pytest.mark.parametrize('mutation',['success','unknown','local','truncated','source','graph','revision','error_changed','redacted','partial_turn','conversation','case','input','binding'])
def test_nonmatching_or_untrusted_evidence_is_not_claimed_as_same_failure(client,mutation):
 task=repeated(client);run=task['runs'][-1];report=run['diagnostics'][-1]
 if mutation in {'success','unknown'}:run['status']=mutation
 elif mutation=='local':report['trace_state']='local_only'
 elif mutation=='truncated':report['truncated']=True
 elif mutation=='source':report['source_hash']='stale'
 elif mutation=='graph':report['source_graph']['published']={'digest':'other'}
 elif mutation=='revision':report['captured_at_revision']=0
 elif mutation=='error_changed':report['nodes'][0]['error']='TypeError: unsupported operand'
 elif mutation=='redacted':report['nodes'][0]['error']='Error [已脱敏]'
 elif mutation=='partial_turn':report['selected_turn']=1
 elif mutation=='conversation':run['conversation_context']={'conversation_id':'existing'}
 elif mutation=='case':run['test_case']={'id':'different','input':{'query':'example'}}
 elif mutation=='input':run['input']={'query':'other'}
 else:run['environment_binding']='different'
 if mutation!='source':report['source_hash']=source_hash(run)
 main.save_task(task);assert read(client,task)['paused_groups']==[]

def test_other_input_is_allowed_without_resetting_blocked_input(client):
 task=repeated(client);other=copy.deepcopy(task['runs'][-1]);other['id']='other-input';other['input']={'query':'different'};other['diagnostics'][-1]['source_hash']=source_hash(other);task['runs'].append(other);main.save_task(task)
 assert len(read(client,task)['paused_groups'])==1
 main.failure_watch.require(task,'run',inputs={'query':'different'})
 with pytest.raises(HTTPException):require(task)

@pytest.mark.parametrize('patch',[{'acknowledge_review':False},{'action':'retry_forever'},{'revision':999},{'note':'Bearer very-sensitive-token-value'}])
def test_invalid_decisions_do_not_release_or_leak(client,patch):
 task=repeated(client);response=decide(client,task,**patch);assert response.status_code in {409,422}
 assert 'very-sensitive' not in response.text and not main.store.list('failure_decision')

def test_dispatch_is_blocked_before_operation_and_one_permission_counts_even_failed_request(client):
 task=repeated(client);calls=[]
 async def operation(*args):calls.append(1);return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
 with pytest.raises(HTTPException):asyncio.run(main.external_action(task['id'],task['revision'],'run',operation,inputs={'query':'example'}))
 assert not calls and main.get_task(task['id'])['runs']==task['runs']
 assert decide(client,task).status_code==200
 asyncio.run(main.external_action(task['id'],task['revision'],'run',operation,inputs={'query':'example'}))
 assert calls==[1] and main.store.list('failure_decision')[0]['status']=='used'

def test_restart_preserves_decisions(client):
 from app.storage import Store
 task=repeated(client);assert decide(client,task).status_code==200;main.store=Store(main.store.root)
 require(task);assert read(client,task)['paused_groups'][0]['permission']['status']=='used'

def test_model_generate_checks_pause_before_call_or_model_request_record(client,monkeypatch):
 from test_task_budget import provider
 from test_model_repairs import model
 task=repeated(client);p=provider(client);task['configuration']['assistant_provider_id']=p['id'];main.save_task(task);calls=model(monkeypatch)
 url=f"/api/tasks/{task['id']}/runs/failed-again"
 scope=client.get(url+'/repair-model-outbound',params={'revision':task['revision'],'diagnostic_id':'second-diagnostic'});assert scope.status_code==200,scope.text
 payload={'revision':task['revision'],'diagnostic_id':'second-diagnostic','outbound_token':scope.json()['outbound_token'],'acknowledge_data_and_cost':True}
 assert client.post(url+'/repair-model-generate',json=payload).status_code==409
 assert not calls and not main.store.list('repair_model_request')
 assert decide(client,task,'model_repair').status_code==200
 response=client.post(url+'/repair-model-generate',json=payload);assert response.status_code==200,response.text
 assert len(calls)==1 and main.store.list('failure_decision')[0]['status']=='used'
