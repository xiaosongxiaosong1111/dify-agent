import copy
import pytest
from test_api import client
from test_intake import new,state,manual,review
from test_conversation_state import plan
from app.intake import topics,validate_review
from app import main


@pytest.mark.parametrize('app_type',['advanced-chat','workflow','agent'])
@pytest.mark.parametrize('text',['多轮对话计数达到三次转人工','持久对话变量保存客户已选择套餐'])
def test_explicit_state_business_request_adds_topic_without_changing_app_type(client,app_type,text):
    t=new(client,app_type);t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':{'rules':text}}).json()
    row=next(x for x in topics(t) if x['id']=='conversation_state')
    assert '重置' in row['question'] and '上限' in row['question'] and '不自动换类型' in row['question']
    assert main.get_task(t['id'])['app_type']==app_type
    assert not state(client,t)['can_confirm'] and not main.budgets.get(t['id'])['entries']


def test_non_state_text_task_does_not_acquire_persistent_state_questions(client):
    t=new(client);assert 'conversation_state' not in {r['id'] for r in topics(t)}


def test_draft_state_requires_special_review_and_old_review_is_stale_not_auto_upgraded(client):
    t=new(client,'advanced-chat');old=manual(client,t).json();assert state(client,old)['can_confirm']
    actual=main.get_task(t['id']);actual['workflow_plan']=plan();main.store.put('task',actual['id'],actual)
    value=state(client,actual);assert 'conversation_state' in {r['id'] for r in value['standard']}
    assert not value['can_confirm']
    missing=review(actual);missing['checks']=[r for r in missing['checks'] if r['topic']!='conversation_state']
    with pytest.raises(ValueError,match='逐项覆盖'):validate_review(actual,missing)
    before=copy.deepcopy(main.get_task(t['id']));state(client,actual);assert main.get_task(t['id'])==before


def test_explicit_state_gap_retains_recommendation_and_unresolved_gate(client):
    t=new(client,'advanced-chat');t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':{'rules':'会话状态计数每轮加一'}}).json()
    value=review(t,gap='conversation_state');validate_review(t,value)
    assert value['checks'][-1]['status']=='needs_input' and value['questions'][0]['topic']=='conversation_state'
    assert not state(client,t)['can_confirm']
