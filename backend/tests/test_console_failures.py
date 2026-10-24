import asyncio
import copy
import json

import httpx
import pytest
from test_api import client
from test_dify_reauth import saved, expired
from test_login import env
from test_transports import transport_client
from app import main, dify, console_failures as failure
from app.storage import Store


@pytest.fixture(autouse=True)
def forbid_real_transport(monkeypatch):
    def forbidden(*a, **kw): pytest.fail('Diagnostic tests must not access real HTTP/model')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


@pytest.mark.parametrize('scenario,expected', [
    ('network', 'login_unreachable'), ('timeout', 'login_timeout'), ('rejected', 'login_rejected'),
    ('http403', 'login_rejected'), ('json', 'login_response_invalid'), ('cookies', 'login_cookies_invalid'),
    ('http500', 'login_service_error'), ('http502', 'login_service_error'), ('http503', 'login_service_error'),
    ('probe403', 'login_probe_failed'), ('probe_network', 'login_probe_unreachable'),
    ('probe_timeout', 'login_probe_timeout'), ('probe_json', 'login_probe_response_invalid'),
])
def test_login_failure_codes_are_specific_and_never_echo_body(monkeypatch, tmp_path, scenario, expected):
    store, target, adapter = saved(tmp_path); seen = []
    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith('/login'):
            if scenario == 'network': raise httpx.ConnectError('PRIVATE-REQUEST-DETAIL', request=request)
            if scenario == 'timeout': raise httpx.ReadTimeout('PRIVATE-TIMEOUT', request=request)
            if scenario == 'rejected': return httpx.Response(200, json={'result': 'fail', 'password': 'PRIVATE-BODY'})
            if scenario == 'http403': return httpx.Response(403, text='PRIVATE-BODY')
            if scenario in ('http500', 'http502', 'http503'): return httpx.Response(int(scenario[4:]), text='PRIVATE-BODY PRIVATE-PASSWORD')
            if scenario == 'json': return httpx.Response(200, text='PRIVATE-BODY')
            headers = [] if scenario == 'cookies' else [('set-cookie', 'access_token=new-access; Path=/'), ('set-cookie', 'csrf_token=new-csrf; Path=/')]
            return httpx.Response(200, json={'result': 'success'}, headers=headers)
        assert request.url.path == '/console/api/apps'
        if scenario == 'probe403': return httpx.Response(403, text='PRIVATE-BODY')
        if scenario == 'probe_network': raise httpx.ConnectError('PRIVATE-REQUEST-DETAIL', request=request)
        if scenario == 'probe_timeout': raise httpx.ReadTimeout('PRIVATE-TIMEOUT', request=request)
        return httpx.Response(200, text='PRIVATE-BODY')
    transport_client(monkeypatch, dify, handler)
    with pytest.raises(dify.DifyError) as err: asyncio.run(adapter.login('PRIVATE-EMAIL@test.local', 'PRIVATE-PASSWORD'))
    assert err.value.code == expected and 'PRIVATE' not in str(err.value)
    assert store.secret('env', 'console_token') == expired()
    assert len(seen) == (2 if scenario.startswith('probe') else 1)


@pytest.mark.parametrize('scenario,expected', [('network', 'workspace_unreachable'), ('timeout', 'workspace_timeout'), ('http', 'workspace_probe_failed'), ('json', 'workspace_response_invalid'), ('missing', 'workspace_response_invalid')])
def test_workspace_failure_codes_do_not_collapse_to_generic(monkeypatch, tmp_path, scenario, expected):
    store, target, adapter = saved(tmp_path)
    def handler(request):
        if scenario == 'network': raise httpx.ConnectError('PRIVATE-REQUEST-DETAIL', request=request)
        if scenario == 'timeout': raise httpx.ReadTimeout('PRIVATE-TIMEOUT', request=request)
        if scenario == 'http': return httpx.Response(403, text='PRIVATE-BODY')
        if scenario == 'json': return httpx.Response(200, text='PRIVATE-BODY')
        return httpx.Response(200, json={'PRIVATE': 'BODY'})
    transport_client(monkeypatch, dify, handler)
    with pytest.raises(dify.DifyError) as err: asyncio.run(adapter.login_workspace({'console_token': 'PRIVATE-TOKEN', 'csrf_token': 'PRIVATE-CSRF'}))
    assert err.value.code == expected and 'PRIVATE' not in str(err.value)


def test_auto_failure_persists_safe_cause_and_stays_paused_after_restart(monkeypatch, tmp_path):
    store, target, adapter = saved(tmp_path); calls = []
    async def fail(self, email, password):
        calls.append(1); raise dify.DifyError('PRIVATE-PASSWORD PRIVATE-EMAIL PRIVATE-TOKEN', code='login_unreachable')
    monkeypatch.setattr(dify.DifyClient, 'login', fail)
    for _ in range(2):
        with pytest.raises(dify.DifyError): asyncio.run(adapter.test())
    current = Store(tmp_path).get('environment', 'env'); row = Store(tmp_path).get(failure.KIND, current['console_failure_id'])
    assert calls == [1] and current['console_login_blocked'] and row['code'] == 'login_unreachable'
    assert not any('PRIVATE' in json.dumps(r) for r in store.list(failure.KIND))
    public = failure.public(store, current); assert public['code'] == 'login_unreachable' and not public['automatic_retry']
    assert store.secret('env', 'console_token') == expired() and store.secret('env', 'service_api_key') == 'independent-service'


