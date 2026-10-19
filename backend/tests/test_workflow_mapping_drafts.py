import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import main
from app.workflow_mapping_drafts import KIND,HISTORY,MAX_BYTES
from test_api import client,create_env
from test_dsl_roundtrip import prepared,capture


def ready(client):
    task,root=prepared(client);task=capture(client,task,root);p=client.get(f"/api/tasks/{task['id']}/dsl-merge").json();target=create_env(client)
    payload={'revision':task['revision'],'reference_id':p['reference_id'],'merge_token':p['merge_token'],'document_token':p['document_token'],'target_environment_id':target['id'],'expected_target_connection_revision':target.get('connection_revision'),'acknowledge_unverified_target':True,'acknowledge_retained_external_settings':True}
    path=f"/api/tasks/{task['id']}/workflow-environment-mapping";response=client.post(path+'/preview',json=payload);assert response.status_code==200,response.text
    return task,target,path,{**payload,'draft_revision':0,'preview_token':response.json()['preview_token']}


def save(client,path,payload):
    response=client.put(path+'/draft',json=payload);assert response.status_code==200,response.text
    return response.json()


def changed(client,path,payload):
    payload={**payload,'additional_dependencies':['public/extra:1@tag']};preview=client.post(path+'/preview',json={k:v for k,v in payload.items() if k not in {'draft_revision','preview_token'}});assert preview.status_code==200,preview.text
    return {**payload,'preview_token':preview.json()['preview_token']}


def test_save_persists_only_inputs_not_task_or_approvals_and_restore_clears_target_confirmations(client,monkeypatch):
    task,env,path,payload=ready(client);before=copy.deepcopy(main.store.get('task',task['id']))
    monkeypatch.setattr(main,'DifyClient',lambda *a,**kw:pytest.fail('No platform adapter'))
    empty=client.get(path+'/draft').json();assert empty['draft_revision']==0 and empty['record'] is None and main.store.get(KIND,task['id']) is None
    result=save(client,path,payload);assert result['draft_revision']==1 and result['restorable'] and not result['confirmed'] and not result['can_apply'] and not result['can_download']
    assert result['record']['payload']['acknowledge_unverified_target'] is True
    restore=result['restore_inputs'];assert restore['acknowledge_unverified_target'] is False and restore['acknowledge_retained_external_settings'] is False
    assert restore['target_parallel_reviews']=={} and restore['target_loop_reviews']=={} and restore['target_document_token'] is None
    assert 'preview' not in result['record'] and 'content' not in result['record']
    assert main.store.get('task',task['id'])==before
    # A new manager instance reads the same store; nothing depends on browser memory.
    from app.workflow_mapping_drafts import WorkflowMappingDrafts
    assert WorkflowMappingDrafts(main).state(main.get_task(task['id']))==result


def test_idempotence_concurrency_and_exact_old_version_archive(client):
    task,env,path,payload=ready(client);first=save(client,path,payload);record=copy.deepcopy(first['record'])
    assert save(client,path,{**payload,'draft_revision':1})['draft_revision']==1
    assert main.store.get(HISTORY,task['id']+':1') is None
    assert client.put(path+'/draft',json=payload).status_code==409
    next_payload=changed(client,path,{**payload,'draft_revision':1});second=save(client,path,next_payload)
    assert second['draft_revision']==2 and main.store.get(HISTORY,task['id']+':1')==record
    history=client.get(path+'/draft/history/1').json();assert history['historical'] and history['record']==record and history['draft_revision']==2
    assert client.get(path+'/draft/history/2').status_code==404


@pytest.mark.parametrize('change',['task_revision','target_revision','target_base','target_version','source_document'])
def test_stale_saved_inputs_remain_readable_but_cannot_restore(change,client):
    task,env,path,payload=ready(client);record=save(client,path,payload)['record']
    if change=='task_revision':
        task['revision']+=1;main.store.put('task',task['id'],task)
    elif change=='source_document':
        ref=main.store.get('dsl_reference',task['dsl_reference']['id']);ref['current']['workflow']['graph']['nodes'][1]['data']['code']+='\n# source changed';main.store.put('dsl_reference',ref['id'],ref)
    else:
        field={'target_revision':'connection_revision','target_base':'base_url','target_version':'version'}[change];env[field]={'connection_revision':'changed','base_url':'http://127.0.0.1:8099','version':'0.0.0'}[field];main.store.put('environment',env['id'],env)
    result=client.get(path+'/draft');assert result.status_code==200,result.text;value=result.json()
    assert value['stale'] and not value['restorable'] and value['restore_inputs'] is None and value['record']==record and value['blocker']


