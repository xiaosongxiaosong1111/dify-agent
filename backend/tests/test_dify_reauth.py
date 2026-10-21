import asyncio,base64,copy,json
import httpx,pytest
from test_api import client
from test_login import env
from test_transports import transport_client
from app import dify,main
from app.storage import Store
from app.console_reauth import EMAIL,PASSWORD,BINDING,available


def expired():
    payload=base64.urlsafe_b64encode(b'{"exp":1}').decode().rstrip('=')
    return 'eyJ0eXAiOiJKV1QifQ.'+payload+'.c2ln'


def saved(tmp_path,token=None):
    store=Store(tmp_path)
    target={'id':'env','base_url':'http://dify.test','version':'1.17.1','connection_revision':'r1',
            BINDING:{'base_url':'http://dify.test','version':'1.17.1'},'capabilities':{}}
    store.put_with_secrets('environment','env',target,{EMAIL:'user@test.local',PASSWORD:'PASSWORD-PRIVATE','console_token':expired() if token is None else token,'csrf_token':'old-csrf','service_api_key':'independent-service'})
    return store,target,dify.DifyClient(target,store)


def mock_login(monkeypatch,action=None):
    calls=[]
    async def login(self,email,password):
        calls.append((email,password));assert email=='user@test.local' and password=='PASSWORD-PRIVATE'
        if action:await action(self)
        return {'console_token':'new-access','csrf_token':'new-csrf'}
    monkeypatch.setattr(dify.DifyClient,'login',login)
    return calls


@pytest.mark.parametrize('remember',[False,True])
def test_opt_in_and_forget_are_encrypted_and_not_in_public_or_task_data(client,monkeypatch,remember):
    target=env(client);calls=mock_login(monkeypatch)
    result=client.post(f"/api/environments/{target['id']}/login",json={'email':'user@test.local','password':'PASSWORD-PRIVATE','remember_login':remember})
    assert result.status_code==200 and len(calls)==1
    public=result.json()['environment'];assert public['has_saved_login']==public['automatic_login_enabled']==remember
    assert main.store.has_secret(target['id'],PASSWORD)==remember
    assert 'PRIVATE' not in result.text and 'user@test.local' not in result.text and BINDING not in public
    with main.store.connect() as db:dump='\n'.join(db.iterdump())
    assert 'PASSWORD-PRIVATE' not in dump and 'user@test.local' not in dump
    result=client.delete(f"/api/environments/{target['id']}/saved-login")
    assert result.status_code==200 and not result.json()['environment']['has_saved_login']
    assert not main.store.has_secret(target['id'],PASSWORD) and not main.store.has_secret(target['id'],EMAIL)
    assert main.store.secret(target['id'],'console_token')=='new-access'


@pytest.mark.parametrize('bad',['false',1,None,[],{}])
def test_remember_flag_requires_real_boolean_and_does_not_echo_password(client,bad):
    target=env(client);r=client.post(f"/api/environments/{target['id']}/login",json={'email':'user@test.local','password':'PASSWORD-PRIVATE','remember_login':bad})
    assert r.status_code==422 and 'PRIVATE' not in r.text


@pytest.mark.parametrize('change',[{'base_url':'http://another.test'},{'version':'future'}])
def test_environment_identity_change_deletes_saved_login(client,monkeypatch,change):
    target=env(client);mock_login(monkeypatch)
    client.post(f"/api/environments/{target['id']}/login",json={'email':'user@test.local','password':'PASSWORD-PRIVATE','remember_login':True})
    r=client.patch(f"/api/environments/{target['id']}",json=change)
    assert r.status_code==200 and not r.json()['has_saved_login'] and not main.store.has_secret(target['id'],PASSWORD)


def test_expired_token_refreshes_once_before_the_only_external_write(monkeypatch,tmp_path):
    store,target,adapter=saved(tmp_path);calls=mock_login(monkeypatch);seen=[]
    def handler(request):
        seen.append(request);assert request.headers['authorization']=='Bearer new-access'
        assert request.headers['x-csrf-token']=='new-csrf' and 'csrf_token=new-csrf' in request.headers['cookie']
        return httpx.Response(200,json={'app_id':'new'})
    transport_client(monkeypatch,dify,handler)
    result=asyncio.run(adapter.import_new('kind: app','demo'))
    assert result['app_id']=='new' and len(calls)==len(seen)==1
    assert store.secret('env','console_token')=='new-access' and store.get('environment','env')['connection_revision']=='r1'
    assert store.secret('env','service_api_key')=='independent-service'


@pytest.mark.parametrize('method',['GET','POST'])
def test_401_refresh_does_not_replay_a_write(monkeypatch,tmp_path,method):
    store,target,adapter=saved(tmp_path,'rejected-access');calls=mock_login(monkeypatch);seen=[]
    def handler(request):
        seen.append(request);return httpx.Response(401,json={'error':'PRIVATE-SERVER'}) if len(seen)==1 else httpx.Response(200,json={'ok':True})
    transport_client(monkeypatch,dify,handler)
    async def request():return await adapter.request(method,'/console/api/check',credential='console_token')
    if method=='GET':assert asyncio.run(request())=={'ok':True} and len(seen)==2
    else:
        with pytest.raises(dify.DifyError,match='未自动重发') as error:asyncio.run(request())
        assert error.value.http_status==401 and len(seen)==1 and 'PRIVATE' not in str(error.value)
    assert len(calls)==1 and store.secret('env','console_token')=='new-access'


