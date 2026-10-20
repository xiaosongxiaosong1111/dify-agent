import json
import pytest
from test_api import client,approved
from test_agent_plan import prepare as agent_task, PLAN as AGENT_PLAN
from test_workflow_plan import base_plan
from test_intake import forbid_intake_external_calls
from app import main


def test_current_scope_is_read_only_type_specific_and_not_live_resource_readiness(client):
    task=approved(client);before=main.get_task(task['id'])
    workflow=client.get('/api/capabilities',params={'app_type':'workflow'}).json()
    chatflow=client.get('/api/capabilities',params={'app_type':'advanced-chat'}).json()
    assert workflow['verification']=='compiler_scope' and workflow['sierra_version']==main.app.version
    assert workflow['target_dify_version']=='1.17.1'
    assert 'end' in [node['type'] for node in workflow['root_nodes']] and 'answer' not in [node['type'] for node in workflow['root_nodes']]
    assert 'assigner' in [node['type'] for node in chatflow['root_nodes']] and 'assigner' not in [node['type'] for node in workflow['root_nodes']]
    assert 'answer' in [node['type'] for node in chatflow['root_nodes']] and 'end' not in [node['type'] for node in chatflow['root_nodes']]
    for scope in workflow['containers']:
        sequence=[node['type'] for node in scope['sequence_nodes']];dag=[node['type'] for node in scope['dag_nodes']]
        assert 'knowledge-retrieval' in sequence and 'http-request' in sequence
        assert 'question-classifier' not in sequence and 'parameter-extractor' not in sequence
        assert 'question-classifier' in dag and 'parameter-extractor' in dag
        assert 'iteration' not in dag and 'loop' not in dag and 'document-extractor' in dag
    assert main.get_task(task['id'])==before
    assert not any(key in json.dumps(workflow) for key in ('api_key','credential-key','base_url','dataset_ids'))


def test_native_agent_is_not_described_as_a_workflow_with_arbitrary_tools(client):
    value=client.get('/api/capabilities',params={'app_type':'agent'}).json()
    assert value['root_nodes']==[] and value['containers']==[]
    assert {row['scope'] for row in value['agent_scopes']}=={'text','knowledge'}
    assert any('空自定义工具列表' in note for note in value['notes'])
    assert any('插件工具' in item for item in value['not_adapted'])


def test_missing_or_unknown_app_type_is_not_silently_assumed_workflow(client):
    assert client.get('/api/capabilities').status_code==422
    response=client.get('/api/capabilities',params={'app_type':'chatbot'})
    assert response.status_code==422 and '不会替换类型' in response.text


@pytest.mark.parametrize('selected', ['workflow', 'advanced-chat', 'agent'])
def test_at05_task_type_cannot_be_patched_even_to_a_supported_alternative(client, selected):
    task = agent_task(client) if selected == 'agent' else approved(client, app_type=selected)
    before = client.get(f"/api/tasks/{task['id']}").json()
    ledger = main.budgets.get(task['id'])
    for alternative in {'workflow', 'advanced-chat', 'agent'} - {selected}:
        response = client.patch(f"/api/tasks/{task['id']}", json={'app_type': alternative})
        assert response.status_code == 422, response.text
        assert client.get(f"/api/tasks/{task['id']}").json() == before
        assert main.budgets.get(task['id']) == ledger


@pytest.mark.parametrize(('selected', 'candidate_type', 'limitation'), [
    ('workflow', 'advanced-chat', 'workflow 计划终点只能使用 end'),
    ('advanced-chat', 'workflow', 'advanced-chat 计划终点只能使用 answer'),
    ('workflow', 'agent', 'workflow_plan.nodes 必须是非空数组'),
    ('advanced-chat', 'agent', 'workflow_plan.nodes 必须是非空数组'),
    ('agent', 'workflow', '未支持的功能不能静默忽略'),
    ('agent', 'advanced-chat', '未支持的功能不能静默忽略'),
])
def test_at05_foreign_type_plan_is_rejected_without_replacing_saved_plan(client, selected, candidate_type, limitation):
    task = agent_task(client) if selected == 'agent' else approved(client, app_type=selected)
    if selected != 'agent':
        response = client.post(f"/api/tasks/{task['id']}/plan", json={
            'revision': task['revision'], 'plan': base_plan(selected),
        })
        assert response.status_code == 200, response.text
        task = response.json()
    before = client.get(f"/api/tasks/{task['id']}").json()
    ledger = main.budgets.get(task['id'])
    candidate = AGENT_PLAN if candidate_type == 'agent' else base_plan(candidate_type)
    response = client.post(f"/api/tasks/{task['id']}/plan", json={
        'revision': task['revision'], 'plan': candidate,
    })
    assert response.status_code == 422 and limitation in response.json()['detail']
    assert client.get(f"/api/tasks/{task['id']}").json() == before
    assert main.budgets.get(task['id']) == ledger
