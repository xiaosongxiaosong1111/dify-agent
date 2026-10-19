import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import main
from app.agent_environment_mapping import DRAFT_KIND,HISTORY_KIND
from test_api import client
from test_agent_environment_mapping import prepared,body,request,MODEL,state


def setup(client):
    task,root,p,target=prepared(client)
    inputs=body(task,p,target);preview=request(client,task,p,target).json()
    return task,inputs,preview,target


def save(client,task,inputs,preview,counter=0,**patch):
    payload={**inputs,'preview_token':preview['preview_token'],'draft_revision':counter,**patch}
    return client.put(f"/api/tasks/{task['id']}/environment-mapping/draft",json=payload)


def read(client,task):return client.get(f"/api/tasks/{task['id']}/environment-mapping/draft")


def test_get_without_body_and_first_save_only_persist_unconfirmed_progress(client):
    task,inputs,preview,target=setup(client);baseline_task=copy.deepcopy(main.get_task(task['id']))
    empty=read(client,task);assert empty.status_code==200 and empty.json()['record'] is None
    response=save(client,task,inputs,preview);assert response.status_code==200,response.text
    value=response.json();assert value['draft_revision']==1 and value['restorable'] and not value['stale']
    assert not value['confirmed'] and not value['can_apply'] and value['restore_payload']['acknowledge_unverified_target'] is False
    assert value['record']['verification']=='unconfirmed_local_mapping_draft'
    assert value['record']['preview']==preview
    assert main.get_task(task['id'])==baseline_task and main.store.list(HISTORY_KIND)==[]
    baseline=state();same=save(client,task,inputs,preview,1);assert same.status_code==200 and same.json()['draft_revision']==1
    assert state()==baseline
    assert read(client,task).json()['record']==value['record']


def test_changed_saved_input_archives_exact_old_record_and_history_read_is_unconfirmed(client):
    task,inputs,preview,target=setup(client);first=save(client,task,inputs,preview).json()['record']
    other={**MODEL,'name':'second-target'};inputs2={**inputs,'target_model_json':json.dumps(other)}
    preview2=client.post(f"/api/tasks/{task['id']}/environment-mapping/preview",json=inputs2).json()
    response=save(client,task,inputs2,preview2,1);assert response.status_code==200,response.text
    assert response.json()['draft_revision']==2 and response.json()['record']['preview_token']!=first['preview_token']
    assert main.store.get(HISTORY_KIND,task['id']+':1')==first
    historical=client.get(f"/api/tasks/{task['id']}/environment-mapping/draft/history/1")
    assert historical.status_code==200,historical.text
    value=historical.json();assert value['historical'] and value['record']==first and value['draft_revision']==2
    assert not value['confirmed'] and not value['can_apply'] and value['restore_payload']['acknowledge_unverified_target'] is False
    assert read(client,task).json()['record']['draft_revision']==2


@pytest.mark.parametrize('patch',[{'draft_revision':1},{'preview_token':'f'*64},{'revision':True},{'acknowledge_unverified_target':False},{'draft_revision':True}],ids=['concurrent','old_preview','strict_revision','no_ack','strict_counter'])
def test_invalid_or_stale_save_never_changes_any_objects(client,patch):
    task,inputs,preview,target=setup(client);baseline=state()
    response=save(client,task,inputs,preview,**patch)
    assert response.status_code in {409,422},response.text
    assert state()==baseline


@pytest.mark.parametrize('kind',['task_revision','target_context','source_file'])
def test_source_or_target_changes_preserve_old_draft_as_stale_readonly(client,kind):
    task,inputs,preview,target=setup(client);record=save(client,task,inputs,preview).json()['record']
    if kind=='task_revision':
        client.patch(f"/api/tasks/{task['id']}",json={'name':'新的源任务名称'})
    elif kind=='target_context':
        env=main.store.get('environment',target['id']);env['connection_revision']='changed';main.store.put('environment',target['id'],env)
    else:
        ref=main.store.get('dsl_reference',preview['reference_id']);ref['current']['app']['description']='另有实际源文件变化';main.store.put('dsl_reference',ref['id'],ref)
    baseline=state();response=read(client,task);assert response.status_code==200,response.text
    value=response.json();assert value['stale'] and not value['restorable'] and value['restore_payload'] is None and value['record']==record
    assert state()==baseline
    again=save(client,task,inputs,preview,1);assert again.status_code in {409,422} and state()==baseline


def test_restoring_inputs_clears_old_ack_and_cannot_silently_save_again(client):
    task,inputs,preview,target=setup(client);save(client,task,inputs,preview)
    restored=read(client,task).json()['restore_payload'];assert not restored['acknowledge_unverified_target']
    baseline=state();response=save(client,task,restored,preview,1)
    assert response.status_code==422 and state()==baseline


def test_history_conflict_does_not_overwrite_original_or_new_progress(client):
    task,inputs,preview,target=setup(client);first=save(client,task,inputs,preview).json()['record']
    corrupt=copy.deepcopy(first);corrupt['created_at']='conflicting-history';main.store.put(HISTORY_KIND,task['id']+':1',corrupt)
    other={**MODEL,'name':'third-target'};inputs2={**inputs,'target_model_json':json.dumps(other)}
    preview2=client.post(f"/api/tasks/{task['id']}/environment-mapping/preview",json=inputs2).json();baseline=state()
    response=save(client,task,inputs2,preview2,1);assert response.status_code==409 and state()==baseline
    assert main.store.get(DRAFT_KIND,task['id'])==first


def test_history_is_task_scoped_and_path_errors_do_not_echo(client):
    task,inputs,preview,target=setup(client);save(client,task,inputs,preview)
    other={**MODEL,'name':'other-target'};inputs2={**inputs,'target_model_json':json.dumps(other)}
    preview2=client.post(f"/api/tasks/{task['id']}/environment-mapping/preview",json=inputs2).json();save(client,task,inputs2,preview2,1)
    task2,_,_,_=setup(client)
    assert client.get(f"/api/tasks/{task2['id']}/environment-mapping/draft/history/1").status_code==404
    response=client.get(f"/api/tasks/{task['id']}/environment-mapping/draft/history/never-echo-invalid-path")
    assert response.status_code==422 and 'never-echo' not in response.text


def test_busy_task_can_read_unconfirmed_progress_but_cannot_save(client):
    task,inputs,preview,target=setup(client);save(client,task,inputs,preview);task=main.get_task(task['id']);task['status']='running';main.save_task(task)
    baseline=state();value=read(client,task);assert value.status_code==200 and not value.json()['confirmed']
    response=save(client,task,inputs,preview,1);assert response.status_code==409 and state()==baseline



def test_foreign_current_record_is_not_exposed_or_overwritten(client):
    task,inputs,preview,target=setup(client);record=save(client,task,inputs,preview).json()['record']
    record['task_id']='foreign-task';record['private']='never-echo-foreign-state';main.store.put(DRAFT_KIND,task['id'],record)
    baseline=state();response=read(client,task)
    assert response.status_code==409 and 'never-echo' not in response.text
    response=save(client,task,inputs,preview,1);assert response.status_code==409 and state()==baseline


@pytest.mark.parametrize('counter',[True,-1,'1'])
def test_corrupt_counter_is_preserved_not_assumed_zero(client,counter):
    task,inputs,preview,target=setup(client);record=save(client,task,inputs,preview).json()['record']
    record['draft_revision']=counter;main.store.put(DRAFT_KIND,task['id'],record);baseline=state()
    assert read(client,task).status_code==409
    assert save(client,task,inputs,preview).status_code==409 and state()==baseline
