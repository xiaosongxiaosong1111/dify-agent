"""Inspect the real planning message path with fake provider output only."""
import copy
import json
from pathlib import Path
import pytest
from test_api import client,approved,planning_provider
from test_workflow_plan import base_plan
from test_agent_plan import prepare as agent_task
from app import main
from test_intake import forbid_intake_external_calls
from app.storage import Store


@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_planning_uses_server_current_catalog_not_cross_app_inheritance(client,monkeypatch,mode):
    planning_provider(client);task=agent_task(client) if mode=='agent' else approved(client,app_type=mode);calls=[]
    expected=client.get('/api/capabilities',params={'app_type':mode}).json()
    plan=copy.deepcopy(task['agent_plan']) if mode=='agent' else base_plan(mode)
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


@pytest.mark.parametrize(('mode', 'goal', 'reason', 'recommendation'), [
    ('workflow', '按会话保存用户偏好并在后续对话沿用。',
     '当前Workflow不支持持久对话状态。', '保留Workflow并由用户每次明确传入偏好；若必须自动沿用，请另行选择Chatflow新建任务。'),
    ('advanced-chat', '每天上午九点自动生成报告。',
     '当前Chatflow不支持定时触发入口。', '保留Chatflow由用户手动发起；若必须定时，请另行选择Workflow新建任务。'),
    ('agent', '用自定义业务工具查询订单并提交人工审核。',
     '当前原生Agent未适配自定义工具与人工介入。', '保留Agent仅提供文字指引并由人工查询审核；若需要流程节点，请另行选择Workflow新建任务。'),
], ids=['workflow-conversation-state', 'chatflow-schedule', 'agent-tools-review'])
def test_at05_unsuitable_type_explains_options_and_waits_without_adoption(
    client, monkeypatch, tmp_path, mode, goal, reason, recommendation,
):
    planning_provider(client)
    task = agent_task(client) if mode == 'agent' else approved(client, app_type=mode)
    task = client.patch(f"/api/tasks/{task['id']}", json={'requirements': {'goal': goal}}).json()
    if mode != 'agent':
        response = client.post(f"/api/tasks/{task['id']}/plan", json={
            'revision': task['revision'], 'plan': base_plan(mode),
        })
        assert response.status_code == 200, response.text
        task = response.json()
    before = copy.deepcopy(client.get(f"/api/tasks/{task['id']}").json())
    calls = []
    questions = [{'question': '接受保留当前类型的人工方案，还是另行选择类型新建任务？',
                  'recommendation': recommendation, 'reason': reason,
                  'experience': '人工方案需要用户主动操作，无法自动完成原目标。',
                  'cost': '真实模型与运行费用尚未核对，不因此批准调用。',
                  'manual_work': '需用户明确选择范围，并自行完成人工步骤。'}]
    usage = {'prompt_tokens': 90, 'completion_tokens': 40}

    async def controlled(provider, key, messages, **kwargs):
        context = json.loads(messages[1]['content'])
        calls.append(context)
        assert context['user_selected_type'] == context['capability_catalog']['app_type'] == mode
        assert context['requirements']['goal'] == goal
        assert '问题和建议不是用户确认，不自动填答案' in messages[0]['content']
        assert any('用户选择的应用类型不自动改变' in note for note in context['capability_catalog']['notes'])
        return json.dumps({'error': reason, 'needs_decision': questions}, ensure_ascii=False), usage

    monkeypatch.setattr(main, 'call_model', controlled)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422 and '没有自动删减功能' in response.json()['detail']
    assert len(calls) == 1
    saved = client.get(f"/api/tasks/{task['id']}").json()
    for field in ('revision', 'app_type', 'requirements', 'configuration', 'requirements_confirmed',
                  'configuration_confirmed', 'confirmations', 'workflow_plan', 'agent_plan',
                  'plan_stale', 'plan_source', 'artifact', 'runs', 'versions', 'dify_app_id'):
        assert saved.get(field) == before.get(field), field
    assert saved['status'] == 'paused'
    record = client.get(f"/api/tasks/{task['id']}/planning").json()['runs'][-1]
    assert record['revision'] == task['revision'] and record['status'] == 'paused'
    assert record['stop_reason'] == 'needs_decision' and len(record['attempts']) == 1
    assert record['attempts'][0]['usage'] == usage and 'last_candidate' not in record
    assert record['decision_report'] == {
        'schema_version': 1, 'verification': 'model_clarification_only', 'message': reason,
        'questions': questions, 'incomplete': False, 'format_valid': True,
    }
    assert Store(tmp_path).get('task', task['id']) == saved
    ledger = copy.deepcopy(main.budgets.get(task['id']))
    assert len(ledger['entries']) == 1
    assert not saved['artifact'] and not saved['runs'] and not saved.get('dify_app_id')
    assert client.get(f"/api/tasks/{task['id']}/artifact").status_code == 404
    assert client.get(f"/api/tasks/{task['id']}").json() == saved
    assert main.budgets.get(task['id']) == ledger and len(calls) == 1

    # Only a user's explicit requirement edit changes scope; old revisions cannot replan it.
    changed = client.patch(f"/api/tasks/{task['id']}", json={
        'requirements': {'goal': '仅提供文字说明，由用户手动完成操作。'},
    }).json()
    assert changed['app_type'] == mode and changed['revision'] > task['revision']
    assert not changed['requirements_confirmed'] and not changed['configuration_confirmed']
    assert client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']}).status_code == 409
    assert client.get(f"/api/tasks/{task['id']}").json() == changed
    assert main.budgets.get(task['id']) == ledger and len(calls) == 1
