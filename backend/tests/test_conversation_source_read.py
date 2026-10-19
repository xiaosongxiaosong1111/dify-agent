import copy
import json
import sqlite3
import pytest
from test_api import client, create
from test_conversation_inputs import first, request
from test_chatflow_inputs import runtime
from app import main
from app.conversation_inputs import KIND
from app.start_inputs import same_initial_parameters


def read(client,task,source,**patch):
    schema=client.get(f"/api/tasks/{task['id']}/run-input-schema").json()
    return client.get(f"/api/tasks/{task['id']}/conversation-input-source/{source}",params={'revision':task['revision'],'source_sha256':schema['source_sha256'],**patch})


def test_local_origin_check_without_decryption_network_budget_or_private_values(client,monkeypatch):
    task,source,seen=first(client,monkeypatch);before=copy.deepcopy(main.get_task(task['id']));proof=main.store.get(KIND,source)
    def forbidden(*a,**kw):pytest.fail('本机来源核对不能解密／联网／登记预算')
    monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.store.cipher,'decrypt',forbidden)
    monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.execution_limits,'require_start',forbidden)
    response=read(client,task,source);assert response.status_code==200,response.text
    value=response.json();assert value['source_binding_valid'] is True and value['state']=='locally_matched'
    assert not any(value[k] for k in ('runtime_inputs_checked','credentials_decrypted','network_requested','platform_checked','business_verified'))
    assert proof['credential_stamp'] not in response.text and 'stable-free' not in response.text and '首轮' not in response.text
    assert main.get_task(task['id'])==before and main.store.get(KIND,source)==proof and len(seen)==1


@pytest.mark.parametrize('change',['credential','service_app','missing_proof','foreign_source'])
def test_known_source_mismatch_is_explicit_not_false_platform_check(client,monkeypatch,change):
    task,source,seen=first(client,monkeypatch)
    if change=='credential':main.store.set_secret(task['environment_id'],'service_api_key','new-origin-key')
    if change=='service_app':
        env=main.store.get('environment',task['environment_id']);env['service_app_id']='other-app';main.store.put('environment',env['id'],env)
    if change=='missing_proof':main.store.delete(KIND,source)
    if change=='foreign_source':source='not-this-task'
    before=copy.deepcopy(main.get_task(task['id']));response=read(client,task,source)
    assert response.status_code==200,response.text
    value=response.json();assert value['source_binding_valid'] is False and value['state']=='not_ready'
    assert value['reason'] and not value['network_requested'] and main.get_task(task['id'])==before and len(seen)==1


def test_source_index_failure_unknown_not_matched_or_known_empty(client,monkeypatch):
    task,source,_=first(client,monkeypatch);original=main.store.get
    def get(kind,item):
        if kind==KIND:raise sqlite3.OperationalError('PRIVATE DB DETAILS')
        return original(kind,item)
    monkeypatch.setattr(main.store,'get',get)
    response=read(client,task,source);assert response.status_code==200,response.text
    value=response.json();assert value['source_binding_valid'] is None and value['state']=='unknown'
    assert 'PRIVATE DB DETAILS' not in response.text and not value['network_requested']


def test_source_revision_artifact_and_app_type_not_silently_substituted(client,monkeypatch):
    task,source,_=first(client,monkeypatch)
    assert read(client,task,source,revision=task['revision']+1).status_code==409
    assert read(client,task,source,source_sha256='0'*64).status_code==409
    agent=create(client,app_type='agent')
    response=client.get(f"/api/tasks/{agent['id']}/conversation-input-source/{source}",params={'revision':agent['revision'],'source_sha256':'0'*64})
    assert response.status_code==422 and main.get_task(agent['id'])['app_type']=='agent'


def test_equivalent_json_numbers_allow_reuse_without_rewriting_original_records(client,monkeypatch):
    task=runtime(client);seen=[]
    async def chat(self,query,inputs=None,conversation_id=None):
        seen.append(copy.deepcopy(inputs));return {'answer':'回答','conversation_id':conversation_id or 'numeric-origin'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=request(client,task,{'query':'首轮','budget':1.0});assert response.status_code==200,response.text
    task=response.json();source=task['runs'][-1]['id']
    response=request(client,task,{'query':'追问','budget':1},source);assert response.status_code==200,response.text
    runs=main.get_task(task['id'])['runs']
    assert type(runs[0]['input']['budget']) is float and type(runs[1]['input']['budget']) is int
    assert type(seen[0]['budget']) is float and type(seen[1]['budget']) is int


@pytest.mark.parametrize('left,right,expected',[
    ({'x':1},{'x':1.0},True), ({'x':True},{'x':1},False),
    ({'x':None},{'x':0},False), ({},{'x':None},False),
    ({'x':'1'},{'x':1},False), ({'x':float('inf')},{'x':float('inf')},False),
])
def test_custom_parameter_equality_keeps_json_scalar_types_and_omission(left,right,expected):
    assert same_initial_parameters(left,right) is expected
