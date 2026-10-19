"""Approved document runs using private, frozen upload and output contracts."""
import asyncio,copy,hashlib,hmac,json,time,uuid
import math
from .file_formats import descriptor,extraction
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field
from .runtime_files import source,target,canonical,unique,FileRoute,KIND as UPLOAD
from .conversation_inputs import ServiceSnapshot,input_digest
from .schedule_observation import CredentialSnapshot
from .schedule_enable import configuration_digest
from .diagnostic_graph_source import fingerprint
from .dsl_roundtrip import parse
from .start_inputs import preflight
from .dify import DifyError
from .file_run_flow import describe
from .node_policy_audit import read_bytes

KIND='runtime_file_run'
PURE_NOTE='批准后只读核对目标App的Service Key归属与发布配置，再派发一次所列格式文档提取运行；不上传、发布、创建或覆盖应用，不调用模型／HTTP节点。不承诺远端文件仍存在或编码可解析；权限／有效性由Dify实际执行检查。两次读取不是原子快照，发布仍可能变化，返回发布ID须一致才记成功。失败／未知不自动重试，不算客户业务验收。'
MODEL_NOTE='本次把所列文件的提取文字、完整提示词及被引用的开始参数发送给目标Dify中该模型连接所配置的服务，实际网络地址与留存政策须在Dify核对，不能仅凭模型名证明供应商。计划执行一次LLM节点；供应商／插件内部请求或重试次数未验证，可能产生费用。没有可靠的本次USD预估，不按0计算；Max tokens不是输入／金额硬上限，长文可能因上下文限制被平台拒绝或调整，本批不拆分且不承诺模型完整读到全文；如有拼接，UTF-8字节上限包括分隔符／编号但不等于token或费用上限，超限停止而非截断，编号不证明来源真实性；累计报价阈值不保证下一次不会超额。超时或暂停Sierra不会取消已派发的平台／供应商请求。本次不重新上传、不发布、不创建／覆盖应用、不索引知识库或执行HTTP节点；失败／未知不自动重试，不算业务验收。'
NOTE='文件上传与运行分开批准；每次数据去向、模型、费用未知项及次数以该份冻结方案为准。旧方案不会自动扩大授权或调用模型。'
PUBLIC={'id','task_id','revision','app_id','environment_id','environment_url','environment_version','artifact_sha256','input','files','node_types','state','attempts','created_at','updated_at','expires_at','resource_token','note','message','run_id','workflow_run_id','observed_status','observed_at','output_contract_rejected','output_contract_reason','workflow_runs','max_remote_reads','automatic_retry','business_verified','published_workflow_id','plan_schema_version','data_flow','execution_policy','approved_at','model_egress_approved','unpriced_model_cost_approved','join_policy_approved','optional_branch_approved','strict_guard_approved','file_case'}

def digest(value):return input_digest(value)
def public(row):
 result={k:copy.deepcopy(v) for k,v in row.items() if k in PUBLIC}
 if result.get('file_case') is not None:result['file_case']['case_text']=json.dumps(result['file_case']['case'],ensure_ascii=False,allow_nan=False,indent=2)
 return result
def plan_token(row):return digest({k:v for k,v in row.items() if k not in {'resource_token','state','attempts','updated_at','message','run_id','published_workflow_id','approved_at','model_egress_approved','unpriced_model_cost_approved','join_policy_approved','optional_branch_approved','strict_guard_approved'}})

def failed_receipt(value,published_id):
 """Keep only same-publication terminal evidence, never outputs/errors/forms."""
 data=value.get('data') if isinstance(value,dict) else None
 if not isinstance(data,dict) or data.get('workflow_id')!=published_id or not canonical(data.get('id')) or value.get('workflow_run_id')!=data['id'] or not isinstance(data.get('status'),str) or data['status'] not in {'failed','stopped','partial-succeeded'}:return None
 safe={k:data[k] for k in ('id','workflow_id','status')}
 for key in ('total_tokens','total_steps','created_at','finished_at'):
  if type(data.get(key)) is int and 0<=data[key]<=9007199254740991:safe[key]=data[key]
 elapsed=data.get('elapsed_time')
 if type(elapsed) in (int,float) and 0<=elapsed<=31536000 and math.isfinite(elapsed):safe['elapsed_time']=elapsed
 return {'workflow_run_id':data['id'],'data':safe,'file_failure_receipt':True,'business_verified':False}

