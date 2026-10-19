import copy,uuid
import pytest
from test_api import client
from test_schedule_observation import setup,mock,route,TRIGGER,PUBLISHED
from app import main
from app.dify import DifyError


def prepared(client,monkeypatch):
    task,env,root=setup(client);mock(client,monkeypatch,task,root,status='disabled')
    observation=client.get(route(task)).json()
    response=client.post(f"/api/tasks/{task['id']}/schedule-enable/prepare",json={'revision':task['revision'],'observation_id':observation['id']})
    assert response.status_code==200,response.text
    return task,env,root,response.json()


def execute(client,task,p,**patch):
    return client.post(f"/api/tasks/{task['id']}/schedule-enable/{p['id']}/execute",json={'revision':task['revision'],'resource_token':p['resource_token'],'approve_resource_plan':True,**patch})


def native(monkeypatch,root,*,enabled=False,pid=PUBLISHED,fail=False,after_disabled=False,change_after=False):
    calls=[]
    async def request(self,method,path,**kwargs):
        nonlocal enabled
        calls.append((method,path))
        if method=='POST':
            assert kwargs['json']=={'trigger_id':TRIGGER,'enable_trigger':True}
            if fail:raise DifyError('写结果未知')
            enabled=True;return {'private':'never-return'}
        if path.endswith('/workflows/publish'):return {'id':str(uuid.uuid4()) if change_after and enabled else pid,'graph':root['workflow']['graph'],**{k:root['workflow'][k] for k in ('features','environment_variables','conversation_variables')}}
        return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'enabled' if enabled and not after_disabled else 'disabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',request);return calls


def test_concrete_local_plan_no_requests_until_explicit_approval(client,monkeypatch):
    task,env,root,p=prepared(client,monkeypatch)
    async def forbidden(*a,**k):pytest.fail('没有批准不能请求')
    monkeypatch.setattr(main.DifyClient,'request',forbidden)
    assert p['action']=='enable' and p['recurring'] and not p['automatic_stop']
    assert p['schedule']['timezone']==root['workflow']['graph']['nodes'][0]['data']['timezone'] and p['max_write_attempts']==1 and '费用' in p['note']
    assert execute(client,task,p,approve_resource_plan=False).status_code==422
    assert execute(client,task,p,resource_token='0'*64).status_code==409
    assert execute(client,task,p,approve_resource_plan='private-input').status_code==422


def test_one_enable_four_reads_preserve_task_no_replay(client,monkeypatch):
    task,env,root,p=prepared(client,monkeypatch);before=copy.deepcopy(main.get_task(task['id']))
    calls=native(monkeypatch,root);r=execute(client,task,p);assert r.status_code==200,r.text
    assert r.json()['state']=='enabled' and r.json()['write_attempted'] and not r.json()['business_verified']
    assert [m for m,_ in calls]==['GET','GET','POST','GET','GET'] and main.get_task(task['id'])==before
    assert execute(client,task,p).status_code==409 and len(calls)==5
    assert 'never-return' not in r.text


def test_already_enabled_no_write(client,monkeypatch):
    task,env,root,p=prepared(client,monkeypatch);calls=native(monkeypatch,root,enabled=True)
    r=execute(client,task,p);assert r.status_code==200,r.text
    assert r.json()['state']=='already_enabled' and not r.json()['write_attempted'] and len(calls)==2


@pytest.mark.parametrize('mode',['revision','source','environment','confirmation'])
def test_local_changes_reject_before_remote_calls(client,monkeypatch,mode):
    task,env,root,p=prepared(client,monkeypatch);row=main.get_task(task['id'])
    if mode=='revision':row['revision']+=1
    elif mode=='environment':row['environment_id']='different'
    elif mode=='confirmation':row['configuration_confirmed']=False
    else:main.artifact_path(row).write_text('invalid',encoding='utf-8')
    main.store.put('task',row['id'],row);calls=native(monkeypatch,root)
    assert execute(client,task,p).status_code in {409,422} and not calls


def test_changed_published_id_same_graph_cannot_enable(client,monkeypatch):
    task,env,root,p=prepared(client,monkeypatch);calls=native(monkeypatch,root,pid=str(uuid.uuid4()))
    assert execute(client,task,p).status_code==502 and len(calls)==1
    assert main.store.get('schedule_enable',p['id'])['state']=='not_dispatched'


@pytest.mark.parametrize('status',['enabled','rate_limited','unknown'])
def test_prepare_requires_current_disabled_observation(client,monkeypatch,status):
    task,env,root,p=prepared(client,monkeypatch);obs=main.store.get('schedule_observation',p['observation_id']);obs['trigger']['records'][0]['status']=status;main.store.put('schedule_observation',obs['id'],obs)
    r=client.post(f"/api/tasks/{task['id']}/schedule-enable/prepare",json={'revision':task['revision'],'observation_id':obs['id']});assert r.status_code==422