def test_failure_for_changed_connection_kept_without_mutating_current_state(tmp_path):
    store, target, _ = saved(tmp_path); current = copy.deepcopy(target); current['base_url'] = 'http://changed.test'; current['connection_revision'] = 'r2'; store.put('environment', 'env', current)
    row = failure.record(store, target, dify.DifyError('PRIVATE', code='login_timeout'), automatic=True)
    assert store.get('environment', 'env') == current and store.get(failure.KIND, row['id'])['code'] == 'login_timeout'
    assert failure.public(store, current) is None


def test_manual_failure_keeps_entire_original_connection_and_records_safe_cause(client, monkeypatch):
    target = env(client, console_token='old-access', csrf_token='old-csrf'); before = main.store.get('environment', target['id'])
    async def fail(*a): raise dify.DifyError('PRIVATE-PASSWORD', code='login_rejected', http_status=403)
    monkeypatch.setattr(dify.DifyClient, 'login', fail)
    r = client.post(f"/api/environments/{target['id']}/login", json={'email': 'PRIVATE@test.local', 'password': 'PRIVATE-PASSWORD'})
    assert r.status_code == 502 and r.headers['X-Sierra-Dify-Code'] == 'login_rejected' and 'PRIVATE' not in r.text
    assert main.store.get('environment', target['id']) == before
    rows = main.store.list(failure.KIND); assert len(rows) == 1 and rows[0]['mode'] == 'manual' and rows[0]['http_status'] == 403
    assert 'PRIVATE' not in json.dumps(rows)


def test_legacy_pause_is_explicitly_unknown_not_guessed(client):
    target = env(client); current = main.store.get('environment', target['id']); current['console_login_blocked'] = True; main.store.put('environment', target['id'], current)
    result = client.get('/api/environments').json()[0]['console_connection']['failure']
    assert result['code'] == 'legacy_unclassified' and result['occurred_at'] is None and not result['automatic_retry']


def test_corrupt_diagnostic_never_exposes_untrusted_strings_or_invalid_status(client):
    target = env(client); original = main.store.get('environment', target['id'])
    row = failure.record(main.store, original, dify.DifyError('PRIVATE', code='login_timeout'), automatic=True)
    row.update(code='PRIVATE-CODE', message='PRIVATE-BODY', next_action='PRIVATE-EMAIL', occurred_at='PRIVATE-TOKEN', http_status='PRIVATE-STATUS', mode='PRIVATE-MODE')
    main.store.put(failure.KIND, row['id'], row)
    r = client.get('/api/environments'); assert 'PRIVATE' not in r.text and 'console_failure_id' not in r.text
    value = r.json()[0]['console_connection']['failure']; assert value['code'] == 'unclassified' and value['http_status'] is None


def test_manual_success_clears_current_hint_but_not_history(client, monkeypatch):
    target = env(client); original = main.store.get('environment', target['id']); row = failure.record(main.store, original, dify.DifyError('PRIVATE', code='login_timeout'), automatic=True)
    async def login(*a): return {'console_token': 'new-access', 'csrf_token': 'new-csrf'}
    monkeypatch.setattr(dify.DifyClient, 'login', login)
    r = client.post(f"/api/environments/{target['id']}/login", json={'email': 'user@test.local', 'password': 'password'})
    assert r.status_code == 200 and r.json()['environment']['console_connection']['failure'] is None
    assert main.store.get(failure.KIND, row['id'])['code'] == 'login_timeout'


def test_diagnostic_only_changes_do_not_fake_connection_identity_drift(client):
    target = env(client); original = main.store.get('environment', target['id']); before = main.env_snapshot(original)
    failure.record(main.store, original, dify.DifyError('PRIVATE', code='login_timeout'), automatic=True)
    assert main.env_snapshot(main.store.get('environment', target['id'])) == before


def test_publication_prepare_keeps_safe_machine_diagnostic_without_writes(client, monkeypatch):
    from test_workflow_publication import setup
    task, target, state = setup(client, monkeypatch)
    async def fail(*a, **kw): raise dify.DifyError('PRIVATE-RESPONSE', code='login_unreachable')
    monkeypatch.setattr(dify.DifyClient, 'request', fail)
    r = client.post(f"/api/tasks/{task['id']}/workflow-publication/prepare", json={'revision': task['revision']})
    assert r.status_code == 502 and r.headers['X-Sierra-Dify-Code'] == 'login_unreachable'
    assert 'login_unreachable' in r.json()['detail'] and 'PRIVATE' not in r.text
    assert not main.store.list('workflow_publication') and not state['calls']


@pytest.mark.parametrize('bad_pointer', [None, {'PRIVATE': 'BODY'}, ['PRIVATE']])
def test_invalid_diagnostic_pointer_is_legacy_unknown_not_a_crash(client, bad_pointer):
    target = env(client); current = main.store.get('environment', target['id']); current['console_failure_id'] = bad_pointer; current['console_login_blocked'] = True; main.store.put('environment', target['id'], current)
    r = client.get('/api/environments'); assert r.status_code == 200 and 'PRIVATE' not in r.text
    assert r.json()[0]['console_connection']['failure']['code'] == 'legacy_unclassified'
