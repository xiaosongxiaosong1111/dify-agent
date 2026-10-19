import copy,uuid
import pytest
from test_api import client,create_env
from test_schedule_observation import setup,route,mock,TRIGGER
from app import main
from app.dify import DifyError


def prepared(client,monkeypatch):
    t,env,root=setup(client);mock(client,monkeypatch,t,root)
    observation=client.get(route(t));assert observation.status_code==200,observation.text
    response=client.post(f"/api/tasks/{t['id']}/schedule-stop/prepare",json={'revision':t['revision'],'observation_id':observation.json()['id']})
    assert response.status_code==200,response.text
    return t,env,response.json()


def execute(client,t,p,**patch):
    return client.post(f"/api/tasks/{t['id']}/schedule-stop/{p['id']}/execute",json={'revision':t['revision'],'resource_token':p['resource_token'],'approve_resource_plan':True,**patch})


def test_prepare_is_local_concrete_and_requires_explicit_approval_before_requests(client,monkeypatch):
    t,env,p=prepared(client,monkeypatch);calls=[]
    async def forbidden(*args,**kwargs):calls.append(1);pytest.fail('未批准不允许请求')
    monkeypatch.setattr(main.DifyClient,'request',forbidden)
    assert p['state']=='prepared' and p['action']=='disable' and p['max_write_attempts']==1
    assert p['environment_id']==env['id'] and p['trigger_id']==TRIGGER and '已入队' in p['note']
    assert execute(client,t,p,approve_resource_plan=False).status_code==422
    assert execute(client,t,p,resource_token='0'*64).status_code==409 and not calls


def test_exact_one_disable_and_read_verification_preserve_task_and_do_not_replay(client,monkeypatch):
    t,env,p=prepared(client,monkeypatch);before=copy.deepcopy(main.get_task(t['id']));calls=[];disabled=False
    async def request(self,method,path,**kwargs):
        nonlocal disabled
        calls.append((method,path));assert self.env['id']==env['id'] and kwargs['credential']=='console_token'
        if method=='POST':
            assert path.endswith('/trigger-enable') and kwargs['json']=={'trigger_id':TRIGGER,'enable_trigger':False}
            disabled=True;return {'status':'disabled','private_payload':'do-not-return'}
        assert method=='GET' and path.endswith('/triggers')
        return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'disabled' if disabled else 'enabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    response=execute(client,t,p);assert response.status_code==200,response.text;result=response.json()
    assert result['state']=='disabled' and result['write_attempted'] and 'private_payload' not in response.text
    assert [m for m,_ in calls]==['GET','POST','GET'] and main.get_task(t['id'])==before
    assert execute(client,t,p).status_code==409 and len(calls)==3


def test_already_disabled_is_no_write_and_no_full_app_stop_claim(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);calls=[]
    async def request(self,method,path,**kwargs):
        calls.append(method);assert method=='GET'
        return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'disabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    r=execute(client,t,p);assert r.status_code==200
    assert r.json()['state']=='already_disabled' and not r.json()['write_attempted'] and calls==['GET']