def test_unknown_enable_no_retry_readonly_reconciliation(client,monkeypatch):
    task,env,root,p=prepared(client,monkeypatch);calls=native(monkeypatch,root,fail=True)
    assert execute(client,task,p).status_code==502 and [m for m,_ in calls]==['GET','GET','POST']
    main.schedule_enables.recover();assert execute(client,task,p).status_code==409
    fresh=client.post(f"/api/tasks/{task['id']}/schedule-enable/prepare",json={'revision':task['revision'],'observation_id':p['observation_id']}).json()
    assert execute(client,task,fresh).status_code==409 and len(calls)==3
    calls=native(monkeypatch,root,enabled=True)
    r=client.get(f"/api/tasks/{task['id']}/schedule-enable/{p['id']}/reconcile");assert r.status_code==200,r.text
    assert r.json()['state']=='enabled_observed_later' and len(calls)==1 and calls[0][0]=='GET'


@pytest.mark.parametrize('options',[{'after_disabled':True},{'change_after':True}])
def test_post_readback_not_proved_never_claim_enabled(client,monkeypatch,options):
    task,env,root,p=prepared(client,monkeypatch);calls=native(monkeypatch,root,**options)
    r=execute(client,task,p);assert r.status_code in {200,502},r.text
    assert main.store.get('schedule_enable',p['id'])['state'] in {'unknown','not_confirmed'} and len(calls)==5


def test_stop_in_progress_blocks_enable_enable_in_progress_blocks_stop(client,monkeypatch):
    task,env,root,p=prepared(client,monkeypatch);stop=client.post(f"/api/tasks/{task['id']}/schedule-stop/prepare",json={'revision':task['revision'],'observation_id':p['observation_id']}).json()
    row=main.store.get('schedule_stop',stop['id']);row['state']='executing';main.store.put('schedule_stop',row['id'],row);calls=native(monkeypatch,root)
    assert execute(client,task,p).status_code==409 and not calls
    row['state']='prepared';main.store.put('schedule_stop',row['id'],row)
    enabled=main.store.get('schedule_enable',p['id']);enabled['state']='executing';main.store.put('schedule_enable',enabled['id'],enabled)
    r=client.post(f"/api/tasks/{task['id']}/schedule-stop/{stop['id']}/execute",json={'revision':task['revision'],'resource_token':stop['resource_token'],'approve_resource_plan':True});assert r.status_code==409 and not calls


def test_credentials_rotation_stops_before_write(client,monkeypatch):
    task,env,root,p=prepared(client,monkeypatch);calls=[]
    async def request(self,method,path,**kw):
        calls.append(method);main.store.set_secret(env['id'],'console_token','fixture-rotated')
        return {'id':PUBLISHED,'graph':root['workflow']['graph'],**{k:root['workflow'][k] for k in ('features','environment_variables','conversation_variables')}}
    monkeypatch.setattr(main.DifyClient,'request',request)
    assert execute(client,task,p).status_code==409 and calls==['GET']


def test_recovery_public_history_no_replay_private_fields_filtered(client,monkeypatch):
    task,env,root,p=prepared(client,monkeypatch);row=main.store.get('schedule_enable',p['id']);row.update(state='executing',write_attempted=True,private='fake-private');main.store.put('schedule_enable',row['id'],row)
    calls=native(monkeypatch,root);main.schedule_enables.recover();assert not calls
    r=client.get(f"/api/tasks/{task['id']}/schedule-enable");assert r.json()['records'][0]['state']=='unknown' and 'fake-private' not in r.text and 'artifact_sha256' not in r.text


@pytest.mark.parametrize('mode',['missing','features','environment_variables','conversation_variables'])
def test_same_core_but_different_or_missing_full_configuration_rejects_enable(client,monkeypatch,mode):
    task,env,root,p=prepared(client,monkeypatch);calls=[]
    async def request(self,method,path,**kw):
        calls.append(method);assert method=='GET'
        value={'id':PUBLISHED,'graph':root['workflow']['graph'],**{k:copy.deepcopy(root['workflow'][k]) for k in ('features','environment_variables','conversation_variables')}}
        if mode=='missing':del value['features']
        elif mode=='features':value['features']['new_unknown']={'enabled':True}
        else:value[mode]=[{'id':str(uuid.uuid4()),'name':'changed','value':'fake-private-value'}]
        return value
    monkeypatch.setattr(main.DifyClient,'request',request)
    r=execute(client,task,p);assert r.status_code==502 and calls==['GET'] and 'fake-private-value' not in r.text
    assert main.store.get('schedule_enable',p['id'])['state']=='not_dispatched'
