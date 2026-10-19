import asyncio
import base64
import json

import httpx
import pytest

from test_api import client
from app import dify, main
from app.storage import Store
from test_transports import transport_client


def env(client, **extra):
    r = client.post('/api/environments', json={'name': '本机测试', 'base_url': 'http://dify.test', 'version': '1.17.1', **extra})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize('prefix', ['', '__Host-'])
def test_login_encodes_password_and_verifies_csrf(monkeypatch, tmp_path, prefix):
    seen = []
    password = '测试密码-secret'
    def handler(request):
        seen.append(request)
        if request.url.path.endswith('/login'):
            payload = json.loads(request.content)
            assert base64.b64decode(payload['password']).decode() == password
            assert payload['remember_me'] is False
            return httpx.Response(200, json={'result': 'success'}, headers=[('Set-Cookie', f'{prefix}access_token=access-test; Path=/'), ('Set-Cookie', f'{prefix}csrf_token=csrf-test; Path=/')])
        assert request.url.path == '/console/api/apps'
        assert request.headers['authorization'] == 'Bearer access-test'
        assert request.headers['x-csrf-token'] == 'csrf-test'
        assert f'{prefix}csrf_token=csrf-test' in request.headers['cookie']
        return httpx.Response(200, json={'data': []})
    transport_client(monkeypatch, dify, handler)
    store = Store(tmp_path)
    result = asyncio.run(dify.DifyClient({'id': 'env', 'base_url': 'http://dify.test'}, store).login('user@test.local', password))
    assert result == {'console_token': 'access-test', 'csrf_token': 'csrf-test'}
    assert not store.has_secret('env', 'console_token')
    assert len(seen) == 2


@pytest.mark.parametrize('variant', ['unauthorized', 'missing_csrf', 'probe_failed', 'redirect', 'non_json'])
def test_login_failure_sanitized_no_automatic_retry(monkeypatch, tmp_path, variant):
    seen = []
    def handler(request):
        seen.append(request)
        if request.url.path.endswith('/apps'):
            return httpx.Response(403, json={'error': 'SECRET-RESPONSE'})
        if variant == 'unauthorized':
            return httpx.Response(401, json={'error': 'SECRET-RESPONSE'})
        if variant == 'redirect':
            return httpx.Response(302, headers={'location': 'https://other.test'})
        if variant == 'non_json':
            return httpx.Response(200, text='SECRET-RESPONSE')
        cookies = [('Set-Cookie', 'access_token=access-test; Path=/')]
        if variant != 'missing_csrf':
            cookies.append(('Set-Cookie', 'csrf_token=csrf-test; Path=/'))
        return httpx.Response(200, json={'result': 'success'}, headers=cookies)
    transport_client(monkeypatch, dify, handler)
    with pytest.raises(dify.DifyError) as error:
        asyncio.run(dify.DifyClient({'id': 'env', 'base_url': 'http://dify.test'}, Store(tmp_path)).login('user@test.local', 'SECRET-PASSWORD'))
    assert 'SECRET' not in str(error.value)
    assert len(seen) == (2 if variant == 'probe_failed' else 1)


def test_login_api_saves_only_encrypted_tokens(client, monkeypatch):
    target = env(client)
    async def login(self, email, password):
        assert email == 'user@test.local' and password == 'PASSWORD-PRIVATE'
        return {'console_token': 'ACCESS-PRIVATE', 'csrf_token': 'CSRF-PRIVATE'}
    monkeypatch.setattr(dify.DifyClient, 'login', login)
    result = client.post(f"/api/environments/{target['id']}/login", json={'email': 'user@test.local', 'password': 'PASSWORD-PRIVATE'})
    assert result.status_code == 200, result.text
    public = result.json()['environment']
    assert public['capabilities']['console'] == 'verified' and public['has_console_token']
    assert 'PRIVATE' not in result.text and 'user@test.local' not in result.text
    assert main.store.secret(target['id'], 'console_token') == 'ACCESS-PRIVATE'
    with main.store.connect() as conn:
        dump = '\n'.join(conn.iterdump())
    assert all(x not in dump for x in ('PASSWORD-PRIVATE', 'user@test.local', 'ACCESS-PRIVATE', 'CSRF-PRIVATE'))


