import copy,json,uuid
import pytest,yaml
from test_api import client,create
from app import main
from app.public_batch_starter import candidate,CODE
from app.dsl_roundtrip import validate_preserved
from app.workflow_plan import compile_workflow_plan

def test_both_public_policies_compile_without_model_and_keep_expected_positions():
 for policy in ('continue_known','stop'):
  value=candidate(policy);p=json.loads(value['plan_text']);content,checked=compile_workflow_plan({'app_type':'workflow','configuration':{},'workflow_plan':p});assert checked['valid'];root=yaml.safe_load(content);assert validate_preserved(root)['valid']
  assert not any(n['data']['type'] in ('llm','knowledge-retrieval','http-request','tool') for n in root['workflow']['graph']['nodes'])
  assert value['example_input']=={'items_json':'[" a ","ERR","a",""]'}
  assert json.loads(candidate(policy)['plan_text'])==p
  if policy=='continue_known':assert value['expected']=={'total':4,'succeeded':3,'failed':1,'failed_indices':[1]}

def test_only_fixed_known_public_function_and_wrapper_fixture_are_executed():
 from app.iteration_outcomes import wrapped
 namespace={};exec(wrapped(CODE),namespace);fn=namespace['main'];values=[' a ','ERR','a',''];rows=[fn(item,i)['outcome'] for i,item in enumerate(values)]
 assert [r['ok'] for r in rows]==[True,False,True,True] and rows[1]['error_category']=='ValueError' and [r['index'] for r in rows]==[0,1,2,3]
 assert [rows[i]['value'] for i in (0,2,3)]==['A','A','']
 namespace={};exec(CODE,namespace)
 with pytest.raises(ValueError):namespace['main']('ERR')

@pytest.mark.parametrize('policy',['continue_known','stop'])
def test_blank_task_read_is_stateless_no_model_platform_or_task_change(client,monkeypatch,policy):
 task=create(client);before=copy.deepcopy(main.get_task(task['id']))
 def forbidden(*a,**kw):pytest.fail('No model or platform calls')
 monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 r=client.get(f"/api/tasks/{task['id']}/public-batch-starter",params={'revision':task['revision'],'policy':policy,'request_nonce':str(uuid.uuid4())});assert r.status_code==200,r.text;v=r.json();assert all(v[k] is False for k in ['task_changed','network_requested','code_executed','platform_checked','business_verified']);assert main.get_task(task['id'])==before and r.headers['cache-control']=='no-store'

@pytest.mark.parametrize('field,value',[('workflow_plan',{}),('artifact',{}),('dify_app_id','old-app'),('dsl_reference',{}),('app_type','advanced-chat'),('app_type','agent')])
def test_existing_assets_and_other_types_are_not_replaced(client,field,value):
 task=create(client);task[field]=value;main.save_task(task);r=client.get(f"/api/tasks/{task['id']}/public-batch-starter",params={'revision':task['revision'],'policy':'continue_known','request_nonce':str(uuid.uuid4())});assert r.status_code==409

def test_policy_nonce_revision_must_be_explicit(client):
 task=create(client);base={'revision':task['revision'],'policy':'stop','request_nonce':str(uuid.uuid4())}
 for patch in ({'policy':''},{'policy':'guess'},{'request_nonce':'bad'},{'revision':'true'},{'revision':task['revision']+1}):assert client.get(f"/api/tasks/{task['id']}/public-batch-starter",params={**base,**patch}).status_code in (409,422)
