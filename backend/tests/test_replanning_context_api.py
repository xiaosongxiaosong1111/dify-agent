"""Actual regeneration messages under isolated provider transport."""
import copy,json
import pytest
from test_api import client,approved,planning_provider,forbid_api_external_calls
from test_workflow_plan import base_plan
from app import main


def existing_task(client):
    planning_provider(client)
    task=approved(client)
    plan=base_plan('workflow')
    plan['nodes'][0]['config']['variables'][0]['type']='paragraph'
    plan['nodes'][1]['config']['model']={
        'provider':'test/provider','name':'test-model','mode':'chat',
        'completion_params':{'temperature':0.2,'max_tokens':512,'thinking':False}}
    task=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan}).json()
    previous=copy.deepcopy(task)
    task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'output':'只改无命中提示，其他输入、模型及流程保持。'}}).json()
    assert task['plan_stale'] and not task['requirements_confirmed'] and not task['configuration_confirmed']
    return task,previous,plan


@pytest.mark.parametrize('needs_decision',[False,True])
def test_saved_graph_and_actual_input_change_reach_regeneration_without_platform_calls(client,monkeypatch,needs_decision):
    task,previous,plan=existing_task(client);calls=[]
    async def controlled(provider,key,messages,**kwargs):
        calls.append(messages)
        context=json.loads(messages[1]['content']);existing=context['existing_plan_context']
        assert existing['plan']==plan and existing['stale']
        assert existing['baseline_revision']==previous['revision']
        assert existing['previous_requirements']==previous['requirements']
        assert existing['changed_requirements_fields']==['output']
        assert existing['changed_configuration_fields']==[]
        assert context['requirements']==task['requirements']
        assert '只改当前明确变更' in messages[0]['content'] and 'needs_decision' in messages[0]['content']
        assert 'test-only' not in messages[1]['content']
        result={'error':'现有分支无法判断目标范围，需明确目标节点。','needs_decision':['修改哪个提示节点？']} if needs_decision else plan
        return json.dumps(result,ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert response.status_code==(422 if needs_decision else 200),response.text
    current=client.get(f"/api/tasks/{task['id']}").json();assert len(calls)==1
    assert current['workflow_plan']==plan and not current['artifact'] and not current['dify_app_id'] and not current['runs']
    assert not current['configuration_confirmed']
    if needs_decision:
        assert current['revision']==task['revision'] and current['plan_stale']
        assert current['planning_runs'][-1]['stop_reason']=='needs_decision'
    else:
        assert not current['plan_stale'] and current['revision']==task['revision']+1
    assert current['planning_runs'][-1]['attempts'][0]['usage']['prompt_tokens']==100


def test_chatflow_replanning_includes_all_interview_edits_since_graph_became_stale(client, monkeypatch):
    planning_provider(client)
    task = approved(client, app_type='advanced-chat')
    path = f"/api/tasks/{task['id']}"
    plan = base_plan('advanced-chat')
    response = client.post(f'{path}/plan', json={'revision': task['revision'], 'plan': plan})
    assert response.status_code == 200, response.text
    original = task = response.json()
    edits = [
        ('output', '无答案时提示请联系人工客服。'),
        ('rules', '模拟订单查询缺少订单号时继续追问。'),
    ]
    patches = iter(edits)
    candidate = copy.deepcopy(plan)
    candidate['nodes'][1]['config']['system_prompt'] = '\n'.join(text for _, text in edits)
    contexts = []

    async def controlled(provider, key, messages, **kwargs):
        if messages[1]['content'].startswith('当前任务资料：'):
            field, text = next(patches)
            assert text in messages[-1]['content']
            result = {'message': '已记录本轮改动。', 'requirements_patch': {field: text}}
        else:
            contexts.append(json.loads(messages[1]['content']))
            result = candidate
        return json.dumps(result, ensure_ascii=False), {'prompt_tokens': 100, 'completion_tokens': 30}

    monkeypatch.setattr(main, 'call_model', controlled)
    for _, content in edits:
        response = client.post(f'{path}/messages', json={'revision': task['revision'], 'content': content})
        assert response.status_code == 200, response.text
        task = response.json()
        assert task['plan_stale'] and task['workflow_plan'] == plan
        assert not task['requirements_confirmed'] and not task['configuration_confirmed']

    response = client.post(f'{path}/plan/generate', json={'revision': task['revision']})
    assert response.status_code == 422, response.text  # A changed candidate awaits explicit adoption.
    assert len(contexts) == 1
    sent = contexts[0]
    baseline = sent['existing_plan_context']
    assert baseline['plan'] == plan and baseline['baseline_revision'] == original['revision']
    assert baseline['previous_requirements'] == original['requirements']
    assert baseline['changed_requirements_fields'] == ['output', 'rules']
    assert sent['requirements'] == {**original['requirements'], **dict(edits)}

    saved = client.get(path).json()
    assert saved['revision'] == task['revision'] and saved['workflow_plan'] == plan
    assert saved['planning_runs'][-1]['stop_reason'] == 'replanning_review'
    assert saved['planning_runs'][-1]['last_candidate'] == candidate
    assert not saved['artifact'] and not saved['runs']