def console_stamp(store,owner):
 with store.connect() as conn:
  values=[conn.execute('SELECT value FROM secrets WHERE id=?',(owner+':'+key,)).fetchone() for key in ('console_token','csrf_token')]
 if not values[0]:raise HTTPException(422,'文件试跑须先在Sierra连接当前环境的管理接口，用于核对Service Key真实App归属。')
 return hashlib.sha256(b''.join(bytes(r[0]) if r else b'' for r in values)).hexdigest()

def profile(h,task):
 frozen=source(h,task);env,bound=target(h,task)
 try:raw=read_bytes(h.artifact_path(task))
 except (OSError,ValueError):raise HTTPException(409,'成果无法再次完整读取，未采用先前文件证明或派发。') from None
 if hashlib.sha256(raw).hexdigest()!=frozen['artifact_sha256']:raise HTTPException(409,'准备期间最终成果字节改变，请重新准备；不把旧文件证明配给新数据流。')
 root=parse(raw.decode('utf-8'),'workflow');graph=root['workflow']['graph']
 try:flow=describe(root)
 except ValueError as exc:raise HTTPException(422,str(exc)) from None
 core=fingerprint(graph)
 if not core:raise HTTPException(422,'最终核心图无法冻结，未派发。')
 try:config=configuration_digest(root['workflow'])
 except ValueError:raise HTTPException(422,'最终特性和变量不完整，未猜默认配置。') from None
 policy=h.store.get('execution_limits',task['id']) or {}
 policy={k:policy.get(k,0 if k=='policy_revision' else None) for k in ('policy_revision','max_started_runs','max_total_minutes','max_reported_cost_usd')}
 return root,copy.deepcopy(env),{**bound,**frozen,'console_stamp':console_stamp(h.store,env['id']),'graph_digest':core['digest'],'configuration_digest':config,'plan_schema_version':{3:4,4:5,5:6,6:7,7:8,8:9}[flow['schema_version']],'data_flow':flow,'execution_policy':policy}

def gates(h,task):
 h.require_idle(task);h.require_manual_entry_runtime(task);h.require_dsl_preservation(task);h.require_coverage(task);h.require_conflicts(task);h.require_intake(task)
 if not task.get('requirements_confirmed') or not task.get('configuration_confirmed'):raise HTTPException(422,'请先确认当前需求和配置，再准备文件试跑。')

