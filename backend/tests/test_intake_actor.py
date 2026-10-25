"""Delegated review provenance through changed requirements and later re-review."""
import copy
import pytest
from test_intake import client, new, manual, state, forbid_intake_external_calls
from app import main
from app.intake import context, sources, digest, model_sources

NOTE='依据用户常规工作委托，核对既有说明，不代表新增人类答复。'

def test_delegated_review_keeps_provenance_in_current_and_archived_context(client):
    task=new(client)
    first=manual(client,task,actor='agent_delegated',actor_note=NOTE)
    assert first.status_code==200,first.text
    saved=first.json(); record=saved['intake_review']
    assert record['source']=='agent_declared' and record['review_actor']=='agent_delegated'
    assert record['actor_note']==NOTE and not saved['requirements_confirmed']
    assert '代理受托复核' in saved['messages'][-1]['content']
    assert '人类签收' in saved['messages'][-1]['content']
    current=state(client,saved)
    assert current['can_confirm'] and not current['stale']
    assert record['context_digest']==digest(saved)
    assert context(saved)['agent_declared_answers'][0]['actor_note']==NOTE
    assert all('代理受托复核' in v for (kind,_),v in sources(saved).items() if kind=='decision')
    assert any('代理受托复核' in row['text'] for row in model_sources(saved) if row['kind']=='decision')
    altered=copy.deepcopy(saved);altered['intake_review']['actor_note']='不同依据'
    assert digest(altered)!=digest(saved)
    confirmed=client.post(f"/api/tasks/{saved['id']}/confirm",json={'revision':saved['revision'],'kind':'requirements'})
    assert confirmed.status_code==200,confirmed.text
    changed=client.patch(f"/api/tasks/{saved['id']}",json={'requirements':{'output':'返回 result 字符串，前缀为结果：。'}}).json()
    again=manual(client,changed,actor='agent_delegated',actor_note=NOTE)
    assert again.status_code==200,again.text
    final=again.json()
    assert final['intake_history'][0]==record
    assert len(context(final)['agent_declared_answers'])==2
    assert not state(client,final)['stale'] and state(client,final)['can_confirm']
    assert not final['configuration_confirmed'] and not final['requirements_confirmed']

@pytest.mark.parametrize('fields',[
    {'actor':'agent_delegated'},
    {'actor':'agent_delegated','actor_note':'   '},
    {'actor':'human_signoff','actor_note':NOTE},
    {'actor':'agent_delegated','actor_note':'a'*1001},
    {'actor':'agent_delegated','actor_note':'password=EXAMPLE_FAKE_SECRET_ONLY'},
])
def test_invalid_delegated_review_is_rejected_without_mutation(client,fields):
    task=new(client);before=copy.deepcopy(main.get_task(task['id']))
    response=manual(client,task,**fields)
    assert response.status_code==422,response.text
    assert main.get_task(task['id'])==before

def test_default_manual_review_remains_user_declaration_and_fresh(client):
    task=new(client);saved=manual(client,task).json()
    assert saved['intake_review']['source']=='user_declared'
    assert 'agent_declared_answers' not in context(saved)
    assert not state(client,saved)['stale'] and state(client,saved)['can_confirm']
    assert all(not v.startswith('【代理') for (kind,_),v in sources(saved).items() if kind=='decision')

def test_old_revision_token_cannot_replay_delegated_review(client):
    task=new(client);token=state(client,task)['context_token']
    assert manual(client,task,actor='agent_delegated',actor_note=NOTE).status_code==200
    before=copy.deepcopy(main.get_task(task['id']))
    response=manual(client,task,context_token=token,actor='agent_delegated',actor_note=NOTE)
    assert response.status_code==409
    assert main.get_task(task['id'])==before
