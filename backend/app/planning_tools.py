"""At most two model requests and one actual curated rule lookup; no repairs."""
import asyncio,copy,hashlib,time
from decimal import Decimal
from fastapi import HTTPException
from .planning import PlanningStopped,reserve_cost,usage_cost
from .providers import ProviderError
from .provider_tool_probe import strict_json
from .planning_tool_protocol import NAME,SYSTEM_NOTE,arguments,encoded,pricing_messages,MAX_RESULT_BYTES
from .node_guidance import lookup,provenance


def execute_query(app_type,node_types):
    """The sole registered dispatch; policy hashes/default context are separate."""
    return lookup(app_type,node_types)


def interrupt_receipts(operation):
    for receipt in operation.get('tool_receipts',[]):
        if receipt.get('status')=='requested':receipt.update(status='interrupted_unknown',message='重启时只读查询回执未完成，未重查或继续回注。')


def candidate_value(text):
    stripped=text.strip()
    if stripped.startswith('```'):
        lines=stripped.splitlines();stripped='\n'.join(lines[1:-1])
    try:value=strict_json(stripped)
    except ValueError:
        a,b=stripped.find('{'),stripped.rfind('}')
        if a<0 or b<a:raise ValueError()
        value=strict_json(stripped[a:b+1])
    if not isinstance(value,dict):raise ValueError()
    return value


