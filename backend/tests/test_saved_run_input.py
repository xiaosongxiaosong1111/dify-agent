import copy
import json
import pytest
from test_api import client, approved, forbid_api_external_calls
from test_run_comparison import sample
from app import main
from app.saved_run_input import preview


@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_single_turn_saved_input_only_is_copied_to_free_draft(mode):
    task=sample(mode);before=copy.deepcopy(task);value=preview(task,'old-run')
    assert json.loads(value['input_text'])==task['runs'][0]['input']
    assert value['task_id']==task['id'] and value['source_revision']==2 and task==before
    assert all(value[k] is False for k in ['task_changed','network_requested','automatic_execution','business_verified','case_copied','conversation_copied','current_schema_checked'])
    assert 'expectation' not in value and 'case_id' not in value and 'conversation_id' not in value


def test_large_integer_and_json_scalar_types_are_lossless_and_not_schema_approved():
    task=sample();task['runs'][0]['input']={'large':9007199254740993,'flag':True,'nothing':None,'text':'引号"与换行\n','ratio':.2}
    value=preview(task,'old-run')
    assert '9007199254740993' in value['input_text'] and json.loads(value['input_text'])==task['runs'][0]['input']
    assert value['numeric_review_required'] and not value['current_schema_checked']


@pytest.mark.parametrize('field,value',[('conversation_context',{}),('file_case',{}),('test_case',{'followups':[{}]}),('result',{'conversation_case':True})])
def test_context_rich_sources_not_flattened(field,value):
    task=sample();task['runs'][0][field]=value
    with pytest.raises(main.HTTPException) as err:preview(task,'old-run')
    assert err.value.status_code==422


@pytest.mark.parametrize('status',['pending','unknown','waiting_platform'])
def test_unresolved_original_request_cannot_prepare_new_input(status):
    task=sample();task['runs'][0]['status']=status
    with pytest.raises(main.HTTPException):preview(task,'old-run')


@pytest.mark.parametrize('value',[{'object':{}},{'array':[]},{'conversation_id':'old-id'},None,{'query':float('nan')},{'query':'x'*128001}])
def test_unbounded_or_non_scalar_input_is_not_partially_copied(value):
    task=sample();task['runs'][0]['input']=value
    with pytest.raises(main.HTTPException):preview(task,'old-run')


@pytest.mark.parametrize('value',[{'password':'DO-NOT-ECHO'},{'query':'Bearer SYNTHETICPRIVATEVALUE12345'},{'query':'app-SYNTHETICPRIVATEVALUE12345'}])
def test_sensitive_input_is_refused_without_echo_or_redacted_partial_copy(value):
    task=sample();task['runs'][0]['input']=value
    with pytest.raises(main.HTTPException) as err:preview(task,'old-run')
    assert 'DO-NOT-ECHO' not in str(err.value.detail) and 'SYNTHETICPRIVATEVALUE' not in str(err.value.detail)


def test_missing_type_mismatched_type_foreign_and_duplicate_records_refused():
    task=sample()
    with pytest.raises(main.HTTPException):preview(task,'foreign')
    task['runs'][0]['app_type']='agent'
    with pytest.raises(main.HTTPException):preview(task,'old-run')
    task['runs'][0]['app_type']=None
    with pytest.raises(main.HTTPException):preview(task,'old-run')
    task=sample();task['runs'].append(copy.deepcopy(task['runs'][0]))
    with pytest.raises(main.HTTPException):preview(task,'old-run')


def test_route_readonly_no_credentials_and_revision_bound_even_before_build(client,monkeypatch):
    task=approved(client);task['runs']=sample()['runs'];main.store.put('task',task['id'],task)
    original=copy.deepcopy(task);budget=main.store.get('task_budget',task['id'])
    def forbid(*args,**kwargs):pytest.fail('Input preview must not write or decrypt')
    monkeypatch.setattr(main.store,'put',forbid);monkeypatch.setattr(main.store,'secret',forbid)
    path=f"/api/tasks/{task['id']}/runs/old-run/input-copy-preview"
    response=client.get(path,params={'revision':task['revision']});assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    assert client.get(path,params={'revision':task['revision']+1}).status_code==409
    assert main.get_task(task['id'])==original and main.store.get('task_budget',task['id'])==budget
