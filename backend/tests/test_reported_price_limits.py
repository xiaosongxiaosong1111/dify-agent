import copy
import pytest
from test_api import client
from test_dsl_roundtrip import prepared
from test_execution_limits import state,save
from test_execution_costs import run,SECOND
from app import main

def charged(client,*records):
 task,_=prepared(client);task['runs']+=list(records);main.save_task(task);return task

def test_known_usd_threshold_deduplicates_and_keeps_old_revision_charges(client):
 first=run(price='.2',revision=1);duplicate=copy.deepcopy(first);duplicate['id']='other-local'
 task=charged(client,first,duplicate);before=copy.deepcopy(task)
 response=save(client,task,max_reported_cost_usd='.2');assert response.status_code==200,response.text
 result=state(client,task);assert result['known_reported_usd']=='0.2' and result['unavailable_usd_executions']==0 and not result['can_start']
 assert main.get_task(task['id'])==before
 assert save(client,task,max_reported_cost_usd='0.200000000001').json()['can_start']

@pytest.mark.parametrize('record',[run(price=None),run(currency='CNY'),run(environment_binding=None),run(status='unknown'),run(status=None),run(app_type='workflow'),run(result=None)])
def test_missing_foreign_or_uncertain_prices_do_not_become_zero_or_free(client,record):
 task=charged(client,record);assert save(client,task,max_reported_cost_usd='1').status_code==200
 result=state(client,task);assert result['unavailable_usd_executions']==1 and not result['can_start']
 assert '不能证明剩余USD报价预算' in ' '.join(result['blockers'])

def test_zero_cap_blocks_before_first_run_and_explicit_null_can_disable(client):
 task,_=prepared(client);result=save(client,task,max_reported_cost_usd='0');assert result.status_code==200 and not result.json()['can_start']
 assert save(client,task,max_reported_cost_usd=None).json()['can_start']

def test_old_client_omission_cannot_clear_new_cost_policy_and_audit_retains_change(client):
 task,_=prepared(client);assert save(client,task,max_reported_cost_usd='.5').status_code==200
 result=save(client,task,count=4).json();assert result['policy']['max_reported_cost_usd']=='0.5'
 assert result['policy']['history'][-1]['before']['max_reported_cost_usd']=='0.5' and result['policy']['history'][-1]['after']['max_reported_cost_usd']=='0.5'

@pytest.mark.parametrize('cost',[True,1,'NaN','Infinity','-1','1.0000000000001','1000001',''])
def test_invalid_or_coerced_cost_is_not_silently_accepted_or_disabled(client,cost):
 task,_=prepared(client);assert save(client,task,max_reported_cost_usd='.5').status_code==200
 assert save(client,task,max_reported_cost_usd=cost).status_code==422
 assert state(client,task)['policy']['max_reported_cost_usd']=='0.5'

def test_conflicting_same_execution_and_truncation_pause_not_lower_budget(client,monkeypatch):
 first=run(price='.2');conflict=run('conflict',price='.3');task=charged(client,first,conflict)
 result=save(client,task,max_reported_cost_usd='1').json();assert result['known_reported_usd']=='0' and not result['can_start']
 from app import execution_costs
 original=execution_costs.summary
 def truncated(task):value=original(task);value['truncated']=True;return value
 monkeypatch.setattr(execution_costs,'summary',truncated);task['runs']=[];main.save_task(task)
 assert not state(client,task)['can_start']

def test_price_zero_gate_blocks_real_run_entry_before_provider_or_pending_record(client,monkeypatch):
 from app.dify import DifyClient
 task,_=prepared(client);env=main.store.get('environment',task['environment_id']);env['service_app_id']=task['dify_app_id'];main.store.put('environment',env['id'],env);main.store.set_secret(env['id'],'service_api_key','fake-service-key');calls=[]
 async def fake(*a,**kw):calls.append(kw);return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
 monkeypatch.setattr(DifyClient,'run_workflow',fake);before=copy.deepcopy(task);assert save(client,task,max_reported_cost_usd='0').status_code==200
 result=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'hello'}})
 assert result.status_code==409 and 'USD报价' in result.text and not calls and main.get_task(task['id'])==before
