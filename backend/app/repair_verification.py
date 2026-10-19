"""Repair follow-up from saved evidence only; never dispatches a rerun."""
from fastapi import HTTPException
from .acceptance import same_json,matches_case
from .run_diagnostics import binding,source_hash
from .diagnostic_graph_source import artifact
from .runtime_repair import checksum,ApplyRequest

NOTE='只汇总当前修复版本的已保存证据，不派发请求、不继承旧运行通过；即使原错误已消失，也不证明完整业务验收或没有模拟依赖。'

def contract(task,env):
 return checksum({k:task.get(k) for k in ('app_type','workflow_plan','requirements','configuration','test_cases','environment_id')} | {'environment_binding':binding(env) if env else None})

def passing(task,run,case=None):
 if run.get('status')!='success':return {'pending':'running','unknown':'unknown','failed':'failed'}.get(run.get('status'),'needs_review')
 result=run.get('result') or {}
 if task['app_type']=='workflow' and (result.get('data') or {}).get('status')!='succeeded':return 'needs_review'
 if case:
  if not matches_case(case,run):return 'needs_review'
  from .evaluation import evaluate_output
  if case.get('followups'):
   from .conversation_cases import evaluate_conversation
   evaluation=evaluate_conversation(case,result)
  else:
   output=(result.get('data') or {}).get('outputs',{}) if task['app_type']=='workflow' else {'answer':result.get('answer')}
   evaluation=evaluate_output(output,case['expectation'])
  status=evaluation.get('status','needs_review')
  if evaluation.get('mode')=='manual':
   review=run.get('manual_review') or {}
   if review.get('source')=='user' and review.get('decision') in {'passed','failed'} and review.get('reason'):return review['decision']
  return status if status in {'passed','failed','needs_review'} else 'needs_review'
 if task['app_type']=='advanced-chat' and not isinstance(result.get('answer'),str):return 'needs_review'
 return 'passed'

