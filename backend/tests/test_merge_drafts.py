import copy
import pytest
from test_api import client
from test_dsl_roundtrip import prepared,capture,changed
from test_parallel_preservation import parallel
from app import main
from app.storage import Store


def setup(client,is_parallel=True):
    t,root=prepared(client)
    if is_parallel:root,nid=parallel()
    else:root=changed(root);nid=None
    t=capture(client,t,root);p=client.get(f"/api/tasks/{t['id']}/dsl-merge").json()
    return t,p,nid


def save(client,t,p,nid,**patch):
    draft={nid:{'reason':'仍在核对共享状态、顺序与费用条件，尚未采用。','ack':False}} if nid else {}
    return client.put(f"/api/tasks/{t['id']}/dsl-merge/draft",json={'revision':t['revision'],'draft_revision':0,'reference_id':p['reference_id'],'document_token':p['document_token'],'choices':{},'parallel_draft':draft,**patch})


def read(client,t):return client.get(f"/api/tasks/{t['id']}/dsl-merge/draft").json()


def test_incomplete_independence_draft_persists_without_changing_task_or_confirming(client,monkeypatch):
    t,p,nid=setup(client);before=copy.deepcopy(main.get_task(t['id']))
    async def forbidden(*a,**kw):pytest.fail('保存草稿不调用模型')
    monkeypatch.setattr(main,'call_model',forbidden)
    response=save(client,t,p,nid);assert response.status_code==200,response.text
    record=response.json()['record'];assert record['verification']=='unconfirmed_local_draft' and not record['parallel_draft'][nid]['ack']
    assert main.get_task(t['id'])==before and not read(client,t)['stale']
    assert client.get(f"/api/tasks/{t['id']}/dsl-merge").json()['validation']['valid'] is False


def test_persistence_survives_store_reopen_and_does_not_clear_acknowledgement_requirements(client,monkeypatch):
    t,p,nid=setup(client);assert save(client,t,p,nid).status_code==200
    old=main.store;new=Store(old.root);monkeypatch.setattr(main,'store',new)
    assert read(client,t)['record']['parallel_draft'][nid]['reason']
    assert not client.get(f"/api/tasks/{t['id']}/dsl-merge").json()['validation']['valid']


@pytest.mark.parametrize('patch',[{'revision':-1},{'draft_revision':9},{'reference_id':'foreign'},{'document_token':'old'}])
def test_stale_or_foreign_write_does_not_replace_draft(client,patch):
    t,p,nid=setup(client);assert save(client,t,p,nid).status_code==200;before=read(client,t)['record']
    response=save(client,t,p,nid,**patch);assert response.status_code==409
    assert read(client,t)['record']==before


def test_draft_revision_controls_update_not_business_revision(client):
    t,p,nid=setup(client);assert save(client,t,p,nid).status_code==200
    response=save(client,t,p,nid,draft_revision=1,parallel_draft={nid:{'reason':'补充核对实际模型调用费用，仍是草稿。','ack':True}})
    assert response.status_code==200 and response.json()['draft_revision']==2
    assert main.get_task(t['id'])['revision']==t['revision'] and not client.get(f"/api/tasks/{t['id']}/dsl-merge").json()['validation']['valid']


@pytest.mark.parametrize('draft',[{'foreign':{'reason':'说明','ack':False}},{'batch':{'reason':'说明','ack':1}},{'batch':{'reason':'x'*2001,'ack':False}},{'batch':{'reason':'说明','ack':False,'unknown':True}}])
def test_unknown_container_or_malformed_values_rejected(client,draft):
    t,p,nid=setup(client);assert save(client,t,p,nid,parallel_draft=draft).status_code==422
    assert read(client,t)['record'] is None


def test_observed_secret_reason_not_stored_or_echoed(client):
    t,p,nid=setup(client);secret='sk-not-real-secret-1234567890'
    response=save(client,t,p,nid,parallel_draft={nid:{'reason':secret,'ack':False}})
    assert response.status_code==422 and secret not in response.text and read(client,t)['record'] is None


def test_saved_notes_become_read_only_when_reference_or_revision_changes(client):
    t,p,nid=setup(client);assert save(client,t,p,nid).status_code==200
    record=read(client,t)['record'];current=main.get_task(t['id']);main.invalidate(current,'隔离测试修订变化');main.save_task(current)
    result=read(client,t);assert result['stale'] and result['record']==record


def test_busy_task_refuses_draft_update_and_preserves_existing(client):
    t,p,nid=setup(client);assert save(client,t,p,nid).status_code==200
    current=main.get_task(t['id']);current['status']='running';main.save_task(current)
    assert save(client,t,p,nid,draft_revision=1).status_code==409
    assert read(client,t)['draft_revision']==1


def test_nonparallel_manual_merge_draft_remains_valid_local_progress(client):
    t,p,nid=setup(client,False);assert save(client,t,p,nid).status_code==200
    assert read(client,t)['record']['parallel_draft']=={} and main.get_task(t['id']).get('dsl_overlay') is None


def test_report_separates_unconfirmed_progress_from_preservation_approval(client):
    t,p,nid=setup(client);assert save(client,t,p,nid).status_code==200
    report=client.get(f"/api/tasks/{t['id']}/report")
    assert report.status_code==200 and '合并进度草稿（未确认）' in report.text
    assert 'unconfirmed_local_draft' in report.text and '仍在核对共享状态' in report.text
    assert main.get_task(t['id']).get('dsl_overlay') is None


def loop_setup(client):
    from test_preserved_loop import native
    t,_=prepared(client);t=capture(client,t,native());p=client.get(f"/api/tasks/{t['id']}/dsl-merge").json();return t,p


def test_incomplete_loop_rule_draft_is_progress_not_guard_approval(client):
    t,p=loop_setup(client)
    response=save(client,t,p,None,loop_draft={'repeat':{'reason':'','progress_variables':[],'no_progress_limit':2,'ack':False}})
    assert response.status_code==200,response.text
    assert read(client,t)['record']['loop_draft']['repeat']['progress_variables']==[]
    assert not client.get(f"/api/tasks/{t['id']}/dsl-merge").json()['validation']['valid'] and main.get_task(t['id']).get('dsl_overlay') is None


@pytest.mark.parametrize('value',[{'reason':'说明','progress_variables':['unknown'],'no_progress_limit':2,'ack':False},{'reason':'说明','progress_variables':['count','count'],'no_progress_limit':2,'ack':False},{'reason':'说明','progress_variables':['count'],'no_progress_limit':True,'ack':False},{'reason':'说明','progress_variables':['count'],'no_progress_limit':11,'ack':False},{'reason':'说明','progress_variables':['count'],'no_progress_limit':2,'ack':1}])
def test_invalid_loop_draft_does_not_enter_store(client,value):
    t,p=loop_setup(client);response=save(client,t,p,None,loop_draft={'repeat':value});assert response.status_code==422
    assert read(client,t)['record'] is None