class FileProof:
 def __init__(self,h,task,values):
  self.task_id=task['id'];self.revision=task['revision'];self.values=copy.deepcopy(values);self.case_snapshot=None
  self.root,self.env,self.context=profile(h,task);self.native=copy.deepcopy(values);self.files=[];private=[]
  for field in self.context['fields']:
   name=field['variable'];value=values.get(name)
   if field['type']=='file' and field.get('required') is False and (name not in values or value is None):continue
   if field['type']=='file-list':
    if not isinstance(value,list) or len(value)>field['max_length']:raise HTTPException(422,'文件列表须为有序引用数组，且不超过已确认max_length；不删除坏项或去重。')
    items=value
   else:items=[value]
   native=[]
   for item in items:
    if not isinstance(item,dict) or set(item)!={'sierra_file_id'} or not canonical(item['sierra_file_id']):raise HTTPException(422,'文件输入只接受本任务上传记录的sierra_file_id；不能提交原生文件ID、URL或其他对象。')
    row=h.store.get(UPLOAD,item['sierra_file_id'])
    if not row or row.get('task_id')!=task['id'] or row.get('revision')!=task['revision'] or row.get('state')!='uploaded' or row.get('attempts')!=1 or row.get('remote_upload_observed') is not True or not canonical(row.get('remote_id')) or not canonical(row.get('remote_created_by')):raise HTTPException(409,'文件不是当前任务和修订中明确上传成功的可信记录；旧版、未知或其他任务文件不能复用。')
    if row.get('variable')!=name or row.get('input_kind')!=field['type'] or any(row.get(k)!=self.context[k] for k in ('environment_id','environment_url','environment_version','app_id','credential_stamp','environment_binding','artifact_sha256')):raise HTTPException(409,'文件变量、成果、应用或原运行连接发生变化，未借用其他文件。')
    try:descriptor(row['filename'])
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    private.append({k:row[k] for k in ('id','remote_id','remote_created_by','content_sha256','size','filename')})
    self.files.append({k:row[k] for k in ('id','filename','size','content_sha256','variable')})
    native.append({'type':'document','transfer_method':'local_file','upload_file_id':row['remote_id']})
   self.native[name]=native if field['type']=='file-list' else native[0]
  if len({r['remote_created_by'] for r in private})>1:raise HTTPException(409,'文件上传用户不一致，未混用归属。')
  self.context['data_flow']['extraction']=extraction(self.files)
  if self.context['data_flow']['schema_version']==4:
   from .optional_file_run_flow import resolve
   try:self.context['data_flow']['resolved_branch']=resolve(self.context['data_flow'],values,self.files)
   except ValueError as exc:raise HTTPException(422,str(exc)) from None
  self.file_digest=digest(private)
  try:preflight(self.root,values,file_validator=self.validate)
  except ValueError as exc:raise HTTPException(422,str(exc)) from None
 def validate(self,row,value):
  if value!=self.values.get(row['variable']):raise ValueError('文件输入与本次冻结引用不一致。')
 def check(self,h,task,values):
  if (task['id'],task['revision'],digest(values))!=(self.task_id,self.revision,digest(self.values)):raise HTTPException(409,'文件试跑修订或输入已改变。')
  now=FileProof(h,task,values)
  if now.context!=self.context or now.file_digest!=self.file_digest:raise HTTPException(409,'文件、成果或连接在核对期间发生变化，未派发。')
  if self.case_snapshot is not None:
   from .file_cases import check_frozen
   check_frozen(h,task,now,self.case_snapshot)

