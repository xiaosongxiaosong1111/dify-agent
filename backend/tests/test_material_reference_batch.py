import copy
import pytest
from test_api import client,forbid_api_external_calls
from test_material_upload_revision import setup,upload
from app import main

def data(client):
    task=setup(client)
    for _ in range(3):task=upload(client,task,task['revision']).json()
    items=[{'id':m['id'],'source_sha256':m['sha256'],'reference_mode':'preserve' if i==1 else 'borrow','preserve_items':'只保留公开术语' if i==1 else ''} for i,m in enumerate(task['materials'][:2])]
    return task,{'revision':task['revision'],'items':items}

def call(client,task,payload,apply=False):return client.post(f"/api/tasks/{task['id']}/materials/reference-batch/{'apply' if apply else 'preview'}",json=payload)

def test_explicit_preview_one_revision_write_and_originals_retained(client):
    task,payload=data(client);task.update(requirements_confirmed=True,configuration_confirmed=True);main.save_task(task);before=copy.deepcopy(main.store.get('task',task['id']));files={p.name:p.read_bytes() for p in (main.DATA_ROOT/task['id']/'materials').iterdir()}
    response=call(client,task,payload);assert response.status_code==200,response.text
    value=response.json();assert value['changed_count']==2 and not value['task_modified'] and not value['original_files_changed'] and main.store.get('task',task['id'])==before
    saved=call(client,task,{**payload,'review_token':value['review_token'],'acknowledge':True},True);assert saved.status_code==200,saved.text
    after=saved.json();assert after['revision']==task['revision']+1 and after['versions'][-1]['materials']==task['materials'] and after['materials'][2]==task['materials'][2]
    assert after['materials'][0]['reference_mode']=='borrow' and after['materials'][1]['preserve_items']=='只保留公开术语'
    assert not after['requirements_confirmed'] and not after['configuration_confirmed'] and after['requirements']==task['requirements']
    assert {p.name:p.read_bytes() for p in (main.DATA_ROOT/task['id']/'materials').iterdir()}==files
    assert call(client,task,{**payload,'review_token':value['review_token'],'acknowledge':True},True).status_code==409

@pytest.mark.parametrize('change',['text','partial_text','reference_mode','preserve_items','status','sha256','name'])
def test_source_changes_at_same_revision_invalidate_preview(client,change):
    task,payload=data(client);value=call(client,task,payload).json();task['materials'][0][change]='changed' if change!='reference_mode' else 'replicate';main.save_task(task);before=main.store.get('task',task['id'])
    assert call(client,task,{**payload,'review_token':value['review_token'],'acknowledge':True},True).status_code==409
    assert main.store.get('task',task['id'])==before

@pytest.mark.parametrize('invalid',['duplicate','missing','foreign_hash','no_choice','empty_preserve','long_note','extra','bad_revision','not_list'])
def test_bad_or_ambiguous_selections_do_not_write(client,invalid):
    task,payload=data(client);before=main.store.get('task',task['id'])
    if invalid=='duplicate':payload['items'].append(copy.deepcopy(payload['items'][0]))
    elif invalid=='missing':payload['items'][0]['id']='other-material'
    elif invalid=='foreign_hash':payload['items'][0]['source_sha256']='b'*64
    elif invalid=='no_choice':payload['items'][0]['reference_mode']=''
    elif invalid=='empty_preserve':payload['items'][1]['preserve_items']=' '
    elif invalid=='long_note':payload['items'][1]['preserve_items']='x'*301
    elif invalid=='extra':payload['extra']='PRIVATE_DO_NOT_ECHO'
    elif invalid=='bad_revision':payload['revision']=True
    else:payload['items']={}
    response=call(client,task,payload);assert response.status_code in {409,422} and 'PRIVATE_DO_NOT_ECHO' not in response.text
    assert main.store.get('task',task['id'])==before

def test_no_changes_ack_false_foreign_task_busy_and_append_semantics(client):
    task,payload=data(client);value=call(client,task,payload).json()
    denied=call(client,task,{**payload,'review_token':value['review_token'],'acknowledge':False},True);assert denied.status_code==422
    other=setup(client);assert call(client,other,{**payload,'revision':other['revision']}).status_code==409
    task['messages'].append({'role':'user','content':'追加原话'});main.save_task(task)
    assert call(client,task,payload).json()['review_token']==value['review_token']
    task['status']='planning';main.save_task(task);assert call(client,task,{**payload,'review_token':value['review_token'],'acknowledge':True},True).status_code==409
    task['status']='draft'
    for item in payload['items']:
        material=next(m for m in task['materials'] if m['id']==item['id']);material.update(reference_mode=item['reference_mode'],preserve_items=item['preserve_items'])
    main.save_task(task);before=main.store.get('task',task['id']);same=call(client,task,payload).json();assert same['changed_count']==0
    assert call(client,task,{**payload,'review_token':same['review_token'],'acknowledge':True},True).status_code==422 and main.store.get('task',task['id'])==before

def test_strict_json_and_unparsed_source_not_upgraded(client):
    task,payload=data(client);task['materials'][0].update(status='needs_input',text='',error='未解析');main.save_task(task);value=call(client,task,payload).json();after=call(client,task,{**payload,'review_token':value['review_token'],'acknowledge':True},True).json()
    assert after['materials'][0]['status']=='needs_input' and after['materials'][0]['text']==''
    path=f"/api/tasks/{task['id']}/materials/reference-batch/preview"
    for raw in ['{"revision":1,"revision":2}','{"revision":NaN}','x'*16385]:assert client.post(path,content=raw,headers={'content-type':'application/json'}).status_code==422
