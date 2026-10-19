"""Encrypted local staging and explicitly approved single file uploads, no runs."""
import asyncio,base64,copy,hashlib,json,time,uuid
from pathlib import PurePosixPath
from fastapi import APIRouter,HTTPException,Request,Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field,ValidationError
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from .dsl_roundtrip import parse,validate_preserved
from .node_policy_audit import read_bytes
from .file_inputs import TYPES,validate as validate_file
from .conversation_inputs import credential_stamp,ServiceSnapshot
from .providers import checked_url
from .dify import DifyError
from .run_diagnostics import binding

class FileRoute(APIRoute):
 def get_route_handler(self):
  handler=super().get_route_handler()
  async def guarded(request):
   try:return await handler(request)
   except RequestValidationError:return JSONResponse(status_code=422,content={'detail':'文件操作方案的修订、批准标识或确认字段无效；未派发，不回显原请求。'})
  return guarded


KIND='runtime_file_upload'
MAX_BYTES=2_000_000
TTL=1800
USER='flowcraft-local'
MIMES={'.txt':'text/plain','.md':'text/markdown','.csv':'text/csv','.json':'application/json','.yaml':'application/yaml','.yml':'application/yaml','.pdf':'application/pdf','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
NOTE='只批准向所列Dify服务目标上传这一个原始文件一次；不创建／覆盖应用、不发布、不索引知识库、不运行工作流或调用模型。服务Key的真实App归属、远端发布配置和文件后续权限尚未在线证明，依实际连接核对。平台存储／扫描等策略可能有费用或留存，上传失败／未知不重试、不自动删除远端资源。切换页面或暂停任务不会撤回已派发上传。适配格式文档提取或模型处理须另行准备并批准文件试跑方案，本次上传不等于可试跑或业务通过。'
PUBLIC={'id','task_id','revision','environment_id','environment_url','environment_version','app_id','variable','input_kind','filename','size','mime_type','content_sha256','artifact_sha256','state','created_at','updated_at','expires_at','attempts','resource_token','message','note','platform_target_verified','runtime_reference_ready','business_verified','remote_upload_observed','automatic_retry','destination','user','upload_count','workflow_runs','model_calls','http_status','approved_at'}


def canonical(value):
 try:return str(uuid.UUID(value)) if isinstance(value,str) else None
 except (ValueError,TypeError,AttributeError):return None


def token(row):return hashlib.sha256(json.dumps({k:v for k,v in row.items() if k not in {'resource_token','state','updated_at','message','attempts','remote_upload_observed','remote_id','remote_created_by'}},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()


def public(row):return {k:copy.deepcopy(v) for k,v in row.items() if k in PUBLIC}


def unique(pairs):
 result={}
 for key,value in pairs:
  if key in result:raise ValueError('请求含重复键')
  result[key]=value
 return result


class Prepare(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 variable:StrictStr=Field(min_length=1,max_length=64)
 filename:StrictStr=Field(min_length=1,max_length=200)
 content_base64:StrictStr=Field(min_length=4,max_length=2_666_668)


class Approve(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 resource_token:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
 acknowledge_upload:StrictBool
 note:StrictStr=Field(min_length=1,max_length=2000)


def source(h,task):
 if task['app_type']!='workflow':raise HTTPException(422,'运行文件上传首批仅Workflow，不改变应用类型。')
 path=h.artifact_path(task)
 try:
  raw=read_bytes(path);root=parse(raw.decode('utf-8'),'workflow');checked=validate_preserved(root)
  if not checked['valid']:raise ValueError()
  nodes=root['workflow']['graph']['nodes']
  starts=[n for n in nodes if n['data'].get('type')=='start']
  if len(starts)!=1 or any(n['data'].get('type')=='trigger-schedule' for n in nodes):raise ValueError()
  variables=starts[0]['data'].get('variables',[])
  fields=[v for v in variables if isinstance(v,dict) and v.get('type') in TYPES]
  if any(validate_file(v) for v in fields):raise ValueError()
 except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):raise HTTPException(422,'当前最终Workflow的文件声明尚未完整适配；先核对成果和根开始节点，不猜旧计划或省略规则。') from None
 except OSError:raise HTTPException(503,'最终成果暂不可读，未准备或上传文件。') from None
 return {'artifact_sha256':hashlib.sha256(raw).hexdigest(),'fields':copy.deepcopy(fields)}


def target(h,task):
 env=h.environment(task)
 if env.get('version')!='1.17.1' or not canonical(task.get('dify_app_id')) or env.get('service_app_id')!=task['dify_app_id']:raise HTTPException(422,'先真实导入当前应用，并将环境的Service API Key应用ID登记为本次App；目标版本须1.17.1，不猜其他Key或应用。')
 try:url=checked_url(env['base_url'])
 except (ValueError,KeyError):raise HTTPException(422,'目标环境地址无效，未准备或上传。') from None
 stamp=credential_stamp(h.store,env['id'])
 if not stamp:raise HTTPException(422,'缺少应用Service API Key，先登记运行连接；准备阶段不解密。')
 return env,{'environment_id':env['id'],'environment_url':url.rstrip('/'),'environment_version':env['version'],'app_id':task['dify_app_id'],'credential_stamp':stamp,'environment_binding':binding(env)}


class RuntimeFiles:
 def __init__(self,host):self.h=host
 def busy(self,item_id):return any(r.get('task_id')==item_id and r.get('state')=='executing' for r in self.h.store.list(KIND))
 def recover(self):
  for row in self.h.store.list(KIND):
   if row.get('state')=='executing':
    row.update(state='unknown',updated_at=self.h.now(),message='上次上传中断，远端可能已有文件；保留单次尝试，不自动重试或删除。')
    self.h.store.put_with_secrets(KIND,row['id'],row,{'file_content':''})
 def register(self):
  h=self.h;router=APIRouter(route_class=FileRoute)
  @router.get('/api/tasks/{item_id}/runtime-files/source')
  def read_source(item_id:str,revision:int=Query(ge=1)):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,revision);value=source(h,task)
    return JSONResponse({**value,'task_id':item_id,'revision':revision,'max_bytes':MAX_BYTES,'extensions':list(MIMES),'verification':'local_file_declarations_only','runtime_reference_ready':False,'network_requested':False},headers={'Cache-Control':'no-store'})
  @router.get('/api/tasks/{item_id}/runtime-files')
  def history(item_id:str):
   with h.store.lock:
    task=h.get_task(item_id);rows=[r for r in h.store.list(KIND) if r.get('task_id')==item_id]
    return JSONResponse({'task_id':item_id,'revision':task['revision'],'records':[public(r) for r in rows[:50]],'total':len(rows),'history_truncated':len(rows)>50,'note':NOTE},headers={'Cache-Control':'no-store'})
  @router.post('/api/tasks/{item_id}/runtime-files/prepare')
  async def prepare(item_id:str,request:Request):
   raw=bytearray()
   async for chunk in request.stream():
    if len(raw)+len(chunk)>2_800_000:raise HTTPException(413,'文件准备请求过大，本批原文件最多2MB，不截断。')
    raw.extend(chunk)
   try:
    if request.headers.get('content-type','').split(';')[0].lower()!='application/json':raise ValueError()
    body=json.loads(raw,object_pairs_hook=unique);payload=Prepare.model_validate(body)
    if any(ord(c)<32 or c in '/\\' for c in payload.filename) or payload.filename.strip()!=payload.filename:raise ValueError()
    payload.filename.encode('utf-8')
    suffix=PurePosixPath(payload.filename).suffix.lower()
    if suffix not in MIMES:raise ValueError()
    content=base64.b64decode(payload.content_base64,validate=True)
    if not 1<=len(content)<=MAX_BYTES:raise ValueError()
   except (ValidationError,ValueError,TypeError,UnicodeError):raise HTTPException(422,'文件准备请求无效：只接受本批扩展名、1字节—2MB文件、无路径及控制字符的原文件名和明确变量／修订；不回显正文、不改名或转换内容。') from None
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task);frozen=source(h,task);env,bound=target(h,task)
    rows=[v for v in frozen['fields'] if v['variable']==payload.variable]
    if len(rows)!=1 or 'local_file' not in rows[0]['allowed_file_upload_methods'] or rows[0]['allowed_file_types']==['custom'] and suffix not in rows[0]['allowed_file_extensions']:raise HTTPException(422,'所选最终入口不允许此文件后缀或local_file方式，未改规则后上传。')
    if sum(r.get('state')=='prepared' for r in h.store.list(KIND) if r.get('task_id')==item_id)>=5:raise HTTPException(409,'本任务已有5份待处理文件方案，请先放弃旧本机暂存；不自动丢弃。')
    row={'id':str(uuid.uuid4()),'task_id':item_id,'revision':task['revision'],**bound,'artifact_sha256':frozen['artifact_sha256'],'variable':payload.variable,'input_kind':rows[0]['type'],'filename':payload.filename,'size':len(content),'mime_type':MIMES[suffix],'content_sha256':hashlib.sha256(content).hexdigest(),'state':'prepared','created_at':h.now(),'updated_at':h.now(),'expires_at':time.time()+TTL,'attempts':0,'message':'原文件仅加密暂存在本机；请核对目标与内容后明确批准单次上传。','note':NOTE,'platform_target_verified':False,'runtime_reference_ready':False,'business_verified':False,'remote_upload_observed':False,'automatic_retry':False,'destination':bound['environment_url']+'/v1/files/upload','user':USER,'upload_count':1,'workflow_runs':0,'model_calls':0}
    row['resource_token']=token(row)
    h.store.put_with_secrets(KIND,row['id'],row,{'file_content':payload.content_base64})
    return public(row)
  @router.post('/api/tasks/{item_id}/runtime-files/{upload_id}/discard')
  def discard(item_id:str,upload_id:str):
   with h.store.lock:
    h.get_task(item_id);row=h.store.get(KIND,upload_id)
    if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该文件方案。')
    if row['state']!='prepared' or row.get('attempts')!=0:raise HTTPException(409,'只可放弃未派发的本机暂存；不删除远端文件或改写历史。')
    row.update(state='discarded',updated_at=h.now(),message='已放弃未派发方案并清除本机加密正文，没有远端删除。');h.store.put_with_secrets(KIND,upload_id,row,{'file_content':''});return public(row)
  @router.post('/api/tasks/{item_id}/runtime-files/{upload_id}/execute')
  async def execute(item_id:str,upload_id:str,payload:Approve):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task);row=h.store.get(KIND,upload_id)
    if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该文件方案。')
    if row['state']!='prepared' or row.get('attempts')!=0:raise HTTPException(409,'该方案已派发或放弃，不重复上传。')
    if row['revision']!=task['revision'] or row['resource_token']!=payload.resource_token:raise HTTPException(409,'文件方案修订或批准标识已过期，未派发。')
    if not payload.acknowledge_upload or not payload.note.strip():raise HTTPException(422,'请核对原文件、完整目标及影响，并明确批准这一个文件的一次上传。')
    if time.time()>row['expires_at']:raise HTTPException(409,'本机上传方案已超过30分钟审批时效，请放弃后重新准备；不是远端文件有效期承诺。')
    env,bound=target(h,task);frozen=source(h,task)
    if row['resource_token']!=payload.resource_token or token(row)!=payload.resource_token or row['revision']!=task['revision'] or any(row.get(k)!=v for k,v in bound.items()) or frozen['artifact_sha256']!=row['artifact_sha256']:raise HTTPException(409,'文件、修订、成果或原运行连接已改变，未派发旧方案。')
    try:content=base64.b64decode(h.store.secret(upload_id,'file_content'),validate=True)
    except Exception:raise HTTPException(422,'本机加密暂存无法完整读取，未上传；不回显正文或解密错误。') from None
    if len(content)!=row['size'] or hashlib.sha256(content).hexdigest()!=row['content_sha256']:raise HTTPException(409,'暂存文件与批准哈希不同，未上传。')
    credentials=ServiceSnapshot(h.store,env['id'])
    if credentials.stamp!=row['credential_stamp']:raise HTTPException(409,'运行凭据已改变，未上传。')
    row.update(state='executing',attempts=1,approved_at=h.now(),updated_at=h.now(),message='已批准单次上传，正在等待回执；不并发重发。');h.store.put(KIND,upload_id,row)
   try:
    value=await asyncio.wait_for(h.DifyClient(copy.deepcopy(env),credentials).upload_runtime_file(row['filename'],content,row['mime_type']),timeout=90)
    rid=canonical(value.get('id')) if isinstance(value,dict) else None
    if not rid or value.get('name')!=row['filename'] or type(value.get('size')) is not int or value['size']!=row['size'] or not canonical(value.get('created_by')):raise DifyError('上传回执不完整，可能已有文件；不重复上传或采用伪引用。')
    with h.store.lock:
     row.update(remote_id=rid,remote_created_by=canonical(value['created_by']),remote_upload_observed=True);h.store.put(KIND,upload_id,row)
     current=h.get_task(item_id);_,now_bound=target(h,current);changed=current['revision']!=row['revision'] or now_bound!=bound or source(h,current)['artifact_sha256']!=row['artifact_sha256']
     row.update(remote_id=rid,remote_created_by=canonical(value['created_by']),remote_upload_observed=True,state='uploaded_stale' if changed else 'uploaded',updated_at=h.now(),message='已观察到文件上传回执，但原上下文已改变；保留旧目标记录，不能用于当前运行。' if changed else '已观察到单次上传回执；可另行准备文档提取或模型处理试跑方案，不等于已试跑或业务通过。')
     h.store.put_with_secrets(KIND,upload_id,row,{'file_content':''});return public(row)
   except BaseException as exc:
    status=exc.http_status if isinstance(exc,DifyError) and type(exc.http_status) is int else None
    if status is not None:row['http_status']=status
    row.update(state='unknown',updated_at=h.now(),message='单次上传未可靠完成或上下文改变，远端可能已有文件；本机正文已清除，不重试／不自动删除。')
    if status is not None:row['message']=f'Dify上传返回HTTP {status}；'+row['message']
    h.store.put_with_secrets(KIND,upload_id,row,{'file_content':''})
    if isinstance(exc,HTTPException):raise
    if isinstance(exc,(TimeoutError,asyncio.CancelledError)):raise HTTPException(504,row['message']) from None
    raise HTTPException(502,row['message']) from None
  h.app.include_router(router)
