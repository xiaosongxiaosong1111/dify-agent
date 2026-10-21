import asyncio
import copy
import json
import threading

import httpx
import pytest
from test_api import client, create
from test_login import env
from test_transports import transport_client
from app import main, dify, saved_console_reconnect as reconnect
from app.console_reauth import EMAIL, PASSWORD, BINDING
from app.storage import Store


@pytest.fixture(autouse=True)
def forbid_external(monkeypatch):
    def forbidden(*a, **kw): pytest.fail('Saved reconnect tests forbid real HTTP/model')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def setup(client, monkeypatch):
    target = env(client); current = main.store.get('environment', target['id'])
    current.update(console_workspace_id='workspace-test', console_login_blocked=True)
    current[BINDING] = {'base_url': current['base_url'], 'version': current['version'], 'workspace_id': 'workspace-test'}
    main.store.put_with_secrets('environment', current['id'], current, {EMAIL: 'private@test.local', PASSWORD: 'PRIVATE-PASSWORD', 'console_token': 'old-access', 'csrf_token': 'old-csrf', 'service_api_key': 'independent-service', 'dataset_api_key': 'independent-dataset'})
    calls = []
    async def login(self, email, password):
        assert email == 'private@test.local' and password == 'PRIVATE-PASSWORD'; calls.append('login')
        return {'console_token': 'new-access', 'csrf_token': 'new-csrf'}
    async def workspace(self, tokens): calls.append('workspace'); return 'workspace-test'
    monkeypatch.setattr(dify.DifyClient, 'login', login); monkeypatch.setattr(dify.DifyClient, 'login_workspace', workspace)
    return current, calls


def prepare(client, target): return client.post(f"/api/environments/{target['id']}/saved-login/reconnect-plan", json={})


def confirm(client, target, plan, **changes):
    return client.post(f"/api/environments/{target['id']}/saved-login/reconnect", json={'plan_id': plan['id'], 'review_token': plan['review_token'], 'confirm_reconnect': True} | changes)


def cipher_rows():
    with main.store.connect() as db: return dict(db.execute('SELECT id,value FROM secrets'))


def test_prepare_is_local_and_one_explicit_confirm_only_updates_management_tokens(client, monkeypatch):
    target, calls = setup(client, monkeypatch); before = cipher_rows(); original = main.env_snapshot(target)
    r = prepare(client, target); assert r.status_code == 200 and not calls
    p = r.json(); assert p['console_reads'] == 2 and p['login_posts'] == 1 and not p['attempted'] and 'binding' not in p and 'PRIVATE' not in r.text
    r = confirm(client, target, p); assert r.status_code == 200, r.text
    assert calls == ['login', 'workspace'] and r.json()['record']['state'] == 'succeeded' and not r.json()['record']['original_operation_replayed']
    assert 'private@test.local' not in r.text and 'new-access' not in r.text and 'new-csrf' not in r.text
    current = main.store.get('environment', target['id']); assert not current.get('console_login_blocked') and main.env_snapshot(current) == original
    for k, value in before.items():
        if k not in {target['id'] + ':console_token', target['id'] + ':csrf_token'}: assert cipher_rows()[k] == value
    assert confirm(client, target, p).status_code == 409 and calls == ['login', 'workspace']
    assert Store(main.store.root).get(reconnect.KIND, p['id'])['state'] == 'succeeded'


@pytest.mark.parametrize('change', ['host', 'version', 'workspace', 'revision', 'password', 'email', 'token', 'forget', 'expiry'])
def test_changed_profile_or_credentials_rejects_before_login(client, monkeypatch, change):
    target, calls = setup(client, monkeypatch); p = prepare(client, target).json(); current = main.store.get('environment', target['id'])
    if change == 'host': current['base_url'] = 'http://other.test'
    elif change == 'version': current['version'] = 'future'
    elif change == 'workspace': current['console_workspace_id'] = 'other-space'
    elif change == 'revision': current['connection_revision'] = 'other-revision'
    elif change in {'password', 'email', 'token'}:
        name = {'password': PASSWORD, 'email': EMAIL, 'token': 'console_token'}[change]
        main.store.set_secret(target['id'], name, 'PRIVATE-CHANGED')
    elif change == 'forget': current.pop(BINDING)
    else:
        row = main.store.get(reconnect.KIND, p['id']); row['expires_at'] = 0; main.store.put(reconnect.KIND, p['id'], row)
    main.store.put('environment', target['id'], current); before = cipher_rows()
    r = confirm(client, target, p); assert r.status_code in {409, 422}, r.text
    assert not calls and cipher_rows() == before


