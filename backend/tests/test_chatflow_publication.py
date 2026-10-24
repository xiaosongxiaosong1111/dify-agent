import copy
import json
import uuid

import httpx
import pytest

from test_api import client, approved, forbid_api_external_calls
from test_workflow_publication import prepare, confirm
from app import main
from app.dify import DifyClient, DifyError
from app.dsl_roundtrip import parse
from app.delivery_next_steps import describe
from app.storage import Store

NATIVE_REQUEST = DifyClient.request


def setup(client, monkeypatch):
    env = client.post('/api/environments', json={'name': '隔离Chatflow', 'base_url': 'http://127.0.0.1:8080',
        'version': '1.17.1', 'console_token': 'ISOLATED-CONSOLE-NO-REAL-TOKEN'}).json()
    task = approved(client, app_type='advanced-chat', env_id=env['id']); tid = task['id']
    task = client.patch('/api/tasks/' + tid, json={'configuration': {'conversation_memory': True,
        'memory_turns': 3, 'opening_statement': '合成售后服务', 'suggested_questions': ['合成订单如何查询？']}}).json()
    assert client.post('/api/tasks/' + tid + '/confirm', json={'revision': task['revision'], 'kind': 'configuration'}).status_code == 200
    response = client.post('/api/tasks/' + tid + '/build', json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json(); root = parse(main.artifact_path(task).read_text('utf-8'), 'advanced-chat')
    app = str(uuid.uuid4()); task.update(dify_app_id=app, status='imported')
    task['runs'].append({'id': 'synthetic-import', 'kind': 'import', 'status': 'success', 'revision': task['revision'],
        'environment_id': env['id'], 'result': {'app_id': app}, 'dsl_baseline': copy.deepcopy(root)})
    main.store.put('task', tid, task)
    state = {'calls': [], 'draft': copy.deepcopy(root['workflow']) | {'hash': 'native-chatflow-draft'},
        'published': None, 'details': {'id': app, 'mode': 'advanced-chat'}}
    async def request(self, method, path, **kwargs):
        state['calls'].append((method, path))
        if method == 'POST':
            assert path == f'/console/api/apps/{app}/workflows/publish'
            assert set(kwargs['json']) == {'marked_name', 'marked_comment'}
            if state.get('post_error'): raise state['post_error']
            state['published'] = copy.deepcopy(state['draft']) | {'id': str(uuid.uuid4())}
            if state.get('post_hook'): state['post_hook']()
            return {'result': 'success'}
        if path == '/console/api/apps/' + app:
            return copy.deepcopy(state['details'])
        if path.endswith('/workflows/draft'): return copy.deepcopy(state['draft'])
        assert path.endswith('/workflows/publish')
        # Dify 1.17.1 also returns successful JSON null when unpublished.
        return copy.deepcopy(state['published'])
    state['adapter'] = request
    monkeypatch.setattr(DifyClient, 'request', request)
    return task, env, state


def writes(state): return sum(method == 'POST' for method, _ in state['calls'])


def test_current_chatflow_review_publish_report_and_no_repeat(client, monkeypatch):
    task, env, state = setup(client, monkeypatch); p = prepare(client, task)
    assert p.status_code == 200, p.text
    p = p.json()
    assert p['app_type'] == 'advanced-chat' and p['planned_console_reads'] == 7
    assert len(state['calls']) == 3 and writes(state) == 0
    result = confirm(client, task, p)
    assert result.status_code == 200, result.text
    assert result.json()['state'] == 'succeeded' and result.json()['app_type'] == 'advanced-chat'
    assert writes(state) == 1 and len(state['calls']) == 8
    after = main.store.get('task', task['id'])
    assert after['app_type'] == 'advanced-chat' and after['artifact'] == task['artifact']
    assert after['runs'][-1]['result']['app_type'] == 'advanced-chat'
    assert not any(row['kind'] == 'run' for row in after['runs'])
    report = client.get('/api/tasks/' + task['id'] + '/report').text
    assert '无需重复发布' in report and 'Chatflow或原生Agent须' not in report
    assert confirm(client, task, p).status_code == 409 and prepare(client, task).status_code == 409
    assert writes(state) == 1


@pytest.mark.parametrize('change', ['wrong_mode', 'missing_mode', 'wrong_app'])
def test_remote_identity_or_mode_mismatch_refuses_before_draft_or_write(client, monkeypatch, change):
    task, env, state = setup(client, monkeypatch)
    if change == 'wrong_mode': state['details']['mode'] = 'workflow'
    if change == 'missing_mode': state['details'].pop('mode')
    if change == 'wrong_app': state['details']['id'] = str(uuid.uuid4())
    response = prepare(client, task)
    assert response.status_code == 409 and len(state['calls']) == 1 and writes(state) == 0
    assert not main.store.list('workflow_publication')


@pytest.mark.parametrize('change', ['mode', 'opening', 'memory', 'conversation', 'published', 'local_type', 'legacy_binding'])
def test_changed_chatflow_proposal_never_dispatches(client, monkeypatch, change):
    task, env, state = setup(client, monkeypatch); response = prepare(client, task)
    assert response.status_code == 200, response.text
    p = response.json()
    if change == 'mode': state['details']['mode'] = 'workflow'
    elif change == 'opening': state['draft']['features']['opening_statement'] = '外部修改'
    elif change == 'memory':
        next(n for n in state['draft']['graph']['nodes'] if n['data']['type'] == 'llm')['data']['memory']['window']['size'] = 2
    elif change == 'conversation': state['draft']['conversation_variables'] = [{'name': 'unknown', 'value': 'changed'}]
    elif change == 'published': state['published'] = state['draft'] | {'id': str(uuid.uuid4())}
    elif change == 'local_type':
        current = main.store.get('task', task['id']); current['app_type'] = 'workflow'; main.store.put('task', task['id'], current)
    else:
        row = main.store.get('workflow_publication', p['id']); row['binding'].pop('app_type'); main.store.put('workflow_publication', p['id'], row)
    response = confirm(client, task, p)
    assert response.status_code in {409, 422} and writes(state) == 0


@pytest.mark.parametrize('failure', ['timeout', '401', 'wrong_graph', 'local_type'])
def test_chatflow_possible_publication_stays_unknown_and_no_replay(client, monkeypatch, failure):
    task, env, state = setup(client, monkeypatch); response = prepare(client, task)
    assert response.status_code == 200, response.text
    p = response.json()
    if failure == 'timeout': state['post_error'] = DifyError('timeout')
    elif failure == '401': state['post_error'] = DifyError('401', http_status=401)
    elif failure == 'wrong_graph': state['post_hook'] = lambda: state['published']['features'].update(opening_statement='different')
    else:
        def change():
            current = main.store.get('task', task['id']); current['app_type'] = 'workflow'; main.store.put('task', task['id'], current)
        state['post_hook'] = change
    assert confirm(client, task, p).status_code == 502
    row = Store(main.store.root).get('workflow_publication', p['id'])
    assert row['state'] == 'unknown' and row['write_attempted']
    main.workflow_publication_recover()
    assert confirm(client, task, p).status_code == 409
    assert writes(state) == 1


def test_real_dify_request_httpx_serialization_with_fake_final_transport(client, monkeypatch):
    task, env, state = setup(client, monkeypatch)
    adapter = state['adapter']; monkeypatch.setattr(DifyClient, 'request', NATIVE_REQUEST)
    async def native(transport, request):
        assert request.url.host == '127.0.0.1' and request.url.port == 8080
        assert request.headers['authorization'] == 'Bearer ISOLATED-CONSOLE-NO-REAL-TOKEN'
        body = json.loads(request.content) if request.content else None
        value = await adapter(None, request.method, request.url.path, **({'json': body} if body is not None else {}))
        return httpx.Response(200, content=json.dumps(value), headers={'content-type': 'application/json'}, request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', native)
    p = prepare(client, task); assert p.status_code == 200, p.text
    result = confirm(client, task, p.json()); assert result.status_code == 200, result.text
    assert len(state['calls']) == 8 and writes(state) == 1


def test_report_does_not_accept_workflow_or_untyped_publish_receipt_for_chatflow():
    from test_delivery_next_steps import saved_task, PASSED
    task = saved_task(); task['app_type'] = 'advanced-chat'
    for mode in [None, 'workflow']:
        task['runs'][-1]['result']['app_type'] = mode
        report = '\n'.join(describe(task, PASSED))
        assert '无需重复发布' not in report and '不套用Workflow发布回执' in report
    task['runs'][-1]['result']['app_type'] = 'advanced-chat'
    assert '无需重复发布' in '\n'.join(describe(task, PASSED))


def test_legacy_workflow_receipt_missing_type_remains_compatible_but_explicit_null_is_not():
    from test_delivery_next_steps import saved_task, PASSED
    task = saved_task()
    assert '无需重复发布' in '\n'.join(describe(task, PASSED))
    task['runs'][-1]['result']['app_type'] = None
    text = '\n'.join(describe(task, PASSED))
    assert '无需重复发布' not in text and '禁止直接重发' in text


def test_workflow_report_without_publication_record_keeps_initial_todo():
    from test_delivery_next_steps import saved_task, PASSED
    task = saved_task(); task['runs'] = task['runs'][:1]
    assert '尚无当前App的发布成功回执' in '\n'.join(describe(task, PASSED))


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat'])
@pytest.mark.parametrize('status', ['pending', 'unknown'])
def test_current_app_dispatch_without_response_metadata_is_not_treated_as_unpublished(mode, status):
    from test_delivery_next_steps import saved_task, PASSED
    task = saved_task(); task['app_type'] = mode
    task['runs'][-1].update(status=status, result={})
    text = '\n'.join(describe(task, PASSED))
    assert '可能已经执行' in text and '禁止直接重发' in text
    assert '尚无当前App的发布成功回执' not in text
