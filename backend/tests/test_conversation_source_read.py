import copy
import json
import sqlite3
import httpx
import pytest
from test_api import client, create
from test_conversation_inputs import first, request
from test_chatflow_inputs import runtime
from app import main
from app.conversation_inputs import KIND
from app.start_inputs import same_initial_parameters


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('AT-17 隔离检查不得访问真实 HTTP 或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)
    monkeypatch.setattr(main.DifyClient, 'request', forbidden)


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


@pytest.mark.parametrize('change', ['selected_environment', 'address', 'version'])
def test_customer_environment_change_invalidates_old_approval_artifact_and_source(client, monkeypatch, change):
    task, source, seen = first(client, monkeypatch)
    # Local fixture only: keeping an old resource ID must not imply it was mapped.
    task['configuration']['dataset_ids'] = ['company-knowledge-id']
    main.save_task(task)
    before = copy.deepcopy(task)
    proof = main.store.get(KIND, source)
    schema = client.get(f"/api/tasks/{task['id']}/run-input-schema").json()
    if change == 'selected_environment':
        response = client.post('/api/environments', json={
            'name': '客户环境', 'base_url': 'https://customer.example', 'version': '1.17.1'})
        assert response.status_code == 201, response.text
        target = response.json()
        assert not target['has_service_api_key']
        assert set(target['capabilities'].values()) == {'untested'}
        response = client.patch(f"/api/tasks/{task['id']}", json={'environment_id': target['id']})
    else:
        payload = {'base_url': 'https://customer.example'} if change == 'address' else {'version': '1.16.0'}
        response = client.patch(f"/api/environments/{task['environment_id']}", json=payload)
    assert response.status_code == 200, response.text
    current = main.get_task(task['id'])
    assert current['revision'] == before['revision'] + 1
    assert current['requirements_confirmed'] and not current['configuration_confirmed']
    assert current['artifact'] is None and current['dify_app_id'] is None
    assert current['app_type'] == before['app_type'] == 'advanced-chat'
    assert current['requirements'] == before['requirements']
    assert current['configuration'] == before['configuration']
    assert current['runs'] == before['runs'] and main.store.get(KIND, source) == proof
    assert current['versions'][-1]['artifact'] == before['artifact']
    if change == 'address':
        assert not main.store.has_secret(task['environment_id'], 'service_api_key')
        assert not main.store.has_secret(task['environment_id'], 'console_token')

    params = {'revision': before['revision'], 'source_sha256': schema['source_sha256']}
    response = client.get(f"/api/tasks/{task['id']}/conversation-input-source/{source}", params=params)
    assert response.status_code == 409, response.text
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={
        'kind': 'configuration', 'revision': before['revision']})
    assert response.status_code == 409, response.text
    response = client.get(f"/api/tasks/{task['id']}/conversation-input-source/{source}",
                          params={**params, 'revision': current['revision']})
    assert response.status_code == 404, response.text
    assert response.json()['detail'] == '当前版本尚未生成文件，请确认方案后生成。'
    def forbidden(*args, **kwargs):
        pytest.fail('环境改变后未重新确认不得登记运行预算')
    monkeypatch.setattr(main.execution_limits, 'require_start', forbidden)
    response = request(client, current, {'query': '客户环境追问', 'budget': 0}, source)
    assert response.status_code == 422, response.text
    assert main.get_task(task['id']) == current and len(seen) == 1


@pytest.mark.parametrize('change', ['address', 'version', 'environment_id', 'missing_environment',
                                  'source_environment', 'proof_environment'])