def test_failed_auto_login_pauses_future_attempts_without_dispatching_original(monkeypatch,tmp_path):
    store,target,adapter=saved(tmp_path);calls=[];seen=[]
    async def fail(self,email,password):calls.append(1);raise dify.DifyError('private login failure')
    monkeypatch.setattr(dify.DifyClient,'login',fail)
    transport_client(monkeypatch,dify,lambda request:seen.append(request) or httpx.Response(200,json={}))
    for _ in range(2):
        with pytest.raises(dify.DifyError):asyncio.run(adapter.import_new('kind: app','demo'))
    assert len(calls)==1 and not seen and store.get('environment','env')['console_login_blocked']
    assert not available(store,store.get('environment','env'))


def test_two_concurrent_requests_share_one_refresh(monkeypatch,tmp_path):
    store,target,adapter=saved(tmp_path)
    async def yield_once(self):await asyncio.sleep(0)
    calls=mock_login(monkeypatch,yield_once);seen=[]
    def handler(request):
        seen.append(request);assert request.headers['authorization']=='Bearer new-access';return httpx.Response(200,json={'ok':True})
    transport_client(monkeypatch,dify,handler)
    async def run():return await asyncio.gather(*(adapter.request('GET','/console/api/check',credential='console_token') for _ in range(2)))
    assert asyncio.run(run())==[{'ok':True},{'ok':True}] and len(calls)==1 and len(seen)==2


@pytest.mark.parametrize('change',['host','version','revision','forget','password'])
def test_change_during_auto_login_prevents_token_commit_and_original_dispatch(monkeypatch,tmp_path,change):
    store,target,adapter=saved(tmp_path);seen=[]
    async def mutate(self):
        value=store.get('environment','env')
        if change=='forget':value.pop(BINDING)
        elif change=='password':store.set_secret('env',PASSWORD,'changed-password')
        else:value[{'host':'base_url','version':'version','revision':'connection_revision'}[change]]='changed'
        store.put('environment','env',value)
    calls=mock_login(monkeypatch,mutate)
    transport_client(monkeypatch,dify,lambda req:seen.append(req) or httpx.Response(200,json={}))
    with pytest.raises(dify.DifyError):asyncio.run(adapter.import_new('kind: app','demo'))
    assert len(calls)==1 and not seen and store.secret('env','console_token')==expired()


def test_saved_login_is_not_forwarded_to_a_changed_host_before_dispatch(monkeypatch,tmp_path):
    store,target,adapter=saved(tmp_path);current=store.get('environment','env');current['base_url']='http://foreign.test';store.put('environment','env',current)
    async def forbidden(*a,**kw):pytest.fail('must not send saved credentials')
    monkeypatch.setattr(dify.DifyClient,'login',forbidden)
    with pytest.raises(dify.DifyError):asyncio.run(adapter.test())


def test_service_requests_do_not_trigger_console_login(monkeypatch,tmp_path):
    store,target,adapter=saved(tmp_path)
    async def forbidden(*a,**kw):pytest.fail('service key must not reauthenticate console')
    monkeypatch.setattr(dify.DifyClient,'login',forbidden)
    def handler(request):
        assert request.headers['authorization']=='Bearer independent-service' and 'cookie' not in request.headers
        return httpx.Response(200,json={})
    transport_client(monkeypatch,dify,handler);assert asyncio.run(adapter.run_workflow({}))=={}


def test_auth_metadata_updates_do_not_stale_resource_proposals(client,monkeypatch):
    target=env(client);value=main.store.get('environment',target['id']);before=main.env_snapshot(value);mock_login(monkeypatch)
    r=client.post(f"/api/environments/{target['id']}/login",json={'email':'user@test.local','password':'PASSWORD-PRIVATE','remember_login':True})
    assert r.status_code==200
    # The first configured-token presence is a resource boundary. Later auth-only
    # changes on this same connection must not invalidate a valid resource read.
    value=main.store.get('environment',target['id']);before=main.env_snapshot(value)
    value['console_checked_at']='changed';value['console_login_blocked']=True
    assert main.env_snapshot(value)==before


def test_freshly_logged_in_token_rejected_again_stops_future_auto_logins(monkeypatch,tmp_path):
    store,target,adapter=saved(tmp_path,'rejected-access');calls=mock_login(monkeypatch);seen=[]
    transport_client(monkeypatch,dify,lambda request:seen.append(request) or httpx.Response(401,json={'error':'private'}))
    for _ in range(2):
        with pytest.raises(dify.DifyError) as error:asyncio.run(adapter.test())
        assert error.value.http_status==401 and 'private' not in str(error.value)
    assert len(calls)==1 and len(seen)==3 and store.get('environment','env')['console_login_blocked']


def test_environment_read_probe_can_succeed_after_auto_refresh_without_false_conflict(client,monkeypatch):
    target=env(client);mock_login(monkeypatch)
    client.post(f"/api/environments/{target['id']}/login",json={'email':'user@test.local','password':'PASSWORD-PRIVATE','remember_login':True})
    main.store.set_secret(target['id'],'console_token',expired())
    transport_client(monkeypatch,dify,lambda request:httpx.Response(200,json={'data':[]}))
    result=client.post(f"/api/environments/{target['id']}/test",json={})
    assert result.status_code==200,result.text
    assert main.store.secret(target['id'],'console_token')=='new-access'