@pytest.mark.parametrize('field,value',[('preview_token','f'*64),('draft_revision',1),('revision',1),('acknowledge_unverified_target',False),('acknowledge_retained_external_settings',False)])
def test_stale_or_unconfirmed_put_does_not_create_record(client,field,value):
    task,env,path,payload=ready(client);before=copy.deepcopy(main.store.get('task',task['id']))
    response=client.put(path+'/draft',json={**payload,field:value});assert response.status_code in {409,422}
    assert main.store.get(KIND,task['id']) is None and main.store.get('task',task['id'])==before


@pytest.mark.parametrize('change',['owner','counter','timestamp','payload_digest','unknown_field','missing_payload','app_type','target_digest'])
def test_corrupt_progress_not_echoed_or_overwritten(client,change):
    task,env,path,payload=ready(client);record=save(client,path,payload)['record'];broken=copy.deepcopy(record)
    if change=='owner':broken['task_id']='other-task'
    elif change=='counter':broken['draft_revision']=True
    elif change=='timestamp':broken['created_at']='PRIVATE-MALFORMED'
    elif change=='payload_digest':broken['payload_token']='f'*64
    elif change=='unknown_field':broken['unexpected']='PRIVATE-MALFORMED'
    elif change=='missing_payload':broken.pop('payload')
    elif change=='app_type':broken['app_type']='agent'
    else:broken['target_document_token']='invalid'
    main.store.put(KIND,task['id'],broken)
    for response in (client.get(path+'/draft'),client.put(path+'/draft',json={**payload,'draft_revision':1})):
        assert response.status_code==409 and 'PRIVATE-MALFORMED' not in response.text
    assert main.store.get(KIND,task['id'])==broken


def test_orphan_history_is_not_reset_to_empty_version(client):
    task,env,path,payload=ready(client);record=save(client,path,payload)['record'];main.store.put(HISTORY,task['id']+':1',record)
    with main.store.connect() as db:db.execute('DELETE FROM objects WHERE kind=? AND id=?',(KIND,task['id']))
    assert client.get(path+'/draft').status_code==409 and client.put(path+'/draft',json=payload).status_code==409
    assert main.store.get(KIND,task['id']) is None


def test_transaction_failure_rolls_back_history_and_current_together(client):
    task,env,path,payload=ready(client);record=save(client,path,payload)['record'];next_payload=changed(client,path,{**payload,'draft_revision':1})
    with main.store.connect() as db:
        db.execute("CREATE TRIGGER fail_mapping_update BEFORE UPDATE ON objects WHEN NEW.kind='workflow_mapping_draft' AND json_extract(NEW.value,'$.draft_revision')=2 BEGIN SELECT RAISE(ABORT,'isolated failure'); END")
    response=client.put(path+'/draft',json=next_payload);assert response.status_code==503,response.text
    assert main.store.get(KIND,task['id'])==record and main.store.get(HISTORY,task['id']+':1') is None


def test_conflicting_history_not_overwritten_and_foreign_history_not_read(client):
    task,env,path,payload=ready(client);record=save(client,path,payload)['record'];conflicting={**record,'created_at':'2026-01-01T00:00:00Z'};main.store.put(HISTORY,task['id']+':1',conflicting)
    response=client.put(path+'/draft',json=changed(client,path,{**payload,'draft_revision':1}));assert response.status_code==409
    assert main.store.get(HISTORY,task['id']+':1')==conflicting and main.store.get(KIND,task['id'])==record
    main.store.put(HISTORY,task['id']+':1',{**record,'task_id':'other-task'})
    assert client.get(path+'/draft/history/1').status_code==409


def test_oversized_invalid_and_duplicate_json_do_not_leak_input(client):
    task,env,path,payload=ready(client)
    raw='{"revision":1,"revision":2,"private":"PRIVATE-MALFORMED"}'
    response=client.put(path+'/draft',content=raw,headers={'Content-Type':'application/json'});assert response.status_code==422 and 'PRIVATE-MALFORMED' not in response.text
    with main.store.connect() as db:db.execute('INSERT INTO objects(kind,id,value) VALUES(?,?,?)',(KIND,task['id'],'x'*(MAX_BYTES+1)))
    response=client.get(path+'/draft');assert response.status_code==409 and 'record' not in response.json()


def test_secret_parameter_in_corrupted_old_payload_never_returned_even_with_recomputed_digest(client):
    from app.dsl_roundtrip import digest
    task,env,path,payload=ready(client);record=save(client,path,payload)['record']
    record['payload']['node_models_json']={'node':json.dumps({'provider':'public/p/model','name':'model','mode':'chat','completion_params':{'temperature':.2,'max_tokens':512,'api_key':'PRIVATE-CREDENTIAL'}})}
    record['payload_token']=digest(record['payload']);main.store.put(KIND,task['id'],record)
    task['revision']+=1;main.store.put('task',task['id'],task)
    response=client.get(path+'/draft');assert response.status_code==409 and 'PRIVATE-CREDENTIAL' not in response.text
