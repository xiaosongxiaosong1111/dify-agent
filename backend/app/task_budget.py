"""Persistent cumulative assistant-model accounting; independent of task revisions."""
from __future__ import annotations
import copy,time,uuid
from decimal import Decimal,InvalidOperation
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictBool
from .planning import PlanningStopped,reserve_cost,usage_cost,validate_pricing
from .providers import ProviderError,usage_summary


def money(value,*,nullable=False):
    if value is None and nullable:return None
    if not isinstance(value,str) or len(value)>40:raise ValueError('金额须为最多 40 字符的 USD 十进制文本。')
    try:amount=Decimal(value)
    except InvalidOperation:raise ValueError('金额不是有效十进制数。') from None
    if not amount.is_finite() or not 0<=amount<=Decimal('1000000') or amount.as_tuple().exponent < -12:raise ValueError('金额须为 0—1000000 的有限非负数，最多 12 位小数。')
    return format(amount,'f')


class PolicyRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    policy_revision:StrictInt
    limit_usd:str|None
    acknowledge_change:StrictBool
    acknowledge_excluded_history:StrictBool=False
    note:str


class ReconcileRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    policy_revision:StrictInt
    actual_cost_usd:str
    acknowledge_actual_bill:StrictBool
    note:str


class TaskBudgetManager:
    def __init__(self,host):self.h=host

    def get(self,item_id,*,create=False):
        h=self.h
        with h.store.lock:
            value=h.store.get('task_budget',item_id)
            if value:return value
            task=h.get_task(item_id)
            records=sum(m.get('source')=='model' for m in task.get('messages',[]))+sum(sum(a.get('status') not in {'pending','not_dispatched','not_sent'} for a in op.get('attempts',[])) for op in task.get('planning_runs',[]))
            value={'id':item_id,'policy_revision':0,'limit_usd':None,'created_at':h.now() if create else None,'excluded_history_present':records>0,'scope':'since_ledger_start','entries':[],'policy_history':[]}
            if create:h.store.put('task_budget',item_id,value)
            return value

    def state(self,value):
        known=sum((Decimal(e['charged_usd']) for e in value['entries'] if e.get('charged_usd') is not None),Decimal(0))
        held=sum((Decimal(e['reserved_usd']) for e in value['entries'] if e['status'] in {'reserved','unknown'} and e.get('reserved_usd') is not None),Decimal(0))
        unknown=sum(e['status']=='unknown' for e in value['entries'])
        pending=sum(e['status']=='reserved' for e in value['entries'])
        limit=Decimal(value['limit_usd']) if value['limit_usd'] is not None else None
        reason=None
        if limit is not None and unknown:reason='有用量／费用不明的调用，请先核对账单并登记，不能按零费用继续。'
        elif limit is not None and known+held>limit:reason='任务累计费用及预留已经超过所设估算上限，请核对或明确修改上限。'
        return {'known_estimated_usd':str(known),'held_estimated_usd':str(held),'accounted_estimated_usd':str(known+held),'remaining_estimated_usd':str(max(Decimal(0),limit-known-held)) if limit is not None else None,'unknown_count':unknown,'pending_count':pending,'blocker':reason,'verification':'configured_price_estimate_and_user_declarations'}

    def ready(self,item_id):
        with self.h.store.lock:
            state=self.state(self.get(item_id))
            if state['blocker']:raise PlanningStopped('task_budget_review',state['blocker'])

    async def call(self,item_id,revision,kind,provider,key,messages,*,operation_id=None,image_reserve_usd=None,planning_tool_stage=None,**kwargs):
        h=self.h
        if not key:raise ProviderError('该模型尚未配置 API Key，请先填写。')
        rates=validate_pricing(provider.get('pricing'))
        counted_messages=messages
        if planning_tool_stage is not None:
            from .planning_tool_protocol import pricing_messages
            counted_messages=pricing_messages(messages,planning_tool_stage)
            if kind!='plan' or kwargs.get('stream') or kwargs.get('allow_images'):raise ProviderError('只读规则工具只服务普通规划，不用于流式、图像或其它任务。')
        multimodal=any(not isinstance(m.get('content'),str) for m in counted_messages)
        if multimodal:
            from .image_messages import prepare_messages
            from .providers import checked_url
            from .provider_presets import runtime_profile
            if kwargs.get('allow_images') is not True:raise ProviderError('图像须通过明确出站确认入口，未预留或派发。')
            try:
                prepare_messages(messages,provider.get('protocol','openai-compatible'),allow_images=True)
                if not any(isinstance(m.get('content'),list) and any(isinstance(p,dict) and p.get('type')=='image_url' for p in m['content']) for m in messages):raise ValueError('单独图像预留只用于真实图像段，不能把普通文字改成数组后绕过文字预算。')
                checked_url(provider['base_url']);runtime_profile(provider)
                reserved=Decimal(money(image_reserve_usd))
                if reserved<=0:raise ValueError('图像调用预留须明确为正USD估算，不能按零费用派发。')
            except (ValueError,KeyError) as exc:
                raise ProviderError(str(exc) if isinstance(exc,ValueError) else '图像服务配置不完整，未派发。') from exc
            if rates is None:raise ProviderError('图像调用须明确已核对的token计价规则；缺少单价时不能把返回用量按零费用结算。')
            text_only=[{'role':m['role'],'content':m['content'] if isinstance(m['content'],str) else '\n'.join(p['text'] for p in m['content'] if p.get('type')=='text')} for m in messages]
            minimum=reserve_cost(text_only,rates,kwargs.get('max_tokens',6000))
            if reserved<minimum:raise ProviderError('图像预留低于明确文字与最大输出的已知估算，未派发；请按真实图像计价重新核对，不会缩减输出限制。')
        else:
            if image_reserve_usd is not None:raise ProviderError('图像单次预留不能用于绕过普通文字费用预检。')
            reserved=reserve_cost(counted_messages,rates,kwargs.get('max_tokens',6000)) if rates is not None else None
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision)
            ledger=self.get(item_id,create=True);state=self.state(ledger)
            reason=state['blocker']
            if ledger['limit_usd'] is not None:
                if reserved is None:reason=reason or '缺少模型估算单价，无法纳入累计预算，未派发调用。'
                elif Decimal(state['accounted_estimated_usd'])+reserved>Decimal(ledger['limit_usd']):reason=reason or '下一次调用的预留会超过任务累计上限，未派发；更换修订或再次点击不会清空费用。'
            if reason:raise PlanningStopped('task_budget_limit',reason)
            entry={'id':str(uuid.uuid4()),'operation_id':operation_id,'revision':revision,'kind':kind,'provider_id':provider['id'],'model':provider['model'],'pricing':copy.deepcopy(rates),'reserved_usd':str(reserved) if reserved is not None else None,'charged_usd':None,'status':'reserved','cost_basis':('user_declared_image_reserve' if multimodal else 'reserved_estimate') if reserved is not None else 'price_unknown','modality':'image' if multimodal else 'text','image_reserve_is_estimate':multimodal,'usage':None,'started_at':h.now(),'policy_revision':ledger['policy_revision']}
            if planning_tool_stage is not None:entry['request_scope']='planning_node_rules_'+planning_tool_stage
            ledger['entries'].append(entry);h.store.put('task_budget',item_id,ledger)
        start=time.monotonic()
        def settle(usage,call_status,partial_usage=None):
            cleaned_usage=usage_summary(usage)
            charge=usage_cost(cleaned_usage,rates) if rates is not None else None
            with h.store.lock:
                current=self.get(item_id);target=next(e for e in current['entries'] if e['id']==entry['id'])
                target.update(status='settled' if charge is not None else 'unknown',call_status=call_status,charged_usd=str(charge) if charge is not None else None,usage=cleaned_usage,cost_basis='reported_usage' if charge is not None else 'reserved_unknown_usage' if reserved is not None else 'price_or_usage_unknown',finished_at=h.now(),elapsed_seconds=round(time.monotonic()-start,3))
                if partial_usage is not None:target['partial_reported_usage']=usage_summary(partial_usage);target['partial_usage_is_final']=False
                h.store.put('task_budget',item_id,current)
        try:
            if planning_tool_stage is not None:
                from .planning_tool_protocol import request
                text,usage=await request(provider,key,messages,stage=planning_tool_stage,**kwargs)
            else:text,usage=await h.call_model(provider,key,messages,**kwargs)
        except BaseException as exc:
            settle(exc.usage if isinstance(exc,ProviderError) else None,'failed_or_interrupted',exc.partial_usage if isinstance(exc,ProviderError) else None)
            raise
        settle(usage,'returned')
        return text,usage

    def recover(self):
        h=self.h
        with h.store.lock:
            for ledger in h.store.list('task_budget'):
                changed=False
                for entry in ledger['entries']:
                    if entry['status']=='reserved':
                        entry.update(status='unknown',call_status='interrupted_by_restart',cost_basis='reserved_unknown_usage' if entry.get('reserved_usd') is not None else 'price_or_usage_unknown',finished_at=h.now());changed=True
                if changed:h.store.put('task_budget',ledger['id'],ledger)
            for task in h.store.list('task'):
                if task.get('status')=='interviewing' or task.get('active_interview_id'):
                    task.pop('active_interview_id',None)
                    task['status']='paused';task['messages'].append({'role':'assistant','source':'system','content':'服务重启时访谈尚未确认结束，保留费用预留与当前需求；请核对账本后继续，不自动重发。','created_at':h.now()});h.save_task(task)

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/budget/usage-summary')
        def usage_summary(item_id:str,revision:int):
            from .assistant_usage_groups import summarize
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,revision);ledger=self.get(item_id)
                return {**summarize(ledger),'task_id':item_id,'task_revision':task['revision'],'policy_revision':ledger['policy_revision'],'ledger_created_at':ledger['created_at'],'excluded_history_present':ledger['excluded_history_present'],'captured_at':h.now()}

        @h.app.get('/api/tasks/{item_id}/budget')
        def get_budget(item_id:str):
            with h.store.lock:
                task=h.get_task(item_id);ledger=self.get(item_id)
                return {**ledger,**self.state(ledger),'task_revision':task['revision'],'excluded_dify_run_records':sum(r.get('kind')=='run' for r in task.get('runs',[])),'scope_note':'仅累计账本起始点后的 Sierra 访谈／规划／覆盖／冲突／配置／验收样例建议及经明确预览确认的图像模型调用。Dify 应用、建库、服务连接测试和起始点之前的记录未计入；不代表供应商总账单。'}

        @h.app.patch('/api/tasks/{item_id}/budget')
        def set_budget(item_id:str,payload:PolicyRequest):
            try:limit=money(payload.limit_usd,nullable=True)
            except ValueError as exc:raise HTTPException(422,str(exc)) from exc
            if not payload.acknowledge_change or not payload.note.strip() or len(payload.note)>2000:raise HTTPException(422,'请明确确认累计上限变更，并填写最多 2000 字的原因。')
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);ledger=self.get(item_id,create=True)
                if ledger['policy_revision']!=payload.policy_revision:raise HTTPException(409,'预算设置或核对记录已变化，请重新读取。')
                if self.state(ledger)['pending_count']:raise HTTPException(409,'还有调用未结算，不能在派发期间修改累计上限。')
                if ledger['excluded_history_present'] and not payload.acknowledge_excluded_history:raise HTTPException(422,'旧任务已有账本起始点前的模型记录，须明确接受历史费用未纳入。')
                ledger['policy_history'].append({'before':ledger['limit_usd'],'after':limit,'note':payload.note.strip(),'created_at':h.now()});ledger['limit_usd']=limit;ledger['policy_revision']+=1;h.store.put('task_budget',item_id,ledger)
                return {**ledger,**self.state(ledger),'task_revision':task['revision']}

        @h.app.post('/api/tasks/{item_id}/budget/entries/{entry_id}/reconcile')
        def reconcile(item_id:str,entry_id:str,payload:ReconcileRequest):
            try:actual=money(payload.actual_cost_usd)
            except ValueError as exc:raise HTTPException(422,str(exc)) from exc
            if not payload.acknowledge_actual_bill or not payload.note.strip() or len(payload.note)>2000:raise HTTPException(422,'请核对实际账单，明确确认人工登记金额及来源。')
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);ledger=self.get(item_id)
                if ledger['policy_revision']!=payload.policy_revision:raise HTTPException(409,'账本已变化，请重新读取。')
                entry=next((e for e in ledger['entries'] if e['id']==entry_id),None)
                if not entry or entry['status']!='unknown':raise HTTPException(422,'只能核对本任务的费用未知条目，不改写已结算／未返回的调用。')
                entry['reconciliation']={'previous_reserved_usd':entry['reserved_usd'],'actual_cost_usd':actual,'note':payload.note.strip(),'created_at':h.now(),'source':'user_declared_bill'};entry.update(status='reconciled',charged_usd=actual,cost_basis='user_declared_bill');ledger['policy_revision']+=1;h.store.put('task_budget',item_id,ledger)
                return {**ledger,**self.state(ledger),'task_revision':task['revision']}
