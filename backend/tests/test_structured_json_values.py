"""Model JSON must retain the same finite/encoding boundary as manual plans."""
import copy
import json
import pytest
import httpx
from fastapi.testclient import TestClient
from test_api import client, approved, planning_provider, forbid_api_external_calls
from test_planning import run, USAGE
from app import main
from app.providers import extract_json

RAW = ['{"PRIVATE_FIELD":NaN}', '{"x":Infinity}', '{"x":-Infinity}',
       '{"x":1e400}', '{"x":-1e400}', r'{"\ud800":"PRIVATE_VALUE"}',
       r'{"x":"PRIVATE_VALUE\udfff"}']


@pytest.mark.parametrize('raw', RAW)
@pytest.mark.parametrize('wrapper', ['plain', 'fence', 'prose'])
def test_model_json_values_reject_ambiguous_or_unencodable_content(raw, wrapper):
    text = raw if wrapper == 'plain' else '```json\n'+raw+'\n```' if wrapper == 'fence' else '公开前缀\n'+raw+'\n公开后缀'
    with pytest.raises(ValueError) as exc:
        extract_json(text)
    assert 'PRIVATE' not in str(exc.value)
    assert '编码' in str(exc.value) or '有限数' in str(exc.value)


@pytest.mark.parametrize('raw', RAW)
def test_planning_value_failure_stops_as_format_without_another_model_call(raw):
    result, operation, calls, reason = run([(raw, USAGE)], settings={'max_retries':3,'max_minutes':1,'max_cost_usd':1})
    assert result is None and reason == 'invalid_plan_format'
    assert len(calls) == 1
    assert operation['last_response_excerpt'] == raw
    assert operation['attempts'][0]['usage'] == USAGE
    assert not operation.get('last_candidate')
    assert 'PRIVATE' not in '\n'.join(operation['diagnostics'])


@pytest.mark.parametrize('raw', RAW)
@pytest.mark.parametrize('stream', [False, True])
def test_interview_invalid_unused_metadata_cannot_apply_patch_or_break_persistence(client, monkeypatch, raw, stream):
    planning_provider(client)
    task = approved(client)
    before = copy.deepcopy(main.get_task(task['id']))
    text = '{"message":"公开回复","requirements_patch":{"goal":"SHOULD_NOT_APPLY"},"metadata":'+raw+'}'
    calls = []
    async def fake(*args, **kwargs):
        calls.append(True)
        if stream:
            await kwargs['on_delta'](text)
        return text, USAGE
    monkeypatch.setattr(main, 'call_model', fake)
    response = client.post(f"/api/tasks/{task['id']}/messages", json={
        'revision': task['revision'], 'content': '公开需求核对', 'stream_response': stream})
    assert response.status_code == 200, response.text
    saved = response.json()
    for key in ('revision','requirements','configuration','workflow_plan','agent_plan','artifact','runs','requirements_confirmed','configuration_confirmed'):
        assert saved.get(key) == before.get(key), key
    assert calls == [True] and not saved.get('active_interview_id')
    attempt = saved['interview_attempts'][-1]
    operation = client.get(f"/api/tasks/{task['id']}/interviews").json()['operations'][-1]
    note = saved['messages'][-1]['content']
    assert attempt['applied'] is False and operation['status'] == 'failed'
    assert attempt['response_excerpt'] == text and attempt['usage'] == USAGE
    assert attempt['reason'] == operation['note'] == note and 'PRIVATE' not in note
    assert '编码' in note or '有限数' in note
    entries = main.budgets.get(task['id'])['entries']
    assert len(entries) == 1 and entries[0]['status'] == 'settled' and entries[0]['cost_basis'] == 'reported_usage'


@pytest.mark.parametrize('raw', [
    '{"x":"NaN Infinity -Infinity", "n":1e308,"empty":null,"flag":false}',
    r'{"\ud83d\ude00":"汉字 \ud83d\ude00"}',
    '{"array":[0,-1,1.25,"",true],"nested":{"x":"原样保留"}}',
])
def test_valid_finite_numbers_and_unicode_are_not_normalized(raw):
    assert extract_json(raw) == json.loads(raw)


@pytest.mark.parametrize('protocol', ['openai-compatible', 'anthropic'])
@pytest.mark.parametrize('action', ['planning', 'interview'])
def test_provider_unencodable_text_is_safe_failure_with_reported_usage(client, monkeypatch, protocol, action):
    from app import providers
    provider = planning_provider(client)
    assert client.patch('/api/providers/'+provider['id'], json={'protocol': protocol}).status_code == 200
    task = approved(client)
    before = copy.deepcopy(main.get_task(task['id']))
    requests = []
    def response(request):
        requests.append(request.url.path)
        text = 'PRIVATE_PROVIDER\ud800'
        body = {'content': [{'type': 'text', 'text': text}], 'usage': {'input_tokens':100,'output_tokens':20}} if protocol == 'anthropic' else {
            'choices': [{'finish_reason':'stop','message':{'role':'assistant','content':text}}], 'usage': USAGE}
        return httpx.Response(200, content=json.dumps(body, ensure_ascii=True).encode('ascii'), headers={'Content-Type':'application/json'})
    original = httpx.AsyncClient
    def local_client(**kwargs):
        return original(**kwargs, transport=httpx.MockTransport(response))
    monkeypatch.setattr(httpx, 'AsyncClient', local_client)
    monkeypatch.setattr(main, 'call_model', providers.call_model)
    path = 'plan/generate' if action == 'planning' else 'messages'
    body = {'revision': task['revision']} if action == 'planning' else {'content':'公开需求核对','revision':task['revision']}
    with TestClient(main.app, raise_server_exceptions=False) as safe:
        result = safe.post(f"/api/tasks/{task['id']}/{path}", json=body)
    assert result.status_code == (422 if action == 'planning' else 200), result.text
    assert '编码' in result.text and 'PRIVATE_PROVIDER' not in result.text
    saved = main.get_task(task['id'])
    for key in ('revision','requirements','configuration','workflow_plan','artifact','runs','requirements_confirmed','configuration_confirmed'):
        assert saved.get(key) == before.get(key), key
    assert len(requests) == 1
    entries = main.budgets.get(task['id'])['entries']
    assert len(entries) == 1 and entries[0]['status'] == 'settled' and entries[0]['cost_basis'] == 'reported_usage'
