import copy
import hashlib
import json
from uuid import uuid4

import pytest

from test_api import client, create, forbid_api_external_calls
from app import main
from app.mock_order import prepare, PREFIX
from app.plan_text_codec import render, parse
from app.workflow_plan import compile_workflow_plan

RECORDS = {'DEMO-001': '合成样例：已发货。', 'DEMO-002': '合成样例：退款审核中。'}


def context(mode='workflow'):
    return {'name': '订单模拟', 'app_type': mode, 'configuration': {'mock_dependencies': ['订单查询模拟']}}


def source(mode='workflow'):
    return {'schema_version': 1, 'nodes': [
        {'id': 'entry', 'type': 'start', 'config': {'variables': [
            {'variable': 'order_id', 'label': '订单号', 'type': 'text-input', 'required': False}]}},
        {'id': 'lookup', 'type': 'code', 'title': '原代码', 'config': {'code_language': 'python3',
            'code': 'def main(order_id: str) -> dict:\n    return {"result": "原逻辑"}\n',
            'variables': [{'variable': 'order_id', 'value_selector': ['entry', 'order_id']}],
            'outputs': {'result': {'type': 'string', 'children': None}}}},
        {'id': 'finish', 'type': 'answer', 'config': {'answer': '{{#lookup.result#}}'}} if mode == 'advanced-chat' else
        {'id': 'finish', 'type': 'end', 'config': {'outputs': [{'variable': 'result', 'value_selector': ['lookup', 'result']}]}}
    ], 'edges': [{'source': 'entry', 'target': 'lookup'}, {'source': 'lookup', 'target': 'finish'}]}


def proposal(task=None, plan=None, records=None, selector=None, node_id='lookup'):
    task = context() if task is None else task
    return prepare(task, render(source(task['app_type']) if plan is None else plan), node_id,
        ['entry', 'order_id'] if selector is None else selector,
        json.dumps(RECORDS if records is None else records, ensure_ascii=False), '订单查询模拟')


@pytest.mark.parametrize('mode,selector', [('workflow', ['entry', 'order_id']),
    ('advanced-chat', ['entry', 'order_id']), ('advanced-chat', ['sys', 'query'])])
def test_only_selected_config_changes_and_complete_native_export_is_valid(mode, selector):
    task = context(mode); original = source(mode); before = copy.deepcopy(original)
    result = proposal(task, original, selector=selector); changed = parse(result['plan_text'])
    changed['nodes'][1]['config'] = copy.deepcopy(original['nodes'][1]['config'])
    assert changed == before and original == before
    assert result['source_text_sha256'] == hashlib.sha256(render(original).encode()).hexdigest()
    assert result['proposal_sha256'] == hashlib.sha256(result['plan_text'].encode()).hexdigest()
    assert all(result[key] is False for key in ['task_changed', 'network_requested', 'code_executed', 'platform_checked', 'business_verified'])
    content, validation = compile_workflow_plan(task | {'workflow_plan': parse(result['plan_text'])})
    assert validation['valid'] and PREFIX in content


@pytest.mark.parametrize('order_id,status', [('DEMO-001', 'mock_found'), (' DEMO-002 ', 'mock_found'),
    ('UNKNOWN', 'mock_not_found'), ('demo-001', 'mock_not_found'), ('', 'mock_missing_order_id'),
    (' \t\n ', 'mock_missing_order_id'), (None, 'mock_missing_order_id')])
def test_reviewed_template_actually_returns_three_explicitly_simulated_results_locally(order_id, status):
    code = parse(proposal()['plan_text'])['nodes'][1]['config']['code']
    scope = {}; exec(compile(code, '<reviewed deterministic mock-order template>', 'exec'), scope)
    value = scope['main'](order_id)
    assert value['status'] == status and value['result'].startswith(PREFIX)
    if status == 'mock_found': assert value['result'] == PREFIX + RECORDS[order_id.strip()]
    if status == 'mock_not_found': assert '合成样例中没有' in value['result']


@pytest.mark.parametrize('value', [123, False, {}, []])
def test_template_does_not_convert_non_text_input_to_order_id(value):
    scope = {}; exec(parse(proposal()['plan_text'])['nodes'][1]['config']['code'], scope)
    with pytest.raises(ValueError, match='不自动转换'): scope['main'](value)


def test_quotes_and_code_like_record_text_remain_literal_data():
    text = '合成样例："引号"\n__import__("os").system("SHOULD_NEVER_RUN")'
    scope = {}; exec(parse(proposal(records={'DEMO-1': text})['plan_text'])['nodes'][1]['config']['code'], scope)
    assert scope['main']('DEMO-1')['result'] == PREFIX + text


