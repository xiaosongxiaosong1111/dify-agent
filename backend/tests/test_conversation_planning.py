import copy,json
import pytest
from test_api import client,approved,planning_provider
from test_conversation_consumers import consumers
from app import main
from app.planning import normalize_draft


@pytest.mark.parametrize('kind,value',[('number',0),('boolean',False),('string','')])
def test_missing_condition_type_uses_valid_declared_cv_without_changing_business_literals(kind,value):
    p=consumers();p['conversation_variables'][0].update(var_type=kind,initial_value=value)
    condition=p['nodes'][3]['config']['cases'][0]['conditions'][0];condition.pop('varType')
    before=copy.deepcopy(p);normalized,fixes=normalize_draft(p,_mode='advanced-chat')
    actual=normalized['nodes'][3]['config']['cases'][0]['conditions'][0]
    assert actual=={**condition,'varType':kind} and fixes and p==before
    assert normalized['conversation_variables']==p['conversation_variables']


@pytest.mark.parametrize('fault',['workflow','duplicate','missing_policy','namespace','existing_type','missing_nodes'])
def test_normalization_never_trusts_invalid_state_or_overwrites_explicit_type(fault):
    p=consumers();condition=p['nodes'][3]['config']['cases'][0]['conditions'][0];condition.pop('varType');mode='advanced-chat'
    if fault=='workflow':mode='workflow'
    elif fault=='duplicate':p['conversation_variables'].append(copy.deepcopy(p['conversation_variables'][0]))
    elif fault=='missing_policy':p['conversation_variables'][0].pop('unwritten_policy')
    elif fault=='namespace':p['nodes'][0]['id']='conversation'
    elif fault=='existing_type':condition['varType']='boolean'
    else:p['nodes']=None
    before=copy.deepcopy(p);normalized,fixes=normalize_draft(p,_mode=mode)
    assert normalized==p==before and not fixes


def test_declared_cv_type_reaches_container_normalization_without_faking_state_values():
    p=consumers();condition=copy.deepcopy(p['nodes'][3]);condition['config']['cases'][0]['conditions'][0].pop('varType')
    # Normalization proves only the field transform, not graph execution or validity.
    p['nodes'].append({'id':'batch','type':'iteration','config':{'nodes':[condition]}})
    before=copy.deepcopy(p);normalized,fixes=normalize_draft(p,_mode='advanced-chat')
    assert normalized['nodes'][-1]['config']['nodes'][0]['config']['cases'][0]['conditions'][0]['varType']=='number'
    assert any('迭代内部' in fix for fix in fixes) and p==before


def test_actual_planning_prompt_allows_declared_state_and_does_not_confirm_generated_business(client,monkeypatch):
    planning_provider(client);t=approved(client,app_type='advanced-chat');p=consumers();calls=[]
    p['nodes'][3]['config']['cases'][0]['conditions'][0].pop('varType')
    async def controlled_call(provider,key,messages,**kwargs):
        calls.append(messages);prompt=messages[0]['content']
        assert '只有schema_version,nodes,edges' not in prompt
        assert '仅Chatflow可按已明确需求增加conversation_variables声明' in prompt
        assert '不自动猜状态、初始值或保留政策' in prompt
        return json.dumps(p,ensure_ascii=False),{'prompt_tokens':90,'completion_tokens':50}
    monkeypatch.setattr(main,'call_model',controlled_call)
    response=client.post(f"/api/tasks/{t['id']}/plan/generate",json={'revision':t['revision']})
    assert response.status_code==200,response.text
    result=response.json();assert len(calls)==1
    assert result['workflow_plan']['conversation_variables']==p['conversation_variables']
    assert result['workflow_plan']['nodes'][3]['config']['cases'][0]['conditions'][0]['varType']=='number'
    assert not result['configuration_confirmed'] and not result['artifact'] and not result['runs']
    assert result['planning_runs'][-1]['attempts'][0]['deterministic_fixes']
