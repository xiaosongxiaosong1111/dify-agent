import asyncio,copy,json,uuid
import httpx
import pytest
from test_api import client
from test_task_budget import provider
from app import main
from app import provider_tool_probe as probe
from app.providers import call_model
from app.provider_presets import VENDORS

def context(client,p):
    response=client.get(f"/api/providers/{p['id']}/tool-probe-plan");assert response.status_code==200,response.text
    return response.json()

def body(plan):return {'request_id':str(uuid.uuid4()),'source_token':plan['source_token'],'acknowledge_cost':True}

def submit(client,p,payload):return client.post(f"/api/providers/{p['id']}/tool-probe",json=payload)

def valid():return {'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'call_public_test','type':'function','function':{'name':probe.TOOL_NAME,'arguments':json.dumps({'text':probe.SAMPLE})}}]}}],'usage':{'prompt_tokens':30,'completion_tokens':12,'total_tokens':42}}

def transport(monkeypatch,data=None,status=200,raw=None):
    calls=[]
    async def handle(self,request):
        calls.append(request);return httpx.Response(status,json=valid() if data is None else data,request=request) if raw is None else httpx.Response(status,content=raw,request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',handle)
    return calls

def test_plan_is_local_no_decryption_no_writes_and_other_protocol_refused(client,monkeypatch):
    p=provider(client);before=copy.deepcopy(main.store.get('provider',p['id']))
    def forbidden(*a,**kw):pytest.fail('Preparation must not decrypt or call upstream')
    monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
    plan=context(client,p);assert plan['ready'] and plan['max_output_tokens']==256 and plan['timeout_seconds']==30 and plan['max_http_requests']==1 and not plan['tool_execution']
    assert main.store.get('provider',p['id'])==before and main.store.list('provider_tool_probe')==[]
    stored=main.store.get('provider',p['id']);stored['protocol']='anthropic';main.store.put('provider',p['id'],stored)
    plan=context(client,p);assert not plan['ready'];assert submit(client,p,body(plan)).status_code==422 and main.store.list('provider_tool_probe')==[]

def test_missing_pricing_or_ack_or_stale_source_never_dispatches(client,monkeypatch):
    p=provider(client,priced=False);calls=transport(monkeypatch);plan=context(client,p)
    assert not plan['ready'] and submit(client,p,body(plan)).status_code==422 and not calls
    p=provider(client);plan=context(client,p)
    assert submit(client,p,body(plan)|{'acknowledge_cost':False}).status_code==422
    assert client.patch(f"/api/providers/{p['id']}",json={'model':'changed-model'}).status_code==200
    assert submit(client,p,body(plan)).status_code==409 and not calls

def test_actual_wire_single_request_receipt_and_idempotent_recovery(client,monkeypatch):
    p=provider(client);calls=transport(monkeypatch);plan=context(client,p);payload=body(plan)
    response=submit(client,p,payload);assert response.status_code==200,response.text;r=response.json()
    assert r['state']=='succeeded' and r['ok'] and r['current_source'] and r['usage']['total_tokens']==42 and not r['tool_execution']
    wire=json.loads(calls[0].content);assert len(calls)==1 and wire['tool_choice']=='required' and wire['parallel_tool_calls'] is False and wire['max_tokens']==256 and wire['stream'] is False
    assert wire['messages']==probe.MESSAGES and wire['tools']==[probe.TOOL] and 'response_format' not in wire
    assert 'TASK-PRIVATE' not in str(wire) and calls[0].headers['Authorization']=='Bearer not-a-real-key'
    again=submit(client,p,payload);assert again.json()['id']==r['id'] and len(calls)==1
    read=client.get(f"/api/providers/{p['id']}/tool-probes/{r['id']}");assert read.status_code==200 and read.json()==again.json()
    public=client.get('/api/providers').json();out=next(v for v in public if v['id']==p['id']);assert out['capabilities']['tools']=='verified' and out['capabilities']['text']=='untested'
    assert out['checks']['tools']['scope']=='single_function_request_only' and not out['checks']['tools']['tool_execution']
    assert 'not-a-real-key' not in json.dumps(r)
    other=provider(client);assert submit(client,other,payload).status_code==409 and client.get(f"/api/providers/{other['id']}/tool-probes/{r['id']}").status_code==404

@pytest.mark.parametrize('kind',['text_only','wrong_role','wrong_name','extra_arguments','wrong_argument_type','duplicate_argument','multiple_calls','missing_id','length','missing_usage','large_response'])
def test_only_strict_fixed_request_is_verified_and_raw_text_not_saved(client,monkeypatch,kind):
    p=provider(client);data=valid();choice=data['choices'][0];call=choice['message']['tool_calls'][0]
    if kind=='text_only':choice['message']={'content':'I executed the tool with PRIVATE-MARKER'};choice['finish_reason']='stop'
    if kind=='wrong_role':choice['message']['role']='user'
    if kind=='wrong_name':call['function']['name']='PRIVATE-MARKER'
    if kind=='extra_arguments':call['function']['arguments']=json.dumps({'text':probe.SAMPLE,'password':'PRIVATE-MARKER'})
    if kind=='wrong_argument_type':call['function']['arguments']='{"text":1}'
    if kind=='duplicate_argument':call['function']['arguments']='{"text":"PRIVATE-MARKER","text":"sierra-probe"}'
    if kind=='multiple_calls':choice['message']['tool_calls'].append(copy.deepcopy(call))
    if kind=='missing_id':call.pop('id')
    if kind=='length':choice['finish_reason']='length'
    if kind=='missing_usage':data.pop('usage')
    calls=transport(monkeypatch,data,raw=b'PRIVATE-MARKER'*12000 if kind=='large_response' else None)
    r=submit(client,p,body(context(client,p))).json();assert len(calls)==1 and not r['tool_execution']
    assert r['ok']==(kind=='missing_usage')
    if kind=='missing_usage':assert r['cost_basis']=='reserved_unknown_usage' and r['usage']=={}
    assert 'PRIVATE-MARKER' not in json.dumps(r) and 'PRIVATE-MARKER' not in str(main.store.list('provider_tool_probe'))

def test_timeout_is_unknown_and_duplicate_does_not_retry(client,monkeypatch):
    p=provider(client);calls=[]
    async def timeout(self,request):calls.append(1);raise httpx.ReadTimeout('PRIVATE-SECRET')
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',timeout)
    payload=body(context(client,p));r=submit(client,p,payload).json()
    assert r['state']=='unknown' and r['usage']=={} and r['cost_basis']=='reserved_unknown_usage' and r['estimated_cost_usd']==r['reserved_estimate_usd']
    assert 'PRIVATE-SECRET' not in str(r);assert submit(client,p,payload).json()['id']==r['id'] and calls==[1]

def test_http_failure_body_not_echoed_and_usage_preserved(client,monkeypatch):
    p=provider(client);data={'error':'Bearer PRIVATE-SECRET','usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3,'secret':'PRIVATE-SECRET'}};calls=transport(monkeypatch,data,status=401)
    r=submit(client,p,body(context(client,p))).json();assert len(calls)==1 and not r['ok'] and r['usage']['total_tokens']==3
    assert r['call_status']=='returned_error' and 'PRIVATE-SECRET' not in json.dumps(r)

def test_redirect_is_not_followed_or_verified_even_with_plausible_body(client,monkeypatch):
    p=provider(client);calls=[]
    async def redirect(self,request):
        calls.append(request);return httpx.Response(302,json=valid(),headers={'Location':'https://other.example/collect'},request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',redirect)
    r=submit(client,p,body(context(client,p))).json();assert not r['ok'] and r['call_status']=='returned_error' and len(calls)==1

def test_plain_http_error_does_not_misclassify_tool_capability(client,monkeypatch):
    p=provider(client);calls=transport(monkeypatch,status=401,raw=b'PRIVATE-SECRET text error')
    r=submit(client,p,body(context(client,p))).json();assert not r['ok'] and r['call_status']=='returned_error' and len(calls)==1
    assert main.store.get('provider',p['id'])['capabilities']['tools']=='untested' and 'PRIVATE-SECRET' not in str(r)

@pytest.mark.parametrize('preset_id',['deepseek-flash','openai-gpt-6.1-sol','openai-gpt-6-luna',next(m['id'] for v in VENDORS for m in v['models'] if m['request_profile']=='qwen')])
def test_protocol_profile_is_preserved_in_fixed_tool_probe(client,monkeypatch,preset_id):
    p=client.post('/api/providers',json={'preset_id':preset_id,'api_key':'not-a-real-key'}).json();calls=transport(monkeypatch)
    r=submit(client,p,body(context(client,p))).json();assert r['ok'] and len(calls)==1
    payload=json.loads(calls[0].content)
    if preset_id.startswith('openai-'):
        assert payload['max_completion_tokens']==256 and 'max_tokens' not in payload
        assert payload['reasoning_effort']==('none' if 'luna' in preset_id else 'low')
    elif preset_id=='deepseek-flash':assert payload['thinking']=={'type':'disabled'}
    else:assert payload['enable_thinking'] is False

def test_edit_during_request_does_not_apply_to_new_configuration(client,monkeypatch):
    p=provider(client);plan=context(client,p)
    async def edit(self,request):
        current=main.store.get('provider',p['id']);main.save_provider({'model':'changed-in-flight'},current)
        return httpx.Response(200,json=valid(),request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',edit)
    r=submit(client,p,body(plan)).json();assert r['state']=='stale' and not r['current_source'] and r['usage']['total_tokens']==42
    current=main.store.get('provider',p['id']);assert current['model']=='changed-in-flight' and current['capabilities']['tools']!='verified'

def test_config_change_makes_past_verified_result_historical(client,monkeypatch):
    p=provider(client);calls=transport(monkeypatch);payload=body(context(client,p));assert submit(client,p,payload).json()['ok']
    client.patch(f"/api/providers/{p['id']}",json={'name':'Renamed'})
    current=next(v for v in client.get('/api/providers').json() if v['id']==p['id']);assert current['capabilities']['tools']=='untested'
    assert not submit(client,p,payload).json()['current_source'] and len(calls)==1

def test_concurrent_and_duplicate_inflight_requests_use_one_dispatch(client,monkeypatch):
    p=provider(client);plan=context(client,p);one=probe.ProbeRequest(**body(plan));two=probe.ProbeRequest(**body(plan))
    async def check():
        entered=asyncio.Event();release=asyncio.Event();calls=[]
        async def wait(*a):calls.append(1);entered.set();await release.wait();return {'verified':True,'call_status':'returned','usage':{'prompt_tokens':1,'completion_tokens':1},'message':'SYNTHETIC ONLY'}
        monkeypatch.setattr(probe,'request_tool_probe',wait)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://isolated') as local:
            url=f"/api/providers/{p['id']}/tool-probe"
            task=asyncio.create_task(local.post(url,json=one.model_dump(mode='json')));await entered.wait()
            same=await local.post(url,json=one.model_dump(mode='json'));assert same.json()['state']=='running'
            other=await local.post(url,json=two.model_dump(mode='json'))
            assert other.status_code==409 and calls==[1];release.set();assert (await task).json()['ok']
    asyncio.run(check())

def test_restart_projection_never_replays_or_claims_success(client,monkeypatch):
    p=provider(client);plan=context(client,p);payload=body(plan);record={'id':payload['request_id'],'provider_id':p['id'],'source_token':plan['source_token'],'owner_instance':'old-process','state':'running','ok':False,'created_at':main.now(),'message':'old','usage':{},'reserved_estimate_usd':'0.1'}
    main.store.put('provider_tool_probe',record['id'],record);before=copy.deepcopy(record);calls=transport(monkeypatch)
    r=submit(client,p,payload).json();assert r['state']=='unknown' and not calls and main.store.get('provider_tool_probe',record['id'])==before

def test_ordinary_text_path_never_sends_tools(client,monkeypatch):
    p=provider(client);calls=transport(monkeypatch,{'choices':[{'finish_reason':'stop','message':{'content':'plain'}}],'usage':{}})
    text,_=asyncio.run(call_model(main.store.get('provider',p['id']),'not-a-real-key',[{'role':'user','content':'plain'}]))
    assert text=='plain' and len(calls)==1 and 'tools' not in json.loads(calls[0].content)

@pytest.mark.parametrize('field,value',[('acknowledge_cost','true'),('request_id','not-uuid'),('source_token','PRIVATE-MARKER')])
def test_invalid_input_not_echoed_or_dispatched(client,monkeypatch,field,value):
    p=provider(client);calls=transport(monkeypatch);response=submit(client,p,body(context(client,p))|{field:value})
    assert response.status_code==422 and 'PRIVATE-MARKER' not in response.text and not calls
