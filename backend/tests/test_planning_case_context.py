import copy
import json

import pytest

from test_api import client, approved, planning_provider, forbid_api_external_calls
from test_agent_plan import prepare as agent_task
from test_workflow_plan import base_plan
from test_planning import USAGE
from app import main


def example():
    return {'id': 'policy', 'name': '公开政策答复完整性', 'input': {'query': '请说明适用条件与政策编号。'},
            'expectation': {'mode': 'contains', 'target': 'answer', 'expected': ['政策编号', '适用条件', '结论']}, 'required': True}


def seed(client, mode='workflow', cases=None):
    planning_provider(client)
    task = agent_task(client) if mode == 'agent' else approved(client, app_type=mode)
    plan = copy.deepcopy(task['agent_plan']) if mode == 'agent' else base_plan(mode)
    if cases is not None:
        response = client.post(f"/api/tasks/{task['id']}/test-cases", json={'revision': task['revision'], 'cases': cases})
        assert response.status_code == 200, response.text
        task = response.json()
    return task, plan


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat', 'agent'])
def test_current_saved_cases_enter_normal_planning_with_revision_and_unverified_source(client, monkeypatch, mode):
    task, plan = seed(client, mode, [example()])
    calls = []
    async def fake(provider, key, messages, **kwargs):
        calls.append(messages)
        context = json.loads(messages[1]['content'])['acceptance_cases']
        assert context['source'] == 'current_saved_test_cases' and context['revision'] == task['revision']
        assert context['items'] == task['test_cases']
        assert context['case_count'] == context['turn_count'] == 1
        assert context['execution_verified'] is False and context['resource_permission_granted'] is False
        assert '不是事实来源' in messages[0]['content']
        return json.dumps(plan, ensure_ascii=False), USAGE
    monkeypatch.setattr(main, 'call_model', fake)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    actual = main.get_task(task['id'])
    assert len(calls) == 1 and actual['test_cases'] == task['test_cases']
    provenance = actual['planning_runs'][-1]['acceptance_cases']
    assert provenance['revision'] == task['revision'] and provenance['case_count'] == 1
    assert 'items' not in provenance and len(provenance['content_sha256']) == 64


def generate_with_context(client, monkeypatch, task, plan):
    seen = []
    async def fake(provider, key, messages, **kwargs):
        seen.append(json.loads(messages[1]['content'])['acceptance_cases'])
        return json.dumps(plan, ensure_ascii=False), USAGE
    monkeypatch.setattr(main, 'call_model', fake)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    return seen[0]


@pytest.mark.parametrize('mode', ['advanced-chat', 'agent'])
def test_followup_input_and_rule_stay_in_order_without_claiming_execution(client, monkeypatch, mode):
    case = example()
    case['followups'] = [{'input': {'query': '公开补充编号'}, 'expectation': {'mode': 'equals', 'target': 'answer', 'expected': '公开模拟结果'}}]
    case['required'] = False
    task, plan = seed(client, mode, [case])
    value = generate_with_context(client, monkeypatch, task, plan)
    assert value['items'] == [case] and value['turn_count'] == 2
    assert not value['truncated'] and not value['execution_verified']


def test_empty_saved_cases_do_not_invent_default_examples(client, monkeypatch):
    task, plan = seed(client)
    value = generate_with_context(client, monkeypatch, task, plan)
    assert value['items'] == [] and value['case_count'] == value['turn_count'] == 0
    assert main.get_task(task['id'])['test_cases'] == []


def test_current_projection_excludes_old_other_task_and_extra_result_metadata(client, monkeypatch):
    old = example(); old['input']['query'] = 'OLD-EXAMPLE-NOT-CURRENT'
    task, plan = seed(client, cases=[old])
    other = approved(client)
    other['test_cases'] = [dict(example(), name='OTHER-TASK-EXAMPLE')]
    main.store.put('task', other['id'], other)
    case = example(); case['saved_result'] = 'UNTRUSTED-PASSED'; case['expectation']['evidence'] = 'NOT-A-RUN'
    response = client.post(f"/api/tasks/{task['id']}/test-cases", json={'revision': task['revision'], 'cases': [case]})
    assert response.status_code == 200
    task = response.json()
    value = generate_with_context(client, monkeypatch, task, plan)
    assert value['items'] == [example()] and value['ignored_metadata_fields'] == 2
    assert all(marker not in json.dumps(value) for marker in ('OLD-EXAMPLE-NOT-CURRENT', 'OTHER-TASK-EXAMPLE', 'UNTRUSTED-PASSED', 'NOT-A-RUN'))
    assert main.get_task(task['id'])['test_cases'] == [case]


