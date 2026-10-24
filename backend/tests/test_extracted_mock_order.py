import copy
import json

import pytest
import yaml

from test_parameter_extractor import plan as extraction_plan
from test_mock_order import RECORDS, PREFIX
from test_api import client, create, forbid_api_external_calls
from app import main
from app.mock_order import prepare
from app.plan_text_codec import render, parse
from app.workflow_plan import validate_plan, compile_workflow_plan


def source(mode='advanced-chat'):
    value = extraction_plan(mode)
    node = next(n for n in value['nodes'] if n['id'] == 'success')
    node['type'] = 'code'
    node['config'] = {'code_language': 'python3', 'code': 'def main(order_id: str) -> dict:\n    return {"result": order_id}\n',
        'variables': [{'variable': 'order_id', 'value_selector': ['extract', 'order_no']}],
        'outputs': {'result': {'type': 'string', 'children': None}}}
    next(n for n in value['nodes'] if n['id'] == 'merge')['config']['variables'][0] = ['success', 'result']
    return value


def context(mode='advanced-chat'):
    return {'name': '提取订单号后模拟查询', 'app_type': mode, 'configuration': {
        'mock_dependencies': ['订单查询模拟'], 'dify_model_provider': 'langgenius/deepseek/deepseek',
        'dify_model': 'deepseek-flash', 'temperature': .2, 'max_tokens': 512, 'model_parameters': {'thinking': False}}}


def proposal(task, plan, selector=None, node='success'):
    return prepare(task, render(plan), node, ['extract', 'order_no'] if selector is None else selector,
                   json.dumps(RECORDS, ensure_ascii=False), '订单查询模拟')


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat'])
def test_extracted_string_connects_without_changing_success_check_or_failure_path(mode):
    task = context(mode); plan = source(mode); before = copy.deepcopy(plan)
    assert validate_plan(task, plan)['valid']
    value = proposal(task, plan); changed = parse(value['plan_text'])
    config = next(n for n in changed['nodes'] if n['id'] == 'success')['config']
    assert config['variables'] == [{'variable': 'order_id', 'value_selector': ['extract', 'order_no']}]
    scope = {}; exec(config['code'], scope)
    assert scope['main']('DEMO-001') == {'result': PREFIX + RECORDS['DEMO-001'], 'status': 'mock_found'}
    next(n for n in changed['nodes'] if n['id'] == 'success')['config'] = copy.deepcopy(before['nodes'][3]['config'])
    assert changed == before and plan == before
    dsl, validation = compile_workflow_plan(task | {'workflow_plan': parse(value['plan_text'])})
    assert validation['valid']
    native = yaml.safe_load(dsl)['workflow']['graph']
    assert next(n for n in native['nodes'] if n['id'] == 'failure')['data']['template'] == '请补充明确订单号。'
    check = next(n for n in native['nodes'] if n['id'] == 'check')['data']
    assert check['cases'][0]['conditions'][0]['variable_selector'] == ['extract', '__is_success']
    assert check['cases'][0]['conditions'][0]['value'] == '1'


@pytest.mark.parametrize('kind', ['number', 'boolean', 'array[string]'])
def test_non_text_extracted_parameter_is_not_converted(kind):
    plan = source()
    next(n for n in plan['nodes'] if n['id'] == 'extract')['config']['parameters'].append({
        'name': 'other', 'type': kind, 'description': '其它参数', 'required': False})
    with pytest.raises(ValueError): proposal(context(), plan, ['extract', 'other'])


@pytest.mark.parametrize('field', ['__is_success', '__reason', '__usage', 'missing'])
def test_extraction_status_and_unknown_fields_are_not_order_numbers(field):
    with pytest.raises(ValueError): proposal(context(), source(), ['extract', field])


def test_failure_branch_cannot_use_default_extracted_business_value():
    plan = source()
    failure = next(n for n in plan['nodes'] if n['id'] == 'failure')
    failure['type'] = 'code'
    failure['config'] = {'code_language': 'python3', 'code': 'def main() -> dict:\n    return {"result": "请补充订单号"}\n',
        'variables': [], 'outputs': {'result': {'type': 'string', 'children': None}}}
    next(n for n in plan['nodes'] if n['id'] == 'merge')['config']['variables'][1] = ['failure', 'result']
    assert validate_plan(context(), plan)['valid']
    original = copy.deepcopy(plan)
    with pytest.raises(ValueError): proposal(context(), plan, node='failure')
    assert plan == original


def test_common_merge_path_cannot_bypass_extractor_success_guard():
    plan = source(); end = plan['nodes'][-1]
    plan['nodes'].insert(-1, {'id': 'common', 'type': 'code', 'config': {'code_language': 'python3',
        'code': 'def main(result: str) -> dict:\n    return {"result": result}\n',
        'variables': [{'variable': 'result', 'value_selector': ['merge', 'output']}],
        'outputs': {'result': {'type': 'string', 'children': None}}}})
    next(e for e in plan['edges'] if e['source'] == 'merge')['target'] = 'common'
    plan['edges'].append({'source': 'common', 'target': end['id']});end['config']['answer'] = '{{#common.result#}}'
    assert validate_plan(context(), plan)['valid']
    with pytest.raises(ValueError): proposal(context(), plan, node='common')


def prepared(client):
    task = create(client, 'advanced-chat'); tid = task['id']
    task = client.patch('/api/tasks/' + tid, json={'requirements': {key: '明确的合成订单查询，提取失败必须追问' for key in main.REQ_KEYS},
        'configuration': context()['configuration']}).json()
    assert client.post('/api/tasks/' + tid + '/confirm', json={'revision': task['revision'], 'kind': 'requirements'}).status_code == 200
    response = client.post('/api/tasks/' + tid + '/plan', json={'revision': task['revision'], 'plan': source()})
    assert response.status_code == 200, response.text
    return response.json()


def test_actual_api_preview_save_build_keeps_extraction_failure_graph(client):
    task = prepared(client); tid = task['id']; original = client.get('/api/tasks/' + tid).json()
    from uuid import uuid4
    response = client.post('/api/tasks/' + tid + '/mock-order-template', json={
        'revision': task['revision'], 'plan_text': render(task['workflow_plan']), 'node_id': 'success',
        'input_selector': ['extract', 'order_no'], 'dependency': '订单查询模拟', 'records_text': json.dumps(RECORDS),
        'acknowledge_mock': True, 'request_nonce': str(uuid4())})
    assert response.status_code == 200, response.text
    assert client.get('/api/tasks/' + tid).json() == original
    response = client.post('/api/tasks/' + tid + '/plan', json={'revision': task['revision'], 'plan': parse(response.json()['plan_text'])})
    assert response.status_code == 200, response.text
    task = response.json()
    assert client.post('/api/tasks/' + tid + '/confirm', json={'revision': task['revision'], 'kind': 'configuration'}).status_code == 200
    response = client.post('/api/tasks/' + tid + '/build', json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert not response.json()['runs'] and not response.json()['dify_app_id']
    exported = client.get('/api/tasks/' + tid + '/artifact').text
    assert 'mock_found' in exported and '请补充明确订单号。' in exported
