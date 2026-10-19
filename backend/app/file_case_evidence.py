"""Read original local file-case receipts, never query or rerun the platform."""
import copy,json,hashlib
from fastapi import APIRouter,HTTPException,Query,Response
from .file_cases import CaseRoute

LIMIT=64000
def output_bytes(run,structured=None):
 if run.get('status')!='success':return None
 result=run.get('result');data=result.get('data') if isinstance(result,dict) else None;outputs=data.get('outputs') if isinstance(data,dict) else None
 if not isinstance(outputs,dict):return None
 if structured is not None:
  from .json_inputs import validate_value
  try:
   if set(outputs)!={structured['output_variable']}:raise ValueError()
   validate_value(structured['schema'],outputs[structured['output_variable']])
  except (ValueError,KeyError,TypeError):raise HTTPException(422,'已存对象不符合原结构化文件方案，不展开未经核对的原始回执。') from None
 elif any(not isinstance(v,str) and not (isinstance(v,list) and len(v)<=20 and all(isinstance(x,str) for x in v)) for v in outputs.values()):raise HTTPException(422,'已存文件输出结构不属于适配的文字／文字列表，未展开未知原始回执。')
 try:return json.dumps(outputs,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')
 except (ValueError,UnicodeError,RecursionError):raise HTTPException(422,'已存文件输出不能完整编码，未修复或截断后当作完整结果。') from None

class FileCaseEvidence:
 def __init__(self,h):self.h=h
 def register(self):
  h=self.h;router=APIRouter(route_class=CaseRoute)
  def source(item_id,run_id):
   task=h.get_task(item_id);run=next((r for r in task['runs'] if r['id']==run_id),None)
   if not run:raise HTTPException(404,'本任务没有该运行记录，未读取其他任务。')
   if run.get('kind')!='run' or not isinstance(run.get('file_case'),dict) or not isinstance(run['file_case'].get('case'),dict):raise HTTPException(422,'该记录不是固定文件样例试跑，未扩大到其他运行或原始平台回执。')
   structured=None;saved=run.get('result');data=saved.get('data') if isinstance(saved,dict) else None;outputs=data.get('outputs') if isinstance(data,dict) else None
   if run.get('status')=='success' and isinstance(outputs,dict) and any(isinstance(v,dict) for v in outputs.values()):
    from .file_run import KIND,canonical
    plans=[p for p in h.store.list(KIND) if isinstance(p,dict) and p.get('task_id')==item_id and p.get('run_id')==run_id and p.get('plan_schema_version') in {6,7,8,9}]
    if len(plans)!=1:raise HTTPException(422,'对象输出缺少唯一原结构化文件方案，未扩大读取范围。')
    p=plans[0];flow=p.get('data_flow');saved=run['result']
    if p.get('model_egress_approved') is not True or p.get('unpriced_model_cost_approved') is not True or p.get('dispatched') is not True or type(p.get('attempts')) is not int or p['attempts']!=1:raise HTTPException(422,'原结构化文件方案缺少明确模型批准或唯一派发，未展示未知对象。')
    if p.get('state')!='platform_finished' or p.get('revision')!=run.get('revision') or any(p.get(k)!=run.get(k) for k in ('app_id','environment_id','environment_binding','input')) or not isinstance(flow,dict) or (p.get('plan_schema_version')==6 and (flow.get('schema_version')!=5 or flow.get('scenario')!='document_model_object') or p.get('plan_schema_version')==7 and (flow.get('schema_version')!=6 or flow.get('scenario')!='document_model_guarded_object' or p.get('strict_guard_approved') is not True) or p.get('plan_schema_version')==8 and (flow.get('schema_version')!=7 or flow.get('scenario')!='document_list_model_object' or p.get('join_policy_approved') is not True) or p.get('plan_schema_version')==9 and (flow.get('schema_version')!=8 or flow.get('scenario')!='document_list_model_guarded_object' or p.get('join_policy_approved') is not True or p.get('strict_guard_approved') is not True)) or flow.get('output_kind')!='json-object' or not canonical(saved.get('workflow_run_id')) or data.get('id')!=saved['workflow_run_id'] or data.get('workflow_id')!=p.get('published_workflow_id') or data.get('status')!='succeeded' or not isinstance(flow.get('structured_output'),dict):raise HTTPException(422,'对象输出与原结构化文件目标／运行／发布绑定不一致，未采用当前新方案代替。')
    structured=flow['structured_output']
    if p.get('plan_schema_version') in {8,9}:
     from .file_join import policy
     try:
      join=flow['join_policy']
      if not isinstance(join,dict) or flow.get('node_types')!=(['start','document-extractor','code','llm','code','end'] if p['plan_schema_version']==9 else ['start','document-extractor','code','llm','end']) or join.get('verification')!='canonical_code_and_binding_static_only' or not isinstance(join.get('node_id'),str) or not join['node_id']:raise ValueError()
      policy(join['policy'])
     except (KeyError,TypeError,ValueError):raise HTTPException(422,'原多文档对象方案缺少完整拼接声明，未展示对象。') from None
    if p.get('plan_schema_version') in {7,9}:
     from .file_schema_guard import validate_saved
     try:validate_saved(flow.get('strict_guard'),structured['node_id'],structured['schema'])
     except (ValueError,KeyError,TypeError):raise HTTPException(422,'原文件Schema校验声明不匹配，不展示未经核对的对象。') from None
   return task,run,structured
  @router.get('/api/tasks/{item_id}/file-cases/runs/{run_id}/evidence')
  def read(item_id:str,run_id:str):
   with h.store.lock:
    task,run,structured=source(item_id,run_id);raw=output_bytes(run,structured);case=run['file_case']['case']
    return {'task_id':item_id,'revision':task['revision'],'run_id':run_id,'run_revision':run['revision'],'case_id':case['id'],'catalog_revision':run['file_case']['catalog_revision'],'status':run['status'],'environment_id':run.get('environment_id'),'app_id':run.get('app_id'),'case_text':json.dumps(case,ensure_ascii=False,allow_nan=False,indent=2),'evaluation':copy.deepcopy(run.get('file_case_evaluation')),'outputs_available':raw is not None,'outputs_preview':raw[:LIMIT].decode('utf-8',errors='ignore') if raw is not None else None,'outputs_sha256':hashlib.sha256(raw).hexdigest() if raw is not None else None,'output_bytes':len(raw) if raw is not None else 0,'preview_limit_bytes':LIMIT,'preview_truncated':len(raw)>LIMIT if raw is not None else False,'verification':'stored_file_case_receipt_only','current_acceptance_rechecked':False,'network_requested':False,'task_changed':False,'workflow_runs':0,'note':'只读本机已保存的原运行回执，未重新查询Dify或执行模型，未重新计算／继承当前验收。是否计入当前结果以固定样例汇总为准；人工复核仍须匹配当前样例并明确提交理由。'}
  @router.get('/api/tasks/{item_id}/file-cases/runs/{run_id}/outputs.json')
  def download(item_id:str,run_id:str,sha256:str=Query(pattern=r'^[a-f0-9]{64}$')):
   with h.store.lock:
    _,run,structured=source(item_id,run_id);raw=output_bytes(run,structured)
    if raw is None:raise HTTPException(409,'该记录没有明确成功的已存输出，不能下载或当作业务通过。')
    actual=hashlib.sha256(raw).hexdigest()
    if actual!=sha256:raise HTTPException(409,'已存输出与预览哈希不一致，请重新读取，不下载另一份结果代替。')
    return Response(raw,media_type='application/json',headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="sierra-file-output.json"','X-Sierra-Output-SHA256':actual})
  h.app.include_router(router)
