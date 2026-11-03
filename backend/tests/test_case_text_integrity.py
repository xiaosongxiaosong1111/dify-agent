"""Bad decoded JSON strings cannot turn case saving or evaluation into a 500."""
import copy,json
import pytest
from fastapi.testclient import TestClient
from test_api import client,approved,forbid_api_external_calls
from app import main
from app.evaluation import evaluate_output,validate_test_cases

BAD='PRIVATE_SYNTHETIC\ud800'
def case():
    return {'id':'public-case','name':'公开样例','required':True,'input':{'query':'公开输入'},'expectation':{'mode':'contains','target':'answer','expected':['公开']}}

def broken(field):
    value=case()
    if field in {'name','id'}:value[field]=BAD
    elif field=='input_value':value['input']['query']=BAD
    elif field=='input_key':value['input']={BAD:'公开'}
    elif field=='expected':value['expectation']['expected']=BAD
    elif field=='expected_key':value['expectation']={'mode':'equals','target':'answer','expected':{BAD:'公开'}}
    elif field=='target':value['expectation']['target']=BAD
    elif field=='manual':value['expectation']={'mode':'manual','description':BAD}
    else:value['followups']=[{'input':{'query':'后续问题'},'expectation':{'mode':'contains','target':'answer','expected':[BAD]}}]
    return value

@pytest.mark.parametrize('field',['name','id','input_value','input_key','expected','expected_key','target','manual','followup'])
def test_bad_decoded_case_is_rejected_before_snapshot_or_store(client,field):
    task=approved(client,app_type='advanced-chat')
    task['test_cases']=[case()];main.store.put('task',task['id'],task)
    before=copy.deepcopy(main.get_task(task['id']));budget=main.store.get('task_budget',task['id'])
    with TestClient(main.app,raise_server_exceptions=False) as safe:
        response=safe.post(f"/api/tasks/{task['id']}/test-cases",content=json.dumps({'revision':task['revision'],'cases':[broken(field)]},ensure_ascii=True).encode('ascii'),headers={'Content-Type':'application/json'})
    assert response.status_code==422,response.text
    assert 'PRIVATE' not in response.text and '\\ud800' not in response.text
    assert main.get_task(task['id'])==before and main.store.get('task_budget',task['id'])==budget

@pytest.mark.parametrize('actual',[{'answer':BAD},{BAD:'公开'}])
def test_evaluation_returns_serializable_safe_diagnostics_for_invalid_output(actual):
    result=evaluate_output(actual,case()['expectation'])
    wire=json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8')
    assert result['status']=='failed' and b'PRIVATE' not in wire
    assert result['actual']=={'preview_unavailable':True}

@pytest.mark.parametrize('expectation',[{'mode':'manual','description':BAD},{'mode':'contains','target':BAD,'expected':['公开']},{'mode':'equals','target':'answer','expected':{BAD:'公开'}}])
def test_legacy_bad_expectation_cannot_leak_unsafe_error_text(expectation):
    result=evaluate_output({'answer':'公开'},expectation)
    wire=json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8')
    assert result['status']=='failed' and b'PRIVATE' not in wire

@pytest.mark.parametrize('text',['公开😀e\u0301\r\n 文字 ','\U00020000'])
def test_valid_unicode_and_whitespace_are_not_rewritten(client,text):
    task=approved(client);value=case();value['input']={text:text};value['expectation']={'mode':'equals','target':'answer','expected':{text:9007199254740993}}
    assert validate_test_cases([value])['valid'] is True
    response=client.post(f"/api/tasks/{task['id']}/test-cases",json={'revision':task['revision'],'cases':[value]})
    assert response.status_code==200,response.text
    assert main.get_task(task['id'])['test_cases']==[value]
