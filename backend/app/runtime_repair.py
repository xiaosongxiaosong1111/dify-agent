"""Local, evidence-bound repair drafts. No provider or Dify requests."""
import ast,copy,hashlib,json,re,symtable,uuid
from fastapi import HTTPException,APIRouter
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
from .plan_drafts import DraftRoute,inspect_text
from .run_diagnostics import binding,source_hash
from .diagnostic_graph_source import artifact,fingerprint
from .dsl_roundtrip import parse

MODULES={'math','re'}
NOTE='仅在本机生成和静态检查修复候选，未在 Dify 运行；采纳后须重新确认配置、构建、核对资源方案并试跑，不自动发布或重跑。'

def checksum(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def missing_import(code,error):
 """Only an unbound module used through attributes; no runtime evaluation."""
 matches=re.findall(r"\bNameError:\s*name ['\"](\w+)['\"] is not defined\b",error or '')
 if len(matches)!=1 or matches[0] not in MODULES or not isinstance(code,str) or len(code)>100000:return None
 module=matches[0]
 try:tree=ast.parse(code);symbols=symtable.symtable(code,'<repair>','exec')
 except (SyntaxError,ValueError,RecursionError):return None
 tables=[symbols]
 while tables:
  table=tables.pop();tables.extend(table.get_children())
  if module in table.get_identifiers():
   symbol=table.lookup(module)
   if symbol.is_assigned() or symbol.is_imported() or symbol.is_parameter() or symbol.is_declared_global() or symbol.is_nonlocal():return None
 parents={id(child):node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
 refs=[n for n in ast.walk(tree) if isinstance(n,ast.Name) and n.id==module]
 if not refs or any(not isinstance(n.ctx,ast.Load) or not isinstance(parents.get(id(n)),ast.Attribute) or parents[id(n)].value is not n for n in refs):return None
 # Preserve docstrings, future imports, comments and all original lines.
 line=0
 for index,node in enumerate(tree.body):
  if index==0 and isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):line=node.end_lineno
  elif isinstance(node,ast.ImportFrom) and node.module=='__future__':line=node.end_lineno
  else:break
 lines=code.splitlines(keepends=True);newline='\r\n' if '\r\n' in code else '\n'
 prefix=''.join(lines[:line]);suffix=''.join(lines[line:])
 fixed=prefix+('' if not prefix or prefix.endswith(('\n','\r')) else newline)+f'import {module}{newline}'+suffix
 try:parsed=ast.parse(fixed)
 except (SyntaxError,ValueError,RecursionError):return None
 imports=[(i,n) for i,n in enumerate(parsed.body) if isinstance(n,ast.Import) and len(n.names)==1 and n.names[0].name==module and n.names[0].asname is None]
 if len(imports)!=1:return None
 del parsed.body[imports[0][0]]
 if ast.dump(parsed,include_attributes=False)!=ast.dump(tree,include_attributes=False):return None
 return {'code':fixed,'module':module,'inserted_line':line+1}

class PreviewRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 diagnostic_id:StrictStr=Field(min_length=1,max_length=128)

class ApplyRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)

