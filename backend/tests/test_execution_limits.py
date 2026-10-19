import copy
import pytest
from test_api import client
from test_dsl_roundtrip import prepared
from app import main

def state(client,t):return client.get(f"/api/tasks/{t['id']}/execution-limits").json()
def save(client,t,count=None,minutes=None,**patch):
 return client.patch(f"/api/tasks/{t['id']}/execution-limits",json={'revision':t['revision'],'policy_revision':state(client,t)['policy']['policy_revision'],'max_started_runs':count,'max_total_minutes':minutes,'acknowledge_scope':True,'note':'本次任务投入限制',**patch})

def test_zero_start_cap_blocks_before_external_operation_without_mutation(client,monkeypatch):
 from app.dify import DifyClient
 task,_=prepared(client);calls=[]
 env=main.store.get('environment',task['environment_id']);env['service_app_id']=task['dify_app_id'];main.store.put('environment',env['id'],env);main.store.set_secret(env['id'],'service_api_key','fake-service-key')
 async def fake(*a,**kw):calls.append(kw);return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
 monkeypatch.setattr(DifyClient,'run_workflow',fake)
 assert save(client,task,count=0).status_code==200
 before=copy.deepcopy(main.get_task(task['id']))
 response=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'x'}})
 assert response.status_code==409 and not calls and main.get_task(task['id'])==before,response.text

def test_old_revision_failed_and_unknown_starts_count_once_per_batch(client):
 task,_=prepared(client)
 task['runs'] += [{'id':'old','kind':'run','revision':1,'status':'failed'},{'id':'unknown','kind':'run','revision':2,'status':'unknown','result':{'conversation_case':True,'turns':[{},{}]}}]
 main.save_task(task);assert save(client,task,count=2).status_code==200
 result=state(client,task);assert result['started_runs']==2 and not result['can_start'] and result['unknown_duration_runs']==2
 task['revision']+=1;main.save_task(task);assert state(client,task)['started_runs']==2

def test_elapsed_budget_uses_recorded_request_time_and_unknown_is_not_zero(client):
 task,_=prepared(client);task['runs'].append({'id':'timed','kind':'run','status':'success','created_at':'2026-10-12T00:00:00+00:00','completed_at':'2026-10-12T00:01:00+00:00'});main.save_task(task)
 assert save(client,task,minutes=1).status_code==200
 result=state(client,task);assert result['known_elapsed_seconds']=='60' and not result['can_start']
 assert save(client,task,minutes=2).status_code==200 and state(client,task)['can_start']
 task['runs'].append({'id':'no-time','kind':'run','status':'failed'});main.save_task(task);assert not state(client,task)['can_start']

def test_policy_changes_audit_and_do_not_invalidate_business_or_reset_history(client):
 task,_=prepared(client);before=copy.deepcopy(task)
 assert save(client,task,count=2).status_code==200 and save(client,task,count=5).status_code==200
 result=state(client,task);assert len(result['policy']['history'])==2 and result['policy']['policy_revision']==2
 assert main.get_task(task['id'])==before
 assert save(client,task,count=10,policy_revision=0).status_code==409
 assert save(client,task,acknowledge_scope=False).status_code==422

def test_unknown_remote_result_does_not_use_restart_time_as_actual_completion(client):
 task,_=prepared(client);task['runs'].append({'id':'old-unknown','kind':'run','revision':1,'status':'unknown','created_at':'2026-10-12T00:00:00+00:00','completed_at':'2026-10-12T00:00:01+00:00'});main.save_task(task)
 assert save(client,task,minutes=2).status_code==200
 result=state(client,task);assert result['unknown_duration_runs']==1 and result['known_elapsed_seconds']=='0' and not result['can_start']

@pytest.mark.parametrize('count,minutes',[(True,None),(-1,None),(10001,None),(None,0),(None,True),(None,10081)])
def test_invalid_policy_is_rejected_without_task_mutation(client,count,minutes):
 task,_=prepared(client);before=copy.deepcopy(task);assert save(client,task,count=count,minutes=minutes).status_code==422
 assert main.get_task(task['id'])==before
