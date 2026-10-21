import copy
import asyncio
import uuid
import pytest
from test_api import client, forbid_api_external_calls
from test_workflow_publication import setup
from app import main
from app.dify import DifyError
from app.storage import Store

KEY = 'app-ISOLATED-CREATED-ONLY'
KEY_ID = '0e826f41-e872-4367-b35a-a102f8b891fd'
SPACE = 'isolated-original-workspace'


def ready(client, monkeypatch):
    task, env, _ = setup(client, monkeypatch)
    e = main.store.get('environment', env['id']); e['console_workspace_id'] = SPACE
    main.store.put_with_secrets('environment', env['id'], e, {'service_api_key': 'app-PREVIOUS-ISOLATED', 'dataset_api_key': 'dataset-isolated'})
    state = {'calls': [], 'created': False}
    async def request(self, method, path, **kwargs):
        state['calls'].append((method, path))
        if state.get('hook'): await asyncio.to_thread(state['hook'], method, path)
        if path.endswith('/workspaces/current/summary'): return {'id': state.get('workspace', SPACE)}
        if path.endswith('/api-keys'):
            if method == 'POST':
                assert kwargs['json'] == {}; state['created'] = True
                if state.get('post_error'): raise state['post_error']
                if state.get('after_post'): state['after_post']()
                return state.get('result', {'id': KEY_ID, 'token': KEY})
            if state['created']: return state.get('after', {'data': [{'id': KEY_ID, 'token': KEY}]})
            return state.get('before', {'data': []})
        return {'id': state.get('app', task['dify_app_id']), 'mode': state.get('mode', task['app_type'])}
    monkeypatch.setattr(main.DifyClient, 'request', request)
    return task, e, state


def plan(client, task): return client.post(f"/api/tasks/{task['id']}/runtime-key-creation/plan", json={'revision': task['revision']})


def confirm(client, task, p, **changes):
    return client.post(f"/api/tasks/{task['id']}/runtime-key-creation/confirm", json={'revision': task['revision'], 'proposal_id': p['id'], 'review_token': p['review_token'], 'confirm_create_and_bind': True} | changes)


def writes(s): return sum(m == 'POST' for m, _ in s['calls'])


def ciphers():
    with main.store.connect() as db: return dict(db.execute('SELECT id,value FROM secrets'))


def test_explicit_create_atomic_archive_binding_and_old_key_preservation(client, monkeypatch):
    t, e, s = ready(client, monkeypatch); original = main.store.get('task', t['id']); before = ciphers()
    p = plan(client, t); assert p.status_code == 200, p.text
    p = p.json(); assert not s['calls'] and not p['write_attempted'] and p['shared_environment_tasks'] == 1
    assert 'binding' not in p and 'fingerprint' not in str(p)
    r = confirm(client, t, p); assert r.status_code == 200, r.text
    assert r.json()['state'] == 'succeeded' and not r.json()['business_verified'] and KEY not in r.text
    assert writes(s) == 1 and len(s['calls']) == 5
    assert main.store.get('task', t['id']) == original
    current = main.store.get('environment', e['id']); assert current['service_app_id'] == t['dify_app_id'] and current['connection_revision'] != e['connection_revision']
    owner = e['id'] + ':app-runtime:' + t['dify_app_id']
    archive = main.store.get('app_runtime_credential', owner); assert archive['workspace_id'] == SPACE and archive['key_id'] == KEY_ID
    assert main.store.secret(owner, 'service_api_key') == main.store.secret(e['id'], 'service_api_key') == KEY
    assert main.store.secret(p['id'] + ':previous-runtime-key', 'service_api_key') == 'app-PREVIOUS-ISOLATED'
    assert main.store.get('runtime_key_previous_binding', p['id'] + ':previous-runtime-key')['origin_verified'] is False
    for k, v in before.items():
        if k != e['id'] + ':service_api_key': assert ciphers()[k] == v
    assert KEY.encode() not in main.store.path.read_bytes()
    assert confirm(client, t, p).status_code == 409 and plan(client, t).status_code == 409 and writes(s) == 1
    history = client.get(f"/api/tasks/{t['id']}/runtime-key-creations"); assert history.status_code == 200 and KEY not in history.text
    assert Store(main.store.root).get('app_runtime_key_creation', p['id'])['state'] == 'succeeded'


