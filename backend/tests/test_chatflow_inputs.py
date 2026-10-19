import copy
import pytest
import yaml
from test_api import client
from test_conversation import prepared
from test_workflow_plan import base_plan, task
from app import main
from app.workflow_plan import validate_plan, compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app.start_inputs import form_schema, preflight


def declaration():
    return [{'variable':'budget','type':'number','required':True},
            {'variable':'region','type':'select','required':False,'options':['华北','华南'],'default':'华南'}]


def configured():
    value=task('advanced-chat');value['workflow_plan']=base_plan('advanced-chat')
    value['workflow_plan']['nodes'][0]['config']['variables']=declaration()
    value['workflow_plan']['nodes'][1]['config']['user_prompt']='{{#sys.query#}} 金额{{#start.budget#}} 区域{{#start.region#}}'
    return value


def native():
    content,check=compile_workflow_plan(configured());assert check['valid'],check
    return yaml.safe_load(content)


def runtime(client):
    t,_=prepared(client)
    main.artifact_path(t).write_text(yaml.safe_dump(native(),allow_unicode=True),encoding='utf-8')
    return t


def test_chatflow_scalar_compile_preserve_and_schema_keep_query_separate():
    t=configured();before=copy.deepcopy(t);root=native()
    assert t==before and root['app']['mode']=='advanced-chat'
    rows=root['workflow']['graph']['nodes'][0]['data']['variables']
    assert [v['variable'] for v in rows]==['budget','region'] and rows[1]['default']=='华南'
    assert validate_preserved(root)['valid']
    schema=form_schema(root)
    assert schema['app_mode']=='advanced-chat' and [f['variable'] for f in schema['fields']]==['query','budget','region']
    assert schema['verification']=='static_only'


@pytest.mark.parametrize('name',['query','conversation_id'])
def test_transport_names_refused_in_plan_and_preserved_source(name):
    t=configured();t['workflow_plan']['nodes'][0]['config']['variables'][0]['variable']=name
    assert not validate_plan(t,t['workflow_plan'])['valid']
    root=native();root['workflow']['graph']['nodes'][0]['data']['variables'][0]['variable']=name
    assert not validate_preserved(root)['valid']
    with pytest.raises(ValueError,match='保留名'):form_schema(root)


@pytest.mark.parametrize('values',[
    {'query':'问题'}, {'query':'问题','budget':True}, {'query':'问题','budget':'3'},
    {'query':'问题','budget':0,'region':'其它'}, {'query':'问题','budget':0,'undeclared':1},
    {'query':'  ','budget':0}, {'query':'问题','budget':0,'conversation_id':'old'},
])
def test_custom_values_fail_before_remote_or_pending_record(client,monkeypatch,values):
    t=runtime(client);before=copy.deepcopy(main.get_task(t['id']))
    async def forbidden(*args,**kwargs):pytest.fail('输入不合法不能请求Dify')
    monkeypatch.setattr(main.DifyClient,'run_chatflow',forbidden)
    response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':values})
    assert response.status_code==422,response.text
    assert main.get_task(t['id'])==before


def test_new_conversation_payload_does_not_fill_defaults_or_move_custom_into_query(client,monkeypatch):
    t=runtime(client);seen=[]
    async def chat(self,query,inputs=None,conversation_id=None):
        seen.append((query,copy.deepcopy(inputs),conversation_id));return {'answer':'已收到','conversation_id':'new-chat'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':{'query':'问题','budget':0}})
    assert response.status_code==200,response.text
    assert seen==[('问题',{'budget':0},None)]
    saved=response.json();assert saved['runs'][-1]['input']=={'query':'问题','budget':0}
    # Reuse must not silently ignore a new initial value.
    response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':{'query':'追问','budget':1},'conversation_from_run_id':saved['runs'][-1]['id']})
    assert response.status_code==422 and len(seen)==1


def test_changed_custom_multi_turn_case_refused_before_first_dispatch(client,monkeypatch):
    t=runtime(client);t['test_cases']=[{'id':'case','name':'两轮','required':True,'input':{'query':'首轮','budget':0},'expectation':{'mode':'manual','description':'核对'},'followups':[{'input':{'query':'续聊','budget':1},'expectation':{'mode':'manual','description':'核对'}}]}]
    main.save_task(t);before=copy.deepcopy(t)
    async def forbidden(*args,**kwargs):pytest.fail('不能派发第一轮')
    monkeypatch.setattr(main.DifyClient,'run_chatflow',forbidden)
    response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'case_id':'case'})
    assert response.status_code==422 and '多轮' in response.text and main.get_task(t['id'])==before


def test_local_api_uses_final_chatflow_schema_without_mutating_task(client,monkeypatch):
    t=runtime(client);before=copy.deepcopy(main.get_task(t['id']))
    schema=client.get(f"/api/tasks/{t['id']}/run-input-schema").json()
    async def forbidden(*args,**kwargs):pytest.fail('本机检查不能访问平台或模型')
    monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
    payload={'revision':t['revision'],'source_sha256':schema['source_sha256'],'input':{'query':'PRIVATE-QUERY','budget':0}}
    response=client.post(f"/api/tasks/{t['id']}/run-input-check",json=payload)
    assert response.status_code==200 and 'PRIVATE-QUERY' not in response.text and not response.json()['platform_checked']
    payload['input']['query']='  '
    assert client.post(f"/api/tasks/{t['id']}/run-input-check",json=payload).status_code==422
    assert main.get_task(t['id'])==before


def test_unknown_custom_type_is_not_dropped_to_text():
    t=configured();t['workflow_plan']['nodes'][0]['config']['variables'][0]['type']='file'
    assert not validate_plan(t,t['workflow_plan'])['valid']
