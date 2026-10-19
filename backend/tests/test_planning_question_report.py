import copy,json
from test_api import client,approved
from app import main
from app.planning_decisions import history,summarize

def saved(revision=2):
    return {'revision':revision,'decision_report':summarize({'error':'缺资料范围','needs_decision':[{'question':'使用哪个库？','recommendation':'先明确资料范围'}]}),'last_response_excerpt':'RAW-PRIVATE','provider_id':'PRIVATE-PROVIDER'}

def test_history_keeps_questions_revision_and_omits_unrelated_fields():
    task={'revision':3,'planning_runs':[saved(2),saved(3)]};before=copy.deepcopy(task);value=history(task)
    assert value['state']=='ready' and len(value['records'])==2
    assert [r['is_current_revision'] for r in value['records']]==[False,True]
    assert value['records'][0]['report']['questions'][0]['recommendation']=='先明确资料范围'
    assert value['records'][0]['report']['format_valid']
    assert 'PRIVATE' not in json.dumps(value) and task==before

def test_unrecognized_source_and_legacy_are_not_guessed():
    item=saved();item['decision_report']['private']='DO-NOT-EXPORT';value=history({'revision':2,'planning_runs':[{'last_response_excerpt':'LEGACY-PRIVATE'},item]})
    assert len(value['records'])==1 and value['records'][0]['planning_position']==2
    assert value['records'][0]['report']['incomplete'] and 'PRIVATE' not in json.dumps(value)
    item['decision_report']['verification']='business_verified'
    value=history({'revision':2,'planning_runs':[saved(),item]})
    assert value['state']=='unavailable' and not value['records']

def test_oversized_history_returns_no_partial_or_mutation():
    items=[saved() for _ in range(51)];before=copy.deepcopy(items)
    assert history({'revision':2,'planning_runs':items})['records']==[] and items==before
    value=history({'revision':True,'planning_runs':[saved()]})
    assert value['state']=='unavailable'

def test_combined_utf8_budget_does_not_export_a_partial_history():
    item=saved();item['decision_report']=summarize({'error':'需复核','needs_decision':['说明'*1000 for _ in range(20)]})
    value=history({'revision':2,'planning_runs':[copy.deepcopy(item) for _ in range(3)]})
    assert value['state']=='unavailable' and not value['records']

def test_question_secret_is_not_exported_even_if_saved_metadata_claims_valid():
    item=saved();item['decision_report']['questions'][0]['question']='sk-'+'A'*32
    value=history({'revision':2,'planning_runs':[item]})
    text=json.dumps(value,ensure_ascii=False)
    assert 'sk-' not in text and 'A'*32 not in text
    assert value['records'][0]['report']['incomplete'] and not value['records'][0]['report']['questions']

def test_task_report_includes_unverified_questions_without_modifying_task(client):
    task=approved(client);task['planning_runs']=[saved(task['revision']-1)];main.store.put('task',task['id'],task)
    before=client.get('/api/tasks/'+task['id']).json();response=client.get('/api/tasks/'+task['id']+'/report')
    assert response.status_code==200
    assert '规划澄清问题（未确认）' in response.text and '使用哪个库？' in response.text
    assert 'model_clarification_only' in response.text and 'is_current_revision": false' in response.text
    assert 'RAW-PRIVATE' not in response.text and 'PRIVATE-PROVIDER' not in response.text
    assert client.get('/api/tasks/'+task['id']).json()==before