@pytest.mark.parametrize('change', ['revision', 'artifact', 'app', 'workspace', 'url', 'key', 'shared', 'pause', 'confirmation', 'missing_import', 'expired', 'token', 'ack'])
def test_stale_or_unapproved_proposal_never_dispatches(client, monkeypatch, change):
    t, e, s = ready(client, monkeypatch); p = plan(client, t).json(); task = main.store.get('task', t['id']); overrides = {}
    if change == 'revision': task['revision'] += 1
    elif change == 'artifact': main.artifact_path(task).write_bytes(main.artifact_path(task).read_bytes() + b'\n#edit')
    elif change == 'app': task['dify_app_id'] = str(uuid.uuid4())
    elif change == 'workspace': e['console_workspace_id'] = 'changed'
    elif change == 'url': e['base_url'] = 'http://127.0.0.1:9999'
    elif change == 'key': main.store.set_secret(e['id'], 'service_api_key', 'app-CHANGED-BY-USER')
    elif change == 'shared':
        other = copy.deepcopy(task); other['id'] = 'shared-new-task'; main.store.put('task', other['id'], other)
    elif change == 'pause': task['pause_generation'] = 1; task['status'] = 'paused'
    elif change == 'confirmation': task['configuration_confirmed'] = False
    elif change == 'missing_import': task['runs'] = []
    elif change == 'expired':
        row = main.store.get('app_runtime_key_creation', p['id']); row['expires_at'] = 0; main.store.put('app_runtime_key_creation', p['id'], row)
    elif change == 'token': overrides['review_token'] = 'wrong'
    else: overrides['confirm_create_and_bind'] = False
    main.store.put('task', task['id'], task); main.store.put('environment', e['id'], e); before = ciphers()
    r = confirm(client, t, p, **overrides); assert r.status_code in {404, 409}, r.text
    assert not s['calls'] and ciphers() == before


@pytest.mark.parametrize('bad', ['workspace', 'app', 'mode', 'before', 'malformed_keys'])
def test_remote_identity_or_existing_keys_stop_before_create(client, monkeypatch, bad):
    t, e, s = ready(client, monkeypatch); p = plan(client, t).json(); before = ciphers()
    if bad in {'workspace', 'app', 'mode'}: s[bad] = 'different'
    elif bad == 'before': s['before'] = {'data': [{'id': KEY_ID, 'token': 'app-EXISTING-ONLY'}]}
    else: s['before'] = {'data': 'malformed'}
    r = confirm(client, t, p); assert r.status_code in {409, 502} and writes(s) == 0
    assert ciphers() == before and main.store.get('environment', e['id']) == e
    assert main.store.get('app_runtime_key_creation', p['id'])['state'] == 'failed'
    assert confirm(client, t, p).status_code == 409


@pytest.mark.parametrize('error', ['timeout', 'malformed_result', 'wrong_list', 'race', 'changed_local'])
def test_possible_dispatch_becomes_unknown_and_cannot_replay(client, monkeypatch, error):
    t, e, s = ready(client, monkeypatch); p = plan(client, t).json(); before = ciphers()
    if error == 'timeout': s['post_error'] = DifyError('LEAK-ME private response')
    elif error == 'malformed_result': s['result'] = {'id': KEY_ID, 'token': 'LEAK-ME invalid key'}
    elif error == 'wrong_list': s['after'] = {'data': []}
    elif error == 'race': s['after'] = {'data': [{'id': KEY_ID, 'token': KEY}, {'id': str(uuid.uuid4()), 'token': 'app-EXTERNAL-RACE'}]}
    else:
        def change():
            task = main.store.get('task', t['id']); task['pause_generation'] = 1; main.store.put('task', t['id'], task)
        s['after_post'] = change
    r = confirm(client, t, p); assert r.status_code == 502 and 'LEAK-ME' not in r.text and KEY not in r.text
    assert writes(s) == 1 and ciphers() == before
    assert main.store.get('app_runtime_key_creation', p['id'])['state'] == 'unknown'
    assert confirm(client, t, p).status_code == 409 and plan(client, t).status_code == 409 and writes(s) == 1


@pytest.mark.parametrize('stage', ['archive', 'last_secret'])
def test_atomic_sql_failure_keeps_original_binding_and_no_partial_archive(client, monkeypatch, stage):
    t, e, s = ready(client, monkeypatch); p = plan(client, t).json(); before = ciphers()
    with main.store.connect() as db:
        if stage == 'archive': db.execute("CREATE TRIGGER fail_archive BEFORE INSERT ON objects WHEN NEW.kind='app_runtime_credential' BEGIN SELECT RAISE(ABORT,'isolated'); END")
        else: db.execute("CREATE TRIGGER fail_secret BEFORE INSERT ON secrets WHEN NEW.id='" + e['id'] + ":service_api_key' BEGIN SELECT RAISE(ABORT,'isolated'); END")
    r = confirm(client, t, p); assert r.status_code == 502 and writes(s) == 1
    assert ciphers() == before and main.store.get('environment', e['id']) == e
    assert not main.store.list('app_runtime_credential') and not main.store.list('runtime_key_previous_binding')
    assert main.store.get('app_runtime_key_creation', p['id'])['state'] == 'unknown'


def test_restart_recovers_without_network_or_retry(client, monkeypatch):
    t, e, s = ready(client, monkeypatch); p = plan(client, t).json(); row = main.store.get('app_runtime_key_creation', p['id'])
    row.update(state='creating', write_attempted=True); main.store.put('app_runtime_key_creation', row['id'], row)
    main.app_runtime_key_creation_recover()
    assert main.store.get('app_runtime_key_creation', row['id'])['state'] == 'unknown' and not s['calls']
    assert plan(client, t).status_code == 409