def test_missing_target_is_not_replaced_with_another_trigger(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);calls=[]
    async def request(self,method,path,**kwargs):
        calls.append(method);assert method=='GET'
        return {'data':[{'id':str(uuid.uuid4()),'node_id':'timer','trigger_type':'trigger-schedule','status':'enabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    assert execute(client,t,p).status_code==502 and calls==['GET']
    saved=main.store.get('schedule_stop',p['id']);assert saved['state']=='not_dispatched' and not saved['write_attempted']


def test_old_observation_stops_original_environment_without_changing_current_environment(client,monkeypatch):
    t,env,p=prepared(client,monkeypatch);other=create_env(client)
    current=main.get_task(t['id']);current['environment_id']=other['id'];current['revision']+=1;main.store.put('task',t['id'],current)
    old=main.store.get('schedule_observation',p['observation_id'])
    response=client.post(f"/api/tasks/{t['id']}/schedule-stop/prepare",json={'revision':current['revision'],'observation_id':old['id']});assert response.status_code==200,response.text
    new=response.json();calls=[]
    async def request(self,method,path,**kwargs):
        calls.append(method);assert self.env['id']==env['id'] and method=='GET'
        return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'disabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    before=copy.deepcopy(main.get_task(t['id']));assert execute(client,current,new).status_code==200
    assert main.get_task(t['id'])==before and calls==['GET'] and new['source_revision']!=current['revision']


def test_environment_or_credential_change_does_not_continue_to_old_write(client,monkeypatch):
    t,env,p=prepared(client,monkeypatch);calls=[]
    async def request(self,method,path,**kwargs):
        calls.append(method);assert method=='GET'
        main.store.set_secret(env['id'],'console_token','new-fixture-console')
        assert self.store.secret(env['id'],'console_token')=='test-console'
        return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'enabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    assert execute(client,t,p).status_code==409 and calls==['GET']
    assert main.store.get('schedule_stop',p['id'])['state']=='not_dispatched'


def test_post_timeout_remains_unknown_and_never_retry_or_enable(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);calls=[]
    async def request(self,method,path,**kwargs):
        calls.append(method)
        if method=='POST':raise DifyError('停用请求超时，结果未知')
        return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'enabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    assert execute(client,t,p).status_code==502
    saved=main.store.get('schedule_stop',p['id']);assert saved['state']=='unknown' and saved['write_attempted']
    assert execute(client,t,p).status_code==409 and calls==['GET','POST']
    main.schedule_stops.recover();assert calls==['GET','POST']


def test_recover_and_validation_do_not_replay_or_echo_input(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);row=main.store.get('schedule_stop',p['id']);row['state']='executing';row['write_attempted']=True;main.store.put('schedule_stop',p['id'],row)
    main.schedule_stops.recover();assert main.store.get('schedule_stop',p['id'])['state']=='unknown'
    response=execute(client,t,p,approve_resource_plan='fake-private-input');assert response.status_code==422 and 'fake-private-input' not in response.text
    history=client.get(f"/api/tasks/{t['id']}/schedule-stop").json();assert len(history['records'])==1


def test_write_success_without_disabled_readback_does_not_claim_stopped(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);calls=[]
    async def request(self,method,path,**kwargs):
        calls.append(method)
        if method=='POST':return {'status':'disabled'}
        return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'enabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',request)
    response=execute(client,t,p);assert response.status_code==200
    assert response.json()['state']=='not_confirmed' and calls==['GET','POST','GET']


def test_current_revision_foreign_plan_and_enable_payload_do_not_dispatch(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);calls=[]
    async def forbidden(*args,**kwargs):calls.append(1);pytest.fail('无效批准不派发')
    monkeypatch.setattr(main.DifyClient,'request',forbidden)
    assert execute(client,t,p,revision=t['revision']+1).status_code==409
    assert execute(client,t,p,enable_trigger=True).status_code==422
    other=main.get_task(t['id']);other['id']=str(uuid.uuid4());main.store.put('task',other['id'],other)
    assert execute(client,other,p).status_code==404 and not calls


def test_public_stop_history_never_returns_private_fields_or_raw_console_reply(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);row=main.store.get('schedule_stop',p['id']);row['private_future_field']='fake-private-secret';main.store.put('schedule_stop',p['id'],row)
    response=client.get(f"/api/tasks/{t['id']}/schedule-stop");assert 'fake-private-secret' not in response.text


def test_ambiguous_or_unmatched_observation_cannot_prepare_resource_plan(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);observation=main.store.get('schedule_observation',p['observation_id']);observation['core_graph_matched']=False;main.store.put('schedule_observation',observation['id'],observation)
    response=client.post(f"/api/tasks/{t['id']}/schedule-stop/prepare",json={'revision':t['revision'],'observation_id':observation['id']})
    assert response.status_code==422


def test_unknown_blocks_another_plan_write_until_readonly_disabled_reconciliation(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);row=main.store.get('schedule_stop',p['id']);row.update(state='unknown',write_attempted=True);main.store.put('schedule_stop',p['id'],row)
    fresh=client.post(f"/api/tasks/{t['id']}/schedule-stop/prepare",json={'revision':t['revision'],'observation_id':p['observation_id']}).json()
    calls=[]
    async def read_only(self,method,path,**kwargs):
        calls.append(method);assert method=='GET'
        return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'disabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',read_only)
    assert execute(client,t,fresh).status_code==409 and not calls
    response=client.get(f"/api/tasks/{t['id']}/schedule-stop/{p['id']}/reconcile");assert response.status_code==200,response.text
    assert response.json()['state']=='disabled_observed_later' and '不能归因' in response.json()['message'] and calls==['GET']
    result=execute(client,t,fresh);assert result.status_code==200 and result.json()['state']=='already_disabled' and calls==['GET','GET']


def test_enabled_readback_does_not_clear_unknown_for_retry(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);row=main.store.get('schedule_stop',p['id']);row.update(state='unknown',write_attempted=True);main.store.put('schedule_stop',p['id'],row)
    async def read_only(self,method,path,**kwargs):
        assert method=='GET';return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'enabled'}]}
    monkeypatch.setattr(main.DifyClient,'request',read_only)
    response=client.get(f"/api/tasks/{t['id']}/schedule-stop/{p['id']}/reconcile")
    assert response.json()['state']=='unknown' and response.json()['reconciled_state']=='enabled'


def test_malformed_reconciliation_stays_known_unknown_and_is_not_a_server_error(client,monkeypatch):
    t,_,p=prepared(client,monkeypatch);row=main.store.get('schedule_stop',p['id']);row.update(state='unknown',write_attempted=True);main.store.put('schedule_stop',p['id'],row)
    async def bad(self,method,path,**kwargs):
        assert method=='GET';return {'data':'bad-shape'}
    monkeypatch.setattr(main.DifyClient,'request',bad)
    response=client.get(f"/api/tasks/{t['id']}/schedule-stop/{p['id']}/reconcile")
    assert response.status_code==502 and main.store.get('schedule_stop',p['id'])==row


def test_concurrent_same_target_plan_is_rejected_before_any_write(client,monkeypatch):
    import asyncio,httpx
    t,_,p=prepared(client,monkeypatch)
    fresh=client.post(f"/api/tasks/{t['id']}/schedule-stop/prepare",json={'revision':t['revision'],'observation_id':p['observation_id']}).json()
    async def run():
        reached=asyncio.Event();release=asyncio.Event();calls=[];disabled=False
        async def request(self,method,path,**kwargs):
            nonlocal disabled
            calls.append(method)
            if len(calls)==1:reached.set();await release.wait()
            if method=='POST':disabled=True;return {}
            return {'data':[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'disabled' if disabled else 'enabled'}]}
        monkeypatch.setattr(main.DifyClient,'request',request)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://fixture') as api:
            def payload(plan):return {'revision':t['revision'],'resource_token':plan['resource_token'],'approve_resource_plan':True}
            first=asyncio.create_task(api.post(f"/api/tasks/{t['id']}/schedule-stop/{p['id']}/execute",json=payload(p)))
            await reached.wait()
            second=await api.post(f"/api/tasks/{t['id']}/schedule-stop/{fresh['id']}/execute",json=payload(fresh))
            assert second.status_code==409 and calls==['GET']
            release.set();assert (await first).status_code==200 and calls==['GET','POST','GET']
    asyncio.run(run())