@pytest.mark.parametrize('bad', [False, 1, 'true', None])
def test_confirm_requires_real_boolean_and_does_not_echo_input(client, monkeypatch, bad):
    target, calls = setup(client, monkeypatch); p = prepare(client, target).json()
    r = confirm(client, target, p, confirm_reconnect=bad); assert r.status_code == 422 and not calls
    r = client.post(f"/api/environments/{target['id']}/saved-login/reconnect", json={'password': 'PRIVATE-PASSWORD'})
    assert r.status_code == 422 and 'PRIVATE' not in r.text and not calls


@pytest.mark.parametrize('failure', ['login', 'space', 'corrupt_cipher'])
def test_failure_preserves_credentials_records_cause_and_invalidates_old_plans(client, monkeypatch, failure):
    target, calls = setup(client, monkeypatch)
    if failure == 'corrupt_cipher':
        with main.store.connect() as db: db.execute('UPDATE secrets SET value=? WHERE id=?', (b'PRIVATE-BROKEN-CIPHER', target['id'] + ':' + PASSWORD))
    p = prepare(client, target).json(); other = prepare(client, target).json(); before = cipher_rows()
    if failure == 'login':
        async def fail(*a): calls.append('login'); raise dify.DifyError('PRIVATE-BODY', code='login_timeout')
        monkeypatch.setattr(dify.DifyClient, 'login', fail)
    elif failure == 'space':
        async def mismatch(*a): calls.append('workspace'); return 'wrong-workspace'
        monkeypatch.setattr(dify.DifyClient, 'login_workspace', mismatch)
    r = confirm(client, target, p); assert r.status_code == 502 and 'PRIVATE' not in r.text and 'wrong-workspace' not in r.text
    assert cipher_rows() == before and not reconnect.busy(main.store, target['id'])
    row = main.store.get(reconnect.KIND, p['id']); assert row['state'] == 'failed' and row['diagnostic_code'] in {'login_timeout', 'workspace_mismatch', 'unclassified'}
    assert main.env_public(main.store.get('environment', target['id']))['console_connection']['failure']['mode'] == 'saved_reconnect'
    count = len(calls); assert confirm(client, target, other).status_code == 409 and len(calls) == count


def test_environment_change_while_login_inflight_does_not_commit_or_replay(client, monkeypatch):
    target, calls = setup(client, monkeypatch); p = prepare(client, target).json(); entered = threading.Event(); release = threading.Event()
    async def wait(self, email, password):
        calls.append('login'); entered.set(); await asyncio.to_thread(release.wait, 8)
        return {'console_token': 'new-access', 'csrf_token': 'new-csrf'}
    monkeypatch.setattr(dify.DifyClient, 'login', wait); results = []
    thread = threading.Thread(target=lambda: results.append(confirm(client, target, p))); thread.start(); assert entered.wait(5)
    try:
        assert prepare(client, target).status_code == 409
        assert client.patch(f"/api/environments/{target['id']}", json={'name': 'change'}).status_code == 409
        assert client.delete(f"/api/environments/{target['id']}/saved-login").status_code == 200
    finally: release.set(); thread.join(10)
    assert results[0].status_code == 502 and main.store.secret(target['id'], 'console_token') == 'old-access'
    assert not main.store.has_secret(target['id'], PASSWORD) and not reconnect.busy(main.store, target['id'])


def test_busy_reconnect_blocks_task_and_snapshot_console_dispatch(client, monkeypatch):
    from app.schedule_observation import CredentialSnapshot
    target, calls = setup(client, monkeypatch); task = create(client, env_id=target['id']); p = prepare(client, target).json()
    row = main.store.get(reconnect.KIND, p['id']); row.update(state='executing', attempted=True); main.store.put(reconnect.KIND, p['id'], row)
    assert client.patch(f"/api/tasks/{task['id']}", json={'requirements': {'goal': 'change'}}).status_code == 409
    snapshot = CredentialSnapshot(main.store, target['id']); adapter = dify.DifyClient(target, snapshot)
    with pytest.raises(dify.DifyError) as err: asyncio.run(adapter.test())
    assert err.value.code == 'reconnect_in_progress' and not calls


