import asyncio
import copy
import json
import sys
from pathlib import Path
import httpx
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main, agent_stream
from app.agent_plan import compile_agent_plan, validate_agent_plan
from app.dify import DifyClient, DifyError
from app.storage import Store
from test_api import client, create

PLAN = {'schema_version': 1, 'scope': 'text', 'system_prompt': '只回答虚构编号，无编号时说明资料不足。'}


def fixture_task():
    return {'name': '原生 Agent 技术验证', 'app_type': 'agent', 'requirements': {k: '明确的技术范围' for k in main.REQ_KEYS},
            'agent_plan': copy.deepcopy(PLAN), 'configuration': {'dify_model_provider': 'langgenius/deepseek/deepseek',
            'dify_model': 'deepseek-flash', 'temperature': .2, 'max_tokens': 256, 'model_parameters': {'thinking': False, 'response_format': 'text'}}}


def test_native_package_has_no_workflow_substitution_or_credentials():
    content, result = compile_agent_plan(fixture_task())
    root = yaml.safe_load(content)
    assert result['valid'] and result['verification'] == 'static_only'
    assert root['app']['mode'] == 'agent' and 'workflow' not in root
    soul = root['agent_packages'][root['agent']['package_ref']]['soul']
    assert soul['model']['plugin_id'] == 'langgenius/deepseek'
    assert soul['model']['model_provider'] == 'langgenius/deepseek/deepseek'
    assert soul['model']['credential_ref'] is None
    assert soul['model']['model_settings']['response_format'] == {'type': 'text'}
    assert soul['model']['model_settings']['thinking'] is False
    assert '内建工具' in result['warnings'][0]


@pytest.mark.parametrize('patch', [
    {'schema_version': True}, {'scope': 'tools'}, {'system_prompt': ''},
    {'system_prompt': '{{#sys.query#}}'}, {'system_prompt': '[§skill:test§]'}, {'tools': []},
])
def test_unsupported_plan_never_silently_drops_fields(patch):
    task = fixture_task(); task['agent_plan'].update(patch)
    with pytest.raises(ValueError): compile_agent_plan(task)


@pytest.mark.parametrize('config', [{'dataset_ids': ['actual-id']}, {'conversation_memory': True}, {'dify_model_provider': 'deepseek'}, {'model_parameters': {'response_format': 'arbitrary'}}])
def test_agent_resource_and_parameter_limitations_are_explicit(config):
    task = fixture_task(); task['configuration'].update(config)
    with pytest.raises(ValueError): compile_agent_plan(task)


def prepare(client):
    task = create(client, 'agent')
    base = fixture_task()
    task = client.patch('/api/tasks/' + task['id'], json={'requirements': base['requirements'], 'configuration': {**base['configuration'], 'resource_plan': '本机新建技术 Agent；部署内建配置 CLI／沙箱需核对，不配置业务工具。'}}).json()
    assert client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': task['revision'], 'kind': 'requirements'}).status_code == 200
    result = client.post(f"/api/tasks/{task['id']}/plan", json={'revision': task['revision'], 'plan': PLAN})
    assert result.status_code == 200, result.text
    return result.json()


def test_agent_plan_requires_confirmation_and_invalidates_on_requirements_change(client):
    task = prepare(client); tid = task['id']
    assert task['app_type'] == 'agent' and task['agent_plan'] == PLAN and task['workflow_plan'] is None
    assert not task['configuration_confirmed']
    assert client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']}).status_code == 422
    assert client.post(f'/api/tasks/{tid}/confirm', json={'revision': task['revision'], 'kind': 'configuration'}).status_code == 200
    result = client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']}); assert result.status_code == 200
    content = client.get(f'/api/tasks/{tid}/dsl').json()['content']
    assert yaml.safe_load(content)['app']['mode'] == 'agent'
    changed = client.patch(f'/api/tasks/{tid}', json={'requirements': {'goal': '变更职责'}}).json()
    assert changed['plan_stale'] and changed['artifact'] is None and not changed['configuration_confirmed']
    assert client.post(f'/api/tasks/{tid}/plan', json={'revision': changed['revision'], 'plan': PLAN}).status_code == 200
    assert client.patch(f'/api/tasks/{tid}', json={'agent_plan': None}).json()['agent_plan'] is None
    assert client.patch(f'/api/tasks/{tid}', json={'workflow_plan': None}).status_code == 422


def test_workflow_cannot_accept_agent_plan(client):
    task = create(client)
    result = client.post(f"/api/tasks/{task['id']}/plan", json={'revision': task['revision'], 'plan': PLAN})
    assert result.status_code == 422
    assert not validate_agent_plan({'app_type': 'workflow'}, PLAN)['valid']


def knowledge_task():
    task = fixture_task(); task['configuration']['dataset_ids'] = ['confirmed-library']
    task['agent_plan'].update(scope='knowledge', knowledge_sets=[{'name': '政策资料', 'description': '回答虚构政策问题', 'dataset_ids': ['confirmed-library'], 'query_mode': 'generated_query', 'top_k': 3}])
    return task


