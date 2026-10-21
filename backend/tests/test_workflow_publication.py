import copy
import asyncio
import threading
import uuid

import pytest
from test_api import client, approved, forbid_api_external_calls
from app import main
from app.dify import DifyError
from app.dsl_roundtrip import parse
from app.storage import Store


def setup(client, monkeypatch):
    env = client.post('/api/environments', json={'name': '隔离测试', 'base_url': 'http://127.0.0.1:8080', 'version': '1.17.1', 'console_token': 'isolated-token'}).json()
    task = approved(client, env_id=env['id'])
    task = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']}).json()
    root = parse(main.artifact_path(task).read_text('utf-8'), 'workflow')
    app = str(uuid.uuid4()); task['dify_app_id'] = app; task['status'] = 'imported'
    task['runs'].append({'id': 'import-fixture', 'kind': 'import', 'status': 'success', 'revision': task['revision'], 'environment_id': env['id'], 'result': {'app_id': app}, 'dsl_baseline': copy.deepcopy(root)})
    main.store.put('task', task['id'], task)
    state = {'draft': copy.deepcopy(root['workflow']) | {'hash': 'draft-native-hash'}, 'published': None, 'calls': []}
    async def request(self, method, path, **kwargs):
        state['calls'].append((method, path))
        if method == 'POST':
            assert path == f'/console/api/apps/{app}/workflows/publish'
            assert set(kwargs['json']) == {'marked_name', 'marked_comment'}
            if state.get('post_error'): raise state['post_error']
            state['published'] = copy.deepcopy(state['draft']) | {'id': 'cbad145b-d134-4ada-9c34-81c147fb5f87'}
            if state.get('post_hook'): state['post_hook']()
            return {'result': 'success'}
        if path.endswith('/workflows/draft'):
            if state.get('read_hook'): await asyncio.to_thread(state['read_hook'])
            return copy.deepcopy(state['draft'])
        assert path.endswith('/workflows/publish')
        if state['published'] is None: raise DifyError('not published', http_status=404)
        return copy.deepcopy(state['published'])
    monkeypatch.setattr(main.DifyClient, 'request', request)
    return task, env, state


def prepare(client, task):
    return client.post(f"/api/tasks/{task['id']}/workflow-publication/prepare", json={'revision': task['revision']})


def confirm(client, task, proposal, **overrides):
    body = {'revision': task['revision'], 'proposal_id': proposal['id'], 'review_token': proposal['review_token'], 'confirm_publish': True} | overrides
    return client.post(f"/api/tasks/{task['id']}/workflow-publication/confirm", json=body)


def writes(state): return sum(method == 'POST' for method, _ in state['calls'])


def test_review_then_confirm_exactly_one_publish_and_no_keys_or_runs(client, monkeypatch):
    task, env, state = setup(client, monkeypatch)
    r = prepare(client, task); assert r.status_code == 200, r.text
    p = r.json(); assert p['state'] == 'ready' and not p['write_attempted'] and writes(state) == 0
    assert len(state['calls']) == 2 and p['new_keys'] == 0 and p['runs'] == 0
    assert 'binding' not in p and 'draft_digest' not in p and 'isolated-token' not in r.text
    r = confirm(client, task, p); assert r.status_code == 200, r.text
    assert r.json()['state'] == 'succeeded' and not r.json()['business_verified']
    assert writes(state) == 1 and len(state['calls']) == 6
    after = client.get(f"/api/tasks/{task['id']}").json()
    assert after['revision'] == task['revision'] and after['dify_app_id'] == task['dify_app_id'] and after['artifact'] == task['artifact']
    assert after['runs'][-1]['kind'] == 'publish' and after['runs'][-1]['status'] == 'success'
    assert confirm(client, task, p).status_code == 409
    assert prepare(client, task).status_code == 409 and writes(state) == 1
    assert Store(main.store.root).get('workflow_publication', p['id'])['state'] == 'succeeded'


@pytest.mark.parametrize('change', ['revision', 'environment', 'artifact', 'confirmation', 'pause', 'app', 'expiry', 'token', 'ack', 'hash', 'remote_graph', 'published'])
def test_changed_or_unapproved_proposal_never_publishes(client, monkeypatch, change):
    task, env, state = setup(client, monkeypatch); p = prepare(client, task).json(); overrides = {}
    current = main.store.get('task', task['id'])
    if change == 'revision': current['revision'] += 1
    elif change == 'environment':
        e = main.store.get('environment', env['id']); e['connection_revision'] = 'changed'; main.store.put('environment', env['id'], e)
    elif change == 'artifact': main.artifact_path(current).write_text(main.artifact_path(current).read_text('utf-8') + '\n#changed', encoding='utf-8')
    elif change == 'confirmation': current['configuration_confirmed'] = False
    elif change == 'pause': current['status'] = 'paused'; current['pause_generation'] = 1
    elif change == 'app': current['dify_app_id'] = str(uuid.uuid4())
    elif change == 'expiry':
        row = main.store.get('workflow_publication', p['id']); row['expires_at'] = 0; main.store.put('workflow_publication', p['id'], row)
    elif change == 'token': overrides['review_token'] = 'wrong'
    elif change == 'ack': overrides['confirm_publish'] = False
    elif change == 'hash': state['draft']['hash'] = 'changed-hash'
    elif change == 'remote_graph': state['draft']['graph']['nodes'][0]['data']['title'] = 'external-edit'
    elif change == 'published': state['published'] = copy.deepcopy(state['draft']) | {'id': 'other-publisher'}
    main.store.put('task', task['id'], current)
    r = confirm(client, task, p, **overrides); assert r.status_code in {404, 409}, r.text
    assert writes(state) == 0


