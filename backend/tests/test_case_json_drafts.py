import copy
import pytest
from test_api import client,approved,forbid_api_external_calls
from app import main
from app.storage import Store

def source(client,task):return client.get(f"/api/tasks/{task['id']}/test-cases/editor",params={'revision':task['revision']}).json()['source_token']
def read(client,task):return client.get(f"/api/tasks/{task['id']}/test-cases/draft",params={'revision':task['revision']})
def save(client,task,counter=0,text='[{"name":"未完成',token=None):return client.put(f"/api/tasks/{task['id']}/test-cases/draft",json={'revision':task['revision'],'draft_revision':counter,'source_token':token or source(client,task),'text':text})
def discard(client,task,counter):return client.request('DELETE',f"/api/tasks/{task['id']}/test-cases/draft",json={'revision':task['revision'],'draft_revision':counter})

def test_incomplete_text_survives_store_reopen_without_changing_task_or_budget(client,monkeypatch):
    task=approved(client);before=copy.deepcopy(task);budget=main.store.get('task_budget',task['id'])
    response=save(client,task);assert response.status_code==200,response.text
    assert response.json()['record']['text']=='[{"name":"未完成' and response.json()['draft_revision']==1
    monkeypatch.setattr(main,'store',Store(main.store.root))
    result=read(client,task);assert result.status_code==200,result.text
    assert result.json()['record']['text']=='[{"name":"未完成' and result.json()['stale'] is False
    assert main.get_task(task['id'])==before and main.store.get('task_budget',task['id'])==budget

def test_draft_cas_and_delete_tombstone_prevent_overwrite_or_resurrection(client):
    task=approved(client);first=save(client,task);assert first.status_code==200,first.text
    assert save(client,task,0,'[{"old":true}]').status_code==409
    assert discard(client,task,0).status_code==409
    removed=discard(client,task,1);assert removed.status_code==200 and removed.json()['record'] is None and removed.json()['draft_revision']==2
    assert save(client,task,1).status_code==409
    assert save(client,task,2,'[{"new":true}]').json()['draft_revision']==3

@pytest.mark.parametrize('change',['revision','cases','foreign'])
def test_stale_or_foreign_source_cannot_save_unconfirmed_text(client,change):
    task=approved(client);token=source(client,task)
    if change=='revision':task['revision']+=1
    elif change=='cases':task['test_cases']=[{'id':'public','name':'新样例','input':{},'expectation':{'mode':'manual','description':'公开核对'}}]
    else:task=approved(client)
    main.store.put('task',task['id'],task)
    result=save(client,task,token=token);assert result.status_code==409,result.text
    assert read(client,task).json()['record'] is None

def test_old_source_is_read_as_reference_and_never_automatically_applied(client):
    task=approved(client);assert save(client,task).status_code==200
    task['revision']+=1;main.store.put('task',task['id'],task);before=copy.deepcopy(task)
    result=read(client,task);assert result.status_code==200,result.text
    assert result.json()['stale'] is True and result.json()['record']['text']=='[{"name":"未完成'
    assert main.get_task(task['id'])==before

@pytest.mark.parametrize('text',['','   ','x'*2_000_001,'sk-SYNTHETIC-ONLY-PRIVATE-1234567890','{"api_key":"PRIVATE-CREDENTIAL-EXAMPLE"}'],ids=['empty','blank','oversize','key-pattern','credential-field'])
def test_empty_oversize_or_secret_text_not_saved(client,text):
    task=approved(client);result=save(client,task,text=text)
    assert result.status_code==422,result.text
    assert 'PRIVATE' not in result.text and read(client,task).json()['record'] is None

def test_bad_raw_unicode_rejected_and_valid_unicode_preserved(client):
    import json
    task=approved(client);token=source(client,task)
    payload={'revision':task['revision'],'draft_revision':0,'source_token':token,'text':'PRIVATE\ud800'}
    result=client.put(f"/api/tasks/{task['id']}/test-cases/draft",content=json.dumps(payload,ensure_ascii=True).encode('ascii'),headers={'Content-Type':'application/json'})
    assert result.status_code==422 and 'PRIVATE' not in result.text
    text='[\n {"name":"公开😀e\u0301","n":9007199254740993}\n]'
    assert save(client,task,text=text).json()['record']['text']==text

def test_reading_other_task_cannot_load_first_tasks_draft(client):
    first=approved(client);second=approved(client);assert save(client,first).status_code==200
    assert read(client,second).json()['record'] is None

def test_same_draft_save_is_idempotent_and_explicit_empty_delete_keeps_counter(client):
    task=approved(client);assert discard(client,task,0).json()['draft_revision']==1
    assert save(client,task,0).status_code==409
    first=save(client,task,1);assert first.status_code==200
    assert save(client,task,2).json()['draft_revision']==2

def test_busy_task_draft_save_is_independent_of_execution(client):
    task=approved(client);task['status']='planning';main.store.put('task',task['id'],task)
    result=save(client,task);assert result.status_code==200,result.text
    assert main.get_task(task['id'])==task
