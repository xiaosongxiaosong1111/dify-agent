import sys,json,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import main
from app.model_number_drafts import KIND,HISTORY
from test_api import client,create
from test_agent_environment_mapping import state


def setup(client):
    task=create(client,'agent');path=f"/api/tasks/{task['id']}/model-number-draft"
    context=json.dumps(main.model_number_drafts.context(task))
    return task,path,{'revision':task['revision'],'draft_revision':0,'model_context_json':context,'temperature_text':'0.10000000000000001','max_tokens_text':'1e'}


def test_unfinished_number_text_saved_separately_with_no_config_or_credential_change(client):
    task,path,body=setup(client);before=copy.deepcopy(main.get_task(task['id']));secrets=state()[1]
    empty=client.get(path);assert empty.status_code==200 and empty.json()['draft_revision']==0
    r=client.put(path,json=body);assert r.status_code==200,r.text;value=r.json()
    assert value['draft_revision']==1 and value['restorable'] and not value['configuration_applied'] and not value['task_modified']
    assert value['record']['temperature_text']==body['temperature_text'] and value['record']['max_tokens_text']=='1e'
    assert 'model_context_json' not in value['record'] and 'configuration' not in value['record']
    assert main.get_task(task['id'])==before and state()[1]==secrets and main.store.list(HISTORY)==[]
    baseline=state();again=client.put(path,json={**body,'draft_revision':1});assert again.status_code==200 and again.json()['draft_revision']==1 and state()==baseline


def test_history_archives_exact_text_and_read_only_restore_does_not_apply(client):
    task,path,body=setup(client);first=client.put(path,json=body).json();record=first['record']
    second=client.put(path,json={**body,'draft_revision':1,'max_tokens_text':'512'});assert second.status_code==200
    assert main.store.get(HISTORY,task['id']+':1')==record
    old=client.get(path+'/history/1');assert old.status_code==200 and old.json()['record']==record and old.json()['draft_revision']==2
    baseline=state();restore={k:body[k] for k in ('revision','model_context_json')};restore.update(source_draft_revision=1,record_token=first['record_token'])
    r=client.post(path+'/restore-preview',json=restore);assert r.status_code==200,r.text
    assert r.json()['max_tokens_text']=='1e' and r.json()['temperature_text']==body['temperature_text'] and not r.json()['configuration_applied'] and state()==baseline


@pytest.mark.parametrize('patch',[{'draft_revision':1},{'revision':True},{'draft_revision':True},{'temperature_text':1},{'max_tokens_text':'private-api-key'},{'temperature_text':'1\n2'},{'max_tokens_text':'1'*2049},{'unknown':True}])
def test_invalid_or_concurrent_progress_never_writes_or_echoes(client,patch):
    _,path,body=setup(client);before=state();r=client.put(path,json={**body,**patch})
    assert r.status_code in {409,422} and 'private-api-key' not in r.text and state()==before


def test_model_environment_context_must_be_current_saved_selection(client):
    task,path,body=setup(client);context=json.loads(body['model_context_json']);context['dify_model']='unsaved-other-model';before=state()
    r=client.put(path,json={**body,'model_context_json':json.dumps(context)});assert r.status_code==409 and state()==before
    r=client.put(path,json={**body,'model_context_json':'{"secret":"private-input"'});assert r.status_code==422 and 'private-input' not in r.text and state()==before


@pytest.mark.parametrize('change',['revision','model','parameters','environment'])
def test_source_changes_keep_saved_text_only_readable_not_restorable(client,change):
    task,path,body=setup(client);first=client.put(path,json=body).json();row=main.get_task(task['id'])
    if change=='revision':row['revision']+=1
    if change=='model':row['configuration']['dify_model']='new-model'
    if change=='parameters':row['configuration']['model_parameters']={'top_p':.75}
    if change=='environment':row['environment_id']='missing-other-env'
    main.save_task(row);before=state();r=client.get(path);assert r.status_code==200 and r.json()['stale'] and not r.json()['restorable'] and r.json()['record']==first['record'] and state()==before
    request={'revision':row['revision'],'model_context_json':json.dumps(main.model_number_drafts.context(row)),'source_draft_revision':1,'record_token':first['record_token']}
    assert client.post(path+'/restore-preview',json=request).status_code==409 and state()==before


def test_foreign_or_corrupt_current_record_never_read_or_overwritten(client):
    task,path,body=setup(client);client.put(path,json=body);record=main.store.get(KIND,task['id']);record['task_id']='private-other-owner';main.store.put(KIND,task['id'],record);before=state()
    r=client.get(path);assert r.status_code==409 and 'private-other-owner' not in r.text
    assert client.put(path,json={**body,'draft_revision':1}).status_code==409 and state()==before


