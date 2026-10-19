import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx,pytest
from app import providers
from app.providers import call_model,ProviderError


class Bytes(httpx.AsyncByteStream):
    def __init__(self,chunks):self.chunks=chunks
    async def __aiter__(self):
        for chunk in self.chunks:yield chunk


def invoke(monkeypatch,body,protocol='openai-compatible',status=200,content_type='text/event-stream',**kwargs):
    original=httpx.AsyncClient;requests=[]
    def handler(request):
        requests.append(json.loads(request.content));return httpx.Response(status,headers={'content-type':content_type},stream=Bytes(body))
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    deltas=[]
    async def receive(text):deltas.append(text)
    def run():return asyncio.run(call_model({'base_url':'https://example.test/v1','model':'fixture','protocol':protocol},'test-key',[{'role':'user','content':'test'}],stream=True,on_delta=receive,**kwargs))
    return run,deltas,requests


def event(value,name=None):return ((('event: '+name+'\n') if name else '')+'data: '+json.dumps(value,ensure_ascii=False)+'\n\n').encode()
def chat(text,**patch):return {'choices':[{'index':0,'delta':{'content':text},'finish_reason':None}],**patch}


def test_openai_stream_chunk_boundaries_utf8_crlf_usage_final_and_one_request(monkeypatch):
    raw=b': ping\r\n\r\n'+event(chat('中文')).replace(b'\n',b'\r\n')+event(chat('结尾'))+event({'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':8,'secret':'private'}})+b'data: [DONE]\n\n'
    chunks=[raw[i:i+1] for i in range(len(raw))]
    run,deltas,requests=invoke(monkeypatch,chunks);text,usage=run()
    assert text=='中文结尾' and deltas==['中文','结尾'] and usage=={'prompt_tokens':100,'completion_tokens':8}
    assert len(requests)==1 and requests[0]['stream'] is True and requests[0]['stream_options']=={'include_usage':True}


def test_anthropic_cumulative_usage_not_added_repeatedly(monkeypatch):
    parts=[event({'type':'message_start','message':{'usage':{'input_tokens':25,'output_tokens':1,'cache_read_input_tokens':7}}},'message_start'),event({'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}},'content_block_start'),event({'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':'hello'}},'content_block_delta'),event({'type':'content_block_stop','index':0},'content_block_stop'),event({'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':10}},'message_delta'),event({'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':15}},'message_delta'),event({'type':'message_stop'},'message_stop')]
    run,deltas,requests=invoke(monkeypatch,parts,'anthropic');text,usage=run()
    assert text=='hello' and deltas==['hello'] and usage=={'input_tokens':25,'output_tokens':15,'cache_read_input_tokens':7}
    assert requests[0]['stream'] is True and 'stream_options' not in requests[0]


@pytest.mark.parametrize('bad',['missing_done','incomplete_event','bad_json','error','tool','multi_choice','bad_type','too_large_line','wrong_mime','http_error'])
def test_incomplete_or_invalid_stream_does_not_return_partial_business_text_or_retry(monkeypatch,bad):
    parts=[event(chat('partial'))];kw={}
    if bad=='missing_done':parts.append(event({'choices':[],'usage':{'prompt_tokens':11,'completion_tokens':3}}))
    elif bad=='incomplete_event':parts.append(b'data: {broken')
    elif bad=='bad_json':parts.append(b'data: bad-json\n\n')
    elif bad=='error':parts.append(event({'error':{'message':'test-key private'}}))
    elif bad=='tool':parts.append(event({'choices':[{'delta':{'tool_calls':[{'function':{'arguments':'private'}}]}}]}))
    elif bad=='multi_choice':parts.append(event({'choices':[{},{}]}))
    elif bad=='bad_type':parts.append(event(chat(12)))
    elif bad=='too_large_line':parts.append(b'data: '+b'x'*65537)
    elif bad=='wrong_mime':kw['content_type']='application/json'
    else:kw['status']=401
    run,deltas,requests=invoke(monkeypatch,parts,**kw)
    with pytest.raises(ProviderError) as exc:run()
    assert len(requests)==1 and 'test-key' not in str(exc.value) and 'private' not in str(exc.value)
    if bad=='missing_done':assert exc.value.usage=={} and exc.value.partial_usage=={'prompt_tokens':11,'completion_tokens':3}


def test_early_anthropic_stop_and_unknown_control_event(monkeypatch):
    run,_,_=invoke(monkeypatch,[event({'type':'message_stop'},'message_stop')],'anthropic')
    with pytest.raises(ProviderError):run()


def test_stream_requires_exact_flag_and_never_falls_back_from_non_sse(monkeypatch):
    async def receive(text):pass
    with pytest.raises(ProviderError):asyncio.run(call_model({},'key',[],stream='true',on_delta=receive))
    with pytest.raises(ProviderError):asyncio.run(call_model({},'key',[],on_delta=receive))
    with pytest.raises(ProviderError):asyncio.run(call_model({},'key',[],stream=True,allow_images=True))



def test_multiline_json_and_cr_only_frames(monkeypatch):
    raw=b'data: {"choices": [\rdata: {"delta": {"content": "ok"}, "index": 0}]}\r\rdata: [DONE]\r\r'
    run,deltas,_=invoke(monkeypatch,[raw]);assert run()==('ok',{}) and deltas==['ok']


def test_absolute_timeout_even_when_chunks_keep_arriving(monkeypatch):
    original=httpx.AsyncClient
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(.01);yield b': ping\n\n'
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Slow())),**kw))
    with pytest.raises(ProviderError,match='时间上限'):
        asyncio.run(call_model({'base_url':'https://example.test','model':'fixture'},'key',[{'role':'user','content':'x'}],stream=True,timeout=.03))
