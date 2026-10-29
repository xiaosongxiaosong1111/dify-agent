import copy
import json
import httpx
import pytest
from test_api import client
from test_conversation import prepared
from app import main
from app.dify import DifyClient, DifyError
from app.dsl_roundtrip import parse
from app.run_diagnostics import binding

APP = 'a161d921-8f76-4a42-ad1e-6150a54cf0d8'
MESSAGE = 'edcc4b1c-2ab2-4e21-aef1-898ae8d983dc'
CONVERSATION = 'cb350c57-ee0e-4642-9b10-ab3e46a98e3b'
REMOTE = '5b66dc55-cce6-4457-bd4b-8f48ecdfc1bd'
OTHER = '895a778d-e2b2-4c41-9e26-5b08747dd59b'


@pytest.fixture(autouse=True)
def no_real_external(monkeypatch):
    def forbidden(*a, **kw): pytest.fail('Chatflow diagnostics must stay in local fixtures')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)
    monkeypatch.setattr(DifyClient, 'request', forbidden)


def recorded(client):
    task, env = prepared(client)
    task['dify_app_id'] = APP
    task['runs'] = [{'id': 'chat-run', 'kind': 'run', 'revision': task['revision'],
        'app_type': 'advanced-chat', 'app_id': APP, 'environment_id': env['id'],
        'environment_binding': binding(env), 'status': 'success', 'error': '',
        'input': {'query': '公开问题'}, 'result': {'event': 'message', 'mode': 'advanced-chat',
            'task_id': OTHER, 'id': MESSAGE, 'message_id': MESSAGE,
            'conversation_id': CONVERSATION, 'answer': '公开答复', 'metadata': {}}}]
    main.save_task(task)
    return task, task['runs'][0]


def diagnose(client, task, remote=True):
    return client.post(f"/api/tasks/{task['id']}/runs/chat-run/diagnose", json={
        'revision': task['revision'], 'read_remote': remote})


def reader(monkeypatch, task, message=None, run_detail=None, on_message=None):
    graph = parse(main.artifact_path(task).read_text('utf-8'), 'advanced-chat')['workflow']['graph']
    llm = next(n for n in graph['nodes'] if n['data']['type'] == 'llm')
    calls = []
    async def request(self, method, path, **kwargs):
        assert method == 'GET' and kwargs['credential'] == 'console_token'
        calls.append(path)
        if '/messages/' in path:
            if on_message: on_message()
            return copy.deepcopy(message if message is not None else {
                'id': MESSAGE, 'conversation_id': CONVERSATION, 'workflow_run_id': REMOTE,
                'query': 'PRIVATE-FETCHED-QUERY', 'answer': 'PRIVATE-FETCHED-ANSWER',
                'message': {'password': 'PRIVATE-FETCHED-CREDENTIAL'}})
        if path.endswith('/node-executions'):
            return {'data': [{'id': OTHER, 'node_id': llm['id'], 'node_type': 'llm',
                'title': '公开回答', 'status': 'succeeded', 'error': None}]}
        if path.endswith('/workflows/publish'):
            return {'id': OTHER, 'graph': graph}
        return copy.deepcopy(run_detail if run_detail is not None else {
            'id': REMOTE, 'status': 'succeeded', 'graph': graph})
    monkeypatch.setattr(DifyClient, 'request', request)
    return calls


def test_blocking_message_maps_exact_app_message_conversation_then_original_trace_chain(client, monkeypatch):
    task, run = recorded(client); before = copy.deepcopy(run)
    budget = copy.deepcopy(main.store.get('task_budget', task['id']))
    calls = reader(monkeypatch, task)
    response = diagnose(client, task); assert response.status_code == 200, response.text
    report = response.json()
    assert report['trace_state'] == 'read' and report['remote_run_id'] == REMOTE
    assert report['source_graph']['matched'] and report['current_source']
    source = report['remote_id_resolution']
    assert source['message_id'] == MESSAGE and source['conversation_id'] == CONVERSATION
    assert source['message_body_saved'] is False and source['workflow_or_nodes_verified'] is False
    assert calls == [f'/console/api/apps/{APP}/messages/{MESSAGE}',
        f'/console/api/apps/{APP}/workflow-runs/{REMOTE}',
        f'/console/api/apps/{APP}/workflow-runs/{REMOTE}/node-executions',
        f'/console/api/apps/{APP}/workflows/publish']
    saved = main.get_task(task['id'])['runs'][0]
    assert {k: v for k, v in saved.items() if k != 'diagnostics'} == before
    assert 'PRIVATE-FETCHED' not in json.dumps(saved)
    assert main.store.get('task_budget', task['id']) == budget


def test_local_analysis_does_not_resolve_or_dispatch(client, monkeypatch):
    task, _ = recorded(client); calls = reader(monkeypatch, task)
    report = diagnose(client, task, False).json()
    assert report['trace_state'] == 'local_only' and report['remote_run_id'] is None and not calls


@pytest.mark.parametrize('changes', [
    {'id': OTHER}, {'id': '../../wrong'}, {'id': True}, {'id': {}},
    {'id': None, 'message_id': None}, {'conversation_id': None}, {'conversation_id': 'PRIVATE-BAD'},
    {'workflow_run_id': 'PRIVATE-BAD'}, {'workflow_run_id': ''}, {'mode': 'chat'}, {'mode': 'agent-chat'},
])
def test_untrusted_or_conflicting_saved_identity_never_starts_lookup(client, changes):
    task, run = recorded(client); run['result'].update(changes); main.save_task(task)
    report = diagnose(client, task).json()
    assert report['trace_state'] == 'unavailable' and report['remote_run_id'] is None
    assert 'PRIVATE' not in report['trace_error']


