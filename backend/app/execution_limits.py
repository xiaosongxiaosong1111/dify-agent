"""Cumulative Dify run starts and recorded elapsed time; not a money budget."""
from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException,APIRouter,Query
from pydantic import BaseModel,ConfigDict,StrictInt,StrictBool,StrictStr,Field
from .plan_drafts import DraftRoute,inspect_text

NOTE='累计启动批次包括失败／未知及旧修订，不因改版本清零；一批多轮对话只计一个启动，内部轮次／循环不逐项计数。耗时来自 Sierra 请求起止时间。USD阈值只依据已保存Dify返回报价，不是供应商账单，不预估下一批费用，下一批可能超过阈值；金额／币种／身份或结果未知及摘要截断时不能证明剩余预算。限制不取消已派发操作，不包含导入／建库／工具隐含费用／助手模型建议，不代表费用硬上限。'

class LimitsRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 policy_revision:StrictInt=Field(ge=0)
 max_started_runs:StrictInt|None=Field(default=None,ge=0,le=10000)
 max_total_minutes:StrictInt|None=Field(default=None,ge=1,le=10080)
 max_reported_cost_usd:StrictStr|None=Field(default=None,max_length=40)
 acknowledge_scope:StrictBool
 note:StrictStr=Field(min_length=1,max_length=1000)

def elapsed(run):
 if run.get('status') in {'pending','unknown'}:return None
 try:
  start=datetime.fromisoformat(run['created_at'].replace('Z','+00:00'));end=datetime.fromisoformat(run['completed_at'].replace('Z','+00:00'))
  if not start.tzinfo or not end.tzinfo:return None
  delta=end-start;seconds=Decimal(delta.days*86400+delta.seconds)+Decimal(delta.microseconds)/1000000
  return seconds if 0<=seconds<=Decimal(86400*366) else None
 except (ValueError,TypeError,KeyError,AttributeError,OverflowError):return None