def test_inflight_creation_blocks_task_edit_login_manual_key_and_other_confirm(client, monkeypatch):
    t, e, s = ready(client, monkeypatch); p = plan(client, t).json(); other = plan(client, t).json(); seen = []
    def hook(method, path):
        if seen: return
        seen.append(True)
        assert client.patch(f"/api/tasks/{t['id']}", json={'name': 'blocked'}).status_code == 409
        assert client.post(f"/api/environments/{e['id']}/login", json={'email': 'isolated@example.invalid', 'password': 'isolated-only'}).status_code == 409
        assert client.post(f"/api/environments/{e['id']}/saved-login/reconnect-plan", json={}).status_code == 409
        assert confirm(client, t, other).status_code == 409
    s['hook'] = hook
    assert confirm(client, t, p).status_code == 200 and writes(s) == 1


def test_committed_success_not_rewritten_when_response_formatter_fails(client, monkeypatch):
    from app import app_runtime_key_creation as module
    t, e, s = ready(client, monkeypatch); p = plan(client, t).json()
    original = module.public
    def broken(row):
        if row['state'] == 'succeeded': raise RuntimeError('isolated formatting failure')
        return original(row)
    monkeypatch.setattr(module, 'public', broken)
    with pytest.raises(RuntimeError): confirm(client, t, p)
    assert main.store.get('app_runtime_key_creation', p['id'])['state'] == 'succeeded'
    assert main.store.secret(e['id'], 'service_api_key') == KEY and writes(s) == 1


@pytest.mark.parametrize('case', ['expired_before', 'write_401', 'bad_response'])
def test_real_adapter_mock_transport_authentication_and_no_write_replay(client, monkeypatch, forbid_api_external_calls, case):
    import httpx
    from app import dify
    from test_transports import transport_client
    from test_dify_reauth import expired
    t, e, s = ready(client, monkeypatch)
    e['console_login_binding'] = {'base_url': e['base_url'], 'version': e['version'], 'workspace_id': SPACE}
    main.store.put_with_secrets('environment', e['id'], e, {'console_token': expired() if case == 'expired_before' else 'isolated-token', 'console_login_email': 'isolated@example.invalid', 'console_login_password': 'ISOLATED-PASSWORD'})
    monkeypatch.setattr(main.DifyClient, 'request', forbid_api_external_calls)
    seen = []; created = []; logins = []
    def handler(req):
        seen.append((req.method, req.url.path))
        if req.url.path.endswith('/login'):
            logins.append(1)
            return httpx.Response(200, json={'result': 'success'}, headers=[('set-cookie', 'access_token=isolated-new-access; Path=/'), ('set-cookie', 'csrf_token=isolated-new-csrf; Path=/')])
        if req.url.path.endswith('/apps'): return httpx.Response(200, json={'data': []})
        if req.url.path.endswith('/workspaces/current/summary'):
            if case == 'bad_response': return httpx.Response(200, text='LEAK-ME not json')
            return httpx.Response(200, json={'id': SPACE})
        if req.url.path.endswith('/api-keys'):
            if req.method == 'POST':
                created.append(1)
                if case == 'write_401': return httpx.Response(401, json={'error': 'LEAK-ME'})
                assert req.headers['authorization'] == 'Bearer isolated-new-access'
                return httpx.Response(201, json={'id': KEY_ID, 'token': KEY})
            return httpx.Response(200, json={'data': [{'id': KEY_ID, 'token': KEY}] if created else []})
        return httpx.Response(200, json={'id': t['dify_app_id'], 'mode': 'workflow'})
    transport_client(monkeypatch, dify, handler)
    p = plan(client, t).json(); r = confirm(client, t, p)
    assert 'LEAK-ME' not in r.text and 'ISOLATED-PASSWORD' not in r.text and KEY not in r.text
    if case == 'expired_before':
        assert r.status_code == 200, r.text
        assert len(logins) == len(created) == 1 and len(seen) == 8
        assert main.store.secret(e['id'], 'service_api_key') == KEY
    else:
        assert r.status_code == 502 and len(created) == (1 if case == 'write_401' else 0)
        row = main.store.get('app_runtime_key_creation', p['id'])
        assert row['state'] == ('unknown' if case == 'write_401' else 'failed')
        assert main.store.secret(e['id'], 'service_api_key') == 'app-PREVIOUS-ISOLATED'
        assert confirm(client, t, p).status_code == 409


def test_source_type_limit_and_missing_workspace_are_local_only(client, monkeypatch):
    t, e, s = ready(client, monkeypatch)
    task = main.store.get('task', t['id']); task['app_type'] = 'agent'; main.store.put('task', t['id'], task)
    r = plan(client, task); assert r.status_code == 422 and 'Agent' in r.text
    assert main.store.get('task', t['id'])['app_type'] == 'agent' and not s['calls']
    task['app_type'] = 'workflow'; main.store.put('task', t['id'], task); e.pop('console_workspace_id'); main.store.put('environment', e['id'], e)
    assert plan(client, task).status_code == 409 and not s['calls']
