"""Inspect the real planning message path with fake provider output only."""
import json
from pathlib import Path
import pytest
from test_api import client,approved,planning_provider
from test_workflow_plan import base_plan
from test_agent_plan import prepare as agent_task
from app import main


@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_planning_uses_server_current_catalog_not_cross_app_inheritance(client,monkeypatch,mode):
    planning_provider(client);task=agent_task(client) if mode=='agent' else approved(client,app_type=mode);calls=[]
    expected=client.get('/api/capabilities',params={'app_type':mode}).json()
    plan={'schema_version':1,'scope':'text','system_prompt':'按已明确规则回答，不编造未提供事实。'} if mode=='agent' else base_plan(mode)
    async def controlled(provider,key,messages,**kwargs):
        calls.append(messages);context=json.loads(messages[1]['content']);catalog=context['capability_catalog']
        assert catalog==expected and catalog['app_type']==context['user_selected_type']==mode
        assert catalog['sierra_version']==main.app.version and catalog['verification']=='compiler_scope'
        assert 'capability_catalog' in messages[0]['content']
        types={n['type'] for n in catalog['root_nodes']}
        if mode=='workflow':assert 'human-input' in types and 'trigger-schedule' in types and catalog['file_workflows']
        elif mode=='advanced-chat':assert 'human-input' not in types and 'trigger-schedule' not in types and catalog['file_workflows'] is None
        else:assert not types and not catalog['containers'] and catalog['file_workflows'] is None and {s['scope'] for s in catalog['agent_scopes']}=={'text','knowledge'}
        assert '资源' in ''.join(catalog['notes'])
        return json.dumps(plan,ensure_ascii=False),{'prompt_tokens':90,'completion_tokens':40}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert response.status_code==200,response.text;result=response.json()
    assert len(calls)==1 and result['app_type']==mode and not result['configuration_confirmed']
    assert not result['artifact'] and not result['runs'] and not result.get('dify_app_id')
    assert result['agent_plan' if mode=='agent' else 'workflow_plan']==plan


def test_current_contract_reconciles_old_blanket_bans_without_enabling_general_execution():
    text=(Path(__file__).parents[2]/'docs/workflow-plan-contract.md').read_text('utf-8')
    assert 'server-generated capability_catalog' in text and 'later explicitly bounded extensions supersede older negative scope statements' in text
    assert 'human-input nodes and nested loops remain unsupported.' not in text
    assert 'human-input inside containers remain unsupported' in text
    assert 'Sierra upload/runtime ownership binding and actual file execution are still not implemented' not in text
    assert 'Sierra暂不导入运行此节点' not in text
    assert '独立确认动作' in text and 'generic file graphs still do not' in text
    assert 'separate approvals remain mandatory' in text
