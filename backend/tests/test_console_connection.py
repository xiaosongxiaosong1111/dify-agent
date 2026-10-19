import asyncio,base64,json,time
import httpx,pytest
from test_api import client
from test_login import env
from test_transports import transport_client
from app import main,dify
from app.console_connection import expiry,summary
from app.storage import Store


def token(value):
    segment=base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
    return f'header.{segment}.signature'


@pytest.mark.parametrize('value',[None,True,-1,1.2,'1000',253402300800,{'secret':'PRIVATE'}])
def test_invalid_exp_claim_is_unknown_without_exposing_claims(value):
    raw=token({'exp':value,'email':'private@test.local','credential':'PRIVATE'})
    assert expiry(raw) is None
    result=summary(raw,True,at=1000)
    assert result['state']=='unknown' and 'PRIVATE' not in json.dumps(result) and 'private@test' not in json.dumps(result)


@pytest.mark.parametrize('raw',['plain-token','a.b.c','a..c','a.invalid+.c','a.b.c.d','x'*16385])
def test_unparseable_tokens_do_not_claim_expiry(raw):
    assert expiry(raw) is None
    assert summary(raw,True,at=1000)['state']=='unknown'


def test_expiry_boundary_and_unknown_auth_not_reported_verified():
    assert summary(token({'exp':1000}),True,1000)['state']=='expired'
    assert summary(token({'exp':1001}),True,1000.5)['seconds_remaining']==1
    assert summary(token({'exp':1300}),True,1000)['state']=='expiring'
    result=summary(token({'exp':1301}),True,1000)
    assert result['state']=='present' and result['verification']=='local_expiry_hint_not_authentication'
    assert '权限' in result['message']
    assert summary('',False,1000)['state']=='missing'
    assert summary(token({'exp':2000}),False,1000)['state']=='incomplete'


def test_duplicate_or_too_deep_payload_is_bounded():
    for payload in ('{"exp":1,"exp":9999}','['*2000+'0'+']'*2000):
        raw='head.'+base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')+'.signature'
        assert expiry(raw) is None


def test_public_environment_returns_only_hint_and_does_not_modify_store(client):
    secret=token({'exp':1,'email':'private@sample.test','credential':'PRIVATE-CLAIM'})
    target=env(client,console_token=secret,csrf_token='PRIVATE-CSRF')
    saved=main.store.get('environment',target['id'])
    assert target['has_console_token'] and target['console_connection']['state']=='expired'
    response=client.get('/api/environments');assert 'PRIVATE' not in response.text and 'private@' not in response.text and secret not in response.text
    assert main.store.get('environment',target['id'])==saved
    assert main.store.secret(target['id'],'console_token')==secret


def test_expired_console_preflight_never_sends_request_or_refreshes(monkeypatch,tmp_path):
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,json={})
    transport_client(monkeypatch,dify,handler);store=Store(tmp_path);store.set_secret('env','console_token',token({'exp':1}));store.set_secret('env','csrf_token','csrf')
    with pytest.raises(dify.DifyError,match='未发送本次请求'):
        asyncio.run(dify.DifyClient({'id':'env','base_url':'http://dify.test'},store).request('POST','/console/api/apps/imports',credential='console_token',json={'technical':'only'}))
    assert calls==[]


def test_console401_is_actionable_sanitized_once_and_preserves_key(monkeypatch,tmp_path):
    seen=[]
    def handler(request):seen.append(request);return httpx.Response(401,json={'error':'PRIVATE-SERVER'})
    transport_client(monkeypatch,dify,handler);store=Store(tmp_path);store.set_secret('env','console_token','opaque-test-key')
    with pytest.raises(dify.DifyError) as raised:
        asyncio.run(dify.DifyClient({'id':'env','base_url':'http://dify.test'},store).test())
    assert raised.value.http_status==401 and 'Sierra' in str(raised.value) and 'PRIVATE' not in str(raised.value)
    assert len(seen)==1 and store.secret('env','console_token')=='opaque-test-key'


def test_console_expiry_never_blocks_independent_service_credentials(monkeypatch,tmp_path):
    seen=[]
    def handler(request):seen.append(request);assert request.headers['Authorization']=='Bearer independent-service';return httpx.Response(200,json={'ok':True})
    transport_client(monkeypatch,dify,handler);store=Store(tmp_path);store.set_secret('env','console_token',token({'exp':1}));store.set_secret('env','service_api_key','independent-service')
    result=asyncio.run(dify.DifyClient({'id':'env','base_url':'http://dify.test'},store).request('GET','/v1/workflows/run/example',credential='service_api_key'))
    assert result=={'ok':True} and len(seen)==1


def test_display_countdown_cannot_invalidate_case_or_configuration_stamps(client,monkeypatch):
    from test_case_dsl_semantics import setup
    from app.configuration_proposals import env_stamp
    from app import console_connection
    task,p,light=setup(client)
    target=env(client,console_token=token({'exp':2000}),csrf_token='csrf')
    task['environment_id']=target['id']
    monkeypatch.setattr(console_connection.time,'time',lambda:1000)
    case_before=main.case_proposals.stamp(task);config_before=env_stamp(main,task)
    public_before=main.env_public(main.store.get('environment',target['id']))
    monkeypatch.setattr(console_connection.time,'time',lambda:2001)
    public_after=main.env_public(main.store.get('environment',target['id']))
    assert public_before['console_connection']['state']=='present' and public_after['console_connection']['state']=='expired'
    assert main.case_proposals.stamp(task)==case_before and env_stamp(main,task)==config_before
    saved=main.store.get('environment',target['id']);saved['base_url']='http://changed.test';main.store.put('environment',target['id'],saved)
    assert main.case_proposals.stamp(task)!=case_before and env_stamp(main,task)!=config_before
