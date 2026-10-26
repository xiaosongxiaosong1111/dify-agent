"""Opt-in two-call cases route: only a known-usage JSON parse failure escalates."""
import asyncio,copy,time
from decimal import Decimal
from fastapi import HTTPException
from .assistant_routing import stamp
from .planning import draft_plan,PlanningStopped,reserve_cost

PARSE_ERROR='返回内容不是可解析的 JSON 计划'


def interrupt_phases(operation):
    """Startup only: describe unfinished phases, never resume or reconcile usage."""
    for phase in operation.get('phases',[]):
        if phase.get('status') in {'running','ready_to_confirm'}:
            phase.update(status='interrupted',stop_reason='server_restart',message='本阶段因服务重启中断，未自动重发或升级；以累计账本核对已知/未知用量。')
            for attempt in phase.get('attempts',[]):
                if attempt.get('status')=='pending':attempt.update(status='unknown_usage',estimated_cost_usd=attempt.get('reserved_cost_usd',0),cost_basis='reserved_unknown_usage')


async def run(h,task,provider,key,messages,settings,operation,context,validate,checkpoint,guard,*,clock=time.monotonic):
    started=clock();phases=[];round_limit=Decimal(str(settings['max_cost_usd']))
    if settings['max_retries']<1:raise PlanningStopped('retry_limit','全局自动修复上限为0，未派发两阶段建议。')

    def source_guard():
        guard()
        if clock()-started>=settings['max_minutes']*60:raise PlanningStopped('time_limit','两阶段已达到同一轮总时间上限，未继续或应用候选。')
        with h.store.lock:
            current=h.get_task(task['id']);policy=h.routing.get(task['id'])
            if policy['policy_revision']!=context['policy_revision']:raise PlanningStopped('routing_changed','建议路由已变化，未继续升级或应用候选。')
            try:fresh=h.routing.upgrade_context(current,'cases')
            except HTTPException:raise PlanningStopped('routing_changed','两阶段模型/路由来源已变化，未继续或应用候选。') from None
            if not fresh or fresh['light_token']!=context['light_token'] or fresh['main_provider_token']!=context['main_provider_token']:raise PlanningStopped('routing_changed','已固定模型来源已变化，未继续升级。')

    def known_spend():
        ledger=h.budgets.get(task['id']);entries=[entry for entry in ledger['entries'] if entry.get('operation_id')==operation['id']]
        if any(entry['status']!='settled' or entry.get('charged_usd') is None for entry in entries):raise PlanningStopped('usage_unknown','本次已有未知或未结算用量，不追加升级调用。')
        if any(entry['status']=='unknown' for entry in ledger['entries']):raise PlanningStopped('usage_unknown','任务保留未知调用，不借用旧预留追加升级。')
        return sum((Decimal(entry['charged_usd']) for entry in entries),Decimal(0)),entries

    def capture(phase):
        if not phases or phases[-1] is not phase:phases.append(phase)
        attempts=[]
        for row in phases:
            for attempt in row['attempts']:
                attempts.append({**copy.deepcopy(attempt),'number':len(attempts)+1,'phase':row['phase'],'provider_id':row['provider_id'],'model':row['model']})
        operation['attempts']=attempts;operation['phases']=copy.deepcopy(phases)
        operation['estimated_cost_usd']=float(sum((Decimal(str(a.get('estimated_cost_usd',0))) for a in attempts),Decimal(0)))
        operation['elapsed_seconds']=round(clock()-started,3)
        for name in ('status','diagnostics','last_response_excerpt','response_truncated','last_candidate','decision_report','scope_change_summary','message','stop_reason'):
            if name in phase:operation[name]=copy.deepcopy(phase[name])
            else:operation.pop(name,None)
        checkpoint()

    async def phase(name,model,secret,limits):
        row={'id':operation['id'],'phase':name,'provider_id':model['id'],'model':model['model'],'source_token':stamp(h,model),'status':'running','attempts':[],'settings':copy.deepcopy(limits)}
        operation.update(provider_id=model['id'],model=model['model'],pricing=copy.deepcopy(model.get('pricing')))
        capture(row)
        async def invoke(msgs,timeout):
            source_guard()
            remaining=settings['max_minutes']*60-(clock()-started)
            return await asyncio.wait_for(h.budgets.call(task['id'],task['revision'],'cases',model,secret,msgs,operation_id=operation['id'],max_tokens=6000,timeout=min(timeout,remaining),json_mode=model.get('protocol')!='anthropic'),timeout=remaining)
        try:return await draft_plan(task,model,copy.deepcopy(messages),limits,row,invoke,validate,lambda:capture(row),source_guard,clock=clock)
        except BaseException:
            if row.get('status')=='running':row.update(status='interrupted',message='本阶段中断，原用量与未知预留保持，不自动重发。')
            for attempt in row['attempts']:
                if attempt['status']=='pending':attempt.update(status='unknown_usage',estimated_cost_usd=attempt.get('reserved_cost_usd',0),cost_basis='reserved_unknown_usage')
            capture(row);raise

    source_guard();known_spend()
    operation['routing']['final_role']='light'
    operation['routing']['upgrade']={'policy':'json_parse_once_known_usage','initial_provider_id':provider['id'],'main_provider_id':context['provider']['id'],'max_model_http_requests':2,'triggered':False}
    light_limits={**settings,'max_retries':0}
    try:return await phase('light',provider,key,light_limits)
    except PlanningStopped as exc:
        first=phases[-1] if phases else None
        if not first or exc.reason!='retry_limit' or first.get('diagnostics')!=[PARSE_ERROR] or len(first['attempts'])!=1 or first['attempts'][0].get('status')!='invalid' or first['attempts'][0].get('cost_basis')!='reported_usage':raise
    source_guard();spent,entries=known_spend()
    if len(entries)!=1:raise PlanningStopped('call_limit','首阶段调用记录不满足一次上界，未追加升级。')
    remaining=settings['max_minutes']*60-(clock()-started)
    if remaining<=0:raise PlanningStopped('time_limit','首阶段后已达本轮时间上限，未派发升级。')
    main_model=context['provider'];reservation=reserve_cost(messages,main_model['pricing'])
    if spent+reservation>round_limit:raise PlanningStopped('cost_limit','首阶段已知费用加主模型预留超出本轮估算上限，未派发升级。')
    with h.store.lock:
        source_guard();secret=h.store.secret(main_model['id'],'api_key')
    operation['routing']['final_role']='main_upgrade'
    operation['routing']['upgrade'].update(triggered=True,reason='known_usage_unparseable_json',first_phase_cost_usd=str(spent))
    main_limits={**settings,'max_retries':0,'max_cost_usd':str(round_limit-spent),'max_minutes':remaining/60}
    return await phase('main_upgrade',main_model,secret,main_limits)