def test_stale_environment_binding_is_rejected_even_with_current_revision_and_artifact(client, monkeypatch, change):
    task, source, seen = first(client, monkeypatch)
    env = main.store.get('environment', task['environment_id'])
    # Deliberately bypass API invalidation in the temporary Store to isolate the provenance guard.
    if change == 'address':
        env['base_url'] = 'https://customer.example'
        main.store.put('environment', env['id'], env)
    elif change == 'version':
        env['version'] = '1.16.0'
        main.store.put('environment', env['id'], env)
    elif change == 'environment_id':
        env['id'] = 'customer-environment'
        main.store.put('environment', env['id'], env)
        task['environment_id'] = env['id']
        main.save_task(task)
    elif change == 'missing_environment':
        main.store.delete('environment', env['id'])
    elif change == 'source_environment':
        task['runs'][-1]['environment_id'] = 'customer-environment'
        main.save_task(task)
    else:
        proof = main.store.get(KIND, source)
        proof['environment_id'] = 'customer-environment'
        main.store.put(KIND, source, proof)
    before = copy.deepcopy(main.get_task(task['id']))
    proof = main.store.get(KIND, source)
    def forbidden(*args, **kwargs):
        pytest.fail('旧环境来源核对不能解密、登记预算或派发')
    monkeypatch.setattr(main.store, 'secret', forbidden)
    monkeypatch.setattr(main.store.cipher, 'decrypt', forbidden)
    monkeypatch.setattr(main.execution_limits, 'require_start', forbidden)
    monkeypatch.setattr(main.DifyClient, 'request', forbidden)
    response = read(client, task, source)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['state'] == 'not_ready' and value['source_binding_valid'] is False
    assert value['reason']
    if change == 'version':
        assert 'Dify 1.17.1' in value['reason']
    assert not any(value[k] for k in ('credentials_decrypted', 'network_requested',
                                      'platform_checked', 'business_verified'))
    assert 'stable-free' not in response.text and 'unit-key' not in response.text
    assert main.get_task(task['id']) == before and main.store.get(KIND, source) == proof
    assert len(seen) == 1


@pytest.mark.parametrize('payload', [
    {'service_api_key': 'customer-unit-key'}, {'service_app_id': 'customer-app'},
])
def test_public_credential_or_app_change_requires_new_source_without_erasing_history(client, monkeypatch, payload):
    task, source, seen = first(client, monkeypatch)
    before = copy.deepcopy(main.get_task(task['id']))
    proof = main.store.get(KIND, source)
    response = client.patch(f"/api/environments/{task['environment_id']}", json=payload)
    assert response.status_code == 200, response.text
    assert main.get_task(task['id']) == before
    response = read(client, task, source)
    assert response.status_code == 200, response.text
    assert response.json()['source_binding_valid'] is False and response.json()['state'] == 'not_ready'
    assert not response.json()['platform_checked']
    def forbidden(*args, **kwargs):
        pytest.fail('旧认证或App来源不得登记预算或派发')
    monkeypatch.setattr(main.execution_limits, 'require_start', forbidden)
    response = request(client, task, {'query': '追问', 'budget': 0}, source)
    assert response.status_code == 422, response.text
    assert 'customer-unit-key' not in response.text
    assert main.get_task(task['id']) == before and main.store.get(KIND, source) == proof
    assert len(seen) == 1


@pytest.mark.parametrize('capability', ['untested', 'failed'])
def test_local_match_is_not_customer_authentication_version_probe_or_resource_mapping(client, monkeypatch, capability):
    task, source, seen = first(client, monkeypatch)
    env = main.store.get('environment', task['environment_id'])
    env['capabilities'] = dict.fromkeys(('console', 'datasets', 'runtime'), capability)
    main.store.put('environment', env['id'], env)
    before = copy.deepcopy(main.get_task(task['id']))
    response = read(client, task, source)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['state'] == 'locally_matched' and value['source_binding_valid'] is True
    assert value['verification'] == 'local_custom_conversation_source_only'
    assert not value['platform_checked'] and not value['business_verified'] and not value['network_requested']
    assert '不是资源／业务通过' in value['reason']
    assert main.store.get('environment', env['id']) == env
    assert main.get_task(task['id']) == before and len(seen) == 1
