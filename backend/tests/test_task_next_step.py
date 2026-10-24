import copy,json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from app import main
from app.storage import Store
from app.task_next_step import describe

def saved():return {'id':'fixture','revision':3,'app_type':'workflow','status':'ready','requirements_confirmed':True,'configuration_confirmed':True,'plan_stale':False,'workflow_plan':None,'runs':[],'environment_id':'env','dify_app_id':'app','artifact':{'revision':3,'validation':{'valid':True}}}
READY={'can_confirm':True,'context_token':'fixture-context'}

@pytest.mark.parametrize('patch,intake,expected,page', [
 ({'status':'interviewing'},READY,'busy','需求'),({'status':'planning'},READY,'busy','流程'),({'status':'paused'},READY,'paused','历史'),({'status':'error'},READY,'paused','历史'),
 ({}, {'can_confirm':False},'intake','需求'),({'requirements_confirmed':False},READY,'requirements','需求'),({'plan_stale':True},READY,'plan','流程'),({'configuration_confirmed':False},READY,'configuration','配置'),
 ({'artifact':None},READY,'build','构建'),({'artifact':{'revision':2,'validation':{'valid':True}}},READY,'build','构建'),({'artifact':{'revision':True,'validation':{'valid':True}}},READY,'build','构建'),({'artifact':{'revision':3,'validation':{'valid':False}}},READY,'build','构建'),
 ({'environment_id':None},READY,'offline','构建'),({'dify_app_id':None},READY,'import','构建'),({},READY,'publication','运行'),({'status':'future'},READY,'manual','历史')])
def test_saved_state_decision_is_navigation_only(patch,intake,expected,page):
    t={**saved(),**patch};before=copy.deepcopy(t);v=describe(t,intake)
    assert v['state']==expected and v['target_page']==page and t==before
    assert all(v[k] is False for k in ('task_changed','network_requested','automatic_execution','business_verified'))

@pytest.mark.parametrize('typ,expected,page',[('trigger-schedule','schedule','流程'),('human-input','human','流程'),('file','files','运行')])
def test_special_entry_never_recommends_ordinary_run(typ,expected,page):
    t=saved();t['workflow_plan']={'nodes':[{'id':'entry','type':typ,'config':{}}] if typ!='file' else [{'id':'start','type':'start','config':{'variables':[{'variable':'document','type':'file'}]}}]}
    v=describe(t,READY);assert v['state']==expected and v['target_page']==page

def test_old_or_foreign_runs_do_not_satisfy_current_run_step():
    t=saved();base={'id':'run','kind':'run','revision':3,'environment_id':'env','app_id':'app','app_type':'workflow','status':'success'}
    for field,value in [('kind','import'),('revision',2),('environment_id','other'),('app_id','other'),('app_type','agent')]:
        t['runs']=[{**base,field:value}];assert describe(t,READY)['state']=='publication'
    t['runs']=[base];v=describe(t,READY);assert v['state']=='review' and v['business_verified'] is False
    t['runs']=[{**base,'status':'failed','error':'private customer detail','result':{'private':'not returned'}}]
    v=describe(t,READY);assert v['state']=='review' and 'private' not in json.dumps(v)

def test_pending_old_operation_has_priority_without_restarting_it():
    t=saved();t['requirements_confirmed']=False;t['runs']=[{'id':'old','status':'pending','revision':1}]
    assert describe(t,{'can_confirm':False})['state']=='busy'

def test_same_revision_changed_saved_status_changes_snapshot_token():
    t=saved();old=describe(t,READY);t['configuration_confirmed']=False
    assert describe(t,READY)['snapshot_token']!=old['snapshot_token']

def test_customer_text_or_secret_fields_are_not_projected():
    t=saved();t.update(requirements={'goal':'private customer goal'},configuration={'api_key':'private-secret'},messages=[{'content':'private-message'}],materials=[{'text':'private-file'}])
    assert 'private' not in json.dumps(describe(t,READY))

@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'store',Store(tmp_path));monkeypatch.setattr(main,'DATA_ROOT',tmp_path)
    with TestClient(main.app) as c:
        t=c.post('/api/tasks',json={'name':'隔离进度引导','app_type':'workflow'}).json();yield c,t

def test_read_only_api_does_not_write_task_budget_or_draft(api):
    c,t=api;url='/api/tasks/'+t['id'];before=c.get(url).json();draft=c.get(url+'/plan-draft').json();ledger=copy.deepcopy(main.store.get('task_budget',t['id']))
    response=c.get(url+'/next-step',params={'revision':t['revision']});assert response.status_code==200,response.text
    assert response.json()['state']=='intake' and response.json()['task_id']==t['id']
    assert c.get(url).json()==before and c.get(url+'/plan-draft').json()==draft
    assert main.store.get('task_budget',t['id'])==ledger

@pytest.mark.parametrize('revision,status',[('999',409),('0',422),('true',422),('private',422)])
def test_stale_or_invalid_api_request_does_not_echo_input(api,revision,status):
    c,t=api;response=c.get('/api/tasks/'+t['id']+'/next-step',params={'revision':revision})
    assert response.status_code==status and 'private' not in response.text