class Prepare(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 input_text:StrictStr=Field(min_length=2,max_length=64000)
 case_id:StrictStr|None=None
 case_catalog_revision:StrictInt|None=Field(default=None,ge=1)
class Execute(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 resource_token:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
 acknowledge_run:StrictBool
 acknowledge_model_egress:StrictBool=False
 acknowledge_unpriced_model_cost:StrictBool=False
 acknowledge_join_policy:StrictBool=False
 acknowledge_optional_branch:StrictBool=False
 acknowledge_strict_guard:StrictBool=False

class FileRuns:
 def __init__(self,h):self.h=h
 def recover(self):
  for row in self.h.store.list(KIND):
   if row.get('state') in {'verifying','executing'}:
     row.update(state='unknown' if row.get('dispatched') else 'not_dispatched',updated_at=self.h.now(),message='上次文件核对／运行中断，未重放；请核对原运行记录。');self.h.store.put(KIND,row['id'],row)
 def register(self):
  h=self.h;router=APIRouter(route_class=FileRoute)
  @router.get('/api/tasks/{item_id}/file-runs')
  def history(item_id:str):
   with h.store.lock:
    t=h.get_task(item_id);rows=[r for r in h.store.list(KIND) if r.get('task_id')==item_id]
    return {'task_id':item_id,'revision':t['revision'],'records':[public(r) for r in rows[-20:]],'history_truncated':len(rows)>20,'note':NOTE}
  @router.post('/api/tasks/{item_id}/file-runs/prepare')
  def prepare(item_id:str,payload:Prepare):
   try:
    if len(payload.input_text.encode('utf-8'))>64000:raise ValueError()
    values=json.loads(payload.input_text,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    if not isinstance(values,dict):raise ValueError()
   except (ValueError,UnicodeError,RecursionError):raise HTTPException(422,'输入须为不超过64000字节、无重复键的严格JSON对象；不修复、不忽略字段。') from None
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,payload.revision);gates(h,task);proof=FileProof(h,task,values)
    if (payload.case_id is None)!=(payload.case_catalog_revision is None):raise HTTPException(422,'文件样例ID和样例集版本须一同提供，未降级为自由试跑。')
    row={'id':str(uuid.uuid4()),'task_id':item_id,'revision':task['revision'],**proof.context,'input':values,'files':proof.files,'file_binding_digest':proof.file_digest,'node_types':proof.context['data_flow']['node_types'],'state':'prepared','attempts':0,'created_at':h.now(),'updated_at':h.now(),'expires_at':time.time()+1800,'note':(MODEL_NOTE if proof.context['data_flow']['model_egress'] else PURE_NOTE)+' 请逐文件核对解析方式及可能的编码／格式／内容变化，再明确批准运行。','message':'仅准备本机文件运行方案，尚未请求Dify或模型。','workflow_runs':1,'max_remote_reads':2,'automatic_retry':False,'business_verified':False}
    if proof.context['data_flow']['schema_version']==4:row['note']='本次完整保留文件存在／缺失两条路径；按冻结输入预计选择其中一条，不删除另一条路径。缺失时预计跳过提取并返回所列说明，有文件时只向Dify传当前可信上传引用。本批无模型、HTTP或自定义代码，不上传、发布或创建应用；只读核对Key归属与同一发布配置后运行一次，不自动重试。预计路径只是静态推导，尚无原节点轨迹证明实际选路；不算客户业务验收。省略与显式null原样保留，空对象／空串不伪装成无文件。'
    if proof.context['data_flow']['schema_version'] in {5,6,7,8}:row['note']+=' 本次返回真正JSON对象，按所列完整Schema本机严格核对后采纳；不解析JSON文字、不补默认、不删字段或修复输出。最多64000字节、整数限±9007199254740991，不保证小数精度。Dify／供应商可能改写或修复Schema及输出，不证明原生严格遵守或业务值真实；不匹配记未知，不自动重跑。'
    if payload.case_id is not None:
     from .file_cases import bind
     row['file_case']=bind(h,task,proof,payload.case_id,payload.case_catalog_revision)
    if proof.context['data_flow']['schema_version'] in {6,8}:row['note']+=' 本次保留完整Sierra v1 Schema检查代码与原对象绑定；不合规由代码节点抛出错误使整次Workflow失败，不补默认或自动重试。完整发布图只是静态核对，不证明远端沙箱已经执行该代码或业务字段真实。'
    row['resource_token']=plan_token(row);h.store.put(KIND,row['id'],row);return public(row)
  @router.post('/api/tasks/{item_id}/file-runs/{plan_id}/execute')
  async def execute(item_id:str,plan_id:str,payload:Execute):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,payload.revision);gates(h,task);row=h.store.get(KIND,plan_id)
    if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该文件试跑方案。')
    if row['state']!='prepared' or row['attempts']!=0 or row['revision']!=task['revision'] or row['resource_token']!=payload.resource_token or plan_token(row)!=payload.resource_token or time.time()>row['expires_at']:raise HTTPException(409,'文件试跑方案已过期、改变或已使用，未重复派发。')
    if not payload.acknowledge_run:raise HTTPException(422,'请明确批准所列文件、输入、目标及一次运行影响。')
    if row.get('plan_schema_version') not in {4,5,6,7,8,9}:raise HTTPException(409,'这是旧版文件试跑方案，请重新准备并核对数据流；不会自动扩展旧授权。')
    if row.get('data_flow',{}).get('model_egress') and (not payload.acknowledge_model_egress or not payload.acknowledge_unpriced_model_cost):raise HTTPException(422,'本次会把提取文字和提示词发送给Dify中所选模型服务，且没有可靠费用预估；请分别明确同意数据出站与可能费用，不复用上传批准。')
    if row.get('data_flow',{}).get('join_policy') and not payload.acknowledge_join_policy:raise HTTPException(422,'请明确同意本次拼接格式、分隔符、数量、字节上限及空值／超限停止规则。')
    if row.get('plan_schema_version')==8 and (row.get('data_flow',{}).get('schema_version')!=7 or row.get('data_flow',{}).get('scenario')!='document_list_model_object' or not row.get('data_flow',{}).get('join_policy')):raise HTTPException(409,'多文件对象方案版本或拼接声明不完整，请重新准备。')
    if row.get('data_flow',{}).get('schema_version')==7 and row.get('plan_schema_version')!=8:raise HTTPException(409,'旧文件方案不能扩大到多文档对象输出。')
    if row.get('plan_schema_version')==9 and (row.get('data_flow',{}).get('schema_version')!=8 or row.get('data_flow',{}).get('scenario')!='document_list_model_guarded_object' or not row.get('data_flow',{}).get('strict_guard') or not row.get('data_flow',{}).get('join_policy')):raise HTTPException(409,'多文档拼接及Schema检查方案不完整，请重新准备。')
    if row.get('data_flow',{}).get('schema_version')==8 and row.get('plan_schema_version')!=9:raise HTTPException(409,'旧文件方案不能扩大到多文档拼接及Schema检查。')
    if row.get('plan_schema_version')==7 and (row.get('data_flow',{}).get('schema_version')!=6 or not row.get('data_flow',{}).get('strict_guard')):raise HTTPException(409,'文件Schema校验方案版本或完整声明不匹配，请重新准备。')
    if row.get('data_flow',{}).get('strict_guard') and row.get('plan_schema_version') not in {7,9}:raise HTTPException(409,'旧文件方案不能扩大到Schema检查代码。')
    if row.get('plan_schema_version') in {7,9} and not payload.acknowledge_strict_guard:raise HTTPException(422,'请明确同意完整Schema检查代码及非法对象使整次Workflow失败、不补默认或重试的行为。')
    if row.get('plan_schema_version')==5 and not payload.acknowledge_optional_branch:raise HTTPException(422,'请明确同意本次文件存在／缺失两条路径、当前输入状态与预计返回说明；不复用普通文件运行批准。')
    proof=FileProof(h,task,row['input'])
    if row.get('file_case') is not None:
     from .file_cases import check_frozen
     check_frozen(h,task,proof,row['file_case']);proof.case_snapshot=copy.deepcopy(row['file_case'])
    if any(row.get(k)!=v for k,v in proof.context.items()) or proof.file_digest!=row['file_binding_digest']:raise HTTPException(409,'方案的文件或连接已改变，未派发。')
    h.execution_limits.require_start(task)
    console=CredentialSnapshot(h.store,proof.env['id']);service=ServiceSnapshot(h.store,proof.env['id'])
    if not console.values.get('console_token') or service.stamp!=row['credential_stamp']:raise HTTPException(409,'原管理或运行凭据不可用，未派发。')
    row.update(state='verifying',attempts=1,strict_guard_approved=bool(row.get('plan_schema_version') in {7,9} and payload.acknowledge_strict_guard),optional_branch_approved=bool(row.get('plan_schema_version')==5 and payload.acknowledge_optional_branch),approved_at=h.now(),model_egress_approved=bool(row['data_flow']['model_egress'] and payload.acknowledge_model_egress),unpriced_model_cost_approved=bool(row['data_flow']['model_egress'] and payload.acknowledge_unpriced_model_cost),join_policy_approved=bool(row['data_flow'].get('join_policy') and payload.acknowledge_join_policy),updated_at=h.now(),message='正在只读核对Key归属与发布图，尚未运行。');h.store.put(KIND,plan_id,row)
   try:
    def check():
     with h.store.lock:
      if time.time()>row['expires_at']:raise HTTPException(409,'文件试跑批准已超过30分钟时效，未继续派发。')
      current=h.get_task(item_id);proof.check(h,current,row['input'])
      if not console.unchanged(h.store):raise HTTPException(409,'原管理凭据改变，未采用新连接继续。')
    async def verify():
     client=h.DifyClient(proof.env,console);check()
     keys=await client.request('GET',f"/console/api/apps/{row['app_id']}/api-keys",credential='console_token');check()
     entries=keys.get('data') if isinstance(keys,dict) else None
     if not isinstance(entries,list) or len(entries)>100 or any(not isinstance(k,dict) or not canonical(k.get('id')) or not isinstance(k.get('token'),str) for k in entries) or sum(hmac.compare_digest(k['token'].encode(),service.value.encode()) for k in entries)!=1:raise DifyError('管理接口未证明所选Service Key唯一归属于该App；未派发。')
     published=await client.published_workflow(row['app_id']);check();core=fingerprint(published.get('graph')) if isinstance(published,dict) else None
     try:config=configuration_digest(published)
     except ValueError:raise DifyError('发布配置不完整，未派发。') from None
     if not canonical(published.get('id')) or not core or core['digest']!=row['graph_digest'] or config!=row['configuration_digest']:raise DifyError('实际发布图或特性／变量与当前成果不一致，未派发；请在Dify核对发布。')
     return canonical(published['id'])
    published_id=await asyncio.wait_for(verify(),timeout=60)
    check()
    async def operation(task,env):
     with h.store.lock:
      row.update(run_id=task['runs'][-1]['id']);h.store.put(KIND,plan_id,row)
     try:check()
     except HTTPException:raise DifyError('派发前原上下文已变化，本次未请求文件运行。') from None
     with h.store.lock:
      row.update(state='executing',dispatched=True,published_workflow_id=published_id,updated_at=h.now(),message='已派发一次已批准文件工作流，不自动重试。');h.store.put(KIND,plan_id,row)
     try:result=await asyncio.wait_for(h.DifyClient(proof.env,service).run_workflow(proof.native),timeout=90)
     except DifyError as exc:
      status=exc.http_status if type(exc.http_status) is int and 400<=exc.http_status<=599 else None
      raise DifyError((f'文件运行接口返回HTTP {status}；' if status else '')+'文件试跑未返回可靠结果，结果可能未知；请核对原连接及文件有效性，不自动重试。',http_status=status) from None
     except BaseException:raise DifyError('文件试跑未返回可靠结果，结果可能未知；不自动重试。') from None
     failure=failed_receipt(result,published_id)
     if failure:
      row.update(observed_status=failure['data']['status'],workflow_run_id=failure['workflow_run_id'],observed_at=h.now())
      h.store.put(KIND,plan_id,row)
      raise DifyError('Dify明确返回文件工作流未成功结束；已保留可信运行编号，可主动读取原节点轨迹定位原因，不自动重试。',result=failure)
     data=result.get('data') if isinstance(result,dict) else None
     if not isinstance(data,dict) or data.get('workflow_id')!=published_id or data.get('status')!='succeeded' or not canonical(data.get('id')) or result.get('workflow_run_id')!=data['id']:raise DifyError('文件试跑未返回同一发布版本的明确成功终态，结果可能未知；不自动重试。')
     def reject_object_contract(error=None):
      from .file_output_reason import make
      declaration=proof.context['data_flow']['structured_output'];reason=make(declaration['schema'],declaration['schema_text'],error)
      row.update(output_contract_rejected=True,output_contract_reason=reason,observed_status='succeeded',workflow_run_id=data['id'],observed_at=h.now());h.store.put(KIND,plan_id,row)
      safe={'workflow_run_id':data['id'],'data':{'id':data['id'],'workflow_id':published_id,'status':'succeeded'}}
      raise DifyError('平台返回成功但文件模型对象不符合结束声明、完整Schema或本机边界，结果可能未知；原运行编号已保存，未保存不合规输出，不解析文字、补默认、删字段或自动重跑。 '+reason['message'],result=safe) from None
     outputs=data.get('outputs');resolution=proof.context['data_flow'].get('resolved_branch');end=next(n for n in proof.root['workflow']['graph']['nodes'] if n['id']==resolution['expected_end_node_id']) if resolution else next(n for n in proof.root['workflow']['graph']['nodes'] if n['data']['type']=='end')
     if not isinstance(outputs,dict) or set(outputs)!={v['variable'] for v in end['data']['outputs']}:
      if proof.context['data_flow']['output_kind']=='json-object':reject_object_contract('output_fields')
      raise DifyError('文件运行输出与当前结束声明不符，结果可能未知；未采纳原始回执。')
     array=proof.context['data_flow']['output_kind']=='text-array'
     if proof.context['data_flow']['output_kind']=='json-object':
      from .json_inputs import validate_value
      declaration=proof.context['data_flow']['structured_output']
      try:validate_value(declaration['schema'],outputs[declaration['output_variable']])
      except ValueError as exc:reject_object_contract(exc)
     elif any(not (isinstance(v,list) and len(v)==len(proof.files) and all(isinstance(x,str) for x in v)) if array else not isinstance(v,str) for v in outputs.values()):raise DifyError('文件提取未返回完整文字结果，结果可能未知；不跳过坏文件。')
     if resolution and resolution['expected_outputs'] is not None and outputs!=resolution['expected_outputs']:raise DifyError('文件缺失路径未返回本次冻结的明确说明，结果可能未知；不采纳为成功或自动重跑。')
     return {'workflow_run_id':data['id'],'data':{k:copy.deepcopy(v) for k,v in data.items() if k in {'id','workflow_id','status','outputs','elapsed_time','total_tokens','total_steps','created_at','finished_at'}}}
    value=await h.external_action(item_id,payload.revision,'run',operation,inputs=row['input'],runtime_context={'file_proof':proof})
    row.update(state='platform_finished',updated_at=h.now(),message=('Dify返回同发布版本成功终态，对象通过所列Schema本机核对；结果见普通运行记录，不等于客户业务通过。' if proof.context['data_flow']['output_kind']=='json-object' else 'Dify返回同发布版本的成功终态；提取结果见普通运行记录，不等于客户业务通过。'));h.store.put(KIND,plan_id,row)
    return {'plan':public(row),'task':value}
   except BaseException as exc:
    known_failure=row.get('observed_status') in {'failed','stopped','partial-succeeded'}
    row.update(state='platform_failed' if known_failure else 'unknown' if row.get('dispatched') else 'not_dispatched',updated_at=h.now(),message=('平台已返回成功终态，但对象输出不符合结束声明或完整Schema／本机边界，不能采纳；原运行编号已保存，可主动读取轨迹，不保存不合规输出或自动重跑。' if row.get('output_contract_rejected') is True else 'Dify明确返回未成功终态，可信运行编号已保存；请主动读取普通运行诊断，不自动重试。' if known_failure else '文件运行已派发但未可靠结束，请核对原运行记录；不重试。' if row.get('dispatched') else '文件方案未通过原上下文／Key归属／发布核对，未派发运行；不自动重试。')+(' '+row['output_contract_reason']['message'] if row.get('output_contract_rejected') is True and isinstance(row.get('output_contract_reason'),dict) else ''));h.store.put(KIND,plan_id,row)
    if isinstance(exc,DifyError) and not row.get('dispatched'):
     row['message']=str(exc);h.store.put(KIND,plan_id,row)
    if isinstance(exc,HTTPException):raise
    raise HTTPException(502,row['message']) from None
  h.app.include_router(router)
