import copy,hashlib,json
import pytest
from fastapi import HTTPException
from test_api import client,approved
from app import main
from app.retained_plan import candidate

def fixture():
    return {'id':'public-task','app_type':'workflow','revision':3,'planning_runs':[{'id':'public-run','revision':3,'status':'paused','last_candidate':{'schema_version':1,'nodes':[{'id':'start'}],'exact':9007199254740993},'last_response_excerpt':'not a fallback'}]}

def test_exact_text_and_digest_do_not_round_or_adopt_invalid_graph():
    task=fixture();before=copy.deepcopy(task);value=candidate(task,'public-run')
    assert '9007199254740993' in value['plan_text'] and json.loads(value['plan_text'])==task['planning_runs'][0]['last_candidate']
    assert value['source_sha256']==hashlib.sha256(value['plan_text'].encode()).hexdigest()
    assert value['byte_count']==len(value['plan_text'].encode()) and value['is_current_revision']
    assert value['verification']=='retained_candidate_unverified'
    assert not any(value[k] for k in ('formal_plan_changed','network_requested','platform_checked','business_verified'))
    assert task==before

def test_historical_candidate_is_labeled_not_rebound_to_new_revision():
    task=fixture();task['revision']=4;value=candidate(task,'public-run')
    assert value['input_revision']==3 and value['current_revision']==4 and not value['is_current_revision']

@pytest.mark.parametrize('status',['running','ready_to_confirm','succeeded','unknown'])
def test_active_or_adopted_candidate_is_not_represented_as_stopped(status):
    task=fixture();task['planning_runs'][0]['status']=status
    with pytest.raises(HTTPException) as caught:candidate(task,'public-run')
    assert caught.value.status_code==409

@pytest.mark.parametrize('kind',['configuration','repair','cases','coverage','conflicts'])
def test_non_plan_output_cannot_be_loaded_as_plan(kind):
    task=fixture();task['planning_runs'][0]['kind']=kind
    with pytest.raises(HTTPException):candidate(task,'public-run')

@pytest.mark.parametrize('plan',[None,{},[],{'n':float('nan')},{'n':float('inf')},{'text':'\ud800'},{'secret':'sk-'+'A'*32},{'text':'x'*2000001}],ids=['missing','empty','list','nan','inf','unicode','secret','size'])
def test_bad_candidate_never_falls_back_to_excerpt_or_echoes_content(plan):
    task=fixture();task['planning_runs'][0]['last_candidate']=plan
    with pytest.raises(HTTPException) as caught:candidate(task,'public-run')
    assert caught.value.status_code==422 and 'sk-' not in str(caught.value.detail)

def test_missing_or_ambiguous_record_is_refused():
    task=fixture()
    with pytest.raises(HTTPException):candidate(task,'another-run')
    task['planning_runs'].append(copy.deepcopy(task['planning_runs'][0]))
    with pytest.raises(HTTPException):candidate(task,'public-run')

@pytest.mark.parametrize('revision',[True,None,0,'3'])
def test_revision_is_not_coerced(revision):
    task=fixture();task['planning_runs'][0]['revision']=revision
    with pytest.raises(HTTPException):candidate(task,'public-run')

def test_api_is_read_only_and_keeps_formal_plan_confirmation_and_credentials(client,monkeypatch):
    task=approved(client);task['planning_runs']=fixture()['planning_runs'];task['planning_runs'][0]['revision']=task['revision'];main.store.put('task',task['id'],task)
    before=client.get('/api/tasks/'+task['id']).json()
    def forbidden(*args,**kwargs):raise AssertionError('只读路径不得写存储或调用外部服务')
    monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
    response=client.get(f"/api/tasks/{task['id']}/planning/public-run/candidate")
    assert response.status_code==200 and response.json()['task_id']==task['id']
    assert client.get('/api/tasks/'+task['id']).json()==before
