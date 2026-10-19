"""Exact repeated failures, saved evidence only. No semantic progress claims."""
import hashlib,json,uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field
from .plan_drafts import DraftRoute,inspect_text
from .run_diagnostics import binding,source_hash,classify
from .diagnostic_graph_source import artifact

NOTE='同一环境、相同完整输入及样例的连续两次可信运行出现相同失败节点和错误摘要时，暂停该输入的试跑及模型修复。跨修订保留；其他输入不算重现。仅比较已保存证据，不证明根因或业务无进展；摘要变化也不证明修复成功。已有会话／多轮、来源不完整或未知结果不自动归入相同问题。'

def digest(value):
 try:
  text=json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False)
  if len(text)>200000: return None
  return hashlib.sha256(text.encode()).hexdigest()
 except (ValueError,TypeError,RecursionError,UnicodeError):return None

def context(run):
 inputs=run.get('input');case=run.get('test_case')
 if not isinstance(inputs,dict) or not inputs or run.get('conversation_context') or 'conversation_id' in inputs or (isinstance(case,dict) and case.get('followups')):return None
 if run.get('app_type') not in {'workflow','advanced-chat'} or not run.get('environment_binding'):return None
 return digest({k:run.get(k) for k in ('environment_id','environment_binding','app_type','input','test_case')})

def evidence(run):
 report=(run.get('diagnostics') or [None])[-1]
 if not isinstance(report,dict):return None
 proof=report.get('source_graph') or {};graph=proof.get('artifact')
 if (run.get('status')!='failed' or report.get('selected_turn') is not None or report.get('source_hash')!=source_hash(run) or report.get('source_revision')!=run.get('revision') or report.get('captured_at_revision')!=run.get('revision') or report.get('app_id')!=run.get('app_id') or not run.get('app_id') or report.get('current_source') is not True or report.get('trace_state')!='read' or report.get('truncated') is not False or report.get('remote_status')!='failed' or proof.get('matched') is not True or not isinstance(graph,dict) or not graph.get('digest') or any(proof.get(k)!=graph for k in ('execution','published'))):return None
 rows=report.get('nodes')
 if not isinstance(rows,list) or not 1<=len(rows)<=1500:return None
 failures=[];public=[]
 for row in rows:
  if not isinstance(row,dict):return None
  if row.get('status') not in {'failed','exception'}:continue
  if not all(isinstance(row.get(k),str) and 0<len(row[k])<=4000 for k in ('node_id','node_type','error')) or '摘要已截断' in row['error'] or '[已脱敏]' in row['error']:return None
  entry=(row['node_id'],row['node_type'],row['error'])
  if entry not in failures:failures.append(entry);public.append({'node_id':row['node_id'],'node_type':row['node_type'],'category':classify(row['error'],row['node_type'])['category']})
 if not failures:return None
 return {'report':report,'signature':digest(sorted(failures)),'nodes':public}