@pytest.mark.parametrize('version', [None, '1.18.0', 'unknown'])
def test_unadapted_recorded_version_does_not_guess_message_api(client, version):
    task, run = recorded(client); env = main.store.get('environment', task['environment_id'])
    env['version'] = version; main.store.put('environment', env['id'], env)
    run['environment_binding'] = binding(env); main.save_task(task)
    assert diagnose(client, task).json()['trace_state'] == 'unavailable'


@pytest.mark.parametrize('alias', ['id', 'message_id'])
def test_one_saved_message_alias_is_sufficient_but_task_id_is_never_used(client, monkeypatch, alias):
    task, run = recorded(client); run['result'].pop(alias); main.save_task(task)
    calls = reader(monkeypatch, task); report = diagnose(client, task).json()
    assert report['trace_state'] == 'read' and calls[0].endswith('/messages/' + MESSAGE)


@pytest.mark.parametrize('value', [
    [], {}, {'id': OTHER, 'conversation_id': CONVERSATION, 'workflow_run_id': REMOTE},
    {'id': MESSAGE, 'conversation_id': OTHER, 'workflow_run_id': REMOTE},
    {'id': MESSAGE, 'conversation_id': CONVERSATION},
    {'id': MESSAGE, 'conversation_id': CONVERSATION, 'workflow_run_id': '../../PRIVATE-BAD'},
    {'id': MESSAGE, 'conversation_id': CONVERSATION, 'workflow_run_id': True},
    {'id': MESSAGE, 'conversation_id': CONVERSATION, 'workflow_run_id': REMOTE, 'app_id': OTHER},
])
def test_mismatched_message_record_stops_before_workflow_or_node_reads(client, monkeypatch, value):
    task, _ = recorded(client); calls = reader(monkeypatch, task, message=value)
    report = diagnose(client, task).json()
    assert report['trace_state'] == 'read_failed' and len(calls) == 1
    assert report['remote_run_id'] is None and 'PRIVATE' not in report['trace_error']


def test_valid_saved_run_id_keeps_old_path_without_extra_message_read(client, monkeypatch):
    task, run = recorded(client); run['result']['workflow_run_id'] = REMOTE; main.save_task(task)
    calls = reader(monkeypatch, task); report = diagnose(client, task).json()
    assert report['trace_state'] == 'read' and len(calls) == 3
    assert not any('/messages/' in path for path in calls)


def test_lookup_success_does_not_bypass_run_identity_check(client, monkeypatch):
    task, _ = recorded(client); calls = reader(monkeypatch, task, run_detail={'id': OTHER})
    report = diagnose(client, task).json()
    assert report['trace_state'] == 'read_failed' and len(calls) == 2


@pytest.mark.parametrize('status', [401, 404, 502])
def test_lookup_http_failure_does_not_retry_or_read_nodes(client, monkeypatch, status):
    task, _ = recorded(client); calls = []
    async def failed(self, method, path, **kwargs):
        calls.append(path); raise DifyError('Dify HTTP ' + str(status), http_status=status)
    monkeypatch.setattr(DifyClient, 'request', failed)
    assert diagnose(client, task).json()['trace_state'] == 'read_failed' and len(calls) == 1


@pytest.mark.parametrize('pending', [False, True, 'malformed', 'other_conversation'])
def test_selected_conversation_turn_and_pending_unknown_are_not_replaced_by_other_turns(client, monkeypatch, pending):
    task, run = recorded(client); selected = copy.deepcopy(run['result'])
    other = {**selected, 'id': OTHER, 'message_id': OTHER}
    run['result'] = {'conversation_case': True, 'conversation_id': CONVERSATION,
        'turns': [{'index': 1, 'result': other, 'evaluation': {'status': 'passed'}},
            {'index': 2, 'result': selected, 'evaluation': {'status': 'failed'}},
            {'index': 3, 'result': other, 'evaluation': {'status': 'passed'}}]}
    if pending:
        run['result']['pending_turn'] = {'index': 4, 'result': selected}
        if pending == 'malformed': run['result']['pending_turn']['result'] = ['not a result']
        if pending == 'other_conversation': run['result']['pending_turn']['result']['conversation_id'] = OTHER
    main.save_task(task); calls = reader(monkeypatch, task)
    report = diagnose(client, task).json()
    assert report['selected_turn'] == (4 if pending else 2)
    if pending in ('malformed', 'other_conversation'):
        assert report['trace_state'] == 'unavailable' and not calls
    else: assert report['trace_state'] == 'read' and calls[0].endswith(MESSAGE)


@pytest.mark.parametrize('mutation', ['result', 'revision', 'environment', 'app'])
def test_source_changed_during_message_read_never_saves_mixed_diagnostic(client, monkeypatch, mutation):
    task, _ = recorded(client)
    def change():
        current = main.get_task(task['id'])
        if mutation == 'result': current['runs'][0]['result']['answer'] = 'changed'
        elif mutation == 'revision': current['revision'] += 1
        elif mutation == 'app': current['dify_app_id'] = OTHER
        else:
            env = main.store.get('environment', task['environment_id']); env['base_url'] = 'https://other.example'
            main.store.put('environment', env['id'], env)
        main.save_task(current)
    reader(monkeypatch, task, on_message=change)
    assert diagnose(client, task).status_code == 409
    assert not main.get_task(task['id'])['runs'][0].get('diagnostics')
