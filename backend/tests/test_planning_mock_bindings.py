import copy
import json

import pytest

from test_api import client, create, planning_provider, forbid_api_external_calls
from test_mock_dependency_exports import export_task, compiler
from test_planning import USAGE
from app import main


DEPENDENCY = '公开模拟订单'


def seed(client, path, bindings):
    planning_provider(client)
    source = export_task(path)
    task = create(client, source['app_type'])
    response = client.patch(f"/api/tasks/{task['id']}", json={'requirements': source['requirements'], 'configuration': source['configuration'] | {'mock_dependencies': [DEPENDENCY], 'mock_dependency_bindings': bindings}})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': task['revision'], 'kind': 'requirements'})
    assert response.status_code == 200, response.text
    task = response.json()
    return task, copy.deepcopy(source.get('agent_plan', source.get('workflow_plan')))


def binding(node):
    return {'dependency': DEPENDENCY, 'node_id': node, 'replacement_todo': '补齐真实接口资料后另行核对接入。'}


def model(monkeypatch, candidate):
    calls = []
    text = json.dumps(candidate, ensure_ascii=False)
    async def fake(*args, **kwargs):
        calls.append(args[2])
        return text, USAGE
    monkeypatch.setattr(main, 'call_model', fake)
    return calls, text


@pytest.mark.parametrize('path', ['explicit-workflow', 'explicit-chat', 'agent'])
@pytest.mark.parametrize('problem', ['missing_node', 'removed_declaration'])
def test_current_binding_errors_stop_normal_plan_before_success_and_keep_fee(client, monkeypatch, path, problem):
    task, candidate = seed(client, path, [binding('deleted-node' if problem == 'missing_node' else ('agent.system_prompt' if path == 'agent' else 'llm'))])
    if problem == 'removed_declaration':
        task['configuration']['mock_dependencies'] = []
        main.store.put('task', task['id'], task)
    before = copy.deepcopy(task)
    calls, text = model(monkeypatch, candidate)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422
    actual = main.get_task(task['id'])
    op = actual['planning_runs'][-1]
    assert len(calls) == 1 and op['status'] == 'paused' and op['stop_reason'] == 'needs_decision'
    assert op['attempts'][0]['status'] == 'invalid'
    assert any(('当前成果中不存在' if problem == 'missing_node' else '不再对应当前声明') in error for error in op['diagnostics'])
    assert op['last_candidate'] == candidate and op['attempts'][0]['response_excerpt'] == text
    assert actual['revision'] == before['revision'] and actual['configuration'] == before['configuration']
    assert actual.get('workflow_plan') == before.get('workflow_plan') and actual.get('agent_plan') == before.get('agent_plan')
    assert not actual.get('artifact') and not actual.get('dify_app_id')
    entries = main.budgets.get(task['id'])['entries']
    assert len(entries) == 1 and entries[0]['status'] == 'settled' and entries[0]['usage'] == USAGE


@pytest.mark.parametrize('path', ['explicit-workflow', 'explicit-chat', 'agent'])
@pytest.mark.parametrize('with_binding', [False, True])
def test_valid_or_absent_binding_keeps_same_candidate_and_compilable_export(client, monkeypatch, path, with_binding):
    task, candidate = seed(client, path, [binding('agent.system_prompt' if path == 'agent' else 'llm')] if with_binding else [])
    calls, _ = model(monkeypatch, candidate)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    actual = main.get_task(task['id'])
    assert actual['agent_plan' if path == 'agent' else 'workflow_plan'] == candidate
    assert actual['configuration'] == task['configuration'] and actual['app_type'] == task['app_type']
    assert len(calls) == 1 and actual['planning_runs'][-1]['status'] == 'succeeded'
    _, checked = compiler(path)(actual)
    assert checked['valid']


def test_rejected_replanning_keeps_old_graph_and_confirmations(client, monkeypatch):
    task, candidate = seed(client, 'explicit-workflow', [binding('llm')])
    task['workflow_plan'] = copy.deepcopy(candidate)
    task['plan_source'] = 'manual'
    main.store.put('task', task['id'], task)
    candidate['nodes'][1]['id'] = 'new_llm'
    candidate['nodes'][-1]['config']['outputs'][0]['value_selector'][0] = 'new_llm'
    candidate['edges'] = [{'source': 'start', 'target': 'new_llm'}, {'source': 'new_llm', 'target': 'end'}]
    calls, _ = model(monkeypatch, candidate)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422
    actual = main.get_task(task['id'])
    assert actual['workflow_plan'] == task['workflow_plan'] and actual['revision'] == task['revision']
    assert actual['confirmations'] == task['confirmations'] and actual['configuration_confirmed'] == task['configuration_confirmed']
    assert len(calls) == 1 and 'scope_change_summary' not in actual['planning_runs'][-1]


@pytest.mark.parametrize('target', ['clean', 'batch__iteration_start'])
def test_container_body_binding_uses_existing_flattened_node_scope(client, monkeypatch, target):
    from test_iteration import batch_plan
    task, _ = seed(client, 'explicit-workflow', [binding(target)])
    candidate = batch_plan()
    calls, _ = model(monkeypatch, candidate)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    _, checked = compiler('explicit-workflow')(main.get_task(task['id']))
    assert checked['valid'] and len(calls) == 1


def test_loop_binding_ids_equal_actual_emitted_nodes():
    import yaml
    from test_loop import loop_plan, task
    from app.workflow_plan import compiled_node_ids, compile_workflow_plan
    plan = loop_plan()
    context = task(plan)
    content, checked = compile_workflow_plan(context)
    assert checked['valid']
    assert compiled_node_ids(context, plan) == {row['id'] for row in yaml.safe_load(content)['workflow']['graph']['nodes']}


def test_optional_tool_planning_uses_same_current_binding_gate(client, monkeypatch):
    from test_planning_tools import setup, save, reply, wire, generate
    from test_planning import plan
    task, _ = setup(client)
    response = client.patch(f"/api/tasks/{task['id']}", json={'configuration': {'mock_dependencies': [DEPENDENCY], 'mock_dependency_bindings': [binding('deleted-node')]}})
    assert response.status_code == 200
    task = response.json()
    assert save(client, task).status_code == 200
    calls = wire(monkeypatch, [reply(json.dumps(plan()))])
    response = generate(client, task)
    assert response.status_code == 422 and len(calls) == 1
    actual = main.get_task(task['id'])
    op = actual['planning_runs'][-1]
    assert op['status'] == 'paused' and op['attempts'][0]['status'] == 'invalid'
    assert any('当前成果中不存在' in error for error in op['diagnostics'])
    assert not actual.get('workflow_plan')
    assert len(main.budgets.get(task['id'])['entries']) == 1
