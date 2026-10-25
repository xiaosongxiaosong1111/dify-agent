"""Single fixed tool-request observation; never execute or answer a tool call."""
import asyncio,copy,hashlib,json,time,uuid
import httpx
from fastapi import APIRouter,HTTPException
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel,ConfigDict,StrictBool,StrictStr,Field,UUID4
from .run_input_transport import validate,AmbiguousInput
from .providers import checked_url,usage_summary,ProviderError
from .provider_presets import runtime_profile
from .planning import reserve_cost,usage_cost

OUTPUT_LIMIT=256
TIMEOUT=30
TOOL_NAME='sierra_probe_echo'
SAMPLE='sierra-probe'
MESSAGES=[{'role':'user','content':'请只请求调用 sierra_probe_echo，参数 text 必须为 sierra-probe。这里只检查工具请求，不执行工具。'}]
TOOL={'type':'function','function':{'name':TOOL_NAME,'description':'固定的无执行能力探测，只检查请求形状。','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}}}

def identity(provider):
    return hashlib.sha256(json.dumps({k:provider.get(k) for k in ('id','base_url','model','protocol','preset_id','request_profile','pricing','configuration_revision')},ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def specification(provider):
    if provider.get('protocol','openai-compatible')!='openai-compatible':raise ValueError('首批仅适配OpenAI兼容协议的工具请求测试；其他协议仍未验证。')
    endpoint=checked_url(provider['base_url'])+'/chat/completions'
    profile=runtime_profile(provider)
    payload={'model':provider['model'],'messages':copy.deepcopy(MESSAGES),'max_tokens':OUTPUT_LIMIT,'stream':False,'tools':[copy.deepcopy(TOOL)],'tool_choice':'required','parallel_tool_calls':False}
    if profile in {'openai-reasoning','openai-luna'}:
        payload['max_completion_tokens']=payload.pop('max_tokens');payload['reasoning_effort']='none' if profile=='openai-luna' else 'low'
    elif profile=='deepseek':payload['thinking']={'type':'disabled'}
    elif profile=='qwen':payload['enable_thinking']=False
    return endpoint,payload

def quote(provider):
    _,payload=specification(provider)
    if not provider.get('pricing'):raise ValueError('请先填写该模型的估算单价，再准备工具请求测试。')
    # Include tool/schema and request overhead in the conservative input estimate.
    return str(reserve_cost([{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],provider['pricing'],OUTPUT_LIMIT))

def unique(pairs):
    value={}
    for k,v in pairs:
        if k in value:raise ValueError('duplicate JSON key')
        value[k]=v
    return value

def strict_json(raw):
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))

def http_failure(status,usage):
    return {'verified':False,'call_status':'returned_error','usage':usage,'message':f'工具请求测试收到HTTP {status}；不能据此确认工具能力，未自动重试。'}

async def request_tool_probe(provider,key):
    endpoint,payload=specification(provider);usage={}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT,follow_redirects=False) as client:
            async with client.stream('POST',endpoint,headers={'Authorization':'Bearer '+key},json=payload) as response:
                raw=bytearray()
                async for block in response.aiter_bytes():
                    raw.extend(block)
                    if len(raw)>131072:
                        if not response.is_success:return http_failure(response.status_code,{})
                        raise ValueError('response too large')
                if not response.is_success:
                    try:
                        failure=strict_json(raw);usage=usage_summary(failure.get('usage')) if isinstance(failure,dict) else {}
                    except (ValueError,TypeError,RecursionError):pass
                    return http_failure(response.status_code,usage)
                data=strict_json(raw)
                usage=usage_summary(data.get('usage')) if isinstance(data,dict) else {}
        choices=data.get('choices') if isinstance(data,dict) else None
        if not isinstance(choices,list) or len(choices)!=1:raise ValueError('choices')
        choice=choices[0];message=choice.get('message');calls=message.get('tool_calls') if isinstance(message,dict) else None
        if choice.get('finish_reason')!='tool_calls' or not isinstance(message,dict) or message.get('role')!='assistant' or not isinstance(calls,list) or len(calls)!=1:raise ValueError('tool request not observed')
        call=calls[0];function=call.get('function') if isinstance(call,dict) else None
        if call.get('type')!='function' or not isinstance(call.get('id'),str) or not call['id'] or len(call['id'])>200 or not isinstance(function,dict) or function.get('name')!=TOOL_NAME:raise ValueError('tool identity')
        arguments=function.get('arguments')
        if not isinstance(arguments,str) or len(arguments)>4096 or strict_json(arguments)!={'text':SAMPLE}:raise ValueError('tool arguments')
        return {'verified':True,'call_status':'returned','usage':usage,'message':'本次返回了名称和参数均符合约定的工具请求；未执行工具、未回注结果，不证明完整Agent能力或工具执行成功。'}
    except (httpx.RequestError,asyncio.TimeoutError):
        return {'verified':False,'call_status':'unknown','usage':usage,'message':'工具请求测试连接失败或超时，派发/计费用量可能未知；保留本机回执，不自动重试。'}
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,RecursionError):
        return {'verified':False,'call_status':'returned_unverified','usage':usage,'message':'未取得完整且符合固定名称/参数的工具请求；可能是格式、截断或协议差异，不能据此宣布工具可用。未执行工具或重试。'}

class ProbeRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:
                raw=await request.body()
                if len(raw)>4096:raise AmbiguousInput()
                if request.method in {'GET','HEAD'}:
                    if raw:raise AmbiguousInput()
                else:validate(raw)
                response=await original(request)
            except (AmbiguousInput,RequestValidationError):
                response=JSONResponse(status_code=422,content={'detail':'工具测试请求须为明确的有限JSON对象及合法请求/来源标记；未处理，不回显输入。'})
            response.headers['Cache-Control']='no-store'
            return response
        return guarded

class ProbeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID4
    source_token:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledge_cost:StrictBool

class ToolProbeManager:
    def __init__(self,host):self.h=host;self.instance=str(uuid.uuid4());self.active=set()

    def public(self,record):
        value={k:copy.deepcopy(v) for k,v in record.items() if k!='owner_instance'}
        if value['state']=='running' and record.get('owner_instance')!=self.instance:
            value.update(state='unknown',message='后台已重启，旧测试终态未知；旧回执保留，不会重新发送。')
        provider=self.h.store.get('provider',record['provider_id'])
        value['current_source']=bool(provider and identity(provider)==record['source_token'])
        return value

    def plan(self,provider):
        try:
            estimate=quote(provider);reason='';ready=self.h.store.has_secret(provider['id'],'api_key')
            if not ready:reason='该模型尚未保存API Key。'
        except (ValueError,ProviderError):
            estimate=None;ready=False;reason='首批需OpenAI兼容协议、有效模型配置及估算单价；未适配或缺条件时不发送测试。'
        history=[r for r in self.h.store.list('provider_tool_probe') if r.get('provider_id')==provider['id']]
        latest=max(history,key=lambda r:r['created_at']) if history else None
        return {'provider_id':provider['id'],'source_token':identity(provider),'configuration_revision':provider.get('configuration_revision',0),'ready':ready,'reason':reason,'estimated_reservation_usd':estimate,'max_output_tokens':OUTPUT_LIMIT,'timeout_seconds':TIMEOUT,'max_http_requests':1,'tool_execution':False,'latest_receipt':self.public(latest) if latest else None,'note':'单次实际模型请求可能计费，未计入任务规划预算；估算不是账单硬限。只发送固定公开样例，不发送任务内容，不执行工具，不自动重试。'}

    def register(self):
        h=self.h;router=APIRouter(route_class=ProbeRoute)
        @router.get('/api/providers/{provider_id}/tool-probe-plan')
        def prepare(provider_id:str):
            with h.store.lock:
                provider=h.store.get('provider',provider_id)
                if not provider:raise HTTPException(404,'模型配置不存在。')
                return self.plan(provider)

        @router.get('/api/providers/{provider_id}/tool-probes/{request_id}')
        def receipt(provider_id:str,request_id:str):
            with h.store.lock:
                record=h.store.get('provider_tool_probe',request_id)
                if not record or record['provider_id']!=provider_id:raise HTTPException(404,'没有该模型的测试回执。')
                return self.public(record)

        @router.post('/api/providers/{provider_id}/tool-probe')
        async def probe(provider_id:str,payload:ProbeRequest):
            request_id=str(payload.request_id)
            with h.store.lock:
                prior=h.store.get('provider_tool_probe',request_id)
                if prior:
                    if prior['provider_id']!=provider_id or prior['source_token']!=payload.source_token:raise HTTPException(409,'该请求标识已属于其他模型或配置，未发送。')
                    return self.public(prior)
                provider=h.store.get('provider',provider_id)
                if not provider:raise HTTPException(404,'模型配置不存在。')
                if not payload.acknowledge_cost:raise HTTPException(422,'请明确同意本次一次可能付费的工具请求测试。')
                if identity(provider)!=payload.source_token:raise HTTPException(409,'模型配置或单价已变化，请重新准备并确认，未发送。')
                context=self.plan(provider)
                if not context['ready']:raise HTTPException(422,context['reason'])
                if provider_id in self.active:raise HTTPException(409,'该模型已有测试正在执行，请读取本机回执，不重复派发。')
                record={'id':request_id,'provider_id':provider_id,'source_token':payload.source_token,'configuration_revision':provider.get('configuration_revision',0),'owner_instance':self.instance,'state':'running','ok':False,'created_at':h.now(),'reserved_estimate_usd':context['estimated_reservation_usd'],'usage':{},'call_status':'pending','tool_execution':False,'max_http_requests':1,'message':'本次工具请求测试进行中；不会执行工具或自动重试。'}
                h.store.put('provider_tool_probe',request_id,record)
                self.active.add(provider_id)
            start=time.monotonic();cancelled=False;dispatched=False
            try:
                key=h.store.secret(provider_id,'api_key')
                if not key:raise ValueError('missing credential')
                dispatched=True;outcome=await request_tool_probe(provider,key)
            except asyncio.CancelledError:
                cancelled=True;outcome={'verified':False,'call_status':'unknown' if dispatched else 'not_dispatched','usage':{},'message':'本机等待已中断；上游可能仍执行，保留回执及未知用量，不自动重发。'}
            except Exception:
                outcome={'verified':False,'call_status':'unknown' if dispatched else 'not_dispatched','usage':{},'message':'工具测试未取得可靠结果；已保留回执，不回显服务正文或凭据，不自动重试。'}
            finally:
                with h.store.lock:self.active.discard(provider_id)
            with h.store.lock:
                usage=usage_summary(outcome['usage']);cost=usage_cost(usage,provider['pricing'])
                unknown=cost is None and outcome['call_status']!='not_dispatched'
                record.update(state='succeeded' if outcome['verified'] else 'unknown' if outcome['call_status']=='unknown' else 'failed',ok=outcome['verified'],call_status=outcome['call_status'],message=outcome['message'],usage=usage,completed_at=h.now(),latency_ms=int((time.monotonic()-start)*1000),estimated_cost_usd=str(cost) if cost is not None else '0' if not unknown else record['reserved_estimate_usd'],cost_basis='reported_usage_estimate' if cost is not None else 'reserved_unknown_usage' if unknown else 'not_dispatched')
                current=h.store.get('provider',provider_id)
                records=[]
                if not current or identity(current)!=payload.source_token:
                    record.update(state='stale',message='测试期间模型配置已变化；旧结果已记录，不更新当前模型能力。')
                elif not cancelled:
                    current.setdefault('capabilities',{})['tools']='verified' if outcome['verified'] else 'failed' if outcome['call_status']=='returned_unverified' else 'untested'
                    current.setdefault('checks',{})['tools']={'probe_id':request_id,'created_at':h.now(),'source_token':payload.source_token,'scope':'single_function_request_only','tool_execution':False,'usage':usage,'state':record['state']}
                    records.append(('provider',provider_id,current))
                records.append(('provider_tool_probe',request_id,record))
                h.store.put_many(records)
                result=self.public(record)
            if cancelled:raise asyncio.CancelledError()
            return result
        h.app.include_router(router)

def register(host):
    host.provider_tool_probes=ToolProbeManager(host);host.provider_tool_probes.register()
