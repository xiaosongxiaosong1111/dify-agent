"""Persisted, bounded semantic proposals; the caller owns applying the candidate."""
import copy,uuid
from fastapi import HTTPException
from .planning import draft_plan,PlanningStopped


async def suggest(h,item_id,revision,kind,build_messages,validate,apply,*,settings_override=None):
    with h.store.lock:
        task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,revision)
        provider=h.routing.provider(task,kind);key=h.store.secret(provider['id'],'api_key')
        upgrade=h.routing.upgrade_context(task,kind)
        messages=build_messages(task)
        settings=copy.deepcopy(h.get_settings())
        if settings_override is not None:settings=copy.deepcopy(settings_override)
        op={'id':str(uuid.uuid4()),'kind':kind,'revision':revision,'provider_id':provider['id'],'model':provider['model'],'status':'running','previous_status':task['status'],'attempts':[],'created_at':h.now(),'settings':settings,'pricing':copy.deepcopy(provider.get('pricing')),'estimated_cost_usd':0,'cost_is_estimate':True,'routing':{'operation':kind,'selected_role':'light' if kind=='cases' and h.routing.get(item_id)['enabled'] else 'main','policy_revision':h.routing.get(item_id)['policy_revision']}}
        task['planning_runs'].append(op);task['status']='planning';h.save_task(task)

    def checkpoint():
        with h.store.lock:
            current=h.get_task(item_id);current['planning_runs']=[copy.deepcopy(op) if r['id']==op['id'] else r for r in current['planning_runs']];h.save_task(current)

    def guard():
        current=h.get_task(item_id)
        if current['revision']!=revision:raise PlanningStopped('revision_changed','需求修订已变化，候选未应用。')
        if current['status']=='paused':raise PlanningStopped('user_pause','已暂停建议生成，候选和用量已保留。')
        h.budgets.ready(item_id)
        if upgrade:
            try:fresh=h.routing.upgrade_context(current,kind)
            except HTTPException:raise PlanningStopped('routing_changed','两阶段模型/路由来源已变化，候选未应用。') from None
            if not fresh or any(fresh.get(key)!=upgrade.get(key) for key in ('policy_revision','light_token','main_provider_id','main_provider_token')):raise PlanningStopped('routing_changed','升级策略来源已变化，候选未应用。')

    async def invoke(msgs,timeout):
        return await h.budgets.call(item_id,revision,kind,provider,key,msgs,operation_id=op['id'],max_tokens=6000,timeout=timeout,json_mode=provider.get('protocol')!='anthropic')

    try:
        if upgrade:
            from .lightweight_upgrade import run
            candidate=await run(h,task,provider,key,messages,settings,op,upgrade,lambda p:validate(task,p),checkpoint,guard)
        else:
            candidate=await draft_plan(task,provider,messages,settings,op,invoke,lambda p:validate(task,p),checkpoint,guard)
        with h.store.lock:
            guard();current=h.get_task(item_id)
            if current['status']!='planning':raise PlanningStopped('state_changed','执行状态变化，候选未应用。')
            current['status']=op['previous_status'];saved=apply(current,candidate)
            op.update(status='succeeded',result_revision=saved['revision'],completed_at=h.now())
            saved['planning_runs']=[copy.deepcopy(op) if r['id']==op['id'] else r for r in saved['planning_runs']]
            return h.save_task(saved)
    except BaseException as exc:
        op.update(status='paused' if isinstance(exc,PlanningStopped) else 'interrupted',stop_reason=exc.reason if isinstance(exc,PlanningStopped) else 'operation_error',message=str(exc) if isinstance(exc,PlanningStopped) else '建议生成中断，候选保留，用量可能未知；请核对后继续。',completed_at=h.now())
        for attempt in op['attempts']:
            if attempt['status']=='pending':attempt.update(status='unknown_usage',estimated_cost_usd=attempt.get('reserved_cost_usd',0),cost_basis='reserved_unknown_usage')
        op['estimated_cost_usd']=sum(a.get('estimated_cost_usd',0) for a in op['attempts'])
        with h.store.lock:
            current=h.get_task(item_id)
            if current['revision']==revision:current['status']='paused'
            current['planning_runs']=[copy.deepcopy(op) if r['id']==op['id'] else r for r in current['planning_runs']];h.save_task(current)
        if isinstance(exc,PlanningStopped):raise HTTPException(422,str(exc)) from exc
        raise
