"""Task 349: origin and credential must come from one approved source generation."""
import asyncio
import base64
import copy
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from test_api import client  # noqa: F401 - shared live Store/app fixture
from test_transports import transport_client
from app import dify, main
from app.schedule_observation import CredentialSnapshot
from app.storage import Store


def expired():
    payload = base64.urlsafe_b64encode(b'{"exp":1}').decode().rstrip('=')
    return 'eyJ0eXAiOiJKV1QifQ.' + payload + '.c2ln'


def new_env(client, **extra):
    response = client.post('/api/environments', json={
        'name': '凭据快照测试', 'base_url': 'http://dify.test', 'version': '1.17.1', **extra})
    assert response.status_code == 201, response.text
    return response.json()


def capture(monkeypatch, seen):
    transport_client(monkeypatch, dify, lambda request: seen.append(request) or httpx.Response(200, json={'data': []}))


def test_concurrent_origin_and_token_change_never_mixes_new_key_with_old_url(client, monkeypatch):
    target = new_env(client, console_token='old-token', csrf_token='old-csrf')
    env_id, revision = target['id'], target['connection_revision']
    seen = []
    capture(monkeypatch, seen)
    original = main.store.secret
    first, edited = threading.Event(), threading.Event()
    def secret(owner, key):
        if owner == env_id and key == 'console_token' and not first.is_set():
            first.set()
            # Bounded chance for the editor portal to finish its PATCH while this
            # credential read is in flight; correctness is judged from the wire.
            edited.wait(1.0)
        return original(owner, key)
    monkeypatch.setattr(main.store, 'secret', secret)
    results = []
    thread = threading.Thread(target=lambda: results.append(client.post(f"/api/environments/{env_id}/test", json={})))
    thread.start()
    assert first.wait(5)
    # The first request's event loop is blocked inside the hook, so the edit must
    # run on a second portal rather than being starved by it.
    second = TestClient(main.app)
    try:
        patched = second.patch(f"/api/environments/{env_id}", json={
            'base_url': 'http://other.test', 'console_token': 'new-token',
            'csrf_token': 'new-csrf', 'expected_connection_revision': revision})
    finally:
        edited.set()
        thread.join(20)
        second.close()
    assert not thread.is_alive() and patched.status_code == 200, patched.text
    assert results, 'GET test did not return'
    assert results[0].status_code in (200, 409, 502), results[0].text
    assert len(seen) <= 1
    for request in seen:
        key = request.headers['authorization'].split(' ', 1)[1]
        cookie = request.headers.get('cookie', '')
        # A dispatched request must be the coherent old pair, never the new one.
        assert request.url.host == 'dify.test' and key == 'old-token'
        assert 'csrf_token=old-csrf' in cookie and 'new-csrf' not in cookie


def test_stale_and_deleted_managed_environment_reject_before_secret_or_network(client, monkeypatch):
    target = new_env(client, console_token='old-token', csrf_token='old-csrf',
                     service_api_key='old-service', dataset_api_key='old-dataset')
    env_id = target['id']
    stale = dify.DifyClient(target, main.store)
    patched = client.patch(f"/api/environments/{env_id}", json={
        'base_url': 'http://other.test', 'console_token': 'new-token',
        'csrf_token': 'new-csrf', 'expected_connection_revision': target['connection_revision']})
    assert patched.status_code == 200, patched.text
    saved = copy.deepcopy(main.store.get('environment', env_id))
    seen, reads = [], []
    capture(monkeypatch, seen)
    original = main.store.secret
    def secret(owner, key):
        reads.append(key)
        return original(owner, key)
    monkeypatch.setattr(main.store, 'secret', secret)
    for credential in ('console_token', 'service_api_key', 'dataset_api_key'):
        with pytest.raises(dify.DifyError) as caught:
            asyncio.run(stale.request('GET', '/console/api/apps', credential=credential))
        assert caught.value.code == 'environment_changed' and caught.value.outcome_unknown is False
        assert 'new-token' not in str(caught.value) and 'other.test' not in str(caught.value)
    with pytest.raises(dify.DifyError) as caught:
        asyncio.run(stale.request('GET', '/v1/datasets', credential='dataset_api_key', secret_owner='another'))
    assert caught.value.code == 'environment_changed'
    with pytest.raises(dify.DifyError) as role:
        asyncio.run(stale.request('GET', '/console/api/apps', credential='console_token', secret_owner='another'))
    assert '独立资源凭据' in str(role.value)
    assert reads == [] and seen == []
    assert main.store.get('environment', env_id) == saved
    fresh = new_env(client)
    deleted = dify.DifyClient(fresh, main.store)
    main.store.delete('environment', fresh['id'])
    reads.clear()
    with pytest.raises(dify.DifyError) as caught:
        asyncio.run(deleted.request('GET', '/console/api/apps', credential='console_token'))
    assert caught.value.code == 'environment_changed' and reads == [] and seen == []


