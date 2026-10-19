from test_api import restore_payload
import copy
import json

import pytest

from test_api import client, approved, create
from test_task_budget import provider
from test_planning import plan
from app import main
from app.case_proposals import case_key


def candidate(app_type='workflow', **changes):
    item = {'id': 'normal1', 'category': 'normal', 'purpose': '检查已声明规则，不证明完整业务质量。', 'source': {'field': 'rules', 'quote': '明确的测试规则'}, 'node_ids': [], 'case': {'name': '正常文字请求', 'input': {'query': '请按规则回答'}, 'required': True, 'expectation': {'mode': 'manual', 'description': '检查回答是否遵守已确认规则，不补造资料事实。'}}}
    item.update(changes)
    return {'schema_version': 1, 'items': [item], 'open_issues': [], 'notes': '仅候选，尚未试跑，语义质量需人工判断。'}


def save(task, value=None):
    value = value or candidate(task['app_type'])
    result = main.case_proposals.validate(task, value)
    assert result['valid'], result
    main.case_proposals.save(task, value)


def state(client, task):
    return client.get(f"/api/tasks/{task['id']}/case-proposal").json()


def adopt(client, task, **patch):
    record = state(client, task)['record']
    return client.post(f"/api/tasks/{task['id']}/case-proposal/adopt", json={'revision': task['revision'], 'proposal_id': record['id'], 'proposal_token': record['proposal_token'], 'item_ids': ['normal1'], 'acknowledge_review': True, **patch})


def test_generation_proposal_only_and_same_budget(client, monkeypatch):
    task = approved(client); p = provider(client)
    task = client.patch(f"/api/tasks/{task['id']}", json={'configuration': {'assistant_provider_id': p['id']}}).json()
    observed = []
    async def model(*args, **kwargs):
        observed.append(json.loads(args[2][1]['content']))
        return json.dumps(candidate()), {'prompt_tokens': 10, 'completion_tokens': 20}
    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f"/api/tasks/{task['id']}/case-proposal/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    new = response.json()
    assert not new['test_cases'] and new['revision'] == task['revision']
    assert new['requirements_confirmed'] and not new['runs']
    assert state(client, task)['can_adopt'] and new['planning_runs'][-1]['kind'] == 'cases'
    assert main.budgets.get(task['id'])['entries'][0]['kind'] == 'cases'
    assert 'assistant_provider_id' not in observed[0]['configuration']
    assert 'api_key' not in json.dumps(observed)


def test_append_selected_preserves_existing_and_invalidates(client):
    task = approved(client)
    old = {'id': 'handwritten', 'name': '人工样例', 'input': {'query': '人工原始输入'}, 'required': False, 'expectation': {'mode': 'equals', 'target': 'result', 'expected': '原始期望'}}
    task['test_cases'] = [old]; main.save_task(task)
    value = candidate(); other = copy.deepcopy(value['items'][0]); other.update(id='normal2'); other['case'].update(name='另一个候选', input={'query': '另外一个问题'}); value['items'].append(other)
    save(task, value)
    assert adopt(client, task, acknowledge_review=False).status_code == 422
    response = adopt(client, task); assert response.status_code == 200, response.text
    new = response.json()
    assert new['test_cases'][0] == old and len(new['test_cases']) == 2
    assert new['revision'] == task['revision'] + 1
    assert not new['requirements_confirmed'] and not new['configuration_confirmed'] and not new['runs']
    record = state(client, new)['record']; assert record['status'] == 'adopted' and record['selected_item_ids'] == ['normal1']
    assert len(record['added_case_ids']) == 1 and new['test_cases'][-1]['id'] == record['added_case_ids'][0]
    assert adopt(client, new).status_code == 409
    assert '验收样例建议记录' in client.get(f"/api/tasks/{task['id']}/report").text
    assert not client.get(f"/api/tasks/{task['id']}/acceptance").json()['all_required_passed']


@pytest.mark.parametrize('selected', [[], ['unknown'], ['normal1', 'normal1']])
def test_invalid_selection_rejected(client, selected):
    task = approved(client); save(task)
    assert adopt(client, task, item_ids=selected).status_code == 422
    assert not main.get_task(task['id'])['test_cases']


@pytest.mark.parametrize('change', ['requirements', 'configuration', 'cases', 'environment', 'restore'])
def test_stale_proposal_cannot_adopt(client, change):
    task = approved(client); save(task)
    if change in {'requirements', 'configuration'}:
        task = client.patch(f"/api/tasks/{task['id']}", json={change: {'goal': '需求改变'} if change == 'requirements' else {'temperature': .5}}).json()
    elif change == 'cases':
        case = {**candidate()['items'][0]['case'], 'input': {'query': '新手工样例'}}
        task = client.post(f"/api/tasks/{task['id']}/test-cases", json={'revision': task['revision'], 'cases': [case]}).json()
    elif change == 'environment':
        from test_api import create_env
        env = create_env(client); task['environment_id'] = env['id']; main.save_task(task)
    else:
        assert client.post(f"/api/tasks/{task['id']}/restore", json=restore_payload(client, task['id'], task['versions'][0]['id'])).status_code == 200
        task = main.get_task(task['id'])
    assert state(client, task)['stale'] and adopt(client, task).status_code == 409


