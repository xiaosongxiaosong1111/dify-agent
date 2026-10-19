import copy
from test_api import client
from test_material_text import unread,payload
from app import main


def path(task,m):return f"/api/tasks/{task['id']}/materials/{m['id']}/text-draft"
def body(task,m,rev=0,**values):return {'revision':task['revision'],'draft_revision':rev,'source_sha256':m['sha256'],'text':'尚未写完：','coverage_note':'',**values}


def test_partial_draft_persists_without_task_changes_and_repeat_is_idempotent(client):
    task,m=unread(client);before=main.get_task(task['id']);url=path(task,m)
    assert client.get(url).json()['draft_revision']==0
    response=client.put(url,json=body(task,m));assert response.status_code==200,response.text
    state=response.json();assert state['draft_revision']==1 and state['record']['status']=='unconfirmed'
    assert state['record']['text']=='尚未写完：' and state['record']['coverage_note']==''
    assert state['can_restore_text'] and not state['revision_changed']
    assert client.put(url,json=body(task,m,1)).json()==state
    assert client.get(url).json()==state and main.get_task(task['id'])==before
    assert '尚未写完：' not in str(main.get_task(task['id'])['materials'])


def test_cas_failure_and_deleted_tombstone_prevent_old_client_aba_overwrite(client):
    task,m=unread(client);url=path(task,m)
    first=client.put(url,json=body(task,m)).json()
    assert client.put(url,json=body(task,m,0,text='旧客户端想覆盖')).status_code==409
    delete={k:v for k,v in body(task,m,1).items() if k not in {'text','coverage_note'}}
    removed=client.request('DELETE',url,json=delete).json();assert removed['draft_revision']==2 and removed['record'] is None
    next_state=client.put(url,json=body(task,m,2,text='明确新草稿')).json();assert next_state['draft_revision']==3
    assert client.put(url,json=body(task,m,first['draft_revision'],text='旧版本碰巧数字相同')).status_code==409
    assert client.get(url).json()['record']['text']=='明确新草稿'


def test_task_revision_change_retains_source_bound_text_but_requires_current_revision_for_writes(client):
    task,m=unread(client);url=path(task,m);client.put(url,json=body(task,m))
    revised=client.patch(f"/api/tasks/{task['id']}/materials/{m['id']}",json={'reference_mode':'borrow'}).json()
    state=client.get(url).json();assert state['revision_changed'] and state['can_restore_text']
    assert client.put(url,json=body(task,m,1)).status_code==409
    assert client.put(url,json=body(revised,m,1,coverage_note='补充范围')).status_code==200


def test_cross_task_material_access_cannot_read_or_write_another_draft(client):
    task,m=unread(client);other,other_m=unread(client);url=path(task,m);client.put(url,json=body(task,m))
    wrong=path(other,m);assert client.get(wrong).status_code==404
    assert client.put(wrong,json=body(other,m)).status_code==404
    assert client.get(path(other,other_m)).json()['record'] is None


def test_source_mismatch_and_active_material_disable_restore_without_deleting_saved_text(client):
    task,m=unread(client);url=path(task,m);client.put(url,json=body(task,m))
    assert client.put(url,json=body(task,m,1,source_sha256='0'*64)).status_code==409
    active=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json=payload(task,m)).json()
    state=client.get(url).json();assert state['record']['text']=='尚未写完：' and not state['can_restore_text']
    assert client.put(url,json=body(active,m,1)).status_code==422


def test_oversize_draft_is_rejected_without_silently_truncating_saved_copy(client):
    task,m=unread(client);url=path(task,m);first=client.put(url,json=body(task,m)).json()
    assert client.put(url,json=body(task,m,1,text='x'*100001)).status_code==422
    assert client.get(url).json()==first


def test_saved_draft_is_not_model_context_or_accepted_material(client):
    from app.material_text import source_metadata
    task,m=unread(client);client.put(path(task,m),json=body(task,m,text='未经采用的草稿不进访谈'))
    saved=main.get_task(task['id']);assert saved['materials'][0]['status']=='needs_input' and saved['materials'][0]['text']==''
    assert source_metadata(saved['materials'][0])['source_file_parsed'] is False
    assert not saved['requirements_confirmed'] and not saved['configuration_confirmed']


def test_development_origin_put_preflight_is_supported_without_widening_origins(client):
    response=client.options('/api/tasks/placeholder/plan-draft',headers={'Origin':'http://127.0.0.1:5173','Access-Control-Request-Method':'PUT','Access-Control-Request-Headers':'Content-Type'})
    assert response.status_code==200 and response.headers['access-control-allow-origin']=='http://127.0.0.1:5173'
    assert client.options('/api/tasks/placeholder/plan-draft',headers={'Origin':'https://unknown.example','Access-Control-Request-Method':'PUT'}).status_code==400