class ExecutionLimits:
 def __init__(self,h):self.h=h
 def state(self,task):
  stored=self.h.store.get('execution_limits',task['id']) or {'id':task['id'],'policy_revision':0,'max_started_runs':None,'max_total_minutes':None,'history':[]}
  stored.setdefault('max_reported_cost_usd',None)
  runs=[r for r in task.get('runs',[]) if isinstance(r,dict) and r.get('kind')=='run'];total=Decimal(0);unknown=0
  for run in runs:
   duration=elapsed(run)
   if duration is None:unknown+=1
   else:total+=duration
  blockers=[]
  from .execution_costs import summary as costs
  reported=costs(task);usd=reported['known_amounts_by_currency'].get('USD','0')
  uncertain_sources={r.get('id') for r in runs if r.get('status') not in {'success','failed'}}
  unavailable=sum(not e['cost_known'] or e['currency']!='USD' or not e['identity_verified'] or any(s['run_id'] in uncertain_sources for s in e['sources']) for e in reported['executions'])
  if stored['max_started_runs'] is not None and len(runs)>=stored['max_started_runs']:blockers.append('累计试跑启动批次已达到上限，本次不派发。')
  if stored['max_total_minutes'] is not None:
   if unknown:blockers.append('历史或当前运行耗时未知，不能证明剩余耗时预算；请核对或主动调整耗时限制，不把未知计为零。')
   elif total>=stored['max_total_minutes']*60:blockers.append('已记录累计试跑耗时达到上限，本次不派发。')
  if stored['max_reported_cost_usd'] is not None:
   if Decimal(usd)>=Decimal(stored['max_reported_cost_usd']):blockers.append('已记录累计Dify USD报价达到阈值，本次不派发；报价不等于供应商账单。')
   elif unavailable or reported['truncated']:blockers.append('历史Dify金额／币种／执行身份或结果不完整，不能证明剩余USD报价预算；未知不按零，不换算其他币种，不自动取消阈值。')
  return {'revision':task['revision'],'policy':stored,'started_runs':len(runs),'known_elapsed_seconds':str(total),'unknown_duration_runs':unknown,'known_reported_usd':usd,'unavailable_usd_executions':unavailable,'cost_summary_truncated':reported['truncated'],'blockers':blockers,'can_start':not blockers,'note':NOTE}
 def preflight(self,task,requested_runs):
  """Read-only whole-batch capacity check; never reserves or changes a policy."""
  from .dsl_roundtrip import digest
  state=self.state(task);cap=state['policy']['max_started_runs'];started=state['started_runs']
  projected=started+requested_runs;remaining=None if cap is None else max(0,cap-started)
  count_fits=cap is None or projected<=cap;blockers=list(state['blockers'])
  if not count_fits:blockers.append(f'本批计划试跑{requested_runs}次，当前累计{started}次、上限{cap}次；若要容纳整批，有限次数上限至少须明确调整为{projected}，不会自动修改或清零。')
  binding={'task_id':task['id'],'revision':task['revision'],'app_id':task.get('dify_app_id'),'requested_runs':requested_runs,'limits':state}
  return {'task_id':task['id'],'revision':task['revision'],'requested_runs':requested_runs,'started_runs':started,'remaining_start_slots':remaining,
          'projected_started_runs':projected,'minimum_finite_start_cap':projected,'count_fits':count_fits,'limits_allow_requested_runs':not blockers,
          'blockers':blockers,'limits':state,'review_token':digest(binding),'network_requested':False,'task_changed':False,'limits_changed':False,'start_slots_reserved':0,
          'resource_permission_granted':False,'note':'仅按本机当前累计次数、已记录耗时和报价检查整批；不是运行次数预留、资源批准或费用预估，不保证后续耗时/报价足够。旧修订、失败和未知运行仍累计，每次实际启动仍重新检查。'}
 def require_start(self,task):
  state=self.state(task)
  if state['blockers']:raise HTTPException(409,' '.join(state['blockers']))
 def register(self):
  h=self.h;router=APIRouter(route_class=DraftRoute)
  @router.get('/api/tasks/{item_id}/execution-limits')
  def read(item_id:str):
   with h.store.lock:return self.state(h.get_task(item_id))
  @router.get('/api/tasks/{item_id}/execution-limits/preflight')
  def preflight(item_id:str,revision:int=Query(ge=1),requested_runs:int=Query(ge=1,le=100)):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,revision)
    return self.preflight(task,requested_runs)
  @router.patch('/api/tasks/{item_id}/execution-limits')
  def save(item_id:str,payload:LimitsRequest):
   if not payload.acknowledge_scope or not payload.note.strip():raise HTTPException(422,'请明确确认执行上限的范围／已派发不取消，并说明调整原因。')
   import json
   inspect_text(json.dumps({'note':payload.note},ensure_ascii=False))
   from .execution_costs import amount
   cost=amount(payload.max_reported_cost_usd) if payload.max_reported_cost_usd is not None else None
   if payload.max_reported_cost_usd is not None and cost is None:raise HTTPException(422,'USD报价阈值须为0—1000000的有限十进制文字，最多12位小数；未知或非法值不自动关闭限制。')
   with h.store.lock:
    task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);state=self.state(task);old=state['policy']
    if payload.policy_revision!=old['policy_revision']:raise HTTPException(409,'执行上限已被其他操作更新，请重新读取，不自动覆盖。')
    if 'max_reported_cost_usd' not in payload.model_fields_set:cost=old['max_reported_cost_usd']
    after={'max_started_runs':payload.max_started_runs,'max_total_minutes':payload.max_total_minutes,'max_reported_cost_usd':cost}
    record={'id':item_id,'policy_revision':old['policy_revision']+1,**after,'updated_at':h.now(),'history':old['history']+[{'before':{k:old[k] for k in after},'after':after,'note':payload.note.strip(),'created_at':h.now(),'source':'user'}]}
    h.store.put('execution_limits',item_id,record);return self.state(task)
  h.app.include_router(router)