class Decision(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 evidence_token:StrictStr=Field(min_length=64,max_length=64)
 action:StrictStr
 acknowledge_review:StrictBool
 note:StrictStr=Field(min_length=1,max_length=1000)

class FailureWatch:
 def __init__(self,h):self.h=h
 def groups(self,task):
  env=self.h.store.get('environment',task.get('environment_id')) if task.get('environment_id') else None
  if not env:return []
  local=artifact(self.h,task)
  if not local:return []
  series={}
  for run in task.get('runs',[]):
   if not isinstance(run,dict) or run.get('kind')!='run' or run.get('environment_id')!=env['id'] or run.get('environment_binding')!=binding(env) or run.get('app_type')!=task.get('app_type'):continue
   key=context(run)
   if not key:continue
   info=evidence(run)
   if not info:series.pop(key,None);continue
   prior=series.get(key)
   streak=prior['runs']+[run] if prior and prior['info']['signature']==info['signature'] else [run]
   series[key]={'runs':streak,'info':info}
  output=[]
  for key,value in series.items():
   runs=value['runs'];latest=runs[-1];info=value['info'];report=info['report']
   if len(runs)<2 or latest.get('revision')!=task['revision'] or latest.get('app_id')!=task.get('dify_app_id') or report['source_graph']['artifact']!=local:continue
   token=digest({'revision':task['revision'],'context':key,'runs':[(r['id'],source_hash(r)) for r in runs],'signature':info['signature'],'artifact':local})
   if not token:continue
   output.append({'evidence_token':token,'context_token':key,'run_ids':[r['id'] for r in runs],'latest_run_id':latest['id'],'consecutive_failures':len(runs),'nodes':info['nodes']})
  return output
 def state(self,task):
  groups=self.groups(task);records=[r for r in self.h.store.list('failure_decision') if r['task_id']==task['id']]
  for group in groups:
   prior=next((r for r in records if r['evidence_token']==group['evidence_token']),None)
   group['permission']={k:prior.get(k) for k in ('id','action','status','created_at','used_at')} if prior else None
   group.pop('context_token')
  return {'revision':task['revision'],'paused_groups':groups,'note':NOTE,'options':[{'action':'run','label':'核对后再试跑一次','effect':'仅允许该输入的一次试跑启动；仍需当前版本的全部确认和资源许可。'},{'action':'model_repair','label':'核对后请求一次模型候选','effect':'仅允许一次候选请求；仍须另行确认具体数据与费用，不能自动采纳或运行。'},{'action':'change_plan','label':'先修改方案或补齐条件','effect':'保留暂停；修改不会抹去历史，同样的问题再次出现仍会检查。'}]}
 def require(self,task,action,*,inputs=None,test_case=None,conversation_context=None,run_id=None):
  groups=self.groups(task)
  if action=='run':
   key=context({'input':inputs,'test_case':test_case,'conversation_context':conversation_context,'app_type':task['app_type'],'environment_id':task.get('environment_id'),'environment_binding':binding(self.h.store.get('environment',task.get('environment_id')) or {})})
   group=next((g for g in groups if g['context_token']==key),None)
  else:group=next((g for g in groups if g['latest_run_id']==run_id),None)
  if not group:return
  decisions=[r for r in self.h.store.list('failure_decision') if r['task_id']==task['id'] and r['evidence_token']==group['evidence_token']]
  record=decisions[0] if decisions else None
  if not record or record.get('status')!='ready' or record['action']!=action:raise HTTPException(409,'相同输入连续两次出现相同可信失败，已暂停本次操作。请在“重复失败暂停”中核对证据与影响，并明确选择下一步；不会自动增加重试或改方案。')
  record.update(status='used',used_at=self.h.now());self.h.store.put('failure_decision',record['id'],record)
 def register(self):
  h=self.h;router=APIRouter(route_class=DraftRoute)
  @router.get('/api/tasks/{item_id}/failure-watch')
  def read(item_id:str):
   with h.store.lock:return self.state(h.get_task(item_id))
  @router.post('/api/tasks/{item_id}/failure-watch/decision')
  def decide(item_id:str,payload:Decision):
   if payload.action not in {'run','model_repair','change_plan'} or not payload.acknowledge_review or not payload.note.strip():raise HTTPException(422,'请核对重复失败，选择明确行为并说明已补齐的条件或下一步。')
   inspect_text(json.dumps({'note':payload.note},ensure_ascii=False))
   with h.store.lock:
    task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
    if not any(g['evidence_token']==payload.evidence_token for g in self.groups(task)):raise HTTPException(409,'失败证据或当前来源已变化，请重新核对，未保存旧决定。')
    prior=[r for r in h.store.list('failure_decision') if r['task_id']==item_id and r['evidence_token']==payload.evidence_token]
    if prior and prior[0]['status']=='used':raise HTTPException(409,'这一组证据的一次操作许可已使用，不能重复授权同一轮；先读取新结果或修改方案。')
    record={'id':str(uuid.uuid4()),'task_id':item_id,'revision':payload.revision,'evidence_token':payload.evidence_token,'action':payload.action,'status':'ready' if payload.action!='change_plan' else 'paused','note':payload.note.strip(),'created_at':h.now()}
    h.store.put('failure_decision',record['id'],record);return self.state(task)
  h.app.include_router(router)