async def run(h,task,provider,key,messages,settings,operation,context,validate,checkpoint,guard,*,clock=time.monotonic):
    started=clock();spent=Decimal(0);limit=Decimal(str(settings['max_cost_usd']));rates=provider['pricing']
    source_messages=copy.deepcopy(messages)
    source_messages[0]['content']+='\n'+SYSTEM_NOTE
    operation['planning_tools']={**copy.deepcopy(context),'tool_name':NAME,'max_model_http_requests':2,'max_local_queries':1,'registered_dispatches_started':0,'verification':'bounded_curated_rules_not_approval','target_runtime_verified':False}
    operation['tool_receipts']=[]

    def capture():
        operation.update(estimated_cost_usd=float(spent),elapsed_seconds=round(clock()-started,3));checkpoint()

    def stop(reason,message):
        operation.update(status='paused',stop_reason=reason,message=message);capture();raise PlanningStopped(reason,message)

    def source_guard():
        guard()
        if clock()-started>=settings['max_minutes']*60:raise PlanningStopped('time_limit','只读工具规划已达同一轮总时间上限，未继续。')
        current=h.get_task(task['id'])
        try:fresh=h.planning_tool_policy.context(current,h.main_provider(current))
        except HTTPException:raise PlanningStopped('tool_source_changed','工具范围/主模型/规则库或版本来源已失效，未继续或应用。') from None
        if not fresh or fresh!=context:raise PlanningStopped('tool_source_changed','只读工具策略来源已变化，未继续。')
        if h.budgets.state(h.budgets.get(task['id']))['unknown_count']:raise PlanningStopped('usage_unknown','助手账本有未知模型调用，不借旧预留继续工具规划。')

    async def call(stage,history):
        nonlocal spent
        source_guard()
        if len(operation['attempts'])>=2:stop('tool_call_limit','本轮最多两次模型请求，不追加调用。')
        try:reserve=reserve_cost(pricing_messages(history,stage),rates)
        except ProviderError:stop('invalid_tool_context','规则工具上下文/消息配对或2MB范围无法核对，未派发，不截断原上下文。')
        if spent+reserve>limit:stop('cost_limit','本轮已有费用加下一工具阶段完整预留超过上限，未派发。')
        attempt={'number':len(operation['attempts'])+1,'status':'pending','reserved_cost_usd':float(reserve),'usage':None,'tool_stage':stage,'provider_id':provider['id'],'model':provider['model']}
        operation['attempts'].append(attempt);capture()
        remaining=settings['max_minutes']*60-(clock()-started)
        if remaining<=0:
            attempt.update(status='not_dispatched',estimated_cost_usd=0,cost_basis='not_dispatched');stop('time_limit','准备期间达到总时间上限，未派发。')
        try:
            packet,usage=await asyncio.wait_for(h.budgets.call(task['id'],task['revision'],'plan',provider,key,history,operation_id=operation['id'],planning_tool_stage=stage,max_tokens=6000,timeout=min(remaining,120),json_mode=stage=='answer'),timeout=remaining)
        except PlanningStopped as exc:
            attempt.update(status='not_dispatched',estimated_cost_usd=0,cost_basis='not_dispatched');stop(exc.reason,str(exc))
        except (ProviderError,asyncio.TimeoutError) as exc:
            usage=exc.usage if isinstance(exc,ProviderError) else None;cost=usage_cost(usage,rates);spent+=cost if cost is not None else reserve
            attempt.update(status='provider_failed' if cost is not None else 'unknown_usage',usage=usage,estimated_cost_usd=float(cost if cost is not None else reserve),cost_basis='reported_usage' if cost is not None else 'reserved_unknown_usage')
            stop('provider_error' if isinstance(exc,ProviderError) else 'time_limit',str(exc) if isinstance(exc,ProviderError) else '规则工具模型等待超时，原用量可能未知，不重发。')
        cost=usage_cost(usage,rates);spent+=cost if cost is not None else reserve
        attempt.update(status='returned',usage=usage,estimated_cost_usd=float(cost if cost is not None else reserve),cost_basis='reported_usage' if cost is not None else 'reserved_unknown_usage')
        operation['response_kind']=packet['kind'];preview=packet['text'] if packet['kind']=='text' else encoded(packet['call']).decode('utf-8')
        operation.update(last_response_excerpt=preview[:16000],response_truncated=len(preview)>16000);capture();source_guard()
        if spent>limit:stop('cost_limit','返回用量估算已超过本轮上限，未应用；估算不是账单硬限。')
        return packet,attempt

    try:
        packet,attempt=await call('select',source_messages)
        if packet['kind']=='tool_request':
            parsed=arguments(packet['call']['function']['arguments'])
            attempt['status']='tool_requested'
            receipt={'name':NAME,'node_types':parsed['node_types'],'status':'requested','read_only':True,'network_requested':False,'resource_permission_granted':False,'followup_prepared':False,'final_text_received':False}
            operation['tool_receipts'].append(receipt);capture();source_guard()
            try:
                operation['planning_tools']['registered_dispatches_started']=1
                value=execute_query(task['app_type'],parsed['node_types'])
                body=encoded({'tool':NAME,'read_only':True,'network_requested':False,'resource_permission_granted':False,'data':value}).decode('utf-8')
                if len(body.encode('utf-8'))>MAX_RESULT_BYTES:raise ValueError()
            except Exception:
                receipt.update(status='failed',message='只读规则结果无法完整核对或超出32KB，未截断/回注/重试。');stop('tool_lookup_failed',receipt['message'])
            receipt.update(status='completed',result_sha256=hashlib.sha256(body.encode('utf-8')).hexdigest(),result_bytes=len(body.encode('utf-8')),provenance=provenance(value));capture();source_guard()
            followup=source_messages+[{'role':'assistant','content':packet['content'],'tool_calls':[packet['call']]},{'role':'tool','tool_call_id':packet['call']['id'],'content':body}]
            receipt['followup_prepared']=True;capture()
            packet,attempt=await call('answer',followup);receipt['final_text_received']=packet['kind']=='text';capture()
        if packet['kind']!='text':stop('invalid_tool_reply','未取得可核对终稿，不继续工具循环。')
        try:candidate=candidate_value(packet['text'])
        except (ValueError,TypeError,RecursionError):stop('invalid_plan_format','本次规则工具规划未返回无重复键/非有限数的JSON计划，原文保留，不追加修复。')
        if 'error' in candidate:
            from .planning_decisions import summarize
            operation['decision_report']=summarize(candidate);attempt['status']='needs_decision';stop('needs_decision','模型说明仍需业务/资源决定，工具资料不是批准，未自动改方案。')
        operation['last_candidate']=copy.deepcopy(candidate);capture();source_guard()
        try:result=await asyncio.wait_for(asyncio.to_thread(validate,candidate),timeout=max(.001,settings['max_minutes']*60-(clock()-started)))
        except asyncio.TimeoutError:stop('time_limit','静态核对达到本轮时间上限，未应用候选。')
        except (ValueError,TypeError,KeyError):stop('validation_error','候选超出校验范围，原候选保留，不追加修复。')
        source_guard()
        if not result['valid']:
            attempt.update(status='invalid',diagnostics=result['errors']);operation['diagnostics']=result['errors'];stop('needs_decision','规则工具规划候选未通过静态校验，保留完整候选，不删功能或追加调用。')
        attempt['status']='valid';operation.update(status='ready_to_confirm',diagnostics=[]);capture();return candidate
    except PlanningStopped as exc:
        operation.update(status='paused',stop_reason=exc.reason,message=str(exc));capture();raise
    except BaseException:
        for attempt in operation['attempts']:
            if attempt['status']=='pending':attempt.update(status='unknown_usage',estimated_cost_usd=attempt.get('reserved_cost_usd',0),cost_basis='reserved_unknown_usage')
        operation.update(status='interrupted',stop_reason='operation_error',message='规则工具规划中断；原回执/用量可能未知，不自动续派。');capture();raise
