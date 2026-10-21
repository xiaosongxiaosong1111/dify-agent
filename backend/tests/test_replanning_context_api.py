"""Actual regeneration messages under isolated provider transport."""
import copy,json
import pytest
from test_api import client,approved,planning_provider
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