def test_open_issues_retained_and_block_adoption(client):
    task = approved(client); value = candidate(); value['open_issues'] = [{'question': '无资料应怎样回复？', 'recommendation': '先明确规则再确认。'}]; save(task, value)
    assert not state(client, task)['can_adopt'] and adopt(client, task).status_code == 409


@pytest.mark.parametrize('mutation', ['source', 'node', 'branch', 'target', 'input', 'missing_input', 'required', 'case_id', 'duplicate', 'bad_manual', 'conversation_id', 'numeric_input'])
def test_fabricated_source_contract_and_bad_cases_rejected(client, mutation):
    task = approved(client); value = candidate(); item = value['items'][0]; case = item['case']
    if mutation == 'source': item['source']['quote'] = '编造的资料事实'
    elif mutation == 'node': item['node_ids'] = ['made-up']
    elif mutation == 'branch': item['category'] = 'branch'
    elif mutation == 'target': case['expectation'] = {'mode': 'contains', 'target': 'invented', 'expected': ['词']}
    elif mutation == 'input': case['input']['made-up'] = '值'
    elif mutation == 'missing_input': case['input'] = {}
    elif mutation == 'required': case['required'] = False
    elif mutation == 'case_id': case['id'] = 'overwrite'
    elif mutation == 'duplicate': value['items'].append(copy.deepcopy(item))
    elif mutation == 'bad_manual': case['expectation']['description'] = ''
    elif mutation == 'conversation_id': case['input']['conversation_id'] = 'forged'
    else: case['input']['query'] = 3
    assert not main.case_proposals.validate(task, value)['valid']


def test_plan_contract_actual_variables_and_outputs(client):
    task = approved(client); value = plan(); value['nodes'][0]['config']['variables'][0]['variable'] = 'text'
    # Contract uses the persisted IR here; this test does not execute that code.
    task['workflow_plan'] = value
    contract = main.case_proposals.contract(task)
    assert list(contract['inputs']) == ['text'] and contract['outputs'] == ['result']
    assert len(contract['nodes']) == len(value['nodes'])
    draft = candidate(); case = draft['items'][0]['case']; case['input'] = {'text': '输入'}
    case['expectation'] = {'mode': 'equals', 'target': 'result', 'expected': '输出'}
    assert main.case_proposals.validate(task, draft)['valid']
    case['input'] = {'query': '错误入口'}
    assert not main.case_proposals.validate(task, draft)['valid']


@pytest.mark.parametrize('app_type', ['advanced-chat', 'agent'])
def test_multi_turn_contract(client, app_type):
    if app_type == 'agent':
        task = create(client, app_type)
        task['requirements'] = {k: '明确的测试规则' for k in main.REQ_KEYS}
    else:
        task = approved(client, app_type=app_type)
    value = candidate(app_type, category='conversation')
    value['items'][0]['case']['followups'] = [{'input': {'query': '接着上一轮的问题'}, 'expectation': {'mode': 'manual', 'description': '检查按已确认规则衔接，无记忆时不编造前文。'}}]
    assert main.case_proposals.validate(task, value)['valid']
    value['items'][0]['case']['followups'][0]['input']['conversation_id'] = 'forged'
    assert not main.case_proposals.validate(task, value)['valid']


def test_workflow_multiturn_rejected(client):
    task = approved(client); value = candidate(category='conversation'); value['items'][0]['case']['followups'] = [{'input': {'query': '后续'}, 'expectation': {'mode': 'manual', 'description': '人工规则'}}]
    assert not main.case_proposals.validate(task, value)['valid']


def test_no_duplicate_saved_cases(client):
    task = approved(client); value = candidate(); task['test_cases'] = [{**value['items'][0]['case'], 'id': 'old'}]
    assert not main.case_proposals.validate(task, value)['valid']


def test_pause_keeps_candidate_without_adoption(client, monkeypatch):
    task = approved(client); provider(client)
    async def model(*a, **kw):
        main.pause(task['id']); return json.dumps(candidate()), {'prompt_tokens': 10, 'completion_tokens': 20}
    monkeypatch.setattr(main, 'call_model', model)
    result = client.post(f"/api/tasks/{task['id']}/case-proposal/generate", json={'revision': task['revision']})
    assert result.status_code == 422
    assert not main.get_task(task['id'])['test_cases'] and not state(client, task)['record']
    assert main.budgets.get(task['id'])['entries'][0]['status'] == 'settled'


