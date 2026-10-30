import json
from test_planning import run, USAGE, plan
from app.providers import ProviderError
from test_api import client, approved, planning_provider, forbid_api_external_calls
from app import main
from test_workflow_plan import base_plan


def test_each_return_keeps_its_own_excerpt_after_json_repair():
    first = '{"nodes":'
    second = json.dumps(plan(), ensure_ascii=False)
    result, op, calls, reason = run([(first, USAGE), (second, USAGE)])
    assert result and reason is None and len(calls) == 2
    assert op['attempts'][0]['response_excerpt'] == first
    assert op['attempts'][1]['response_excerpt'] == second
    assert op['last_response_excerpt'] == second
    assert all(attempt['response_truncated'] is False for attempt in op['attempts'])


def test_truncation_belongs_to_each_response_and_final_compatibility_field_is_unchanged():
    first='公开合成畸形响应'+('x'*17000)
    second=json.dumps(plan(),ensure_ascii=False)
    result,op,calls,reason=run([(first,USAGE),(second,USAGE)])
    assert result and reason is None and len(calls)==2
    assert op['attempts'][0]['response_excerpt']==first[:16000] and op['attempts'][0]['response_truncated'] is True
    assert op['attempts'][1]['response_excerpt']==second and op['attempts'][1]['response_truncated'] is False
    assert op['last_response_excerpt']==second and op['response_truncated'] is False


def test_invalid_returns_keep_distinct_source_when_no_progress_stops():
    first='{"nodes":'
    second='{\n "nodes":'
    result,op,calls,reason=run([(first,USAGE),(second,USAGE)])
    assert result is None and reason=='no_progress' and len(calls)==2
    assert [row['response_excerpt'] for row in op['attempts']]==[first,second]
    assert all(row['usage']==USAGE for row in op['attempts'])


def test_preflight_and_provider_failure_do_not_invent_response_text():
    result,op,calls,reason=run([],settings={'max_retries':3,'max_minutes':1,'max_cost_usd':.001})
    assert result is None and reason=='cost_limit' and not calls
    assert all('response_excerpt' not in row for row in op['attempts'])
    result,op,calls,reason=run([ProviderError('公开失败',usage=USAGE)])
    assert result is None and reason=='provider_error' and len(calls)==1
    assert all('response_excerpt' not in row for row in op['attempts'])


def test_api_serializes_each_attempt_excerpt_and_keeps_separate_usage(client, monkeypatch):
    planning_provider(client);task=approved(client);tid=task['id'];responses=['{"nodes":',json.dumps(base_plan(),ensure_ascii=False)];calls=[]
    async def fake(*args,**kwargs):
        calls.append(args[2]);return responses[len(calls)-1],USAGE
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(f'/api/tasks/{tid}/plan/generate',json={'revision':task['revision']})
    assert response.status_code==200,response.text
    op=response.json()['planning_runs'][-1]
    assert len(calls)==2 and [row['response_excerpt'] for row in op['attempts']]==responses
    assert op['last_response_excerpt']==responses[-1]
    assert all(row['usage']==USAGE for row in op['attempts'])
    assert len(main.budgets.get(tid)['entries'])==2