@pytest.mark.parametrize('bad', ['wrong_graph', 'missing_import', 'old_import', 'wrong_import_env', 'already_published', 'agent'])
def test_prepare_rejects_unknown_or_existing_targets(client, monkeypatch, bad):
    task, env, state = setup(client, monkeypatch)
    current = main.store.get('task', task['id'])
    if bad == 'wrong_graph': state['draft']['features']['unreviewed'] = True
    elif bad == 'missing_import': current['runs'] = []
    elif bad == 'old_import': current['runs'][0]['revision'] -= 1
    elif bad == 'wrong_import_env': current['runs'][0]['environment_id'] = 'other'
    elif bad == 'already_published': state['published'] = state['draft'] | {'id': 'existing'}
    else: current['app_type'] = 'agent'
    main.store.put('task', task['id'], current)
    r = prepare(client, task); assert r.status_code in {409, 422}, r.text
    assert writes(state) == 0


@pytest.mark.parametrize('failure', ['timeout', '401', 'invalid_json', 'mismatch', 'local_change'])
def test_possible_dispatch_is_persisted_unknown_and_never_replayed(client, monkeypatch, failure):
    task, env, state = setup(client, monkeypatch); p = prepare(client, task).json()
    if failure == 'timeout': state['post_error'] = DifyError('timeout')
    elif failure == '401': state['post_error'] = DifyError('401 already reauthenticated', http_status=401)
    elif failure == 'invalid_json': state['post_error'] = ValueError('must-not-leak-sensitive-response')
    elif failure == 'mismatch': state['post_hook'] = lambda: state['published']['graph']['nodes'][0]['data'].update(title='other-draft')
    else:
        def changed():
            current = main.store.get('task', task['id']); current['pause_generation'] = 1; current['status'] = 'paused'; main.store.put('task', task['id'], current)
        state['post_hook'] = changed
    r = confirm(client, task, p); assert r.status_code == 502, r.text
    assert 'must-not-leak' not in r.text and writes(state) == 1
    row = Store(main.store.root).get('workflow_publication', p['id']); assert row['state'] == 'unknown'
    current = client.get(f"/api/tasks/{task['id']}").json(); assert current['runs'][-1]['status'] == 'unknown'
    assert confirm(client, task, p).status_code == 409 and prepare(client, task).status_code == 409
    assert writes(state) == 1


def test_local_change_during_read_refuses_and_auto_auth_metadata_does_not(client, monkeypatch):
    task, env, state = setup(client, monkeypatch)
    def auth_metadata():
        e = main.store.get('environment', env['id']); e['console_checked_at'] = 'new'; e['console_auth_mode'] = 'password'; main.store.put('environment', env['id'], e)
    state['read_hook'] = auth_metadata
    p = prepare(client, task); assert p.status_code == 200, p.text
    def change():
        e = main.store.get('environment', env['id']); e['base_url'] = 'http://127.0.0.1:9999'; main.store.put('environment', env['id'], e)
    state['read_hook'] = change
    assert confirm(client, task, p.json()).status_code == 409 and writes(state) == 0


def test_two_confirmations_only_one_post_and_restart_marks_unknown(client, monkeypatch):
    task, env, state = setup(client, monkeypatch); p = prepare(client, task).json(); entered = threading.Event(); release = threading.Event()
    def wait(): entered.set(); assert release.wait(8)
    state['read_hook'] = wait; responses = []
    thread = threading.Thread(target=lambda: responses.append(confirm(client, task, p)))
    thread.start(); assert entered.wait(5)
    try:
        assert confirm(client, task, p).status_code == 409
        assert client.patch(f"/api/tasks/{task['id']}", json={'requirements': {'goal': 'change'}}).status_code == 409
    finally: release.set(); thread.join(10)
    assert responses[0].status_code == 200 and writes(state) == 1
    row = main.store.get('workflow_publication', p['id']); row['state'] = 'publishing'; main.store.put('workflow_publication', p['id'], row)
    current = main.store.get('task', task['id']); current['runs'][-1]['status'] = 'pending'; main.store.put('task', task['id'], current)
    main.recover_external_actions()
    assert main.store.get('workflow_publication', p['id'])['state'] == 'unknown'
    assert main.store.get('task', task['id'])['runs'][-1]['status'] == 'unknown'
    assert prepare(client, task).status_code == 409 and writes(state) == 1


def test_automatic_trigger_cannot_enter_manual_publication(client, monkeypatch):
    task, env, state = setup(client, monkeypatch)
    root = parse(main.artifact_path(task).read_text('utf-8'), 'workflow')
    root['workflow']['graph']['nodes'][0]['data']['type'] = 'trigger-webhook'
    import yaml
    main.artifact_path(task).write_text(yaml.safe_dump(root, allow_unicode=True), encoding='utf-8')
    r = prepare(client, task); assert r.status_code == 422 and writes(state) == 0
    assert not state['calls']