def test_login_failure_preserves_existing_credentials(client, monkeypatch):
    target = env(client, console_token='old-access', csrf_token='old-csrf')
    async def fail(self, email, password):
        raise dify.DifyError('未连接')
    monkeypatch.setattr(dify.DifyClient, 'login', fail)
    assert client.post(f"/api/environments/{target['id']}/login", json={'email': 'user@test.local', 'password': 'private'}).status_code == 502
    assert main.store.secret(target['id'], 'console_token') == 'old-access'


def test_login_rejects_changed_environment_during_probe(client, monkeypatch):
    target = env(client, console_token='old-access')
    async def changed(self, email, password):
        record = main.store.get('environment', target['id'])
        record['base_url'] = 'http://another.test'
        main.store.put('environment', target['id'], record)
        return {'console_token': 'new-access', 'csrf_token': 'new-csrf'}
    monkeypatch.setattr(dify.DifyClient, 'login', changed)
    assert client.post(f"/api/environments/{target['id']}/login", json={'email': 'user@test.local', 'password': 'private'}).status_code == 409
    assert main.store.secret(target['id'], 'console_token') == 'old-access'


@pytest.mark.parametrize('body', [{'email': 'bad', 'password': 'SECRET'}, {'email': 'user@test.local', 'password': ['SECRET']}, {'email': 'user@test.local', 'password': 'SECRET', 'other': 1}])
def test_login_input_errors_never_echo_password(client, body):
    target = env(client)
    result = client.post(f"/api/environments/{target['id']}/login", json=body)
    assert result.status_code == 422 and 'SECRET' not in result.text


def test_environment_host_change_clears_old_credentials(client):
    target = env(client, console_token='old-console', csrf_token='old-csrf', service_api_key='old-service', dataset_api_key='old-dataset')
    result = client.patch(f"/api/environments/{target['id']}", json={'base_url': 'http://another.test'})
    assert result.status_code == 200, result.text
    assert all(not result.json()[k] for k in ('has_console_token', 'has_service_api_key', 'has_dataset_api_key'))
    assert not main.store.has_secret(target['id'], 'csrf_token')


def test_console_post_carries_csrf_cookie_but_service_does_not(monkeypatch, tmp_path):
    store = Store(tmp_path)
    for key, value in [('console_token', 'console'), ('csrf_token', 'csrf'), ('service_api_key', 'service')]:
        store.set_secret('env', key, value)
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={})
    transport_client(monkeypatch, dify, handler)
    adapter = dify.DifyClient({'id': 'env', 'base_url': 'http://dify.test'}, store)
    asyncio.run(adapter.import_new('kind: app', 'test'))
    asyncio.run(adapter.run_workflow({}))
    assert 'csrf_token=csrf' in seen[0].headers['cookie']
    assert '__Host-csrf_token=csrf' in seen[0].headers['cookie']
    assert 'cookie' not in seen[1].headers and 'x-csrf-token' not in seen[1].headers


def test_login_requires_json_content_type(client):
    target = env(client)
    result = client.post(f"/api/environments/{target['id']}/login", content='{"email":"user@test.local","password":"SECRET"}', headers={"content-type": "text/plain"})
    assert result.status_code == 422 and "SECRET" not in result.text


def test_login_does_not_dispatch_during_environment_run(client, monkeypatch):
    target = env(client)
    task = client.post('/api/tasks', json={"name": "busy", "app_type": "workflow", "environment_id": target['id']}).json()
    task['status'] = 'running'
    main.store.put('task', task['id'], task)
    async def forbidden(*args, **kwargs):
        pytest.fail('Busy environment must not dispatch login')
    monkeypatch.setattr(dify.DifyClient, 'login', forbidden)
    result = client.post(f"/api/environments/{target['id']}/login", json={"email": "user@test.local", "password": "private"})
    assert result.status_code == 409
