import json
from test_api import client,approved
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
