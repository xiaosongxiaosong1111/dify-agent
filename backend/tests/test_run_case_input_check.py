import copy
import pytest
import yaml
from test_api import client, approved, create
from test_chatflow_inputs import native
from test_chatflow_case_inputs import case as multi_case
from app import main


def setup(client, chat=False):
    task=approved(client,app_type='advanced-chat' if chat else 'workflow')
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200
    task=response.json()
    if chat:main.artifact_path(task).write_text(yaml.safe_dump(native(),allow_unicode=True),encoding='utf-8')
    value=multi_case() if chat else {'id':'one','name':'本机入口样例','required':True,'input':{'query':'PRIVATE-INPUT'},'expectation':{'mode':'manual','description':'检查结果'}}
    task['test_cases']=[value];main.save_task(task)
    schema=client.get(f"/api/tasks/{task['id']}/run-input-schema").json()
    return task,value,schema


def check(client,task,case,schema,**patch):
    return client.post(f"/api/tasks/{task['id']}/run-case-input-check",json={'revision':task['revision'],'case_id':case['id'],'source_sha256':schema['source_sha256'],**patch})


@pytest.mark.parametrize('chat',[False,True])
def test_saved_case_checked_without_environment_credentials_calls_or_task_change(client,monkeypatch,chat):
    task,case,schema=setup(client,chat);before=copy.deepcopy(main.get_task(task['id']))
    assert not task.get('environment_id') and not task.get('dify_app_id')
    def forbidden(*args,**kwargs):pytest.fail('固定样例本机检查不能读凭据／登记预算／请求平台或模型')
    monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
    monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main.execution_limits,'require_start',forbidden)
    response=check(client,task,case,schema);assert response.status_code==200,response.text
    value=response.json();assert value['valid'] and value['verification']=='local_case_input_shape_only'
    assert not any(value[k] for k in ('platform_checked','business_verified','defaults_copied'))
    assert [r['index'] for r in value['checked_turns']]==list(range(1,3 if chat else 2))
    assert 'PRIVATE-INPUT' not in response.text and main.get_task(task['id'])==before


@pytest.mark.parametrize('input',[
    {'query':'追问'}, {'query':'追问','budget':'PRIVATE-BAD'},
    {'query':'追问','budget':1}, {'query':'追问','budget':0,'extra':'PRIVATE-BAD'},
])
def test_all_turns_final_fields_and_stable_parameters_without_changing_case(client,input):
    task,case,schema=setup(client,True);case['followups'][0]['input']=input
    task['test_cases']=[case];main.save_task(task);before=copy.deepcopy(main.get_task(task['id']))
    response=check(client,task,case,schema);assert response.status_code==422 and '第2轮' in response.text
    assert 'PRIVATE-BAD' not in response.text and main.get_task(task['id'])==before


def test_expected_case_source_revision_and_forbidden_replacement_bound(client):
    task,case,schema=setup(client)
    assert check(client,task,case,schema,revision=task['revision']+1).status_code==409
    assert check(client,task,case,schema,source_sha256='e'*64).status_code==409
    assert check(client,task,case,schema,case_id='foreign').status_code==404
    assert check(client,task,case,schema,input={'query':'replacement'}).status_code==422


def test_final_source_changed_during_check_rejected(client,monkeypatch):
    task,case,schema=setup(client);original=main.read_run_input_schema;calls=0
    def read(item):
        nonlocal calls;calls+=1
        if calls==2:
            path=main.artifact_path(task);path.write_text(path.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        return original(item)
    monkeypatch.setattr(main,'read_run_input_schema',read)
    assert check(client,task,case,schema).status_code==409


def test_stored_case_changed_during_check_not_adopted(client,monkeypatch):
    task,case,schema=setup(client);original=main.read_run_input_schema;calls=0
    def read(item):
        nonlocal calls;calls+=1
        if calls==2:
            current=main.get_task(item);current['test_cases'][0]['input']['query']='new';main.save_task(current)
        return original(item)
    monkeypatch.setattr(main,'read_run_input_schema',read)
    assert check(client,task,case,schema).status_code==409


def test_corrupt_case_list_and_app_type_not_silently_replaced(client):
    task,case,schema=setup(client);task['test_cases']=None;main.save_task(task)
    assert check(client,task,case,schema).status_code==422
    agent=create(client,app_type='agent')
    response=check(client,agent,case,schema);assert response.status_code==422 and '不替换' in response.text
    assert main.get_task(agent['id'])['app_type']=='agent'
