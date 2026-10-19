import copy,json
import pytest
from test_api import client
from test_image_preview import setup,prepare
from test_image_execution import ack,route,RESULT
from app import main


def ready(client,monkeypatch):
    t,m,p=setup(client);r=prepare(client,t,m,p).json()['record']
    async def controlled(*a,**kw):return json.dumps(RESULT),{'prompt_tokens':100,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    r=client.post(route(t,m,'execute'),json=ack(t,r)).json()['record']
    return t,m,r

def url(t,m,r):return route(t,m,r['id']+'/review-draft')
def payload(t,m,**kw):return {'revision':t['revision'],'draft_revision':0,'source_sha256':m['sha256'],'text':'未写完的人工修订','coverage_note':'右侧待补充',**kw}


def test_image_review_draft_survives_reload_without_task_or_candidate_mutation(client,monkeypatch):
    t,m,r=ready(client,monkeypatch);before=main.get_task(t['id']);plan=main.store.get('image_preview',r['id']);budget=main.budgets.get(t['id'])
    response=client.put(url(t,m,r),json=payload(t,m));assert response.status_code==200,response.text
    state=response.json();assert state['draft_revision']==1 and state['can_restore_text']
    assert state['record']['candidate_token']==r['candidate_token'] and state['record']['plan_id']==r['id']
    assert client.get(url(t,m,r)).json()==state
    assert client.put(url(t,m,r),json=payload(t,m,draft_revision=1)).json()['draft_revision']==1
    assert main.get_task(t['id'])==before and main.store.get('image_preview',r['id'])==plan and main.budgets.get(t['id'])==budget
    assert client.put(url(t,m,r),json=payload(t,m,text='覆盖另一页')).status_code==409
    deleted=client.request('DELETE',url(t,m,r),json={k:v for k,v in payload(t,m,draft_revision=1).items() if k not in ('text','coverage_note')}).json()
    assert deleted['draft_revision']==2 and deleted['record'] is None
    assert client.put(url(t,m,r),json=payload(t,m,draft_revision=1)).status_code==409
    assert client.put(url(t,m,r),json=payload(t,m,draft_revision=2,text='',coverage_note='')).json()['draft_revision']==3


@pytest.mark.parametrize('change',['wrong_owner','no_candidate','source','revision','adopted'])
def test_image_review_draft_binding_blocks_unrelated_or_stale_writes(client,monkeypatch,change):
    t,m,r=ready(client,monkeypatch)
    if change in ('wrong_owner','no_candidate','adopted'):
        record=main.store.get('image_preview',r['id'])
        if change=='wrong_owner':record['material_id']='another'
        elif change=='no_candidate':record.pop('candidate')
        else:record['status']='adopted'
        main.store.put('image_preview',r['id'],record)
    elif change=='source':m['sha256']='b'*64
    else:
        current=main.get_task(t['id']);main.invalidate(current,'fixture');main.save_task(current)
    before=main.get_task(t['id']);response=client.put(url(t,m,r),json=payload(t,m))
    assert response.status_code in (404,409,422),response.text
    assert main.get_task(t['id'])==before and not main.store.list('image_review_draft')


def test_old_revision_draft_is_only_text_recovery_and_candidate_change_disables_restore(client,monkeypatch):
    t,m,r=ready(client,monkeypatch);assert client.put(url(t,m,r),json=payload(t,m)).status_code==200
    current=main.get_task(t['id']);main.invalidate(current,'fixture');main.save_task(current)
    state=client.get(url(t,m,r)).json();assert state['revision_changed'] and state['can_restore_text']
    record=main.store.get('image_preview',r['id']);record['candidate_token']='different-candidate';main.store.put('image_preview',r['id'],record)
    assert not client.get(url(t,m,r)).json()['can_restore_text']
