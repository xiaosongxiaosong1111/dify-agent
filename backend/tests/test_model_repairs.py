import copy,json
import pytest
from test_api import client
from test_runtime_repair import ready
from test_task_budget import provider,USAGE
from app import main
from app.run_diagnostics import source_hash
from app.providers import ProviderError

def configured(client):
 task=ready(client);p=provider(client);task['configuration']['assistant_provider_id']=p['id'];main.save_task(task);return task,p

def outbound(client,task):
 return client.get(f"/api/tasks/{task['id']}/runs/failed-re-run/repair-model-outbound",params={'revision':task['revision'],'diagnostic_id':'re-diagnostic'})

def generate(client,task,preview,**fields):
 return client.post(f"/api/tasks/{task['id']}/runs/failed-re-run/repair-model-generate",json={'revision':task['revision'],'diagnostic_id':'re-diagnostic','outbound_token':preview['outbound_token'],'acknowledge_data_and_cost':True,**fields})

def candidate():
 return {'schema_version':1,'patches':[{'node_id':'code','code':'import re\ndef main(query: str) -> dict:\n    return {"result": re.sub(r"\\s+", " ", query)}\n','reason':'补导入，输入输出不变，需要验证。'}],'summary':'仅代码候选，尚未执行','open_issues':[]}

def model(monkeypatch,response=None,error=None):
 calls=[]
 async def fake(*args,**kwargs):
  calls.append((args,kwargs))
  if error:raise error
  return json.dumps(response or candidate()),USAGE
 monkeypatch.setattr(main,'call_model',fake);return calls

def test_outbound_generate_and_explicit_business_apply_are_separate(client,monkeypatch):
 task,p=configured(client);task['runs'][-1]['input']={'query':'private-input-not-outbound'};task['runs'][-1]['result']={'answer':'private-output-not-outbound'};task['runs'][-1]['diagnostics'][-1]['source_hash']=source_hash(task['runs'][-1]);main.save_task(task)
 calls=model(monkeypatch);response=outbound(client,task);assert response.status_code==200,response.text;scope=response.json()
 text=json.dumps(scope);assert 'private-input-not-outbound' not in text and 'private-output-not-outbound' not in text and 'not-a-real-key' not in text
 assert scope['settings']['max_retries']==0 and not calls
 assert generate(client,task,scope,acknowledge_data_and_cost=False).status_code==422 and not calls
 response=generate(client,task,scope);assert response.status_code==200,response.text;assert len(calls)==1
 updated=response.json();assert updated['revision']==task['revision'] and updated['workflow_plan']==task['workflow_plan'] and updated['configuration_confirmed']
 record=main.store.list('runtime_repair')[0];assert record['kind']=='model_code_proposal' and record['status']=='ready'
 assert record['provider_id']==p['id'] and record['planning_run_id']==updated['planning_runs'][-1]['id']
 assert client.post(f"/api/tasks/{task['id']}/runtime-repairs/{record['id']}/apply",json={'revision':task['revision']}).status_code==422
 assert main.budgets.get(task['id'])['entries'][0]['kind']=='repair'
 path=f"/api/tasks/{task['id']}/runtime-repairs/{record['id']}/model-apply"
 assert client.post(path,json={'revision':task['revision'],'acknowledge_business_review':False}).status_code==422
 response=client.post(path,json={'revision':task['revision'],'acknowledge_business_review':True});assert response.status_code==200,response.text
 result=response.json()['task'];assert result['revision']==task['revision']+1 and not result['requirements_confirmed'] and not result['configuration_confirmed'] and result['runs']==task['runs']
 assert client.post(path,json={'revision':task['revision'],'acknowledge_business_review':True}).status_code==409

@pytest.mark.parametrize('mutation',['code','provider','settings','report'])
def test_stale_outbound_confirmation_does_not_dispatch(client,monkeypatch,mutation):
 task,p=configured(client);scope=outbound(client,task).json();calls=model(monkeypatch)
 if mutation=='code':task['workflow_plan']['nodes'][1]['config']['code']+='\n# changed';main.save_task(task)
 elif mutation=='provider':p['model']='changed';main.store.put('provider',p['id'],p)
 elif mutation=='settings':settings=main.get_settings();settings['max_cost_usd']=.5;main.store.put('settings','execution',settings)
 else:task['runs'][-1]['diagnostics'][-1]['id']='changed';main.save_task(task)
 assert generate(client,task,scope).status_code==409 and not calls

@pytest.mark.parametrize('patch',[
 {'code':'import os\ndef main(query):\n return {"result":os.getcwd()}'},
 {'code':'def main(query):\n return {"result":eval(query)}'},
 {'node_id':'end'},
 {'provider':'different'},
 {'code':'def main(query):\n return {"result":query.__class__.__name__}'},
])
def test_unsafe_or_out_of_scope_model_candidate_stops_after_one_call(client,monkeypatch,patch):
 task,p=configured(client);scope=outbound(client,task).json();response=candidate();response['patches'][0].update(patch);calls=model(monkeypatch,response=response)
 response=generate(client,task,scope);assert response.status_code==422 and len(calls)==1 and not main.store.list('runtime_repair')
 assert main.get_task(task['id'])['workflow_plan']==task['workflow_plan']

def test_no_progress_two_calls_cap_and_provider_error_never_auto_retries(client,monkeypatch):
 task,p=configured(client);calls=model(monkeypatch,error=ProviderError('受控供应商失败'))
 for _ in range(2):
  scope=outbound(client,task).json();assert generate(client,task,scope).status_code==422
 assert len(calls)==2 and outbound(client,task).status_code==409

def test_invalid_json_one_call_and_budget_records_usage(client,monkeypatch):
 task,p=configured(client);scope=outbound(client,task).json();calls=[]
 async def fake(*a,**kw):calls.append(kw);return 'invalid JSON',USAGE
 monkeypatch.setattr(main,'call_model',fake)
 assert generate(client,task,scope).status_code==422 and len(calls)==1
 assert main.get_task(task['id'])['planning_runs'][-1]['attempts'][0]['usage']==USAGE

def test_interrupted_model_request_is_not_replayed_on_recover(client,monkeypatch):
 task,p=configured(client);calls=model(monkeypatch)
 request={'id':'interrupted-request','task_id':task['id'],'run_id':'failed-re-run','revision':task['revision'],'status':'running'};main.store.put('repair_model_request',request['id'],request)
 main.model_repairs.recover()
 assert main.store.get('repair_model_request',request['id'])['status']=='interrupted' and not calls
 assert outbound(client,task).json()['prior_requests']==1
