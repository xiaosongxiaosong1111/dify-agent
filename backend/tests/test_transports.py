import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import providers, dify
from app.storage import Store


def transport_client(monkeypatch, module, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_openai_compatible_payload_and_usage(monkeypatch):
    import asyncio, json
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"message":"ok"}'}}], "usage": {"prompt_tokens": 10}})
    transport_client(monkeypatch, providers, handler)
    result, usage = asyncio.run(providers.call_model({"base_url": "https://example.test/v1", "model": "exact-user-model", "protocol": "openai-compatible"}, "unit-test-key", [{"role": "user", "content": "测试"}], json_mode=True))
    assert seen[0].url.path == "/v1/chat/completions"
    body = json.loads(seen[0].content)
    assert body["model"] == "exact-user-model" and body["response_format"]["type"] == "json_object"
    assert seen[0].headers["authorization"] == "Bearer unit-test-key"
    assert usage["prompt_tokens"] == 10 and providers.extract_json(result)["message"] == "ok"


def test_provider_error_does_not_echo_response_secrets(monkeypatch):
    import asyncio
    def handler(request):
        return httpx.Response(401, json={"error": "unit-test-secret-sensitive"})
    transport_client(monkeypatch, providers, handler)
    with pytest.raises(providers.ProviderError) as error:
        asyncio.run(providers.call_model({"base_url": "https://example.test/v1", "model": "test"}, "test", [{"role": "user", "content": "x"}]))
    assert "401" in str(error.value) and "unit-test-secret" not in str(error.value)


def test_anthropic_system_and_message_split(monkeypatch):
    import asyncio, json
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "真实协议路径测试"}], "usage": {"input_tokens": 4}})
    transport_client(monkeypatch, providers, handler)
    result, _ = asyncio.run(providers.call_model({"base_url": "https://example.test", "model": "test", "protocol": "anthropic"}, "test", [{"role": "system", "content": "规则"}, {"role": "user", "content": "问题"}]))
    assert seen[0].url.path == "/v1/messages"
    body = json.loads(seen[0].content)
    assert body["system"] == "规则" and body["messages"][0]["role"] == "user"
    assert result == "真实协议路径测试"


def test_console_import_never_sets_overwrite_id(monkeypatch, tmp_path):
    import asyncio, json
    store = Store(tmp_path)
    store.set_secret("env", "console_token", "console-test")
    store.set_secret("env", "csrf_token", "csrf-test")
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "completed", "app_id": "new"})
    transport_client(monkeypatch, dify, handler)
    client = dify.DifyClient({"id": "env", "base_url": "https://dify.test"}, store)
    result = asyncio.run(client.import_new("kind: app", "新应用"))
    assert seen[0].url.path == "/console/api/apps/imports"
    body = json.loads(seen[0].content)
    assert body["mode"] == "yaml-content" and "app_id" not in body
    assert seen[0].headers["X-CSRF-Token"] == "csrf-test" and result["app_id"] == "new"


def test_service_key_is_not_console_key(monkeypatch, tmp_path):
    import asyncio
    store = Store(tmp_path)
    store.set_secret("env", "console_token", "console-only")
    client = dify.DifyClient({"id": "env", "base_url": "https://dify.test"}, store)
    with pytest.raises(dify.DifyError) as error:
        asyncio.run(client.run_workflow({"query": "test"}))
    assert "service_api_key" in str(error.value)


def test_dataset_pagination_uses_dataset_credential(monkeypatch, tmp_path):
    import asyncio
    store = Store(tmp_path)
    store.set_secret("env", "dataset_api_key", "dataset-test")
    store.set_secret("env", "console_token", "console-test")
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "dataset-id", "name": "保修资料"}], "has_more": False})
    transport_client(monkeypatch, dify, handler)
    result = asyncio.run(dify.DifyClient({"id": "env", "base_url": "https://dify.test"}, store).datasets(page=2, limit=20))
    assert seen[0].url.params["page"] == "2" and seen[0].url.params["limit"] == "20"
    assert seen[0].headers["authorization"] == "Bearer dataset-test"
    assert result["data"][0]["id"] == "dataset-id"


def test_known_console_no_content_response_is_not_an_unknown_json_failure(monkeypatch, tmp_path):
    import asyncio
    store=Store(tmp_path)
    store.set_secret('env','console_token','test')
    transport_client(monkeypatch,dify,lambda request:httpx.Response(204))
    result=asyncio.run(dify.DifyClient({'id':'env','base_url':'https://dify.test'},store).request('POST','/console/api/technical-fixture',credential='console_token',json={}))
    assert result=={}