def test_generation_requires_confirmation_and_current_plan(client, monkeypatch):
    task = create(client); provider(client)
    async def forbidden(*a, **kw): raise AssertionError('不应调用模型')
    monkeypatch.setattr(main, 'call_model', forbidden)
    result = client.post(f"/api/tasks/{task['id']}/case-proposal/generate", json={'revision': task['revision']}); assert result.status_code == 422
    task = approved(client); task['plan_stale'] = True; main.save_task(task)
    result = client.post(f"/api/tasks/{task['id']}/case-proposal/generate", json={'revision': task['revision']}); assert result.status_code == 422


def test_cross_task_and_busy_adoption(client):
    one, two = approved(client), approved(client); save(one); record = state(client, one)['record']
    assert client.post(f"/api/tasks/{two['id']}/case-proposal/adopt", json={'revision': two['revision'], 'proposal_id': record['id'], 'proposal_token': record['proposal_token'], 'item_ids': ['normal1'], 'acknowledge_review': True}).status_code == 409
    one['status'] = 'running'; main.save_task(one); assert adopt(client, one).status_code == 409


def test_reference_requires_current_overlay(client):
    task = approved(client); task['dsl_reference'] = {'id': 'reference'}; main.save_task(task)
    value = state(client, task); assert value['blocker'] and not value['contract']
    assert not main.case_proposals.validate(task, candidate())['valid']


def test_final_preserved_dsl_output_used_not_old_ir(client):
    from test_dsl_roundtrip import prepared, capture, apply
    import yaml
    task, root = prepared(client)
    node = next(n for n in root['workflow']['graph']['nodes'] if n['data']['type'] == 'end')
    node['data']['outputs'][0]['variable'] = 'renamed_result'
    task = capture(client, task, root)
    response, _ = apply(client, task); assert response.status_code == 200, response.text
    task = response.json()
    assert main.case_proposals.contract(task)['outputs'] == ['renamed_result']
    value = candidate(); value['items'][0]['case']['expectation'] = {'mode': 'contains', 'target': 'result', 'expected': ['词']}
    assert not main.case_proposals.validate(task, value)['valid']
    value['items'][0]['case']['expectation']['target'] = 'renamed_result'
    assert main.case_proposals.validate(task, value)['valid']
    save(task, value)
    path = main.DATA_ROOT / task['id'] / task['dsl_overlay']['filename']
    path.write_text(yaml.safe_dump(root) + '\n# test change\n', encoding='utf-8')
    # Digest is structural; comments alone do not change the final contract.
    assert not state(client, task)['stale']
    changed = copy.deepcopy(root)
    next(n for n in changed['workflow']['graph']['nodes'] if n['data']['type'] == 'end')['data']['outputs'][0]['variable'] = 'other'
    path.write_text(yaml.safe_dump(changed), encoding='utf-8')
    assert state(client, task)['stale'] and adopt(client, task).status_code == 409


def test_branch_reference_requires_real_condition_node(client):
    task = approved(client); task['workflow_plan'] = plan()
    task['workflow_plan']['nodes'].append({'id': 'decision', 'type': 'if-else', 'config': {}})
    value = candidate(category='branch', node_ids=['decision'])
    assert main.case_proposals.validate(task, value)['valid']


def test_budget_stop_before_dispatch(client, monkeypatch):
    task = approved(client); provider(client)
    ledger = main.budgets.get(task['id']); ledger['limit_usd'] = '0'; main.store.put('task_budget', task['id'], ledger)
    async def forbidden(*a, **kw): raise AssertionError('预算耗尽不能派发模型')
    monkeypatch.setattr(main, 'call_model', forbidden)
    result = client.post(f"/api/tasks/{task['id']}/case-proposal/generate", json={'revision': task['revision']})
    assert result.status_code == 422 and not state(client, task)['record']
    assert not main.budgets.get(task['id'])['entries']


def test_invalid_candidate_retained_and_no_retry(client, monkeypatch):
    task = approved(client); provider(client); calls = []
    value = candidate(); value['items'][0]['source']['quote'] = '伪造原文'
    async def model(*a, **kw):
        calls.append(True); return json.dumps(value), {'prompt_tokens': 10, 'completion_tokens': 20}
    monkeypatch.setattr(main, 'call_model', model)
    result = client.post(f"/api/tasks/{task['id']}/case-proposal/generate", json={'revision': task['revision']})
    assert result.status_code == 422 and len(calls) == 1
    new = main.get_task(task['id']); assert not new['test_cases'] and not state(client, new)['record']
    assert new['planning_runs'][-1]['last_candidate'] == value
