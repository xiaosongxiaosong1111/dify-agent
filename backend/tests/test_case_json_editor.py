import copy,json
import pytest
from test_api import client,approved,forbid_api_external_calls
from app import main

def case():return {'id':'public-case','name':'原公开名称','required':True,'input':{'amount':1.0,'id':9007199254740993},'expectation':{'mode':'equals','target':'result','expected':{'amount':1.0,'id':9007199254740993}}}
def seeded(client):
    task=approved(client);task['test_cases']=[case()];main.store.put('task',task['id'],task);return task
def read(client,task):return client.get(f"/api/tasks/{task['id']}/test-cases/editor",params={'revision':task['revision']})
def write(client,task,meta,text):return client.post(f"/api/tasks/{task['id']}/test-cases/editor",json={'revision':task['revision'],'source_token':meta['source_token'],'cases_text':text})

def test_read_source_preserves_numbers_and_does_not_grant_or_write(client):
    task=seeded(client);response=read(client,task);assert response.status_code==200,response.text
    meta=response.json();assert '9007199254740993' in meta['cases_text'] and '1.0' in meta['cases_text']
    assert meta['structured_editing_safe'] is False and meta['task_id']==task['id'] and meta['app_type']==task['app_type']
    assert meta['task_changed'] is False and meta['network_requested'] is False and meta['business_verified'] is False
    assert main.get_task(task['id'])==task

def test_rename_via_original_json_keeps_numeric_types_and_versioned_source(client):
    task=seeded(client);meta=read(client,task).json();text=meta['cases_text'].replace('原公开名称','只修改名称')
    result=write(client,task,meta,text);assert result.status_code==200,result.text
    saved=main.get_task(task['id']);row=saved['test_cases'][0]
    assert row['name']=='只修改名称' and type(row['input']['amount']) is float and row['input']['id']==9007199254740993
    assert type(row['expectation']['expected']['amount']) is float
    assert saved['versions'][-1]['test_cases']==task['test_cases'] and saved['revision']==task['revision']+1
    assert not saved['requirements_confirmed'] and not saved['configuration_confirmed']

@pytest.mark.parametrize('change',['revision','content','foreign','busy'])
def test_stale_foreign_or_busy_cannot_save_even_valid_json(client,change):
    task=seeded(client);meta=read(client,task).json()
    if change=='revision':task['revision']+=1
    elif change=='content':task['test_cases'][0]['name']='外部保存的新名称'
    elif change=='foreign':
        other=approved(client);other['test_cases']=task['test_cases'];task=other
    else:task['status']='planning'
    main.store.put('task',task['id'],task);before=copy.deepcopy(task)
    result=write(client,task,meta,meta['cases_text']);assert result.status_code==409,result.text
    assert main.get_task(task['id'])==before

@pytest.mark.parametrize('text',['{}','[1]','[{"id":"a","id":"b"}]','[],"extra":true','[NaN]','[{"input":{"x":1e-999}}]','[{"input":{"x":"\\ud800"}}]'])
def test_bad_raw_json_rejected_before_modifying_any_saved_case(client,text):
    task=seeded(client);meta=read(client,task).json();before=copy.deepcopy(task)
    result=write(client,task,meta,text);assert result.status_code==422,result.text
    assert main.get_task(task['id'])==before

@pytest.mark.parametrize('hazard',['ordinary','float_integer','big_integer','metadata'])
def test_only_lossless_known_forms_are_enabled(client,hazard):
    task=seeded(client);row=case();row['input']={'query':'公开'};row['expectation']={'mode':'contains','target':'answer','expected':['公开']}
    if hazard=='float_integer':row['input']['n']=1.0
    elif hazard=='big_integer':row['input']['n']=9007199254740993
    elif hazard=='metadata':row['business_metadata']={'public':'必须保留'}
    task['test_cases']=[row];main.store.put('task',task['id'],task)
    result=read(client,task);assert result.status_code==200,result.text
    assert result.json()['structured_editing_safe']==(hazard=='ordinary')

def test_reading_during_busy_is_allowed_and_stale_revision_is_not(client):
    task=seeded(client);task['status']='planning';main.store.put('task',task['id'],task)
    assert read(client,task).status_code==200
    task['revision']-=1;assert read(client,task).status_code==409

def test_same_values_do_not_create_an_extra_revision_or_confirmation(client):
    task=seeded(client);meta=read(client,task).json()
    result=write(client,task,meta,' \n'+meta['cases_text']+'\n ')
    assert result.status_code==200,result.text
    assert main.get_task(task['id'])==task

def test_oversize_editor_text_is_rejected_without_echo_or_mutation(client):
    task=seeded(client);meta=read(client,task).json()
    result=write(client,task,meta,'['+' ' * 2_000_001+']')
    assert result.status_code==422 and len(result.content)<1000
    assert main.get_task(task['id'])==task
