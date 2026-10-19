import copy
import pytest,yaml
from test_api import client,approved,create_env
from test_document_extractor import plan
from test_workflow_plan import plan_task
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app import main

def root():return yaml.safe_load(compile_workflow_plan(plan_task(plan()))[0])
def data(value):return next(n['data'] for n in value['workflow']['graph']['nodes'] if n['id']=='documents')

@pytest.mark.parametrize('patch',[
 {'retry_config':{'retry_enabled':True,'max_retries':3,'retry_interval':100}},
 {'retry_config':{'retry_enabled':'false'}},{'retry_config':{'retry_enabled':0}},
 {'retry_config':None},{'retry_config':[]},{'retry_config':{'retry_enabled':False,'unknown':0}},
 {'retry_config':{'retry_enabled':False,'max_retries':-1}}, {'retry_config':{'retry_enabled':False,'retry_interval':True}},
 {'error_strategy':'default-value'},{'error_strategy':'fail-branch'},{'error_strategy':''},
 {'default_value':[{'key':'text','type':'array[string]','value':['fallback']}]},
 {'version':'2'},{'version':1},{'version':None}, {'unstructured_api_key':'not-a-real-secret'}, {'unknown_execution':{}},
 ])
def test_native_policy_is_not_projected_away_or_silently_disabled(patch):
 value=root();data(value).update(patch);old=copy.deepcopy(value);checked=validate_preserved(value)
 assert not checked['valid'] and value==old

@pytest.mark.parametrize('retry',[{}, {'retry_enabled':False}, {'retry_enabled':False,'max_retries':3,'retry_interval':1000}])
def test_inactive_known_defaults_and_editor_metadata_are_retained(retry):
 value=root();data(value).update(version='1',error_strategy=None,default_value=[],retry_config=retry,_runningStatus='NotStarted',width=244)
 old=copy.deepcopy(value);assert validate_preserved(value)['valid'];assert value==old

@pytest.mark.parametrize('kind',['import','run'])
def test_final_document_policy_is_checked_before_pending_or_remote_writes(client,monkeypatch,kind):
 env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'policy-fixture','service_api_key':'fixture-only'})
 t=approved(client,env_id=env['id']);t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json()
 value=root();data(value)['error_strategy']='default-value';main.artifact_path(t).write_text(yaml.safe_dump(value,allow_unicode=True),encoding='utf-8')
 if kind=='run':t['dify_app_id']='policy-fixture';main.save_task(t)
 before=copy.deepcopy(main.get_task(t['id']));calls=[]
 async def remote(*args,**kwargs):calls.append(True);raise AssertionError('no dispatch')
 monkeypatch.setattr(main.DifyClient,'run_workflow',remote);monkeypatch.setattr(main.DifyClient,'import_new',remote)
 response=client.post(f"/api/tasks/{t['id']}/{kind}",json={'revision':t['revision'],**({'input':{'query':'fixture'}} if kind=='run' else {})})
 assert response.status_code==422 and '文档提取' in response.text,response.text
 assert main.get_task(t['id'])==before and not calls