def test_native_knowledge_sets_keep_selected_ids_and_explicit_retrieval_policy():
    root = yaml.safe_load(compile_agent_plan(knowledge_task())[0]); sets = root['agent_packages']['agent_1']['soul']['knowledge']['sets']
    assert len(sets) == 1 and sets[0]['datasets'] == [{'id': 'confirmed-library'}]
    assert sets[0]['query']['mode'] == 'generated_query'
    assert sets[0]['retrieval']['mode'] == 'multiple' and sets[0]['retrieval']['top_k'] == 3 and not sets[0]['retrieval']['reranking_enable']
    assert sets[0]['metadata_filtering']['mode'] == 'disabled'


@pytest.mark.parametrize('patch', [{'dataset_ids': ['invented-library']}, {'dataset_ids': []}, {'top_k': True}, {'query_mode': 'user_query'}, {'reranking_enable': True}, {'description': ''}])
def test_unsupported_or_unconfirmed_knowledge_plan_blocks_compile(patch):
    task = knowledge_task(); task['agent_plan']['knowledge_sets'][0].update(patch)
    with pytest.raises(ValueError): compile_agent_plan(task)


def test_knowledge_plan_rejects_duplicate_sets_and_missing_selected_library():
    task = knowledge_task(); task['agent_plan']['knowledge_sets'].append(copy.deepcopy(task['agent_plan']['knowledge_sets'][0]))
    assert not validate_agent_plan(task, task['agent_plan'])['valid']
    task = knowledge_task(); task['configuration']['dataset_ids'].append('another-selected-library')
    assert not validate_agent_plan(task, task['agent_plan'])['valid']


def sse(events):
    return ''.join('data: ' + json.dumps(e) + '\n\n' for e in events)