class RepairVerification:
 def __init__(self,h):self.h=h
 def context(self,item_id,repair_id):
  h=self.h;task=h.get_task(item_id);record=h.store.get('runtime_repair',repair_id)
  if not record or record['task_id']!=item_id:raise HTTPException(404,'本任务没有该修复记录。')
  env=h.store.get('environment',task.get('environment_id')) if task.get('environment_id') else None
  source=next((r for r in task['runs'] if r['id']==record['run_id']),None)
  reason=None
  if record['status']!='applied':reason='候选尚未采纳，先核对差异并采纳为新修订。'
  elif not record.get('verification_contract') or not record.get('source_run_hash'):reason='旧修复记录未冻结验证计划，仅作历史参考；需人工核对输入与样例。'
  elif task['revision']!=record.get('result_revision') or record['verification_contract']!=contract(task,env):reason='修复后需求、配置、流程、样例或环境已经改变，旧验证计划不能套用当前版本。'
  elif not source or record['source_run_hash']!=source_hash(source):reason='原失败记录或复核已变化，需要人工重新核对来源。'
  return task,record,env,source,reason
 def replay(self,task,source):
  inputs=source.get('input') if source else None
  if not isinstance(inputs,dict) or not inputs:return None,'原失败记录没有完整输入，请人工补齐重现样例。'
  if source.get('conversation_context') or 'conversation_id' in inputs:return None,'原失败依赖已有会话，不能自动重放历史；请整理为从新会话开始的正式多轮样例。'
  case=source.get('test_case')
  if case:
   current=next((c for c in task.get('test_cases',[]) if c['id']==case.get('id')),None)
   if not current or not matches_case(current,source):return None,'原失败样例已变化，不能把修改后的输入／预期当作原失败重现。'
   return {'input':inputs,'case_id':current['id']},None
  return {'input':inputs,'case_id':None},None
 def summarize(self,item_id,repair_id):
  h=self.h;task,record,env,source,reason=self.context(item_id,repair_id)
  value={'repair_id':repair_id,'revision':task['revision'],'result_revision':record.get('result_revision'),'state':'stale' if reason else 'not_run','message':reason or '先重新确认配置、构建并导入，再运行原失败输入及现有样例。','can_prepare':False,'reproduction':{'status':'not_run','run_id':None},'cases':[],'error_cleared':False,'verification':'repair_followup_only','note':NOTE}
  if reason:return value
  recipe,replay_reason=self.replay(task,source);value['can_prepare']=bool(recipe);value['replay_blocker']=replay_reason
  runs=[r for r in task['runs'] if r.get('kind')=='run' and r.get('revision')==task['revision'] and r.get('environment_id')==task.get('environment_id') and r.get('environment_binding')==binding(env) and r.get('app_type')==task['app_type'] and r.get('app_id') and r.get('app_id')==task.get('dify_app_id')]
  for case in task.get('test_cases',[]):
   current=next((r for r in reversed(runs) if (r.get('test_case') or {}).get('id')==case['id']),None)
   value['cases'].append({'id':case['id'],'name':case['name'],'required':case.get('required',True),'status':passing(task,current,case) if current else 'not_run','run_id':current['id'] if current else None})
  # Recheck all existing cases: dependency pruning is not proven yet.
  repro=next((r for r in reversed(runs) if recipe and not r.get('conversation_context') and same_json(r.get('input'),recipe['input']) and ((r.get('test_case') or {}).get('id')==recipe['case_id'] if recipe['case_id'] else not r.get('test_case'))),None)
  case=next((c for c in task.get('test_cases',[]) if recipe and c['id']==recipe['case_id']),None)
  status=passing(task,repro,case) if repro else 'not_run';value['reproduction']={'status':status,'run_id':repro['id'] if repro else None}
  local=artifact(h,task)
  if repro and status=='passed':
   report=(repro.get('diagnostics') or [None])[-1];proof=(report or {}).get('source_graph') or {}
   trusted=bool(report and report.get('selected_turn')==record.get('source_selected_turn') and report.get('source_hash')==source_hash(repro) and report.get('source_revision')==task['revision'] and report.get('captured_at_revision')==task['revision'] and report.get('app_id')==task.get('dify_app_id') and report.get('current_source') and report.get('trace_state')=='read' and not report.get('truncated') and report.get('remote_status')=='succeeded' and local and proof.get('matched') and all(proof.get(k)==local for k in ('artifact','execution','published')))
   repaired={change['node_id'] for change in record['changes']}
   nodes=[n for n in (report or {}).get('nodes',[]) if n.get('node_id') in repaired]
   value['error_cleared']=bool(trusted and repaired<={n.get('node_id') for n in nodes} and all(n.get('status')=='succeeded' and not n.get('error') for n in nodes))
  if not task['requirements_confirmed']:state,message='needs_requirements','模型代码可能影响业务行为，请先核对并重新确认需求。'
  elif not task['configuration_confirmed']:state,message='needs_configuration','修复产生新版本，请先重新确认配置。'
  elif not local:state,message='needs_build','当前修复版本尚未可信构建，请先构建并核对成果。'
  elif not task.get('dify_app_id'):state,message='needs_import','当前修复版本尚未导入；先核对具体资源方案，不自动覆盖原应用。'
  elif any(r.get('status') in {'pending','unknown'} for r in runs):state,message='unknown','当前版本有未完成或结果未知的运行；先核对远端，不盲目重跑。'
  elif replay_reason:state,message='needs_input',replay_reason
  elif status=='failed':state,message='failed','原失败输入的最新运行仍未通过，不计修复成功，不继续猜测修改或自动重跑。'
  elif status!='passed':state,message='not_run','请先运行原失败输入；输入、正式样例预期与版本保持一致。'
  elif not value['error_cleared']:state,message='needs_trace','原失败输入已返回，但尚缺当前来源的完整节点轨迹，不能证明修复节点已执行成功；读取该次新运行的轨迹。'
  elif not value['cases']:state,message='needs_cases','原失败输入和修复节点已有成功证据，但尚无正式验收样例；请补齐样例，不能仅凭自由试跑计为完整验证。'
  elif any(c['status']!='passed' for c in value['cases']):state,message='needs_cases','原修复节点已有成功证据；仍需重跑全部现有样例，不能继承旧版本通过。'
  else:state,message='verified','原失败输入及当前现有样例已通过，修复节点有当前来源成功轨迹；只证明这次修复及已声明检查，仍需完整业务验收。'
  if state=='verified' and task['configuration'].get('mock_dependencies'):state,message='mock_only','原失败输入及声明检查通过，但有模拟依赖，仅作阶段性成果。'
  value.update(state=state,message=message);return value
 def register(self,router):
  h=self.h
  @router.get('/api/tasks/{item_id}/runtime-repairs/{repair_id}/verification')
  def read(item_id:str,repair_id:str):
   with h.store.lock:return self.summarize(item_id,repair_id)
  @router.post('/api/tasks/{item_id}/runtime-repairs/{repair_id}/prepare-input')
  def prepare(item_id:str,repair_id:str,payload:ApplyRequest):
   with h.store.lock:
    task,record,env,source,reason=self.context(item_id,repair_id);h.require_revision(task,payload.revision)
    if reason:raise HTTPException(409,reason)
    recipe,reason=self.replay(task,source)
    if reason:raise HTTPException(422,reason)
    from .plan_drafts import inspect_text
    import json
    inspect_text(json.dumps(recipe,ensure_ascii=False))
    return dict(recipe,revision=task['revision'],repair_id=repair_id,note='仅准备输入，不运行、不复用历史会话、不修改正式样例；实际试跑仍按已有确认与资源门禁。')