@pytest.mark.parametrize('bad', ['not_list', 'invalid', 'too_many', 'too_large', 'secret_key', 'secret_text'])
def test_bad_context_blocks_before_secret_read_operation_or_fee(client, monkeypatch, bad):
    task, _ = seed(client)
    cases = [example()]
    if bad == 'not_list': cases = None
    elif bad == 'invalid': cases[0]['expectation']['mode'] = 'not-a-mode'
    elif bad == 'too_many': cases = [dict(example(), id=str(i)) for i in range(31)]
    elif bad == 'too_large': cases[0]['input']['query'] = 'x' * 24001
    elif bad == 'secret_key': cases[0]['input']['password'] = 'PUBLIC-SENSITIVE-FIXTURE'
    elif bad == 'secret_text': cases[0]['input']['query'] = 'Bearer PUBLICONLY1234567890123456'
    task['test_cases'] = cases
    main.store.put('task', task['id'], task)
    before = main.store.get('task', task['id'])
    before_budget = main.store.get('task_budget', task['id'])
    def forbidden(*args, **kwargs): pytest.fail('Rejected examples must not read credentials or invoke a model')
    monkeypatch.setattr(main.store, 'secret', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422
    assert 'PUBLIC-SENSITIVE' not in response.text and 'PUBLICONLY' not in response.text
    assert main.store.get('task', task['id']) == before
    assert main.store.get('task_budget', task['id']) == before_budget


def test_invalid_unicode_has_fixed_error_without_echoing_text():
    from app.planning_case_context import current
    from fastapi import HTTPException
    case = example(); case['input']['query'] = '\ud800'
    with pytest.raises(HTTPException) as error:
        current({'revision': 1, 'app_type': 'workflow', 'test_cases': [case]})
    assert error.value.status_code == 422 and '\ud800' not in error.value.detail


def test_context_byte_and_case_limits_are_exact_without_truncation():
    from app.planning_case_context import current, MAX_BYTES, MAX_CASES
    from fastapi import HTTPException
    task = {'revision': 2, 'app_type': 'workflow', 'test_cases': [example()]}
    count = current(task)['json_bytes']
    task['test_cases'][0]['input']['query'] += 'x' * (MAX_BYTES - count)
    value = current(task)
    assert value['json_bytes'] == MAX_BYTES and not value['truncated']
    task['test_cases'][0]['input']['query'] += 'x'
    with pytest.raises(HTTPException): current(task)
    task['test_cases'] = [dict(example(), id=str(i)) for i in range(MAX_CASES)]
    assert current(task)['case_count'] == MAX_CASES
    task['test_cases'].append(dict(example(), id='extra'))
    with pytest.raises(HTTPException): current(task)


def test_structured_values_keep_json_types_and_stable_content_hash():
    from app.planning_case_context import current
    case = example()
    case['input'] = {'query': '公开结构样例', 'data': [1, False, None]}
    case['expectation'] = {'mode': 'equals', 'target': 'result', 'expected': {'ok': False, 'count': 1, 'value': None}}
    task = {'revision': 3, 'app_type': 'workflow', 'test_cases': [case]}
    before = copy.deepcopy(task)
    first = current(task)
    case['input'] = dict(reversed(list(case['input'].items())))
    second = current(task)
    assert first['content_sha256'] == second['content_sha256']
    assert first['items'] == before['test_cases'] and task == before
    assert first['items'][0]['expectation']['expected']['ok'] is False


def test_ignored_saved_metadata_is_not_sent_or_counted_as_example_content():
    from app.planning_case_context import current
    case = example(); case['old_run_metadata'] = 'not-current-evidence' * 2000
    value = current({'revision': 1, 'app_type': 'workflow', 'test_cases': [case]})
    assert value['ignored_metadata_fields'] == 1 and value['items'] == [example()]
    assert value['json_bytes'] < 1000 and not value['execution_verified']


def test_revision_change_keeps_current_cases_and_does_not_apply_old_model_candidate(client, monkeypatch):
    task, plan = seed(client, cases=[example()])
    original_revision = task['revision']
    async def fake(*args, **kwargs):
        current = main.get_task(task['id'])
        current['revision'] += 1
        current['test_cases'][0]['name'] = '新修订的当前样例'
        main.store.put('task', current['id'], current)
        return json.dumps(plan), USAGE
    monkeypatch.setattr(main, 'call_model', fake)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422
    actual = main.get_task(task['id']); op = actual['planning_runs'][-1]
    assert op['stop_reason'] == 'revision_changed' and op['acceptance_cases']['revision'] == original_revision
    assert actual['test_cases'][0]['name'] == '新修订的当前样例' and not actual.get('workflow_plan')
    assert main.budgets.get(task['id'])['entries'][0]['status'] == 'settled'


def test_optional_tool_followup_preserves_same_saved_example_context(client, monkeypatch):
    from test_planning_tools import setup, save, wire, reply, tool, generate
    from test_planning import plan
    task, _ = setup(client)
    task = client.post(f"/api/tasks/{task['id']}/test-cases", json={'revision': task['revision'], 'cases': [example()]}).json()
    assert save(client, task).status_code == 200
    calls = wire(monkeypatch, [reply(call=tool()), reply(json.dumps(plan()))])
    response = generate(client, task)
    assert response.status_code == 200, response.text
    assert len(calls) == 2
    first = json.loads(calls[0]['messages'][1]['content'])['acceptance_cases']
    second = json.loads(calls[1]['messages'][1]['content'])['acceptance_cases']
    assert first == second and first['items'] == [example()]
    assert response.json()['planning_runs'][-1]['acceptance_cases']['content_sha256'] == first['content_sha256']
    assert len(main.budgets.get(task['id'])['entries']) == 2
