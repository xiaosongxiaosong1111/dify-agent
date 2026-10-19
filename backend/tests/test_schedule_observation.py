import copy,json,uuid
import pytest
from test_api import client,approved,create_env
from test_schedule_trigger import plan
from app import main
from app.dify import DifyError

APP=str(uuid.uuid4());PUBLISHED=str(uuid.uuid4());TRIGGER=str(uuid.uuid4())


def setup(client):
    env=create_env(client);t=approved(client,env_id=env['id']);t['workflow_plan']=plan();main.store.put('task',t['id'],t)
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    t=response.json();import yaml
    root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'))
    return t,env,root


def route(t):return f"/api/tasks/{t['id']}/schedule-observe?app_id={APP}&revision={t['revision']}"


def mock(client,monkeypatch,t,root,*,status='enabled',changed=False,rows=None,published=True):
    calls=[]
    async def request(self,method,path,**kwargs):
        assert method=='GET' and kwargs['credential']=='console_token';calls.append(path)
        if path.endswith('/workflows/publish'):
            if not published:return None
            graph=copy.deepcopy(root['workflow']['graph'])
            if changed:graph['nodes'][1]['data']['template']='远端已改变'
            return {'id':PUBLISHED,'graph':graph,'private_metadata':'fixture-private-do-not-return'}
        assert path.endswith('/triggers')
        return {'data':rows if rows is not None else [{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':status,'title':'fixture-private-do-not-return'}]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    return calls


@pytest.mark.parametrize('status',['enabled','disabled','rate_limited','unexpected-sensitive-value'])
def test_current_observation_is_two_reads_and_independent_history_not_activation_or_task_change(client,monkeypatch,status):
    t,env,root=setup(client);before=copy.deepcopy(main.get_task(t['id']));calls=mock(client,monkeypatch,t,root,status=status)
    response=client.get(route(t));assert response.status_code==200,response.text;r=response.json()
    assert len(calls)==2 and r['core_graph_matched'] and r['source_state']=='matched'
    assert r['trigger']['state']==(status if status!='unexpected-sensitive-value' else 'unknown')
    assert r['published_workflow_id']==PUBLISHED and not r['ownership_verified'] and not r['activation_verified']
    assert main.get_task(t['id'])==before
    history=client.get(f"/api/tasks/{t['id']}/schedule-observations").json()
    assert history['records'][0]==r
    text=json.dumps(history);assert 'fixture-private' not in text and 'unexpected-sensitive-value' not in text and 'console_token' not in text and env['base_url'] not in text
    other=approved(client);assert not client.get(f"/api/tasks/{other['id']}/schedule-observations").json()['records']


@pytest.mark.parametrize('changed,published,expected',[(True,True,'different_graph'),(False,False,'published_unavailable')])
def test_matching_trigger_id_is_not_current_source_version_proof(client,monkeypatch,changed,published,expected):
    t,_,root=setup(client);mock(client,monkeypatch,t,root,changed=changed,published=published)
    r=client.get(route(t)).json();assert r['source_state']==expected and not r['core_graph_matched']
    assert r['trigger']['state']=='enabled' and not r['activation_verified']


@pytest.mark.parametrize('rows,expected',[
    ([], 'missing'),
    ([{'id':TRIGGER,'node_id':'other','trigger_type':'trigger-schedule','status':'enabled'}],'missing'),
    ([{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'enabled'}]*2,'ambiguous')])
def test_missing_other_or_duplicate_trigger_does_not_select_an_arbitrary_record(client,monkeypatch,rows,expected):
    t,_,root=setup(client);mock(client,monkeypatch,t,root,rows=rows)
    r=client.get(route(t)).json();assert r['trigger']['state']==expected


def test_bad_uuid_fails_before_dify_and_stale_revision_does_not_request(client,monkeypatch):
    t,_,root=setup(client);calls=mock(client,monkeypatch,t,root)
    assert client.get(route(t).replace(APP,'invalid')).status_code==422
    assert client.get(route(t).replace(f"revision={t['revision']}",f"revision={t['revision']+1}")).status_code==409
    assert not calls


@pytest.mark.parametrize('fault',['artifact','environment','revision'])
def test_source_change_during_reads_prevents_stale_receipt(client,monkeypatch,fault):
    t,env,root=setup(client)
    async def request(self,method,path,**kwargs):
        assert method=='GET'
        if path.endswith('/workflows/publish'):return {'id':PUBLISHED,'graph':root['workflow']['graph']}
        if fault=='artifact':main.artifact_path(main.get_task(t['id'])).write_text(main.artifact_path(t).read_text(encoding='utf-8')+'\n# changed',encoding='utf-8')
        elif fault=='environment':
            changed=main.store.get('environment',env['id']);changed['base_url']='http://127.0.0.1:9999';main.store.put('environment',env['id'],changed)
        else:
            changed=main.get_task(t['id']);changed['revision']+=1;main.store.put('task',t['id'],changed)
        return {'data':[]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    response=client.get(route(t));assert response.status_code==409,response.text
    assert not client.get(f"/api/tasks/{t['id']}/schedule-observations").json()['records']


def test_console_failure_has_no_retry_or_partial_history(client,monkeypatch):
    t,_,root=setup(client);calls=[]
    async def fail(self,method,path,**kwargs):calls.append(path);raise DifyError('管理连接不可用',http_status=401)
    monkeypatch.setattr(main.DifyClient,'request',fail)
    assert client.get(route(t)).status_code==502 and len(calls)==1
    assert not client.get(f"/api/tasks/{t['id']}/schedule-observations").json()['records']


def test_bad_remote_shape_does_not_persist_partial_observation(client,monkeypatch):
    t,_,root=setup(client);mock(client,monkeypatch,t,root,rows=[{'id':'bad','node_id':'timer','trigger_type':'trigger-schedule','status':'enabled'}])
    assert client.get(route(t)).status_code==502
    assert not client.get(f"/api/tasks/{t['id']}/schedule-observations").json()['records']


def test_plain_start_artifact_cannot_be_used_to_probe_arbitrary_schedules(client,monkeypatch):
    env=create_env(client);t=approved(client,env_id=env['id']);response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200
    t=response.json();calls=[]
    async def forbidden(*args,**kwargs):calls.append(1);pytest.fail('非定时成果不应查询调度')
    monkeypatch.setattr(main.DifyClient,'request',forbidden)
    assert client.get(route(t)).status_code==422 and not calls


def test_readonly_observation_does_not_pause_active_interview_or_depend_on_idle_model_budget(client,monkeypatch):
    t,_,root=setup(client);t['status']='interviewing';t['active_interview_id']='fixture-active';main.store.put('task',t['id'],t)
    before=copy.deepcopy(main.get_task(t['id']));mock(client,monkeypatch,t,root)
    response=client.get(route(t));assert response.status_code==200,response.text
    assert main.get_task(t['id'])==before


@pytest.mark.parametrize('fault',['console_token','csrf_token','base_url'])
def test_connection_change_after_first_read_does_not_send_new_credentials_to_old_target(client,monkeypatch,fault):
    t,env,root=setup(client);calls=[]
    async def request(self,method,path,**kwargs):
        calls.append(path);assert method=='GET' and path.endswith('/workflows/publish')
        old=self.store.secret(env['id'],'console_token');assert old=='test-console'
        if fault=='base_url':
            changed=main.store.get('environment',env['id']);changed['base_url']='https://new-connection.example';main.store.put('environment',env['id'],changed)
        else:main.store.set_secret(env['id'],fault,'new-fixture-secret-not-returned')
        assert self.store.secret(env['id'],'console_token')==old
        return {'id':PUBLISHED,'graph':root['workflow']['graph']}
    monkeypatch.setattr(main.DifyClient,'request',request)
    response=client.get(route(t));assert response.status_code==409,response.text
    assert len(calls)==1 and 'new-fixture-secret' not in response.text
    assert not client.get(f"/api/tasks/{t['id']}/schedule-observations").json()['records']


def test_transient_credential_snapshot_never_provides_another_owner_or_runtime_key(client):
    from app.schedule_observation import CredentialSnapshot
    env=create_env(client);snapshot=CredentialSnapshot(main.store,env['id'])
    assert snapshot.secret('other-owner','console_token') is None
    assert snapshot.secret(env['id'],'service_api_key') is None
    main.store.set_secret(env['id'],'console_token','rotated-fixture-value')
    assert snapshot.secret(env['id'],'console_token')=='test-console' and not snapshot.unchanged(main.store)
