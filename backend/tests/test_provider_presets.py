import asyncio
import copy
import json
import sys
from pathlib import Path
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main, providers
from app.provider_presets import VENDORS, get_preset
from app.providers import call_model, ProviderError
from test_api import client

IDS = [m['id'] for v in VENDORS for m in v['models']]


def test_catalog_is_local_metadata_not_a_fake_account_check(client, monkeypatch):
    async def forbidden(*args, **kwargs): raise AssertionError('catalog must not invoke a model')
    monkeypatch.setattr(main, 'call_model', forbidden)
    result = client.get('/api/provider-presets').json()
    assert len(result['vendors']) == 4 and result['availability'] == 'account_unverified'
    assert {m['id'] for v in result['vendors'] for m in v['models']} == set(IDS)


@pytest.mark.parametrize('preset_id', IDS)
def test_only_preset_and_key_are_needed_for_a_usable_saved_config(client, preset_id):
    secret = 'test-key-never-published'
    result = client.post('/api/providers', json={'preset_id': preset_id, 'api_key': secret})
    assert result.status_code == 201, result.text
    saved, preset = result.json(), get_preset(preset_id)
    assert all(saved[k] == preset[k] for k in ('base_url', 'model', 'protocol', 'provider'))
    assert saved['pricing'] == preset['pricing'] and saved['role'] == 'main' and saved['has_api_key']
    assert saved['capabilities']['text'] == 'untested'
    assert secret not in result.text and main.store.secret(saved['id'], 'api_key') == secret


def test_preset_rejects_unknown_missing_key_and_address_override(client):
    for body in ({'preset_id': 'invented', 'api_key': 'test'}, {'preset_id': 'deepseek-flash'}, {'preset_id': 'deepseek-flash', 'api_key': 'test', 'base_url': 'https://different.example'}):
        assert client.post('/api/providers', json=body).status_code == 422
    assert not client.get('/api/providers').json()


def test_editing_a_keyless_legacy_service_into_a_preset_requires_key(client):
    p = client.post('/api/providers', json={'name': '待连接', 'provider': 'deepseek', 'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash'}).json()
    assert not p['has_api_key']
    response = client.patch('/api/providers/' + p['id'], json={'preset_id': 'deepseek-flash'})
    assert response.status_code == 422 and 'API Key' in response.text


def test_edit_and_same_vendor_model_change_keep_encrypted_key(client):
    p = client.post('/api/providers', json={'preset_id': 'deepseek-flash', 'api_key': 'test-secret', 'name': '我的助手'}).json()
    same = client.patch('/api/providers/' + p['id'], json={'preset_id': 'deepseek-flash', 'name': '名称调整'}).json()
    assert same['name'] == '名称调整' and same['has_api_key'] and main.store.secret(p['id'], 'api_key') == 'test-secret'
    switched = client.patch('/api/providers/' + p['id'], json={'preset_id': 'deepseek-v4-pro'}).json()
    assert switched['model'] == 'deepseek-v4-pro' and switched['pricing']['input_per_million_usd'] == 1.32
    assert main.store.secret(p['id'], 'api_key') == 'test-secret'


def test_cross_vendor_never_forwards_old_key_and_failed_save_is_unchanged(client):
    p = client.post('/api/providers', json={'preset_id': 'deepseek-flash', 'api_key': 'old-test-secret'}).json()
    result = client.patch('/api/providers/' + p['id'], json={'preset_id': 'openai-gpt-6-luna'})
    assert result.status_code == 422 and '新服务' in result.text
    assert main.store.get('provider', p['id'])['model'] == 'deepseek-flash'
    assert main.store.secret(p['id'], 'api_key') == 'old-test-secret'
    changed = client.patch('/api/providers/' + p['id'], json={'preset_id': 'openai-gpt-6-luna', 'api_key': 'new-test-secret'})
    assert changed.status_code == 200 and main.store.secret(p['id'], 'api_key') == 'new-test-secret'


def test_manual_custom_connection_and_user_prices_are_preserved(client):
    p = client.post('/api/providers', json={'name': '自有网关', 'provider': 'custom', 'base_url': 'https://gateway.example/v1', 'model': 'self-model', 'api_key': 'test-secret', 'pricing': {'input_per_million_usd': 1, 'output_per_million_usd': 2}, 'pricing_note': '自有单价'}).json()
    edited = client.patch('/api/providers/' + p['id'], json={'name': '改名', 'preset_id': None}).json()
    assert edited['base_url'] == p['base_url'] and edited['model'] == 'self-model'
    assert edited['pricing'] == p['pricing'] and edited['pricing_note'] == '自有单价'
    assert main.store.secret(p['id'], 'api_key') == 'test-secret'


