"""Declared simulated services must remain visible in every generated export."""
import copy
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.agent_plan import compile_agent_plan
from app.dsl import REQUIREMENT_KEYS, compile_dsl
from app.workflow_plan import compile_workflow_plan
from test_api import client, create, forbid_api_external_calls


DECLARATIONS = ["订单接口未提供；目前只采用公开固定样例，真实接入待办：补充订单查询服务。", "物流服务尚未接入。"]


def export_task(path):
    app_type = 'agent' if path == 'agent' else ('advanced-chat' if path.endswith('chat') else 'workflow')
    task = {'name': '模拟依赖交付核对', 'app_type': app_type,
            'requirements': {key: '只处理公开合成售后问题。' for key in REQUIREMENT_KEYS},
            'configuration': {'dify_model_provider': 'langgenius/deepseek/deepseek',
                              'dify_model': 'deepseek-flash', 'model_parameters': {'thinking': False},
                              'temperature': .2, 'max_tokens': 512, 'dataset_ids': []}}
    if path == 'agent':
        task['agent_plan'] = {'schema_version': 1, 'scope': 'text', 'system_prompt': '只按给定资料回答。'}
    elif path.startswith('explicit'):
        chat = app_type == 'advanced-chat'
        terminal = {'id': 'answer', 'type': 'answer', 'title': '答复', 'config': {'answer': '{{#llm.text#}}'}} if chat else {
            'id': 'end', 'type': 'end', 'title': '结束', 'config': {'outputs': [{'variable': 'result', 'value_selector': ['llm', 'text']}]}}
        task['workflow_plan'] = {'schema_version': 1, 'nodes': [
            {'id': 'start', 'type': 'start', 'title': '开始', 'config': {'variables': [] if chat else [
                {'variable': 'query', 'label': '问题', 'type': 'text-input', 'required': True}]}},
            {'id': 'llm', 'type': 'llm', 'title': '回答', 'config': {'system_prompt': '只按给定资料回答。',
                'user_prompt': '{{#sys.query#}}' if chat else '{{#start.query#}}'}}, terminal],
            'edges': [{'source': 'start', 'target': 'llm'}, {'source': 'llm', 'target': terminal['id']}]}
    return task


def compiler(path):
    return compile_agent_plan if path == 'agent' else (compile_workflow_plan if path.startswith('explicit') else compile_dsl)


@pytest.mark.parametrize('path', ['basic-workflow', 'basic-chat', 'explicit-workflow', 'explicit-chat', 'agent'])
def test_simulation_declarations_survive_export_without_changing_business_graph(path):
    task = export_task(path)
    baseline, clean_validation = compiler(path)(task)
    task['configuration']['mock_dependencies'] = copy.deepcopy(DECLARATIONS)
    before = copy.deepcopy(task)
    content, validation = compiler(path)(task)
    assert task == before and validation['valid']
    assert any('包含模拟依赖' in warning and '不能视为已连接或已验证' in warning for warning in validation['warnings'])
    actual, expected = yaml.safe_load(content), yaml.safe_load(baseline)
    descriptions = [actual['app']['description']]
    actual['app']['description'] = expected['app']['description']
    if path == 'agent':
        metadata = actual['agent_packages'][actual['agent']['package_ref']]['metadata']
        descriptions.append(metadata['description'])
        metadata['description'] = expected['agent_packages'][expected['agent']['package_ref']]['metadata']['description']
    for description in descriptions:
        assert '模拟依赖（未接入真实服务）' in description
        assert all(note in description for note in DECLARATIONS)
    assert actual == expected  # No added mock nodes, changed prompts, parameters or app type.
    assert not any('包含模拟依赖' in warning for warning in clean_validation['warnings'])
    task['configuration']['mock_dependencies'] = []
    assert compiler(path)(task) == (baseline, clean_validation)


@pytest.mark.parametrize('path', ['explicit-workflow', 'explicit-chat', 'agent'])
def test_api_build_and_download_keep_declared_simulation_visible(client, path):
    source = export_task(path)
    task = create(client, source['app_type'])
    tid = task['id']
    task = client.patch(f'/api/tasks/{tid}', json={'requirements': source['requirements'],
        'configuration': source['configuration'] | {'mock_dependencies': DECLARATIONS}}).json()
    assert client.post(f'/api/tasks/{tid}/confirm', json={'revision': task['revision'], 'kind': 'requirements'}).status_code == 200
    response = client.post(f'/api/tasks/{tid}/plan', json={'revision': task['revision'],
        'plan': source.get('agent_plan', source.get('workflow_plan'))})
    assert response.status_code == 200, response.text
    task = response.json()
    assert client.post(f'/api/tasks/{tid}/confirm', json={'revision': task['revision'], 'kind': 'configuration'}).status_code == 200
    response = client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    artifact = response.json()['artifact']
    assert artifact['verification'] == 'static_only'
    assert any('包含模拟依赖' in warning for warning in artifact['validation']['warnings'])
    exported = yaml.safe_load(client.get(f'/api/tasks/{tid}/artifact').text)
    assert exported['app']['mode'] == source['app_type']
    assert all(note in exported['app']['description'] for note in DECLARATIONS)
    report = client.get(f'/api/tasks/{tid}/report')
    assert report.status_code == 200 and all(note in report.text for note in DECLARATIONS)
    assert '按原确认范围替换并重新验证' in report.text
    assert '不能当真实依赖已经交付' in report.text
    persisted = main.store.get('task', tid)
    assert persisted['configuration']['mock_dependencies'] == DECLARATIONS
    assert not persisted['runs'] and not persisted.get('dify_app_id')