class RuntimeRepair:
 def __init__(self,h):self.h=h
 def context(self,item_id,run_id,revision,diagnostic_id,*,_task=None):
  h=self.h;task=_task if _task is not None else h.get_task(item_id);h.require_idle(task);h.require_revision(task,revision)
  if task.get('dsl_reference') or task.get('dsl_overlay'):raise HTTPException(409,'当前使用实际 DSL 保留方案，不能用计划修复覆盖手改；请在实际 DSL 中核对错误并重新合并。')
  if task.get('app_type') not in {'workflow','advanced-chat'} or not task.get('workflow_plan') or task.get('plan_stale'):raise HTTPException(422,'本机小修复需要当前未过期的 Workflow／Chatflow 计划，原生 Agent 暂不支持。')
  if any(r.get('status') in {'pending','unknown'} for r in task.get('runs',[])):raise HTTPException(409,'有未结束或结果未知的操作，请先核对，不能据此启动修复。')
  run=next((r for r in task['runs'] if r['id']==run_id),None)
  report=(run.get('diagnostics') or [None])[-1] if run else None
  env=h.store.get('environment',task.get('environment_id'))
  if not run or run.get('kind')!='run' or run.get('status')!='failed':raise HTTPException(409,'只处理明确失败的试跑；成功但预期不匹配、未知或中断记录须人工核对。')
  if not isinstance(report,dict) or report.get('id')!=diagnostic_id or not report.get('current_source') or report.get('trace_state')!='read' or report.get('truncated'):raise HTTPException(409,'需要最新且完整的当前来源节点诊断；请先读取 Dify 轨迹并核对来源。')
  if not env or run.get('environment_binding')!=binding(env) or run.get('environment_id')!=task.get('environment_id') or run.get('app_id')!=task.get('dify_app_id') or not run.get('app_id') or run.get('app_type')!=task['app_type'] or run.get('revision')!=revision or report.get('source_revision')!=revision or report.get('captured_at_revision')!=revision or report.get('remote_status')!='failed' or report.get('app_id')!=run['app_id'] or report.get('source_hash')!=source_hash(run):raise HTTPException(409,'运行、环境或复核已变化，旧诊断不能用于当前修复。')
  local=artifact(h,task);proof=report.get('source_graph') or {}
  if not local or not proof.get('matched') or any(proof.get(k)!=local for k in ('artifact','execution','published')):raise HTTPException(409,'执行／发布／当前成果的来源不一致，请先核对实际 DSL。')
  try:generated=fingerprint(parse(h.compile_current(task)[0],task['app_type'])['workflow']['graph'])
  except (ValueError,TypeError,KeyError):generated=None
  if generated!=local:raise HTTPException(409,'计划与当前成果内容不一致，不能修复旧计划覆盖实际代码。')
  inspect_text(json.dumps(task['workflow_plan'],ensure_ascii=False))
  stamp=checksum({'plan':task['workflow_plan'],'configuration':task['configuration'],'requirements':task['requirements'],'run':source_hash(run),'report':report,'artifact':local,'environment':binding(env)})
  return task,report,stamp
 def candidate(self,task,report):
  plan=copy.deepcopy(task['workflow_plan']);lookup={}
  def collect(nodes,depth=0):
   for node in nodes:
    lookup.setdefault(node.get('id'),[]).append(node)
    if depth==0 and node.get('type') in {'loop','iteration'}:collect(node.get('config',{}).get('nodes',[]),1)
  collect(plan['nodes']);changes=[];changed={}
  failed=[n for n in report.get('nodes',[]) if n.get('status') in {'failed','exception'}]
  if not failed:raise HTTPException(422,'没有明确失败节点，不能自动猜测修复位置。')
  for evidence in failed:
   nodes=lookup.get(evidence.get('node_id'),[])
   if evidence.get('node_type')!='code' or len(nodes)!=1 or nodes[0].get('type')!='code':raise HTTPException(422,'失败涉及非代码或无法唯一关联的节点，需要人工处理；不生成部分修复后算作完成。')
   node=nodes[0];cfg=node['config']
   if cfg.get('code_language','python3')!='python3':raise HTTPException(422,'该代码语言没有已验证的本机小修复规则，请人工处理。')
   prior=changed.get(node['id'])
   patch=missing_import(prior['before'] if prior else cfg.get('code'),evidence.get('error'))
   if not patch:raise HTTPException(422,'当前错误不满足小修复规则。仅支持明确 NameError 且代码中未绑定的 math／re 标准库属性引用；不改业务表达式、输入输出或资源。')
   if prior:
    if prior['after']!=patch['code']:raise HTTPException(422,'同一节点有不同失败原因，需要人工核对，不合并猜测多个修复。')
    continue
   old=cfg['code'];cfg['code']=patch['code'];change={'node_id':node['id'],'rule':'missing_standard_import','module':patch['module'],'inserted_line':patch['inserted_line'],'before':old,'after':patch['code']};changes.append(change);changed[node['id']]=change
  from .workflow_plan import validate_plan
  result=validate_plan(task,plan)
  if not result['valid']:raise HTTPException(422,'修复候选未通过完整静态校验，未保存；请在流程页核对相关配置。')
  return plan,changes,result
 def register(self):
  h=self.h;router=APIRouter(route_class=DraftRoute)
  @router.get('/api/tasks/{item_id}/runtime-repairs')
  def history(item_id:str):
   with h.store.lock:
    task=h.get_task(item_id)
    return {'revision':task['revision'],'records':[r for r in h.store.list('runtime_repair') if r['task_id']==item_id],'note':NOTE}
  @router.post('/api/tasks/{item_id}/runs/{run_id}/repair-preview')
  def preview(item_id:str,run_id:str,payload:PreviewRequest):
   with h.store.lock:
    task,report,stamp=self.context(item_id,run_id,payload.revision,payload.diagnostic_id)
    for prior in h.store.list('runtime_repair'):
     if prior['task_id']==item_id and prior['run_id']==run_id and prior['source_stamp']==stamp:return prior
    plan,changes,validation=self.candidate(task,report)
    record={'id':str(uuid.uuid4()),'task_id':item_id,'run_id':run_id,'diagnostic_id':report['id'],'revision':task['revision'],'source_stamp':stamp,'status':'ready','verification':'static_only','candidate':plan,'changes':changes,'validation':validation,'created_at':h.now(),'note':NOTE}
    h.store.put('runtime_repair',record['id'],record);return record
  @router.post('/api/tasks/{item_id}/runtime-repairs/{repair_id}/apply')
  def apply(item_id:str,repair_id:str,payload:ApplyRequest):
   with h.store.lock:
    record=h.store.get('runtime_repair',repair_id)
    if not record or record['task_id']!=item_id:raise HTTPException(404,'本任务没有该修复候选。')
    if record.get('kind')=='model_code_proposal':raise HTTPException(422,'模型代码候选需先明确核对业务行为，使用模型候选采纳入口。')
    if record['status']!='ready':raise HTTPException(409,'该候选已经采纳，不重复产生新版本；请查看当前任务。')
    task,report,stamp=self.context(item_id,record['run_id'],payload.revision,record['diagnostic_id'])
    if record['revision']!=payload.revision or stamp!=record['source_stamp']:raise HTTPException(409,'候选来源已经变化，未采纳；请重新生成修复候选。')
    plan,changes,validation=self.candidate(task,report)
    if plan!=record['candidate'] or changes!=record['changes']:raise HTTPException(409,'修复候选内容不一致，未采纳。')
    h.invalidate(task,'运行修复前保存',preserve_requirements=True)
    task.update(workflow_plan=plan,plan_source='runtime_repair',plan_stale=False,updated_at=h.now())
    record.update(status='applied',result_revision=task['revision'],applied_at=h.now())
    from .repair_verification import contract
    source=next(r for r in task['runs'] if r['id']==record['run_id'])
    record.update(verification_contract=contract(task,h.store.get('environment',task.get('environment_id'))),source_run_hash=source_hash(source),source_selected_turn=(source.get('diagnostics') or [{}])[-1].get('selected_turn'))
    task['messages'].append({'role':'assistant','source':'system','content':'已采纳本机小修复为新修订；旧失败记录保留，配置需重新确认。'+NOTE,'created_at':h.now()})
    h.store.put_many([('task',item_id,task),('runtime_repair',repair_id,record)])
    return {'task':task,'repair':record}
  from .repair_verification import RepairVerification
  RepairVerification(h).register(router)
  from .model_repairs import ModelRepairs
  h.model_repairs=ModelRepairs(h)
  h.model_repairs.register(router)
  h.app.include_router(router)
