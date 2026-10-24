"""A 5xx login is a service failure, never evidence of a bad password."""
import asyncio
import json

import httpx
import pytest
from test_api import client
from test_dify_reauth import saved
from test_saved_console_reconnect import setup, prepare, confirm, cipher_rows
from test_transports import transport_client
from app import main, dify, console_failures


@pytest.fixture(autouse=True)
def no_real_http_or_models(monkeypatch):
    def forbidden(*a, **kw): pytest.fail('Isolated login diagnostics must never use real HTTP or models')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


@pytest.mark.parametrize('status', [500, 502, 503])
def test_automatic_login_service_failure_stays_paused_without_retry(tmp_path, monkeypatch, status):
    store, target, adapter = saved(tmp_path); seen = []
    with store.connect() as db: before = dict(db.execute('SELECT id,value FROM secrets'))
    def handler(request):
        seen.append((request.method, request.url.path))
        assert request.method == 'POST' and request.url.path == '/console/api/login'
        return httpx.Response(status, text='PRIVATE-PASSWORD PRIVATE-TOKEN PRIVATE-SERVER-BODY')
    transport_client(monkeypatch, dify, handler)
    for _ in range(2):
        with pytest.raises(dify.DifyError): asyncio.run(adapter.test())
    assert seen == [('POST', '/console/api/login')]
    current = store.get('environment', target['id']); assert current['console_login_blocked']
    value = console_failures.public(store, current)
    assert value['code'] == 'login_service_error' and value['http_status'] == status
    assert not value['automatic_retry'] and '无法据此判断账号密码' in value['message']
    assert 'PRIVATE' not in json.dumps(value) and len(store.list(console_failures.KIND)) == 1
    with store.connect() as db: assert dict(db.execute('SELECT id,value FROM secrets')) == before
    assert current['console_workspace_id'] == target['console_workspace_id']


@pytest.mark.parametrize('status,code', [(502, 'login_service_error'), (503, 'login_service_error'), (401, 'login_rejected'), (403, 'login_rejected')])
def test_explicit_reconnect_records_actual_http_diagnostic_once_and_keeps_credentials(client, monkeypatch, status, code):
    original_login = dify.DifyClient.login
    target, calls = setup(client, monkeypatch)
    monkeypatch.setattr(dify.DifyClient, 'login', original_login)
    plan = prepare(client, target).json(); before = cipher_rows(); seen = []
    def handler(request):
        seen.append(request.url.path)
        assert request.method == 'POST' and request.url.path == '/console/api/login'
        return httpx.Response(status, text='PRIVATE-PASSWORD PRIVATE-EMAIL PRIVATE-TOKEN')
    transport_client(monkeypatch, dify, handler)
    response = confirm(client, target, plan)
    assert response.status_code == 502 and response.headers['X-Sierra-Dify-Code'] == code
    assert 'PRIVATE' not in response.text
    record = client.get(f"/api/environments/{target['id']}/saved-login/reconnections").json()['records'][0]
    assert record['state'] == 'failed' and record['diagnostic_code'] == code and not record['automatic_retry']
    assert confirm(client, target, plan).status_code == 409
    assert seen == ['/console/api/login'] and not calls and cipher_rows() == before
    current = main.store.get('environment', target['id'])
    assert current['console_login_blocked'] and current['console_workspace_id'] == target['console_workspace_id']
    value = console_failures.public(main.store, current)
    assert value['code'] == code and value['http_status'] == status
