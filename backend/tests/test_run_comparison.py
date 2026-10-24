import copy
import json

import pytest

from test_api import client, approved, forbid_api_external_calls
from app import main
from app.run_comparison import compare


def sample(mode='workflow'):
    old = {'id':'old-run','kind':'run','app_type':mode,'revision':2,'environment_id':'saved-env',
        'app_id':'old-app','environment_binding':{'profile':'original'},'status':'success',
        'input':{'query':'DEMO-001'},'test_case':{'id':'same-case','expectation':{'mode':'equals','target':'result','expected':'旧回复'}},
        'result':{'data':{'outputs':{'result':'旧回复'}}} if mode=='workflow' else {'answer':'旧回复'}}
    new = copy.deepcopy(old);new.update(id='new-run',revision=3,app_id='new-app')
    new['test_case']['expectation']['expected']='新回复'
    new['result']={'data':{'outputs':{'result':'新回复'}}} if mode=='workflow' else {'answer':'新回复'}
    return {'id':'local-task','revision':3,'app_type':mode,'runs':[old,new]}


@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_saved_inputs_expectations_outputs_and_scope_changes_are_explicit(mode):
    task=sample(mode);before=copy.deepcopy(task);value=compare(task,'old-run','new-run')
    assert [r['comparison'] for r in value['sections']]==['same','changed','changed']
    assert value['conditions_same']=={'revision':False,'environment_id':True,'app_id':False,'environment_binding':True,'case_id':True}
    assert '旧回复' in value['sections'][2]['before']['text'] and '新回复' in value['sections'][2]['after']['text']
    assert all(value[k] is False for k in ['task_changed','network_requested','automatic_execution','business_verified'])
    assert task==before and '不能归因' in ''.join(value['warnings'])


def test_strict_bool_number_and_large_integer_remain_distinct_and_lossless_text():
    task=sample();task['runs'][0]['input']={'value':True,'large':9007199254740993};task['runs'][1]['input']={'value':1,'large':9007199254740992}
    value=compare(task,'old-run','new-run')['sections'][0]
    assert value['comparison']=='changed' and '9007199254740993' in value['before']['text']


def test_missing_output_is_not_null_and_unknown_partial_never_proves_completion():
    task=sample();task['runs'][0]['result']={};task['runs'][1].update(status='unknown',result={'data':{'outputs':None}})
    value=compare(task,'old-run','new-run');output=value['sections'][2]
    assert output['comparison']=='missing' and output['before']['state']=='missing'
    assert output['after']=={'state':'saved','text':'null'}
    assert '不能直接重试' in ''.join(value['warnings'])


@pytest.mark.parametrize('value',[{'password':'DO-NOT-ECHO-THIS'},'Bearer SYNTHETICPRIVATEVALUE12345','sk-SYNTHETICPRIVATEVALUE12345','x'*16001,float('nan')])
def test_sensitive_oversize_or_invalid_values_unavailable_without_echo(value):
    task=sample();task['runs'][0]['result']['data']['outputs']=value
    response=compare(task,'old-run','new-run');section=response['sections'][2]
    assert section['comparison']=='unavailable' and section['before']['state']=='unavailable'
    text=json.dumps(response,ensure_ascii=False)
    assert 'DO-NOT-ECHO' not in text and 'SYNTHETICPRIVATEVALUE' not in text and 'x'*100 not in text


@pytest.mark.parametrize('field,value',[('conversation_context',{}),('file_case',{}),('app_type',None),('test_case',{'followups':[{}]}),('result',{'conversation_case':True})])
def test_context_rich_or_untyped_records_not_silently_flattened(field,value):
    task=sample();task['runs'][0][field]=value
    with pytest.raises(main.HTTPException) as error:compare(task,'old-run','new-run')
    assert error.value.status_code==422


def test_other_record_kinds_duplicates_and_other_task_ids_are_refused():
    task=sample()
    with pytest.raises(main.HTTPException):compare(task,'old-run','old-run')
    task['runs'][0]['kind']='publish'
    with pytest.raises(main.HTTPException):compare(task,'old-run','new-run')
    with pytest.raises(main.HTTPException):compare(task,'foreign-run','new-run')
    task=sample();task['runs'].append(copy.deepcopy(task['runs'][0]))
    with pytest.raises(main.HTTPException):compare(task,'old-run','new-run')


def test_missing_scope_is_unknown_not_assumed_current_and_types_cannot_mix():
    task=sample();task['runs'][0].pop('environment_binding');task['runs'][1].pop('environment_id')
    value=compare(task,'old-run','new-run')
    assert value['conditions_same']['environment_binding'] is None and value['conditions_same']['environment_id'] is None
    task['runs'][1]['app_type']='advanced-chat'
    with pytest.raises(main.HTTPException):compare(task,'old-run','new-run')


def test_same_revision_output_change_invalidates_observation_token():
    task=sample();first=compare(task,'old-run','new-run')
    task['runs'][1]['result']['data']['outputs']['result']='稍后保存的回复'
    second=compare(task,'old-run','new-run')
    assert first['snapshot_token']!=second['snapshot_token'] and first['revision']==second['revision']


def test_actual_route_is_readonly_no_decrypt_and_revision_bound(client,monkeypatch):
    task=approved(client);task['runs']=sample()['runs'];main.store.put('task',task['id'],task)
    before=copy.deepcopy(task);budget=main.store.get('task_budget',task['id'])
    def forbid(*args,**kwargs):pytest.fail('Comparison must never write or decrypt')
    monkeypatch.setattr(main.store,'secret',forbid);monkeypatch.setattr(main.store,'put',forbid)
    path=f"/api/tasks/{task['id']}/run-comparison";params={'revision':task['revision'],'before_run_id':'old-run','after_run_id':'new-run'}
    response=client.get(path,params=params);assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    assert response.json()['task_id']==task['id'] and response.json()['revision']==task['revision']
    assert client.get(path,params={**params,'revision':task['revision']+1}).status_code==409
    assert client.get(path,params={**params,'after_run_id':'foreign'}).status_code==404
    assert main.store.get('task',task['id'])==before and main.store.get('task_budget',task['id'])==budget