def test_same_preset_keeps_user_price_override_and_changed_model_gets_new_default(client):
    p = client.post('/api/providers', json={'preset_id': 'deepseek-flash', 'api_key': 'test', 'pricing': {'input_per_million_usd': 9, 'output_per_million_usd': 10}}).json()
    assert '用户调整' in p['pricing_note']
    same = client.patch('/api/providers/' + p['id'], json={'preset_id': 'deepseek-flash'}).json()
    assert same['pricing'] == p['pricing'] and same['pricing_note'] == p['pricing_note']
    changed = client.patch('/api/providers/' + p['id'], json={'preset_id': 'deepseek-v4-pro'}).json()
    assert changed['pricing'] == get_preset('deepseek-v4-pro')['pricing']


@pytest.mark.parametrize('preset_id,expected', [
    ('deepseek-flash', {'thinking': {'type': 'disabled'}, 'max_tokens': 123}),
    ('openai-gpt-6.1-sol', {'max_completion_tokens': 123, 'reasoning_effort': 'low'}),
    ('openai-gpt-6-luna', {'max_completion_tokens': 123, 'reasoning_effort': 'none'}),
    ('qwen3.7-plus', {'max_tokens': 123, 'enable_thinking': False}),
    ('claude-sonnet-5-5', {'max_tokens': 123}),
])
def test_selected_preset_maps_to_native_request_without_user_protocol_work(monkeypatch, preset_id, expected):
    preset = get_preset(preset_id); p = {**preset, 'preset_id': preset_id}; captured = []
    def handler(req):
        body = json.loads(req.content); captured.append((str(req.url), body))
        if preset['protocol'] == 'anthropic': return httpx.Response(200, json={'content': [{'type': 'text', 'text': '{"ok":true}'}], 'usage': {'input_tokens': 2, 'output_tokens': 3}})
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"ok":true}'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 2, 'completion_tokens': 3}})
    original = httpx.AsyncClient
    monkeypatch.setattr(providers.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    text, _ = asyncio.run(call_model(p, 'test-secret', [{'role': 'user', 'content': 'JSON test'}], max_tokens=123, json_mode=preset['protocol'] != 'anthropic'))
    assert text == '{"ok":true}' and len(captured) == 1
    url, body = captured[0]; assert all(body[k] == v for k, v in expected.items())
    if preset_id.startswith('openai-'): assert 'max_tokens' not in body
    if preset['protocol'] == 'anthropic': assert url == 'https://api.anthropic.com/v1/messages'
    else: assert url == preset['base_url'] + '/chat/completions' and body['response_format'] == {'type': 'json_object'}


def test_modified_preset_identity_cannot_silently_use_another_request_profile(monkeypatch):
    p = {**get_preset('deepseek-flash'), 'preset_id': 'deepseek-flash', 'base_url': 'https://unknown.example'}
    with pytest.raises(ProviderError, match='不一致'): asyncio.run(call_model(p, 'test', []))


def test_selecting_preset_resets_old_capability_evidence_even_same_model(client):
    p = client.post('/api/providers', json={'name': '旧 DeepSeek', 'provider': 'deepseek', 'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash', 'api_key': 'test'}).json()
    stored = main.store.get('provider', p['id']); stored['capabilities']['text'] = 'verified'; main.store.put('provider', p['id'], stored)
    updated = client.patch('/api/providers/' + p['id'], json={'preset_id': 'deepseek-flash'}).json()
    assert updated['capabilities']['text'] == 'untested' and updated['name'] == '旧 DeepSeek'

@pytest.mark.parametrize('model',['deepseek-flash','deepseek-v4-pro','deepseek-v4-flash'])
def test_legacy_official_deepseek_reserves_output_for_text(monkeypatch,model):
    p={'provider':'deepseek','base_url':'https://api.deepseek.com/','model':model,'protocol':'openai-compatible','pricing':{'input_per_million_usd':9,'output_per_million_usd':10}}
    original_p=copy.deepcopy(p);requests=[]
    def handler(req):
        body=json.loads(req.content);requests.append(body)
        assert body['thinking']=={'type':'disabled'} and body['response_format']=={'type':'json_object'}
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':3}})
    original=httpx.AsyncClient;monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    text,usage=asyncio.run(call_model(p,'test-secret',[{'role':'user','content':'JSON test'}],max_tokens=6000,json_mode=True))
    assert text=='{"ok":true}' and usage['completion_tokens']==3 and len(requests)==1 and p==original_p

@pytest.mark.parametrize('patch',[{'base_url':'https://proxy.example'},{'base_url':'https://api.deepseek.com.evil.example'},{'provider':'custom'},{'model':'unknown-model'}])
def test_legacy_adaptation_does_not_guess_other_endpoints(monkeypatch,patch):
    p={'provider':'deepseek','base_url':'https://api.deepseek.com','model':'deepseek-flash','protocol':'openai-compatible',**patch};captured=[]
    def handler(req):
        captured.append(json.loads(req.content));return httpx.Response(200,json={'choices':[{'message':{'content':'ok'}}]})
    original=httpx.AsyncClient;monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    asyncio.run(call_model(p,'test',[]))
    assert 'thinking' not in captured[0]
