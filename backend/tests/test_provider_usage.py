import asyncio
import sys
from pathlib import Path
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import providers
from app.providers import ProviderError, call_model
from app.planning import draft_plan, PlanningStopped


def controlled(monkeypatch, body, protocol='openai-compatible'):
    original = httpx.AsyncClient
    monkeypatch.setattr(providers.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)), **kwargs))
    return lambda: asyncio.run(call_model({'base_url': 'http://127.0.0.1', 'model': 'controlled-model', 'protocol': protocol}, 'test-key', [{'role': 'user', 'content': 'test'}]))


def test_empty_content_at_limit_keeps_known_usage_and_finish_reason(monkeypatch):
    invoke = controlled(monkeypatch, {'choices': [{'finish_reason': 'length', 'message': {'content': None, 'reasoning_content': 'private'}}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'api_key': 'private', 'completion_tokens_details': {'reasoning_tokens': 20}}})
    with pytest.raises(ProviderError, match='输出上限') as e: invoke()
    assert e.value.usage == {'prompt_tokens': 100, 'completion_tokens': 20, 'completion_tokens_details': {'reasoning_tokens': 20}}
    assert e.value.finish_reason == 'length' and 'private' not in str(e.value)


def test_malformed_choices_still_keep_reported_usage(monkeypatch):
    invoke = controlled(monkeypatch, {'choices': [], 'usage': {'prompt_tokens': 11, 'completion_tokens': 0}})
    with pytest.raises(ProviderError) as e: invoke()
    assert e.value.usage == {'prompt_tokens': 11, 'completion_tokens': 0}


def test_anthropic_empty_text_keeps_reported_tokens(monkeypatch):
    invoke = controlled(monkeypatch, {'content': [{'type': 'tool_use', 'input': 'private'}], 'usage': {'input_tokens': 13, 'output_tokens': 2}}, 'anthropic')
    with pytest.raises(ProviderError) as e: invoke()
    assert e.value.usage == {'input_tokens': 13, 'output_tokens': 2}


def test_success_usage_filters_unexpected_private_fields(monkeypatch):
    text, usage = controlled(monkeypatch, {'choices': [{'finish_reason': 'stop', 'message': {'content': 'ok'}}], 'usage': {'total_tokens': 9, 'password': 'private', 'prompt_tokens_details': {'cached_tokens': 3, 'secret': 'private'}}})()
    assert text == 'ok' and usage == {'total_tokens': 9, 'prompt_tokens_details': {'cached_tokens': 3}}


def test_planning_failure_accounts_reported_usage_without_retry():
    calls, operation = [], {'attempts': [], 'settings': {}, 'status': 'running'}
    async def invoke(*args):
        calls.append(True)
        raise ProviderError('没有正文', usage={'prompt_tokens': 100, 'completion_tokens': 20}, finish_reason='length')
    with pytest.raises(PlanningStopped):
        asyncio.run(draft_plan({}, {'pricing': {'input_per_million_usd': .3, 'output_per_million_usd': 1.2}}, [{'role': 'user', 'content': 'q'}], {'max_minutes': 1, 'max_cost_usd': 1, 'max_retries': 3}, operation, invoke, lambda p: {'valid': True, 'errors': []}, lambda: None, lambda: None))
    attempt = operation['attempts'][0]
    assert len(calls) == 1 and attempt['status'] == 'provider_failed' and attempt['cost_basis'] == 'reported_usage'
    assert attempt['estimated_cost_usd'] == pytest.approx(.000054) and attempt['finish_reason'] == 'length'