def test_startup_recovers_unknown_without_reauthentication_or_credential_changes(client, monkeypatch):
    target, calls = setup(client, monkeypatch); p = prepare(client, target).json(); before = cipher_rows()
    row = main.store.get(reconnect.KIND, p['id']); row.update(state='executing', attempted=True); main.store.put(reconnect.KIND, p['id'], row)
    main.saved_console_reconnect_recover()
    assert not calls and cipher_rows() == before
    assert main.store.get(reconnect.KIND, p['id'])['state'] == 'unknown' and main.store.get('environment', target['id'])['console_login_blocked']
    assert confirm(client, target, p).status_code == 409


def test_receipt_and_tokens_are_one_transaction_on_database_failure(client, monkeypatch):
    target, calls = setup(client, monkeypatch); p = prepare(client, target).json(); before = cipher_rows()
    with main.store.connect() as db:
        db.execute("CREATE TRIGGER reject_success BEFORE UPDATE ON objects WHEN NEW.kind='saved_console_reconnect' AND json_extract(NEW.value,'$.state')='succeeded' BEGIN SELECT RAISE(ABORT, 'PRIVATE-SQL-FAILURE'); END")
    r = confirm(client, target, p); assert r.status_code == 502 and 'PRIVATE' not in r.text
    assert cipher_rows() == before and main.store.secret(target['id'], 'console_token') == 'old-access'
    assert main.store.get(reconnect.KIND, p['id'])['state'] == 'failed'


def test_transport_path_is_exactly_one_login_and_two_identity_reads(client, monkeypatch):
    real_login = dify.DifyClient.login; real_workspace = dify.DifyClient.login_workspace
    target, calls = setup(client, monkeypatch)
    monkeypatch.setattr(dify.DifyClient, 'login', real_login); monkeypatch.setattr(dify.DifyClient, 'login_workspace', real_workspace)
    # Restore real adapter methods only; all actual I/O goes through MockTransport.
    paths = []
    def handler(request):
        paths.append((request.method, request.url.path))
        if request.url.path.endswith('/login'):
            return httpx.Response(200, json={'result': 'success'}, headers=[('set-cookie', 'access_token=fresh; Path=/'), ('set-cookie', 'csrf_token=fresh-csrf; Path=/')])
        if request.url.path.endswith('/apps'): return httpx.Response(200, json={'data': []})
        if request.url.path.endswith('/summary'): return httpx.Response(200, json={'id': 'workspace-test'})
        pytest.fail('Unexpected remote path')
    transport_client(monkeypatch, dify, handler)
    p = prepare(client, target).json(); r = confirm(client, target, p); assert r.status_code == 200, r.text
    assert paths == [('POST', '/console/api/login'), ('GET', '/console/api/apps'), ('GET', '/console/api/workspaces/current/summary')]


def test_response_format_failure_does_not_claim_committed_tokens_rolled_back(client, monkeypatch):
    target, calls = setup(client, monkeypatch); p = prepare(client, target).json()
    def fail(*a): raise RuntimeError('controlled response formatter failure')
    monkeypatch.setattr(main, 'env_public', fail)
    with pytest.raises(RuntimeError, match='controlled'): confirm(client, target, p)
    assert main.store.get(reconnect.KIND, p['id'])['state'] == 'succeeded'
    assert main.store.secret(target['id'], 'console_token') == 'new-access' and not reconnect.busy(main.store, target['id'])


def test_history_is_current_origin_scoped_and_diagnostic_text_is_allowlisted(client, monkeypatch):
    target, calls = setup(client, monkeypatch); p = prepare(client, target).json()
    old = copy.deepcopy(main.store.get(reconnect.KIND, p['id'])); old['id'] = 'old-origin-row'; old['base_url'] = 'http://other.test'; main.store.put(reconnect.KIND, old['id'], old)
    current = main.store.get(reconnect.KIND, p['id']); current.update(state='failed', diagnostic_code='PRIVATE-DETAIL'); main.store.put(reconnect.KIND, p['id'], current)
    r = client.get(f"/api/environments/{target['id']}/saved-login/reconnections")
    assert r.status_code == 200 and len(r.json()['records']) == 1 and 'PRIVATE' not in r.text and 'other.test' not in r.text
    assert r.json()['records'][0]['diagnostic_code'] == 'unclassified' and not calls


def test_prepare_never_accepts_or_echoes_supplied_credentials(client, monkeypatch):
    target, calls = setup(client, monkeypatch)
    r = client.post(f"/api/environments/{target['id']}/saved-login/reconnect-plan", json={'email': 'PRIVATE@test.local', 'password': 'PRIVATE-PASSWORD'})
    assert r.status_code == 422 and 'PRIVATE' not in r.text and not calls and not main.store.list(reconnect.KIND)
