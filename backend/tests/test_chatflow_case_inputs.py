import copy
import pytest
from test_api import client, approved
from test_chatflow_inputs import runtime, configured
from app import main


def case():
    return {'id':'stable','name':'客户参数固定的追问','required':True,
            'input':{'query':'先回答问题','budget':0},
            'expectation':{'mode':'equals','target':'answer','expected':'第一轮'},
            'followups':[{'input':{'query':'继续上一轮','budget':0},
                          'expectation':{'mode':'equals','target':'answer','expected':'第二轮'}}]}


def prepared(client, value=None):
    task=runtime(client);task['test_cases']=[value or case()];main.save_task(task)
    return task


def run(client,task):
    return client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'case_id':'stable'})


def test_custom_fixed_case_sends_exact_values_in_fresh_then_same_conversation(client,monkeypatch):
    task=prepared(client);seen=[];original=copy.deepcopy(task['test_cases'])
    async def chat(self,query,inputs=None,conversation_id=None):
        seen.append((query,copy.deepcopy(inputs),conversation_id))
        return {'answer':'第一轮' if len(seen)==1 else '第二轮','conversation_id':conversation_id or 'fresh-stable'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=run(client,task);assert response.status_code==200,response.text
    assert seen==[('先回答问题',{'budget':0},None),('继续上一轮',{'budget':0},'fresh-stable')]
    value=response.json();record=value['runs'][-1]
    assert record['evaluation']['status']=='passed' and record['result']['complete']
    assert value['test_cases']==original and record['test_case']==original[0]
    assert all('region' not in turn['input'] for turn in record['result']['turns'])


@pytest.mark.parametrize('values',[
    {'query':'继续上一轮'}, {'query':'继续上一轮','budget':True},
    {'query':'继续上一轮','budget':'0'}, {'query':'继续上一轮','budget':1},
    {'query':'继续上一轮','budget':0,'region':'无此选项'},
    {'query':'继续上一轮','budget':0,'extra':'PRIVATE-VALUE'},
    {'query':'继续上一轮','budget':0,'region':None},
    {'query':'继续上一轮','budget':0,'conversation_id':'forged'},
])
def test_all_turns_checked_before_any_budget_pending_or_remote_dispatch(client,monkeypatch,values):
    value=case();value['followups'][0]['input']=values;task=prepared(client,value);before=copy.deepcopy(main.get_task(task['id']))
    def forbidden(*a,**kw):pytest.fail('所有轮次未通过前不能开始预算／创建待执行／派发')
    monkeypatch.setattr(main.execution_limits,'require_start',forbidden)
    monkeypatch.setattr(main.DifyClient,'run_chatflow',forbidden)
    response=run(client,task);assert response.status_code==422,response.text
    assert 'PRIVATE-VALUE' not in response.text and main.get_task(task['id'])==before


def test_explicit_optional_null_stays_null_in_each_turn_without_default_fill(client,monkeypatch):
    value=case();value['input']['region']=None;value['followups'][0]['input']['region']=None
    task=prepared(client,value);seen=[]
    async def chat(self,query,inputs=None,conversation_id=None):
        seen.append(copy.deepcopy(inputs));return {'answer':'第一轮' if len(seen)==1 else '第二轮','conversation_id':conversation_id or 'null-stable'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=run(client,task);assert response.status_code==200,response.text
    assert seen==[{'budget':0,'region':None}]*2


def test_pause_after_first_turn_keeps_checkpoint_and_never_dispatches_followup(client,monkeypatch):
    task=prepared(client);seen=[]
    async def chat(self,query,inputs=None,conversation_id=None):
        seen.append(query);current=main.get_task(task['id']);current['status']='paused';main.save_task(current)
        return {'answer':'第一轮','conversation_id':'paused-stable'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=run(client,task);assert response.status_code==502,response.text
    saved=main.get_task(task['id']);record=saved['runs'][-1]
    assert seen==['先回答问题'] and saved['status']=='paused'
    assert len(record['result']['turns'])==1 and not record['result']['complete'] and not record.get('evaluation')


@pytest.mark.parametrize('budget,valid',[(0,True),(1,False)])
def test_model_case_candidates_must_keep_declared_custom_parameters_stable(client,budget,valid):
    from test_case_proposals import candidate
    task=approved(client,app_type='advanced-chat');task['workflow_plan']=configured()['workflow_plan']
    value=candidate('advanced-chat',category='conversation');value['items'][0]['case']['input']={'query':'首轮','budget':0}
    value['items'][0]['case']['followups']=[{'input':{'query':'追问','budget':budget},'expectation':{'mode':'manual','description':'检查衔接'}}]
    checked=main.case_proposals.validate(task,value);assert checked['valid']==valid,checked
