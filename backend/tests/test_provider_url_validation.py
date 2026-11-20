import asyncio
import copy
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.providers import ProviderError, call_model, checked_url
from test_api import client

INVALID_URLS = [
    'http://model.invalid:abc/v1',
    'http://model.invalid:65536/v1',
    'http://model.invalid:0/v1',
    'http://[::1/v1',
]

VALID_ROUTING = [
    ('https://api.example.com', 'https://api.example.com'),
    ('https://api.example.com/v1/', 'https://api.example.com/v1'),
    ('http://127.0.0.1:8080/v1', 'http://127.0.0.1:8080/v1'),
    ('http://localhost:11434', 'http://localhost:11434'),
    ('http://192.168.1.20:8000/custom/path', 'http://192.168.1.20:8000/custom/path'),
    ('http://[::1]:8080/v1/', 'http://[::1]:8080/v1'),
    ('https://[2001:db8::1]/v1', 'https://[2001:db8::1]/v1'),
    ('https://gateway.example:8443/base', 'https://gateway.example:8443/base'),
]


@pytest.fixture(autouse=True)
def forbid_physical_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('地址校验测试不得发起真实 HTTP 或模型请求')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def provider_payload(base_url):
    return {
        'name': '隔离地址模型',
        'provider': 'custom',
        'base_url': base_url,
        'model': 'fixture-model',
        'api_key': 'fixture-only-key',
        'pricing': {'input_per_million_usd': 1, 'output_per_million_usd': 1},
    }


def persisted_broken(client, base_url):
    created = client.post('/api/providers', json=provider_payload('https://gateway.example/v1'))
    assert created.status_code == 201, created.text
    provider_id = created.json()['id']
    stored = main.store.get('provider', provider_id)
    stored['base_url'] = base_url
    main.store.put('provider', provider_id, stored)
    return provider_id, stored


@pytest.mark.parametrize('value', INVALID_URLS)
def test_checked_url_rejects_malformed_address_without_echoing_it(value):
    with pytest.raises(ProviderError) as error:
        checked_url(value)
    message = str(error.value)
    assert '地址' in message
    assert value not in message


@pytest.mark.parametrize('value', [
    'ftp://example.com/v1',
    'https://user:pass@example.com/v1',
    'https://example.com/v1?token=fixture',
    'https://example.com/v1#fragment',
    'https:///v1',
])
def test_checked_url_keeps_existing_rejections(value):
    with pytest.raises(ProviderError):
        checked_url(value)


@pytest.mark.parametrize('value,expected', VALID_ROUTING)
def test_checked_url_preserves_valid_routing_spelling(value, expected):
    assert checked_url(value) == expected


@pytest.mark.parametrize('base_url', INVALID_URLS)
def test_create_rejects_invalid_address_before_persisting_provider_or_secret(client, base_url):
    response = client.post('/api/providers', json=provider_payload(base_url))
    assert response.status_code == 422
    assert '地址' in response.text
    assert 'fixture-only-key' not in response.text and base_url not in response.text
    assert main.store.list('provider') == []
    with main.store.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM secrets').fetchone()[0] == 0


@pytest.mark.parametrize('base_url', INVALID_URLS)
def test_edit_invalid_address_preserves_prior_configuration_key_and_other_providers(client, base_url):
    created = client.post('/api/providers', json=provider_payload('https://gateway.example/v1'))
    assert created.status_code == 201, created.text
    provider_id = created.json()['id']
    stored = main.store.get('provider', provider_id)
    stored['capabilities']['text'] = 'verified'
    stored['checks'] = {'text': {'marker': 'fixture-check'}}
    main.store.put('provider', provider_id, stored)
    other = client.post('/api/providers', json=provider_payload('https://other.example/v1'))
    assert other.status_code == 201, other.text
    before = copy.deepcopy(main.store.get('provider', provider_id))
    before_key = main.store.secret(provider_id, 'api_key')
    before_other = copy.deepcopy(main.store.get('provider', other.json()['id']))
    response = client.patch(f'/api/providers/{provider_id}', json={
        'base_url': base_url,
        'expected_configuration_revision': before['configuration_revision'],
    })
    assert response.status_code == 422
    assert 'fixture-only-key' not in response.text and base_url not in response.text
    assert main.store.get('provider', provider_id) == before
    assert main.store.secret(provider_id, 'api_key') == before_key
    assert main.store.get('provider', other.json()['id']) == before_other


@pytest.mark.parametrize('base_url,expected', VALID_ROUTING)
def test_valid_address_spelling_is_saved_without_rewrite(client, base_url, expected):
    response = client.post('/api/providers', json=provider_payload(base_url))
    assert response.status_code == 201, response.text
    assert response.json()['base_url'] == expected


@pytest.mark.parametrize('base_url', INVALID_URLS)
def test_legacy_broken_saved_address_fails_before_http_client(client, monkeypatch, base_url):
    provider_id, stored = persisted_broken(client, base_url)
    constructed = []

    def forbidden_client(*args, **kwargs):
        constructed.append(1)
        raise AssertionError('坏地址不得构造 HTTP 客户端')

    monkeypatch.setattr(httpx, 'AsyncClient', forbidden_client)
    with pytest.raises(ProviderError) as error:
        asyncio.run(call_model(stored, 'fixture-only-key', [{'role': 'user', 'content': '固定检查'}]))
    message = str(error.value)
    assert not constructed and '地址' in message
    assert 'fixture-only-key' not in message and base_url not in message
    assert main.store.secret(provider_id, 'api_key') == 'fixture-only-key'


@pytest.mark.parametrize('base_url', INVALID_URLS)
def test_legacy_broken_saved_address_text_probe_reports_controlled_failure(client, base_url):
    provider_id, stored = persisted_broken(client, base_url)
    response = client.post(f'/api/providers/{provider_id}/test')
    assert response.status_code == 502, response.text
    assert '地址' in response.text
    assert 'fixture-only-key' not in response.text and base_url not in response.text
    assert main.store.get('provider', provider_id) == stored
