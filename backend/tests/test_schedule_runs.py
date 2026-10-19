import copy,json,uuid
import pytest
from test_api import client,approved
from test_schedule_observation import setup,APP,PUBLISHED
from app import main
from app.dify import DifyError

RUN=str(uuid.uuid4())


def route(t):return f"/api/tasks/{t['id']}/schedule-runs/read?app_id={APP}&revision={t['revision']}"


def responses(monkeypatch,t,root,*,fault=None,status='succeeded',count=1):
    calls=[];ids=[RUN]+[str(uuid.uuid4()) for _ in range(max(count-1,0))]
    async def request(self,method,path,**kwargs):
        assert method=='GET' and kwargs['credential']=='console_token';calls.append(path)
        if path.endswith('/workflows/publish'):return {'id':PUBLISHED,'version':'published-version','graph':root['workflow']['graph']}
        if path.endswith('/workflow-app-logs'):
            assert kwargs['params']=={'page':1,'limit':20,'detail':False}
            rows=[{'workflow_run':{'id':rid,'version':'published-version','triggered_from':'schedule','status':status},'created_by_account':{'email':'private-fixture-email'}} for rid in ids[:count]]
            if fault=='manual':rows[0]['workflow_run']['triggered_from']='app-run'
            if fault=='duplicate':rows.append(copy.deepcopy(rows[0]))
            if fault=='credentials':main.store.set_secret(self.env['id'],'console_token','new-fixture-console')
            return {'data':rows,'has_more':True}
        assert '/workflow-runs/' in path
        graph=copy.deepcopy(root['workflow']['graph'])
        if fault=='graph':graph['nodes'][1]['data']['template']='changed-remote-code'
        return {'id':str(uuid.uuid4()) if fault=='id' else path.rsplit('/',1)[1],'version':None if fault=='missing_version' else 'other-version' if fault=='version' else 'published-version','graph':graph,'status':'failed' if fault=='status' else status,'created_at':1700000000,'inputs':{'secret':'private-fixture-input'},'outputs':{'secret':'private-fixture-output'},'error':'private-fixture-error'}
    monkeypatch.setattr(main.DifyClient,'request',request)
    return calls


def test_schedule_log_detail_version_and_graph_are_linked_without_business_or_published_id_claim(client,monkeypatch):
    t,_,root=setup(client);before=copy.deepcopy(main.get_task(t['id']));calls=responses(monkeypatch,t,root)
    response=client.get(route(t));assert response.status_code==200,response.text;r=response.json()
    assert len(calls)==3 and r['runs'][0]['state']=='matched_platform_success'
    assert r['runs'][0]['run_id']==RUN and r['runs'][0]['triggered_from']=='schedule'
    assert not r['runs'][0]['business_verified'] and not r['runs'][0]['same_published_workflow_id_verified']
    assert not r['business_verified'] and r['log_page_has_more']
    assert main.get_task(t['id'])==before
    history=client.get(f"/api/tasks/{t['id']}/schedule-runs").json();assert history['records'][0]==r
    text=json.dumps(history);assert 'private-fixture' not in text and 'console_token' not in text and 'changed-remote-code' not in text
    other=approved(client);assert not client.get(f"/api/tasks/{other['id']}/schedule-runs").json()['records']


@pytest.mark.parametrize('fault',['id','version','missing_version','graph','status'])
def test_mismatched_run_source_is_not_current_schedule_success(client,monkeypatch,fault):
    t,_,root=setup(client);responses(monkeypatch,t,root,fault=fault)
    response=client.get(route(t));assert response.status_code==200
    assert response.json()['runs'][0]['state']=='source_not_proved'


@pytest.mark.parametrize('status',['failed','stopped','running','partial-succeeded'])
def test_non_success_platform_status_does_not_become_acceptance_pass(client,monkeypatch,status):
    t,_,root=setup(client);responses(monkeypatch,t,root,status=status)
    r=client.get(route(t)).json();assert r['runs'][0]['state']=='matched_platform_non_success'
    assert r['runs'][0]['status']==status and not r['business_verified']


def test_manual_or_missing_log_does_not_count_as_schedule_run(client,monkeypatch):
    t,_,root=setup(client);calls=responses(monkeypatch,t,root,fault='manual')
    r=client.get(route(t)).json();assert not r['runs'] and len(calls)==2 and r['other_log_count']==1
    assert '排队' in r['note']


def test_detail_read_is_bounded_to_three_and_does_not_hide_more_history(client,monkeypatch):
    t,_,root=setup(client);calls=responses(monkeypatch,t,root,count=4)
    r=client.get(route(t)).json();assert len(r['runs'])==3 and len(calls)==5 and r['schedule_detail_truncated']


def test_duplicate_ids_and_connection_change_do_not_persist_partial_evidence(client,monkeypatch):
    t,_,root=setup(client);calls=responses(monkeypatch,t,root,fault='duplicate')
    assert client.get(route(t)).status_code==502 and len(calls)==2
    assert not client.get(f"/api/tasks/{t['id']}/schedule-runs").json()['records']
    calls=responses(monkeypatch,t,root,fault='credentials')
    assert client.get(route(t)).status_code==409 and len(calls)==2
    assert not client.get(f"/api/tasks/{t['id']}/schedule-runs").json()['records']


def test_failure_has_no_retry_or_run_dispatch(client,monkeypatch):
    t,_,root=setup(client);calls=[]
    async def fail(self,method,path,**kwargs):
        assert method=='GET';calls.append(path);raise DifyError('管理连接不可用')
    monkeypatch.setattr(main.DifyClient,'request',fail)
    assert client.get(route(t)).status_code==502 and len(calls)==1
    assert not client.get(f"/api/tasks/{t['id']}/schedule-runs").json()['records']