def test_credential_refresh_between_token_and_csrf_reads_stays_one_generation(client, monkeypatch):
    target = new_env(client, console_token='old-token', csrf_token='old-csrf')
    env_id = target['id']
    seen = []
    capture(monkeypatch, seen)
    original = main.store.secret
    first, written = threading.Event(), threading.Event()
    writer = []
    def secret(owner, key):
        value = original(owner, key)
        if owner == env_id and key == 'console_token' and not first.is_set():
            first.set()
            def rotate():
                main.store.set_secret(env_id, 'console_token', 'new-token')
                main.store.set_secret(env_id, 'csrf_token', 'new-csrf')
                written.set()
            thread = threading.Thread(target=rotate, daemon=True)
            thread.start()
            writer.append(thread)
            # Bounded chance for the rotation to land between the token and CSRF
            # reads; correctness is judged from the captured cookie pair.
            written.wait(1.0)
        return value
    monkeypatch.setattr(main.store, 'secret', secret)
    result = client.post(f"/api/environments/{env_id}/test", json={})
    assert result.status_code == 200, result.text
    for thread in writer:
        thread.join(5)
    assert len(seen) == 1
    key = seen[0].headers['authorization'].split(' ', 1)[1]
    cookie = seen[0].headers.get('cookie', '')
    assert (key, 'csrf_token=new-csrf' in cookie) in {('old-token', False), ('new-token', True)}
    assert seen[0].url.host == 'dify.test'


def test_immutable_snapshot_expired_token_is_controlled_no_send_and_no_login(client, monkeypatch):
    target = new_env(client, console_token=expired(), csrf_token='old-csrf')
    env = main.store.get('environment', target['id'])
    snapshot = CredentialSnapshot(main.store, target['id'])
    seen = []
    capture(monkeypatch, seen)
    async def forbidden(*args, **kwargs):
        pytest.fail('immutable snapshot must not trigger live automatic login')
    monkeypatch.setattr(dify.DifyClient, 'login', forbidden)
    adapter = dify.DifyClient(env, snapshot)
    with pytest.raises(dify.DifyError) as caught:
        asyncio.run(adapter.request('GET', '/console/api/apps', credential='console_token'))
    assert caught.value.code == 'console_credentials_missing'
    assert '未发送本次请求' in str(caught.value) and seen == []


def test_store_that_gains_an_environment_after_construction_rejects_changed_source(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.set_secret('public-unpersisted', 'console_token', 'old-dummy')
    adapter = dify.DifyClient({'id': 'public-unpersisted', 'base_url': 'https://old-env.invalid',
                               'version': '1.17.1'}, store)
    store.put_with_secrets('environment', 'public-unpersisted', {
        'id': 'public-unpersisted', 'name': 'public new source', 'base_url': 'https://new-env.invalid',
        'version': '1.17.1', 'connection_revision': 'new-public-revision'}, {'console_token': 'new-dummy'})
    seen, reads = [], []
    capture(monkeypatch, seen)
    original = store.secret
    def secret(owner, key):
        reads.append(key)
        return original(owner, key)
    monkeypatch.setattr(store, 'secret', secret)
    with pytest.raises(dify.DifyError) as caught:
        asyncio.run(adapter.request('GET', '/console/api/apps', credential='console_token'))
    assert caught.value.code == 'environment_changed' and caught.value.outcome_unknown is False
    assert reads == [] and seen == []


def test_caller_alias_mutation_cannot_change_adapter_owner_or_key(tmp_path, monkeypatch):
    store = Store(tmp_path)
    for ident, key in (('legacy-A', 'dummy-key-A'), ('legacy-B', 'dummy-key-B')):
        store.put_with_secrets('environment', ident, {
            'id': ident, 'name': ident, 'base_url': 'https://legacy.test', 'version': '1.17.1'},
            {'console_token': key})
    source = {'id': 'legacy-A', 'base_url': 'https://legacy.test', 'version': '1.17.1'}
    adapter = dify.DifyClient(source, store)
    source['id'] = 'legacy-B'
    seen = []
    capture(monkeypatch, seen)
    asyncio.run(adapter.request('GET', '/console/api/apps', credential='console_token'))
    assert adapter.env['id'] == 'legacy-A'
    assert len(seen) == 1 and seen[0].headers['authorization'] == 'Bearer dummy-key-A'
    assert 'cookie' not in seen[0].headers


def test_legacy_bad_address_is_a_controlled_api_error_without_key_or_transport(client, monkeypatch):
    target = new_env(client, console_token='dummy-token')
    row = main.store.get('environment', target['id'])
    row['base_url'] = 'http://model.invalid:abc'
    main.store.put('environment', row['id'], row)
    seen, reads = [], []
    capture(monkeypatch, seen)
    original = main.store.secret
    def secret(owner, key):
        reads.append(key)
        return original(owner, key)
    monkeypatch.setattr(main.store, 'secret', secret)
    response = client.get(f"/api/environments/{row['id']}/models")
    assert response.status_code == 502, response.text
    assert 'model.invalid' not in response.text and 'dummy-token' not in response.text
    assert '地址' in response.text and seen == [] and reads == []


def test_secret_only_wrapper_keeps_the_stateless_sdk_path(monkeypatch):
    class Secrets:
        def secret(self, owner, key):
            return {'console_token': 'unit-console', 'csrf_token': 'unit-csrf',
                    'service_api_key': 'unit-service'}.get(key, '')
    seen = []
    capture(monkeypatch, seen)
    adapter = dify.DifyClient({'id': 'fixture', 'base_url': 'https://fixture.test'}, Secrets())
    asyncio.run(adapter.request('GET', '/console/api/apps', credential='console_token'))
    asyncio.run(adapter.request('GET', '/v1/datasets', credential='service_api_key'))
    assert len(seen) == 2
    assert seen[0].headers['authorization'] == 'Bearer unit-console'
    assert 'csrf_token=unit-csrf' in seen[0].headers['cookie']
    assert seen[1].headers['authorization'] == 'Bearer unit-service' and 'cookie' not in seen[1].headers
