import copy,json
import pytest
from test_api import client,create,forbid_api_external_calls
from app import main


def setup(client,count=123):
    task=create(client);task['messages']=[{'role':'user','content':f'公开原话{i}🙂\r\n'+('x'*1000),'context_revision':1} for i in range(count)];main.save_task(task)
    return main.get_task(task['id'])


def recent(client,task):return client.get(f"/api/tasks/{task['id']}?message_window=recent")
def cursor(meta):return {k:meta[k] for k in ('start','end','anchor_count','source_token')}
def read(client,task,meta,start,end,**kw):return client.post(f"/api/tasks/{task['id']}/history/window",json={'revision':task['revision'],'cursor':cursor(meta),'start':start,'end':end,**kw})


def test_opt_in_transport_window_preserves_old_full_read_and_store(client,monkeypatch):
    task=setup(client);before=main.store.get('task',task['id'])
    monkeypatch.setattr(main.store,'put',lambda *a,**k:pytest.fail('read must not write'))
    monkeypatch.setattr(main.store,'secret',lambda *a,**k:pytest.fail('read must not decrypt'))
    full=client.get('/api/tasks/'+task['id']);response=recent(client,task)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    value=response.json();meta=value['message_window'];assert len(full.json()['messages'])==123 and value['message_count']==123
    assert value['messages']==task['messages'][73:123] and meta['start']==73 and meta['end']==123 and meta['anchor_count']==123
    assert {k:v for k,v in value.items() if k not in ('messages','message_count','message_window')}=={k:v for k,v in task.items() if k!='messages'}
    assert len(response.content)<len(full.content)/2 and main.store.get('task',task['id'])==before


def test_all_previous_windows_exact_no_dropped_or_duplicate_indices(client):
    task=setup(client);meta=recent(client,task).json()['message_window'];parts=[task['messages'][73:]]
    response=read(client,task,meta,23,73);assert response.status_code==200;value=response.json();parts.insert(0,value['messages'])
    response=read(client,task,value,0,23);assert response.status_code==200;parts.insert(0,response.json()['messages'])
    assert sum(parts,[])==task['messages']
    assert not response.json()['task_modified'] and not response.json()['model_called'] and not response.json()['external_network_requested']


def test_append_allows_old_window_and_reports_new_total_without_expanding_anchor(client):
    task=setup(client);meta=recent(client,task).json()['message_window'];task['messages'].append({'role':'assistant','content':'追加'});main.save_task(task)
    response=read(client,task,meta,23,73);assert response.status_code==200
    assert response.json()['total_messages']==124 and response.json()['anchor_count']==123 and len(response.json()['messages'])==50
    latest=recent(client,task).json();assert latest['message_window']['start']==74 and latest['message_count']==124


def test_explicit_latest_reanchors_current_count_but_still_checks_held_source(client):
    task=setup(client);meta=recent(client,task).json()['message_window'];task['messages'].append({'role':'assistant','content':'新记录'});main.save_task(task)
    path=f"/api/tasks/{task['id']}/history/window"
    response=client.post(path,json={'revision':task['revision'],'cursor':cursor(meta),'latest':True});assert response.status_code==200
    result=response.json();assert result['start']==74 and result['end']==124 and result['anchor_count']==124
    assert result['state_sequence']>=meta['state_sequence']
    task['messages'][80]['content']='改持有窗';main.save_task(task)
    assert client.post(path,json={'revision':task['revision'],'cursor':cursor(meta),'latest':True}).status_code==409


def test_empty_known_window_can_explicitly_read_later_first_message(client):
    task=setup(client,0);meta=recent(client,task).json()['message_window'];task['messages'].append({'role':'user','content':'首次追加'});main.save_task(task)
    response=client.post(f"/api/tasks/{task['id']}/history/window",json={'revision':task['revision'],'cursor':cursor(meta),'latest':True})
    assert response.status_code==200 and response.json()['messages'][0]['content']=='首次追加'


