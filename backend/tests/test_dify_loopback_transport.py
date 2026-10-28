"""Loopback must bypass inherited proxy routing without disabling TLS CA settings."""
import asyncio,sys
from pathlib import Path
import httpx,pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.dify import DifyClient
from app.storage import Store

@pytest.fixture
def system_proxy(monkeypatch):
    # Also models Windows registry proxy discovery when no *_PROXY variable exists.
    monkeypatch.setattr(httpx._client,'get_environment_proxies',lambda:{'all://':'http://public-proxy.invalid:8888'})

@pytest.mark.parametrize('base,local',[
    ('http://127.0.0.1:8080',True),('http://127.0.0.2:8080',True),
    ('http://localhost:8080',True),('https://LOCALHOST:8443',True),
    ('http://[::1]:8080',True),('https://localhost.:8443',True),
    ('http://10.0.0.9:8080',False),('https://public-dify.invalid',False),
])
def test_actual_httpx_route_under_inherited_system_proxy(base,local,system_proxy):
    async def inspect():
        target=DifyClient({'base_url':base},None)
        async with httpx.AsyncClient(**target._client_options()) as client:
            pool=client._transport_for_url(httpx.URL(base))._pool
            assert type(pool).__name__==('AsyncConnectionPool' if local else 'AsyncHTTPProxy')
    asyncio.run(inspect())

def test_direct_transport_retains_ca_environment_contract(monkeypatch):
    calls=[]
    monkeypatch.setattr(httpx,'AsyncHTTPTransport',lambda **kw:calls.append(kw) or 'direct')
    assert DifyClient({'base_url':'https://localhost:8443'},None)._client_options()=={'transport':'direct'}
    assert calls==[{'proxy':None,'trust_env':True}]
    assert DifyClient({'base_url':'https://public-dify.invalid'},None)._client_options()=={}

@pytest.mark.parametrize('base,local',[('http://127.0.0.1:8080',True),('https://public-dify.invalid',False)])
@pytest.mark.parametrize('operation',['request','login','workspace'])
def test_all_three_sdk_clients_apply_loopback_transport(tmp_path,monkeypatch,base,local,operation):
    store=Store(tmp_path);store.set_secret('public-env','service_api_key','PUBLIC_SYNTHETIC_ONLY')
    client=DifyClient({'id':'public-env','base_url':base},store);captured=[]
    class StopBeforeNetwork(RuntimeError):pass
    class Spy:
        def __init__(self,**kw):captured.append(kw)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):
            if 'transport' in captured[-1]:await captured[-1]['transport'].aclose()
        async def deny(self,*a,**kw):raise StopBeforeNetwork()
        get=post=request=deny
    monkeypatch.setattr(httpx,'AsyncClient',Spy)
    async def run():
        with pytest.raises(StopBeforeNetwork):
            if operation=='request':await client.request('GET','/public',credential='service_api_key')
            elif operation=='login':await client.login('public@example.invalid','PUBLIC_SYNTHETIC_ONLY')
            else:await client.login_workspace({'console_token':'PUBLIC_TOKEN','csrf_token':'PUBLIC_CSRF'})
    asyncio.run(run());assert len(captured)==1
    assert ('transport' in captured[0]) is local
    assert captured[0]['follow_redirects'] is False
    assert captured[0]['timeout']==(90 if operation=='request' else 30)

@pytest.mark.parametrize('base,expected_pool',[('http://127.0.0.1:8080','AsyncConnectionPool'),('https://public-dify.invalid','AsyncHTTPProxy')])
def test_login_access_probe_and_workspace_use_correct_route(base,expected_pool,system_proxy,monkeypatch):
    calls=[]
    async def transport(self,request):
        assert type(self._pool).__name__==expected_pool;calls.append(request.url.path)
        if request.url.path.endswith('/login'):
            return httpx.Response(200,json={'result':'success'},headers=[('set-cookie','access_token=PUBLIC_ACCESS_TOKEN_123456789; Path=/'),('set-cookie','csrf_token=PUBLIC_CSRF_TOKEN_123456789; Path=/')])
        return httpx.Response(200,json={'id':'PUBLIC_WORKSPACE'} if request.url.path.endswith('/summary') else {'data':[]})
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',transport)
    async def run():
        client=DifyClient({'id':'public-env','base_url':base},None)
        tokens=await client.login('public@example.invalid','PUBLIC_SYNTHETIC_ONLY')
        assert await client.login_workspace(tokens)=='PUBLIC_WORKSPACE'
    asyncio.run(run())
    assert calls==['/console/api/login','/console/api/apps','/console/api/workspaces/current/summary']