@pytest.mark.parametrize('records', [{}, [], {'A': 7}, {'A': None}, {'A': ''}, {'A': 'x' * 501},
    {'has space': 'x'}, {'A': {}}, {str(i): 'x' for i in range(11)}])
def test_invalid_mock_tables_are_refused_without_partial_proposal(records):
    with pytest.raises(ValueError): proposal(records=records)


def test_duplicate_record_id_and_missing_declaration_are_refused():
    with pytest.raises(ValueError, match='重复'):
        prepare(context(), render(source()), 'lookup', ['entry', 'order_id'], '{"A":"first","A":"second"}', '订单查询模拟')
    with pytest.raises(ValueError, match='明确声明'): proposal(context() | {'configuration': {}})
    task = context(); task['configuration']['mock_dependency_bindings'] = [
        {'dependency': '订单查询模拟', 'node_id': 'elsewhere', 'replacement_todo': '保留原待办'}]
    with pytest.raises(ValueError, match='其它位置'): proposal(task)


@pytest.mark.parametrize('selector', [['sys', 'query'], ['entry', 'absent'], ['lookup', 'result']])
def test_unsupported_input_is_not_guessed(selector):
    with pytest.raises(ValueError, match='订单号只接受'): proposal(selector=selector)


def test_downstream_reference_incompatible_with_template_is_not_deleted():
    plan = source(); plan['nodes'][1]['config']['outputs']['original'] = {'type': 'string', 'children': None}
    plan['nodes'][2]['config']['outputs'][0]['value_selector'] = ['lookup', 'original']
    before = copy.deepcopy(plan)
    with pytest.raises(ValueError, match='下游输出引用不兼容'): proposal(plan=plan)
    assert plan == before


def payload(task):
    return {'revision': task['revision'], 'plan_text': render(source()), 'node_id': 'lookup',
        'input_selector': ['entry', 'order_id'], 'records_text': json.dumps(RECORDS),
        'dependency': '订单查询模拟', 'acknowledge_mock': True, 'request_nonce': str(uuid4())}


def test_actual_preview_api_is_readonly_and_candidate_can_be_manually_saved_built_downloaded(client):
    task = create(client); tid = task['id']
    task = client.patch('/api/tasks/' + tid, json={'requirements': {key: '明确的合成售后模拟规则' for key in main.REQ_KEYS},
        'configuration': {'mock_dependencies': ['订单查询模拟']}}).json()
    before = client.get('/api/tasks/' + tid).json()
    budgets_before = copy.deepcopy(main.store.list('task_budget'))
    response = client.post('/api/tasks/' + tid + '/mock-order-template', json=payload(task))
    assert response.status_code == 200, response.text
    candidate = response.json(); assert candidate['task_id'] == tid
    assert client.get('/api/tasks/' + tid).json() == before
    assert main.store.list('task_budget') == budgets_before
    assert client.post('/api/tasks/' + tid + '/confirm', json={'revision': task['revision'], 'kind': 'requirements'}).status_code == 200
    response = client.post('/api/tasks/' + tid + '/plan', json={'revision': task['revision'], 'plan': parse(candidate['plan_text'])})
    assert response.status_code == 200, response.text
    task = response.json()
    assert not task['configuration_confirmed'] and not task['artifact']
    assert client.post('/api/tasks/' + tid + '/confirm', json={'revision': task['revision'], 'kind': 'configuration'}).status_code == 200
    response = client.post('/api/tasks/' + tid + '/build', json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert PREFIX in client.get('/api/tasks/' + tid + '/artifact').text
    assert not client.get('/api/tasks/' + tid).json()['runs']


@pytest.mark.parametrize('mutation,status', [('no-ack', 422), ('stale', 409), ('extra', 422), ('no-declaration', 422)])
def test_rejected_preview_requests_do_not_write_or_dispatch(client, mutation, status):
    task = create(client)
    if mutation != 'no-declaration': task = client.patch('/api/tasks/' + task['id'], json={'configuration': {'mock_dependencies': ['订单查询模拟']}}).json()
    data = payload(task)
    if mutation == 'no-ack': data['acknowledge_mock'] = False
    if mutation == 'stale': data['revision'] += 1
    if mutation == 'extra': data['completed'] = True
    before = client.get('/api/tasks/' + task['id']).json()
    response = client.post('/api/tasks/' + task['id'] + '/mock-order-template', json=data)
    assert response.status_code == status and client.get('/api/tasks/' + task['id']).json() == before