@pytest.mark.parametrize('change',['body','labels','remove','revision','foreign','token'])
def test_changed_held_window_or_scope_rejected(client,change):
    task=setup(client);meta=recent(client,task).json()['message_window']
    if change=='body':task['messages'][80]['content']='PRIVATE CHANGE'
    if change=='labels':task['messages'][80]['purpose']='discussion'
    if change=='remove':task['messages'].pop()
    if change=='revision':task['revision']+=1
    if change in ('body','labels','remove','revision'):main.save_task(task)
    if change=='foreign':task=setup(client)
    if change=='token':meta['source_token']='0'*64
    response=read(client,task,meta,23,73,revision=meta['revision']);assert response.status_code==409
    assert 'PRIVATE CHANGE' not in response.text


def test_new_page_is_current_read_not_claimed_whole_history_snapshot(client):
    task=setup(client);meta=recent(client,task).json()['message_window'];task['messages'][5]['content']='当前新页的已修改原话';main.save_task(task)
    response=read(client,task,meta,0,50);assert response.status_code==200
    assert response.json()['messages'][5]['content']=='当前新页的已修改原话' and '不可变快照' in response.json()['note']


@pytest.mark.parametrize('change',['negative','bool','over50','past_anchor','bad_cursor','bool_cursor','empty','extra'])
def test_invalid_window_does_not_guess_positions(client,change):
    task=setup(client);meta=recent(client,task).json()['message_window'];body={'revision':task['revision'],'cursor':cursor(meta),'start':23,'end':73}
    if change=='negative':body['start']=-1
    if change=='bool':body['start']=False
    if change=='over50':body['start']=22
    if change=='past_anchor':body.update(start=122,end=124)
    if change=='bad_cursor':body['cursor']['unknown']='PRIVATE REQUEST'
    if change=='bool_cursor':body['cursor']['start']=True
    if change=='empty':body['start']=73
    if change=='extra':body['unknown']='PRIVATE REQUEST'
    response=client.post(f"/api/tasks/{task['id']}/history/window",json=body);assert response.status_code==422 and 'PRIVATE REQUEST' not in response.text


def test_empty_task_not_fabricated_and_unknown_get_mode_rejected(client):
    task=setup(client,0);response=recent(client,task);assert response.status_code==200
    value=response.json();assert value['messages']==[] and value['message_count']==0 and value['message_window']['start']==0
    assert read(client,task,value['message_window'],0,0).json()['messages']==[]
    invalid=client.get(f"/api/tasks/{task['id']}?message_window=PRIVATE_MODE");assert invalid.status_code==422 and 'PRIVATE_MODE' not in invalid.text


@pytest.mark.parametrize('raw',['{"revision":1,"revision":2,"private":"HIDDEN"}','{"revision":Infinity}','[]'])
def test_strict_json_no_echo(client,raw):
    task=setup(client);r=client.post(f"/api/tasks/{task['id']}/history/window",content=raw,headers={'Content-Type':'application/json'})
    assert r.status_code==422 and 'HIDDEN' not in r.text


def test_read_view_never_writes_window_metadata_into_saved_task(client):
    task=setup(client);before=main.store.get('task',task['id']);recent(client,task)
    assert main.store.get('task',task['id'])==before and 'message_window' not in before and 'message_count' not in before


def test_write_response_keeps_legacy_full_task_and_original_history(client):
    task=setup(client);recent(client,task)
    response=client.patch(f"/api/tasks/{task['id']}",json={'expected_revision':task['revision'],'requirements':{'goal':'新的公开需求'}})
    assert response.status_code==200,response.text
    value=response.json();assert 'message_window' not in value and 'message_count' not in value
    assert value['messages'][:123]==task['messages'] and len(value['messages'])>=123
    assert main.get_task(task['id'])['messages'][:123]==task['messages']