def stream_call(tmp_path, monkeypatch, events, *, stop=False, status=200, content_type='text/event-stream'):
    store = Store(tmp_path); store.set_secret('env', 'service_api_key', 'test-key')
    adapter = DifyClient({'id': 'env', 'base_url': 'http://127.0.0.1:8080'}, store)
    observed = []
    original = httpx.AsyncClient
    def handler(req):
        observed.append((req.url.path, json.loads(req.content)))
        if req.url.path.endswith('/stop'): return httpx.Response(200, json={'result': 'success'})
        return httpx.Response(status, headers={'content-type': content_type}, text=sse(events))
    monkeypatch.setattr(agent_stream.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return adapter, observed, lambda: asyncio.run(adapter.run_agent('联调', should_stop=lambda: stop))


def test_sse_requires_native_terminal_and_retains_usage(tmp_path, monkeypatch):
    events = [{'event': 'agent_message', 'answer': 'A', 'conversation_id': 'conversation-1', 'task_id': 'task-1'},
              {'event': 'agent_thought', 'observation': 'private observation'},
              {'event': 'message', 'answer': 'A'},
              {'event': 'message_replace', 'answer': 'B'},
              {'event': 'message_end', 'metadata': {'usage': {'total_tokens': 10}}}]
    _, observed, invoke = stream_call(tmp_path, monkeypatch, events)
    result = invoke()
    assert result['terminal'] is True and result['answer'] == 'B' and result['metadata']['usage']['total_tokens'] == 10
    assert result['thought_events'] == 1 and 'private' not in json.dumps(result)
    assert observed[0][1]['response_mode'] == 'streaming' and len(observed) == 1


def test_agent_preview_is_not_concatenated_with_final_answer(tmp_path, monkeypatch):
    _, _, invoke = stream_call(tmp_path, monkeypatch, [
        {'event': 'agent_message', 'answer': 'A', 'conversation_id': 'c', 'task_id': 't'},
        {'event': 'agent_message', 'answer': 'B'}, {'event': 'message', 'answer': 'AB'}, {'event': 'message_end'}])
    assert invoke()['answer'] == 'AB'


def test_agent_preview_without_final_answer_is_unknown(tmp_path, monkeypatch):
    _, _, invoke = stream_call(tmp_path, monkeypatch, [
        {'event': 'agent_message', 'answer': 'A', 'conversation_id': 'c', 'task_id': 't'}, {'event': 'message_end'}])
    with pytest.raises(DifyError, match='结果可能未知'): invoke()


@pytest.mark.parametrize('tail', [[], [{'event': 'unknown_new_event'}], [{'event': 'message_end'}], [{'event': 'message', 'answer': 'B', 'conversation_id': 'other'}]])
def test_missing_terminal_unknown_event_and_identity_conflict_stop_without_retry(tmp_path, monkeypatch, tail):
    # Empty output at message_end is also rejected.
    events = [{'event': 'message', 'answer': '', 'conversation_id': 'conversation-1', 'task_id': 'task-1'}, *tail]
    _, observed, invoke = stream_call(tmp_path, monkeypatch, events)
    with pytest.raises(DifyError, match='结果可能未知') as error: invoke()
    assert error.value.result['stop_acknowledged'] is True
    assert [p for p, _ in observed] == ['/v1/chat-messages', '/v1/chat-messages/task-1/stop']


def test_sse_error_is_failed_not_success_or_automatic_retry(tmp_path, monkeypatch):
    _, observed, invoke = stream_call(tmp_path, monkeypatch, [{'event': 'error', 'message': 'private error'}])
    with pytest.raises(DifyError) as error: invoke()
    assert error.value.result['terminal'] and error.value.result['data']['status'] == 'failed'
    assert 'private' not in str(error.value) and len(observed) == 1


def test_sse_pause_stops_before_consume_and_keeps_unknown(tmp_path, monkeypatch):
    _, observed, invoke = stream_call(tmp_path, monkeypatch, [{'event': 'message', 'answer': 'x'}], stop=True)
    with pytest.raises(DifyError, match='派发前已暂停'): invoke()
    assert len(observed) == 0


def test_sse_pause_after_dispatch_stops_known_remote_task(tmp_path, monkeypatch):
    adapter, observed, _ = stream_call(tmp_path, monkeypatch, [
        {'event': 'agent_message', 'answer': 'part', 'conversation_id': 'c', 'task_id': 't'},
        {'event': 'message', 'answer': 'final'}, {'event': 'message_end'}])
    checks = []
    def paused():
        checks.append(True)
        return len(checks) > 3  # before dispatch, data line, blank boundary, next data line
    with pytest.raises(DifyError, match='结果可能未知') as error:
        asyncio.run(adapter.run_agent('q', should_stop=paused))
    assert error.value.result['stop_acknowledged'] and error.value.result['answer'] == 'part'
    assert len(observed) == 2


def test_usage_metadata_does_not_copy_unknown_sensitive_fields(tmp_path, monkeypatch):
    _, _, invoke = stream_call(tmp_path, monkeypatch, [
        {'event': 'message', 'answer': 'ok', 'conversation_id': 'c', 'task_id': 't'},
        {'event': 'message_end', 'metadata': {'usage': {'total_tokens': 1, 'api_key': 'private'}, 'observations': 'private'}}])
    assert invoke()['metadata'] == {'usage': {'total_tokens': 1}}


def test_sse_total_time_limit_attempts_remote_stop_and_preserves_partial(tmp_path, monkeypatch):
    store = Store(tmp_path); store.set_secret('env', 'service_api_key', 'test-key')
    adapter = DifyClient({'id': 'env', 'base_url': 'http://127.0.0.1:8080'}, store)
    original, paths = httpx.AsyncClient, []
    class Delayed(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse([{'event': 'agent_message', 'answer': 'part', 'conversation_id': 'c', 'task_id': 't'}]).encode()
            await asyncio.sleep(1)
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={'result': 'success'}) if request.url.path.endswith('/stop') else httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Delayed())
    monkeypatch.setattr(agent_stream.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(DifyError, match='时间上限') as error:
        asyncio.run(adapter.run_agent('q', seconds=.02))
    assert error.value.result['answer'] == 'part' and error.value.result['stop_acknowledged']
    assert paths == ['/v1/chat-messages', '/v1/chat-messages/t/stop']


def runtime_task(client):
    task = prepare(client); tid = task['id']
    client.post(f'/api/tasks/{tid}/confirm', json={'revision': task['revision'], 'kind': 'configuration'})
    task = client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']}).json()
    # Controlled test store only, never a fabricated record in the user database.
    main.store.put('environment', 'env', {'id': 'env', 'base_url': 'http://127.0.0.1:8080', 'version': '1.17.1', 'service_app_id': 'app'})
    main.store.set_secret('env', 'service_api_key', 'test-key')
    task.update(environment_id='env', dify_app_id='app', status='imported')
    main.store.put('task', tid, task)
    return task


def test_native_run_adapter_used_without_workflow_or_chatflow_substitution(client, monkeypatch):
    task = runtime_task(client); calls = []
    async def native(self, query, **kwargs):
        calls.append((query, kwargs['seconds'], kwargs['should_stop']()))
        return {'answer': 'ok', 'conversation_id': 'c', 'terminal': True, 'transport': 'native_agent_sse'}
    monkeypatch.setattr(DifyClient, 'run_agent', native)
    response = client.post(f"/api/tasks/{task['id']}/run", json={'revision': task['revision'], 'input': {'query': 'q'}})
    assert response.status_code == 200 and response.json()['runs'][-1]['status'] == 'success'
    assert calls == [('q', 300, False)]


@pytest.mark.parametrize('result', [{'answer': 'partial', 'conversation_id': 'c'}, {'terminal': True, 'answer': '', 'conversation_id': 'c'}])
def test_agent_nonterminal_result_keeps_unknown_and_blocks_repeat(client, monkeypatch, result):
    task = runtime_task(client)
    async def incomplete(*args, **kwargs): return result
    monkeypatch.setattr(DifyClient, 'run_agent', incomplete)
    body = {'revision': task['revision'], 'input': {'query': 'q'}}
    assert client.post(f"/api/tasks/{task['id']}/run", json=body).status_code == 502
    saved = client.get(f"/api/tasks/{task['id']}").json()
    assert saved['runs'][-1]['status'] == 'unknown' and saved['runs'][-1]['result'] == result
    assert client.post(f"/api/tasks/{task['id']}/run", json=body).status_code == 409
