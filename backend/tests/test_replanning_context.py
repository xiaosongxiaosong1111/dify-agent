import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.planning_context import replanning_context


def source(mode='workflow'):
    key='agent_plan' if mode=='agent' else 'workflow_plan'
    plan={'schema_version':1,'nodes':[{'id':'reply','type':'llm','config':{'model':{'completion_params':{'thinking':False,'temperature':0.2}},'user_prompt':'保留原文'}}],'edges':[]}
    return {'app_type':mode,'revision':9,key:plan,'plan_stale':True,
            'requirements':{'output':'新版提示'},'configuration':{'max_tokens':512},
            'versions':[], 'messages':['not-for-context'], 'runs':[{'secret':'not-for-context'}],
            'materials':[{'text':'not-for-context'}],'secrets':'not-for-context'}


@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_complete_selected_plan_without_history_is_explicit_and_detached(mode):
    task=source(mode);key='agent_plan' if mode=='agent' else 'workflow_plan';before=copy.deepcopy(task)
    task['workflow_plan' if key=='agent_plan' else 'agent_plan']={'wrong':'other-type'}
    context=replanning_context(task)
    assert context['plan']==before[key] and context['stale'] and not context['baseline_available']
    assert 'previous_requirements' not in context and 'not-for-context' not in str(context)
    context['plan']['nodes'][0]['config']['model']['completion_params']['thinking']=True
    assert task[key]==before[key]


def test_latest_real_input_transition_not_newer_name_or_case_snapshot():
    task=source();plan=task['workflow_plan']
    old={'revision':4,'workflow_plan':copy.deepcopy(plan),'requirements':{'output':'更早提示'},'configuration':{'max_tokens':256}}
    prior={**copy.deepcopy(old),'revision':6,'requirements':{'output':'旧版提示'},'configuration':{'max_tokens':512}}
    same={**copy.deepcopy(prior),'revision':8,'name':'只是更名','requirements':copy.deepcopy(task['requirements'])}
    task['versions']=[old,prior,same];snapshot=copy.deepcopy(task)
    context=replanning_context(task)
    assert context['baseline_revision']==6 and context['changed_requirements_fields']==['output']
    assert context['changed_configuration_fields']==[] and context['previous_requirements']=={'output':'旧版提示'}
    context['previous_configuration']['max_tokens']=1
    assert task==snapshot


def test_foreign_plan_is_not_used_as_history_baseline():
    task=source();task['versions']=[{'revision':8,'workflow_plan':{'schema_version':1,'nodes':[]},'requirements':{'output':'陌生流程'}}]
    context=replanning_context(task)
    assert not context['baseline_available'] and 'previous_requirements' not in context


def test_same_inputs_can_be_baseline_without_invented_change():
    task=source();task['versions']=[{**copy.deepcopy(task),'revision':7}]
    context=replanning_context(task)
    assert context['baseline_revision']==7 and context['changed_requirements_fields']==context['changed_configuration_fields']==[]


@pytest.mark.parametrize('plan',[None,[],False])
def test_initial_generation_has_no_invented_existing_plan(plan):
    task=source();task['workflow_plan']=plan
    assert replanning_context(task) is None
