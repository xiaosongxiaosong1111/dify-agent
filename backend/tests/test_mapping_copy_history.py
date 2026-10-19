import sys,copy,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import main
from app.environment_mapping_copy import COPY_KIND
from test_api import client
from test_environment_mapping_copy import ready,create
from test_agent_environment_mapping import state


def history(client,task):return client.get(f"/api/tasks/{task['id']}/environment-mapping/copies")


def test_history_recovers_persistent_local_target_after_scope_refresh_without_writes(client):
    task,_,_,_,scope,payload=ready(client);assert scope['existing_copy_receipt_count']==0
    before=state();assert history(client,task).json()['total']==0 and state()==before
    created=create(client,task,payload).json()['task'];before=state()
    value=history(client,task);assert value.status_code==200
    rows=value.json();assert rows['total']==rows['shown']==1 and not rows['invalid_in_window'] and not rows['truncated']
    row=rows['rows'][0];assert row['operation_id']==payload['operation_id'] and row['target_task_id']==created['id']
    assert row['target_revision']==1 and row['source_revision']==task['revision'] and state()==before
    assert set(row)=={'operation_id','target_task_id','target_name','target_revision','source_revision','created_at'}
    refreshed=client.get(f"/api/tasks/{task['id']}/environment-mapping/copy-scope").json()
    assert refreshed['existing_copy_receipt_count']==1 and refreshed['scope_token']!=scope['scope_token']


def test_different_operation_same_old_scope_cannot_create_second_task(client):
    task,_,_,_,_,payload=ready(client);assert create(client,task,payload).status_code==201
    before=state();second=create(client,task,{**payload,'operation_id':str(uuid.uuid4())})
    assert second.status_code==409 and state()==before
    same=create(client,task,payload);assert same.status_code==201 and not same.json()['created'] and state()==before


def test_history_is_source_owned_and_invalid_rows_never_expose_private_fields(client):
    task,_,_,_,_,payload=ready(client);create(client,task,payload)
    key=task['id']+':'+str(uuid.uuid4());main.store.put(COPY_KIND,key,{'id':key,'source_task_id':'other-owner','target_task_id':'do-not-expose-private'})
    main.store.put(COPY_KIND,'other-task:'+str(uuid.uuid4()),{'source_task_id':'other-task','target_task_id':'private-other'})
    before=state();r=history(client,task);assert r.status_code==200 and state()==before
    v=r.json();assert v['total']==2 and v['shown']==1 and v['invalid_in_window']==1
    assert 'do-not-expose-private' not in r.text and 'private-other' not in r.text


def test_missing_or_changed_target_history_is_not_a_valid_zero_or_verified_resource(client):
    task,_,_,_,_,payload=ready(client);created=create(client,task,payload).json()['task']
    row=main.store.get('task',created['id']);row['mapping_origin']['source_task_id']='not-owner';main.store.put('task',row['id'],row)
    v=history(client,task).json();assert v['total']==1 and v['shown']==0 and v['invalid_in_window']==1
    assert v['verification']=='local_mapping_copy_receipts_only' and v['rows']==[]


def test_history_window_is_latest_twenty_and_large_malformed_receipts_bounded(client):
    task,_,_,_,_,payload=ready(client);created=create(client,task,payload).json()['task']
    for i in range(23):
        key=task['id']+':'+str(uuid.uuid4());main.store.put(COPY_KIND,key,{'id':key,'source_task_id':task['id'],'private':'x'*20000})
    v=history(client,task).json();assert v['total']==24 and v['shown']==0 and v['invalid_in_window']==20 and v['truncated']
    assert len(str(v))<1000


def test_history_copies_current_target_metadata_not_original_source_claim(client):
    task,_,_,_,_,payload=ready(client);target=create(client,task,payload).json()['task']
    target['revision']=2;target['name']='用户后续修改的本机任务';main.store.put('task',target['id'],target)
    row=history(client,task).json()['rows'][0];assert row['target_revision']==2 and row['target_name']==target['name']
    assert row['source_revision']==task['revision']


def test_receipt_lookup_invalid_target_origin_or_record_id_rejected_without_echo(client):
    task,_,_,_,_,payload=ready(client);new=create(client,task,payload).json()['task']
    path=f"/api/tasks/{task['id']}/environment-mapping/copies/{payload['operation_id']}"
    target=main.store.get('task',new['id']);target['mapping_origin']=None;main.store.put('task',target['id'],target)
    before=state();r=client.get(path);assert r.status_code==409 and state()==before
    key=task['id']+':'+payload['operation_id'];receipt=main.store.get(COPY_KIND,key);receipt['id']='private-foreign-key';main.store.put(COPY_KIND,key,receipt)
    before=state();r=client.get(path);assert r.status_code==409 and 'private-foreign-key' not in r.text and state()==before
