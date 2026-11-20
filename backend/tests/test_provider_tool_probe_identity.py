import json,threading,uuid
import httpx
import pytest
from fastapi.testclient import TestClient
from test_api import client
from test_task_budget import provider
from app import main
from app import provider_tool_probe as probe

OLD_KEY='not-a-real-key'
NEW_KEY='new-public-dummy-key-347'
NEW_URL='https://new-provider.example.invalid/v1'
NEW_MODEL='new-public-model-347'

def context(client,p):
    response=client.get(f"/api/providers/{p['id']}/tool-probe-plan");assert response.status_code==200,response.text
    return response.json()

def body(plan):return {'request_id':str(uuid.uuid4()),'source_token':plan['source_token'],'acknowledge_cost':True}

def submit(client,p,payload):return client.post(f"/api/providers/{p['id']}/tool-probe",json=payload)

def valid():return {'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'call_public_test','type':'function','function':{'name':probe.TOOL_NAME,'arguments':json.dumps({'text':probe.SAMPLE})}}]}}],'usage':{'prompt_tokens':30,'completion_tokens':12,'total_tokens':42}}

def wire(monkeypatch):
    calls=[]
    async def handle(self,request):
        calls.append({'url':str(request.url),'authorization':request.headers.get('Authorization'),'model':json.loads(request.content)['model']})
        return httpx.Response(200,json=valid(),request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',handle)
    return calls

def race(client,monkeypatch,kind):
    """Real create/plan/POST/PATCH APIs; the editor lives on a second TestClient eventloop."""
    p=provider(client);plan=context(client,p)
    assert p['base_url']=='https://example.com/v1' and p['model']=='test'
    calls=wire(monkeypatch)
    first=threading.Event();patching=threading.Event();patched=threading.Event()
    original=main.store.secret;reads=[]
    def hooked(item_id,key):
        reads.append(item_id)
        if not first.is_set():
            first.set();patching.set()
            # Short bounded chance for the editor thread to complete its PATCH while this
            # credential read is in flight; correctness is judged from the captured wire.
            patched.wait(0.5)
        return original(item_id,key)
    monkeypatch.setattr(main.store,'secret',hooked)
    payload=body(plan);outcome={}
    def run():outcome['probe']=submit(client,p,payload)
    thread=threading.Thread(target=run,name='probe-request');editor=TestClient(main.app)
    try:
        thread.start()
        assert patching.wait(10),'probe never read the credential'
        edit={'api_key':NEW_KEY} if kind=='key-only' else {'base_url':NEW_URL,'model':NEW_MODEL,'api_key':NEW_KEY}
        outcome['patch']=editor.patch(f"/api/providers/{p['id']}",json=edit)
    finally:
        patched.set();thread.join(15);editor.close()
    assert not thread.is_alive(),'probe request did not terminate'
    return {'provider':p,'plan':plan,'payload':payload,'calls':calls,'reads':reads,'original':original,'outcome':outcome}

@pytest.mark.parametrize('kind',['key-only','origin-model-key'])
def test_probe_uses_one_locked_snapshot_when_config_is_edited_in_flight(client,monkeypatch,kind):
    state=race(client,monkeypatch,kind);p=state['provider'];payload=state['payload']
    assert state['outcome']['patch'].status_code==200,state['outcome']['patch'].text
    response=state['outcome']['probe'];assert response.status_code==200,response.text
    r=response.json()
    assert state['calls'] and len(state['calls'])==1
    request=state['calls'][0]
    # Coherent old tuple: the old address/model never travel with the new key.
    assert request['authorization']=='Bearer '+OLD_KEY
    assert request['authorization']!='Bearer '+NEW_KEY
    assert request['model']=='test' and request['url']=='https://example.com/v1/chat/completions'
    assert r['ok'] and r['usage']['total_tokens']==42
    saved=main.store.get('provider',p['id'])
    assert saved['base_url']==(NEW_URL if kind=='origin-model-key' else 'https://example.com/v1')
    assert saved['model']==(NEW_MODEL if kind=='origin-model-key' else 'test')
    assert state['original'](p['id'],'api_key')==NEW_KEY
    # A completion from the old snapshot never promotes the edited configuration.
    assert saved['capabilities']['tools']=='untested' and 'tools' not in (saved.get('checks') or {})
    receipt=client.get(f"/api/providers/{p['id']}/tool-probes/{r['id']}").json()
    assert receipt['current_source'] is False and receipt['state'] in {'stale','succeeded'}
    stored=main.store.get('provider_tool_probe',payload['request_id'])
    assert stored['source_token']==payload['source_token'] and stored['configuration_revision']==state['plan']['configuration_revision']
    assert OLD_KEY not in json.dumps(receipt) and NEW_KEY not in json.dumps(receipt)
    assert OLD_KEY not in json.dumps(client.get('/api/providers').json())
    reads=len(state['reads']);calls=len(state['calls'])
    again=submit(client,p,payload)
    assert again.json()['id']==r['id'] and len(state['calls'])==calls
    assert len(state['reads'])==reads,'a duplicate receipt must not decrypt the credential again'

@pytest.mark.parametrize('failure',['empty','raises'])
def test_unavailable_credential_is_not_dispatched_and_leaves_no_orphan(client,monkeypatch,failure):
    p=provider(client);plan=context(client,p);calls=wire(monkeypatch)
    if failure=='empty':
        monkeypatch.setattr(main.store,'secret',lambda *a,**k:'')
    else:
        def broken(*a,**k):raise RuntimeError('synthetic credential decryption failure')
        monkeypatch.setattr(main.store,'secret',broken)
    response=submit(client,p,body(plan));assert response.status_code==200,response.text
    r=response.json()
    assert r['state']=='failed' and not r['ok'] and r['call_status']=='not_dispatched'
    assert r['usage']=={} and r['cost_basis']=='not_dispatched' and r['estimated_cost_usd']=='0'
    assert not calls and not main.provider_tool_probes.active
    saved=main.store.get('provider',p['id'])
    assert saved['capabilities']['tools']=='untested' and saved['checks']['tools']['state']=='failed'
    assert 'synthetic credential decryption failure' not in json.dumps(r)