def test_orphan_history_does_not_reset_missing_current_counter_to_zero(client):
    task,path,body=setup(client);first=client.put(path,json=body).json()['record'];main.store.put(HISTORY,task['id']+':1',first)
    with main.store.connect() as db:db.execute('DELETE FROM objects WHERE kind=? AND id=?',(KIND,task['id']))
    before=state();assert client.get(path).status_code==409 and client.put(path,json=body).status_code==409 and state()==before


def test_context_float_format_differences_are_semantic_not_lexical(client):
    task,path,body=setup(client);row=main.get_task(task['id']);row['configuration']['model_parameters']={'top_p':1e-7};main.save_task(row)
    context=json.dumps(main.model_number_drafts.context(row)).replace('1e-07','1e-7');r=client.put(path,json={**body,'model_context_json':context});assert r.status_code==200,r.text


def test_history_conflict_and_bad_restore_token_never_replace_any_records(client):
    task,path,body=setup(client);first=client.put(path,json=body).json();record=copy.deepcopy(first['record']);record['temperature_text']='9';main.store.put(HISTORY,task['id']+':1',record);before=state()
    assert client.put(path,json={**body,'draft_revision':1,'max_tokens_text':'512'}).status_code==409
    restore={'revision':task['revision'],'model_context_json':body['model_context_json'],'source_draft_revision':1,'record_token':'e'*64}
    assert client.post(path+'/restore-preview',json=restore).status_code==409 and state()==before


def test_atomic_failure_rolls_back_new_history_and_current(client,monkeypatch):
    task,path,body=setup(client);client.put(path,json=body);before=state();original=main.store.put_many
    def fail(rows):return original([*rows,('invalid',object(),{})])
    monkeypatch.setattr(main.store,'put_many',fail)
    with pytest.raises(Exception):client.put(path,json={**body,'draft_revision':1,'max_tokens_text':'512'})
    assert state()==before


def test_duplicate_transport_keys_and_unknown_stored_fields_no_echo(client):
    task,path,body=setup(client);before=state();raw=json.dumps(body)[:-1]+',"temperature_text":"private-input"}'
    r=client.put(path,content=raw,headers={'Content-Type':'application/json'});assert r.status_code==422 and 'private-input' not in r.text and state()==before
    record=client.put(path,json=body).json()['record'];record['api_key']='PRIVATE-CREDENTIAL';main.store.put(KIND,task['id'],record);before=state()
    r=client.get(path);assert r.status_code==409 and 'PRIVATE-CREDENTIAL' not in r.text and state()==before


@pytest.mark.parametrize('patch',[{'draft_revision':True},{'draft_revision':9007199254740992},{'created_at':'PRIVATE-TIME'},{'verification':'approved'}])
def test_corrupt_saved_metadata_not_zero_or_auto_overwritten(client,patch):
    task,path,body=setup(client);record=client.put(path,json=body).json()['record'];record.update(patch);main.store.put(KIND,task['id'],record);before=state()
    r=client.get(path);assert r.status_code==409 and 'PRIVATE-TIME' not in r.text
    assert client.put(path,json=body).status_code==409 and state()==before


def test_history_key_counter_mismatch_never_restores_wrong_version(client):
    task,path,body=setup(client);first=client.put(path,json=body).json();client.put(path,json={**body,'draft_revision':1,'max_tokens_text':'512'})
    changed=copy.deepcopy(first['record']);changed['draft_revision']=2;main.store.put(HISTORY,task['id']+':1',changed)
    from app.dsl_roundtrip import digest
    request={'revision':task['revision'],'model_context_json':body['model_context_json'],'source_draft_revision':1,'record_token':digest(changed)}
    before=state();assert client.post(path+'/restore-preview',json=request).status_code==409 and state()==before


def test_numeric_progress_does_not_decrypt_credentials_and_inner_context_duplicate_rejected(client,monkeypatch):
    task,path,body=setup(client)
    def no_secret(*args):pytest.fail('numeric text progress must not decrypt credentials')
    monkeypatch.setattr(main.store,'secret',no_secret);before=state()
    raw=body['model_context_json'][:-1]+',"dify_model":"private-duplicate"}'
    r=client.put(path,json={**body,'model_context_json':raw});assert r.status_code==422 and 'private-duplicate' not in r.text and state()==before
    saved=client.put(path,json=body);assert saved.status_code==200 and client.get(path).json()['record']==saved.json()['record']
