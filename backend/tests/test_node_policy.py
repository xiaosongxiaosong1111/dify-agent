import copy
import pytest,yaml
from test_api import client,approved,create_env
from test_workflow_plan import base_plan,plan_task,task
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved
from app.node_policy import require_native
from app import main

def plan(kind='llm'):
 p=base_plan();n=p['nodes'][1]
 if kind=='code':n.update(type='code',config={'code_language':'python3','code':'def main():\n    return {"text":"ok"}','variables':[],'outputs':{'text':{'type':'string'}}})
 elif kind=='template-transform':n.update(type=kind,config={'template':'ok','variables':[]});p['nodes'][-1]['config']['outputs'][0]['value_selector']=['llm','output']
 return p

def root(kind='llm'):
 content,checked=compile_workflow_plan(plan_task(plan(kind)));assert checked['valid'],checked;return yaml.safe_load(content)

@pytest.mark.parametrize('kind',['llm','code','template-transform'])
@pytest.mark.parametrize('policy',[{'retry_config':{'retry_enabled':True,'max_retries':2,'retry_interval':1000}},{'error_strategy':'default-value'},{'default_value':[{'key':'text','type':'string','value':'fallback'}]}])
def test_native_common_strategy_not_projected_away(kind,policy):
 value=root(kind);value['workflow']['graph']['nodes'][1]['data'].update(policy);before=copy.deepcopy(value)
 checked=validate_preserved(value);assert not checked['valid'] and '/workflow/graph/nodes/1/data' in str(checked['errors']) and value==before
 with pytest.raises(ValueError):require_native(value)

@pytest.mark.parametrize('kind',['llm','code','template-transform'])
def test_known_inactive_execution_fields_keep_original_values(kind):
 value=root(kind);value['workflow']['graph']['nodes'][1]['data'].update(error_strategy=None,default_value=[],retry_config={'retry_enabled':False,'max_retries':3,'retry_interval':1200})
 before=copy.deepcopy(value);assert validate_preserved(value)['valid'];require_native(value);assert value==before

@pytest.mark.parametrize('policy',[{'retry_config':None},{'retry_config':{'retry_enabled':'false'}},{'retry_config':{'retry_enabled':False,'unknown':0}},{'retry_config':{'retry_interval':True}},{'retry_config':{'max_retries':-1}}])
def test_inactive_malformed_policy_not_coerced(policy):
 value=root();value['workflow']['graph']['nodes'][1]['data'].update(policy);assert not validate_preserved(value)['valid']

@pytest.mark.parametrize('kind',['llm','code','template-transform'])
@pytest.mark.parametrize('policy',[{'retry_config':{'retry_enabled':False}},{'error_strategy':'fail-branch'},{'default_value':[]}])
def test_ir_does_not_drop_unemitted_execution_configuration(kind,policy):
 p=plan(kind);p['nodes'][1]['config'].update(policy);old=copy.deepcopy(p);checked=validate_plan(task(),p)
 assert not checked['valid'] and '不能省略配置后生成' in str(checked['errors']) and p==old


def test_existing_http_retry_support_is_preserved_not_blanket_rejected():
 from test_preservation_extensions import http_plan
 p=http_plan();p['nodes'][1]['config']['retry_config']={'retry_enabled':True,'max_retries':2,'retry_interval':1500}
 content,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked
 value=yaml.safe_load(content);before=copy.deepcopy(value);assert validate_preserved(value)['valid'];require_native(value);assert value==before

@pytest.mark.parametrize('kind',['import','run'])
def test_old_final_llm_artifact_is_rejected_before_pending_and_dispatch(client,monkeypatch,kind):
 env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'policy-fixture','service_api_key':'fixture-only'})
 t=approved(client,env_id=env['id']);t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();value=root()
 value['workflow']['graph']['nodes'][1]['data']['error_strategy']='default-value';main.artifact_path(t).write_text(yaml.safe_dump(value,allow_unicode=True),encoding='utf-8')
 if kind=='run':t['dify_app_id']='policy-fixture';main.save_task(t)
 before=copy.deepcopy(main.get_task(t['id']));calls=[]
 async def remote(*args,**kwargs):calls.append(True);raise AssertionError('no dispatch')
 monkeypatch.setattr(main.DifyClient,'import_new',remote);monkeypatch.setattr(main.DifyClient,'run_workflow',remote)
 response=client.post(f"/api/tasks/{t['id']}/{kind}",json={'revision':t['revision'],**({'input':{'query':'fixture'}} if kind=='run' else {})})
 assert response.status_code==422 and '/workflow/graph/nodes/1/data' in response.text,response.text
 assert main.get_task(t['id'])==before and not calls


@pytest.mark.parametrize('kind',['llm','code','template-transform'])
def test_case_semantic_source_cannot_hide_active_execution_strategy(kind):
 from fastapi import HTTPException
 from app.case_dsl_semantics import summary
 value=root(kind);value['workflow']['graph']['nodes'][1]['data']['retry_config']={'retry_enabled':True,'max_retries':2,'retry_interval':1000}
 before=copy.deepcopy(value)
 with pytest.raises(HTTPException,match='未适配执行策略'):summary(value)
 assert value==before


@pytest.mark.parametrize('field',['retry_config','timeout'])
def test_case_semantic_source_rejects_malformed_http_execution_metadata(field):
 from fastapi import HTTPException
 from app.case_dsl_semantics import summary
 from test_preservation_extensions import http_plan
 value=yaml.safe_load(compile_workflow_plan(plan_task(http_plan()))[0]);value['workflow']['graph']['nodes'][1]['data'][field]=0
 before=copy.deepcopy(value)
 with pytest.raises(HTTPException,match='HTTP执行策略未适配'):summary(value)
 assert value==before
