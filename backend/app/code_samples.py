"""Explicit local pure-Python sample preparation and single-use container execution."""
import asyncio,copy,hashlib,json,re,time,uuid
from fastapi import APIRouter,HTTPException,Request
from . import code_sample_docker as docker
from .code_sample_policy import validate_code,parse_inputs,output_matches
from .code_entry_contract import check as entry_check
KIND='code_sample'
TYPES={'string','number','boolean','object','array[string]','array[number]','array[boolean]','array[object]'}
NOTE='仅本机受限纯计算样例：固定已安装镜像、无网络或宿主文件挂载、非root/只读及资源时限；不读取真实上游、不调用Dify/模型、不改变原任务确认或平台成绩。不是目标Sandbox或完整业务验收。'

def busy(store,task_id=None):return any(r.get('state')=='executing' and (task_id is None or r.get('task_id')==task_id) for r in store.list(KIND))
def text_sha(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def fingerprint(task):return docker.digest({'id':task['id'],'revision':task['revision'],'app_type':task['app_type'],'plan':task.get('workflow_plan'),'reference':task.get('dsl_reference')})

def source(h,task_id,node_id,revision,*,idle=True):
 task=h.get_task(task_id);h.require_revision(task,revision)
 if idle:h.require_idle(task)
 if task.get('status')=='paused':raise HTTPException(409,'任务已暂停，请先核对并明确恢复，未执行样例。')
 if task['app_type']!='workflow' or task.get('dsl_reference') is not None or task.get('plan_stale') or not isinstance(task.get('workflow_plan'),dict):raise HTTPException(422,'本批只支持当前已保存、未过期的显式Workflow根Python节点；引用DSL、其他类型或嵌套节点未适配。')
 rows=[n for n in task['workflow_plan'].get('nodes',[]) if n.get('id')==node_id]
 if len(rows)!=1 or rows[0].get('type')!='code':raise HTTPException(422,'请明确选择唯一根代码节点，不进入容器内部或其他节点。')
 cfg=rows[0].get('config')
 if not isinstance(cfg,dict):raise HTTPException(422,'根代码节点配置无效，未执行。')
 if cfg.get('code_language')!='python3':raise HTTPException(422,'本机受限样例仅支持Python同步纯计算，JavaScript不自动转换。')
 try:
  validate_code(cfg.get('code'));variables=cfg.get('variables')
  if not isinstance(variables,list) or any(not isinstance(v,dict) or not isinstance(v.get('variable'),str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',v['variable']) for v in variables):raise ValueError('节点输入别名不完整。')
  names=[v['variable'] for v in variables];errors,warnings=entry_check(cfg['code'],names)
  if errors or warnings:raise ValueError('Python同步main入口无法明确绑定全部参数，不执行动态或不确定入口。')
  outputs=cfg.get('outputs')
  if not isinstance(outputs,dict) or not outputs or any(not isinstance(k,str) or not k or not isinstance(v,dict) or v.get('type') not in TYPES or set(v)-{'type','children'} or v.get('children') is not None for k,v in outputs.items()):raise ValueError('本批输出声明仅支持明确JSON文字/数字/布尔/对象及其数组。')
 except (ValueError,TypeError,UnicodeError,RecursionError) as exc:raise HTTPException(422,str(exc) if isinstance(exc,ValueError) else '代码声明无法核对，未执行。') from None
 return task,copy.deepcopy(cfg),names

async def body(request,fields):
 try:
  if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':raise ValueError()
  chunks=[];size=0
  async for chunk in request.stream():
   size+=len(chunk)
   if size>140000:raise ValueError()
   chunks.append(chunk)
  raw=b''.join(chunks)
  def unique(pairs):
   out={}
   for key,value in pairs:
    if key in out:raise ValueError()
    out[key]=value
   return out
  value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
  if not isinstance(value,dict) or set(value)!=set(fields) or type(value.get('revision'))is not int or not 0<value['revision']<=9007199254740991:raise ValueError()
  if any(not isinstance(value.get(k),str) or not value[k] for k in fields if k not in ('revision','acknowledge_limits')):raise ValueError()
  return value
 except (ValueError,TypeError,UnicodeError,RecursionError):raise HTTPException(422,'本机样例请求格式或大小无效，未回显代码和输入，也未派发容器。') from None

def inputs(text,names):
 try:
  value=parse_inputs(text)
  if set(value)!=set(names):raise ValueError('JSON键必须与此节点全部输入别名一致，不自动取上游或补值。')
  return value
 except (ValueError,TypeError,UnicodeError,RecursionError):raise HTTPException(422,'样例须为64KB内无重复键/非有限数/数值损失的完整JSON对象，键与节点输入别名一致；未派发。') from None

def public(row):
 fields=('id','task_id','revision','node_id','state','created_at','expires_at','source_sha256','code_sha256','input_sha256','input_text_sha256','review_token','image_id','profile','limits','result','started_at','completed_at','phase','create_dispatches','start_dispatches','source_current_at_return')
 return {k:copy.deepcopy(row[k]) for k in fields if k in row}|{'schema_version':1,'verification':'local_sample_only','dify_sandbox_verified':False,'business_verified':False,'task_changed':False,'note':NOTE}

def register(h):
 router=APIRouter()
 @router.get('/api/tasks/{item_id}/code-samples')
 def history(item_id:str):
  h.get_task(item_id);return {'records':[public(r) for r in h.store.list(KIND) if r.get('task_id')==item_id][:10],'note':NOTE}
 @router.post('/api/tasks/{item_id}/code-samples/prepare')
 async def prepare(item_id:str,request:Request):
  value=await body(request,('revision','node_id','input_text'))
  with h.store.lock:
   if busy(h.store):raise HTTPException(409,'已有本机隔离样例执行中，请等待原回执，不并行派发。')
   task,cfg,names=source(h,item_id,value['node_id'],value['revision']);stamp=fingerprint(task);sample=inputs(value['input_text'],names)
  def ready():
   with docker.LocalDocker() as client:return client.ready()
  try:runtime=await asyncio.to_thread(ready)
  except docker.DockerProblem:raise HTTPException(503,'本机Docker引擎、默认seccomp或固定已安装镜像尚不可核实；不联网拉镜像或退回宿主执行。') from None
  with h.store.lock:
   latest,_,_=source(h,item_id,value['node_id'],value['revision'])
   if fingerprint(latest)!=stamp:raise HTTPException(409,'准备期间保存来源已变化，未返回执行方案。')
   row={'id':str(uuid.uuid4()),'task_id':item_id,'revision':task['revision'],'node_id':value['node_id'],'state':'prepared','created_at':h.now(),'expires_at':time.time()+900,'source_sha256':stamp,'code_sha256':text_sha(cfg['code']),'input_sha256':docker.digest(sample),'input_text_sha256':text_sha(value['input_text']),'image_id':runtime['image_id'],'profile':runtime['profile'],'limits':runtime['limits'],'worker_sha256':text_sha(docker.worker_source()),'create_dispatches':0,'start_dispatches':0}
   row['review_token']=docker.digest(row);h.store.put(KIND,row['id'],row);return public(row)
 @router.post('/api/tasks/{item_id}/code-samples/execute')
 async def execute(item_id:str,request:Request):
  value=await body(request,('revision','proposal_id','review_token','input_text','acknowledge_limits'))
  if value['acknowledge_limits'] is not True:raise HTTPException(422,'请核对本机隔离、资源/时间范围及非目标平台验证边界。')
  with h.store.lock:
   row=h.store.get(KIND,value['proposal_id'])
   if not row or row.get('task_id')!=item_id or row.get('revision')!=value['revision'] or row.get('state')!='prepared' or row.get('review_token')!=value['review_token'] or row.get('expires_at',0)<time.time():raise HTTPException(409,'本机样例方案已使用、过期或归属不符，未重复执行。')
   if busy(h.store):raise HTTPException(409,'已有本机样例执行中，不并发派发。')
   task,cfg,names=source(h,item_id,row['node_id'],value['revision']);sample=inputs(value['input_text'],names)
   if row['source_sha256']!=fingerprint(task) or row['code_sha256']!=text_sha(cfg['code']) or row['input_sha256']!=docker.digest(sample) or row['input_text_sha256']!=text_sha(value['input_text']) or row['worker_sha256']!=text_sha(docker.worker_source()) or row['image_id']!=docker.IMAGE or row['profile']!=docker.PROFILE or row['limits']!=docker.LIMITS:raise HTTPException(409,'代码、样例原文或执行边界已变化，请重新准备，不采用旧确认。')
   row.update(state='executing',phase='admitted',started_at=h.now());h.store.put(KIND,row['id'],row)
  def progress(**fields):
   with h.store.lock:
    current=h.store.get(KIND,row['id'])
    if current and current.get('state')=='executing':current.update(fields);h.store.put(KIND,row['id'],current)
  try:
   result=await asyncio.to_thread(docker.execute,cfg['code'],sample,row['id'],progress)
   if result.get('status')=='returned':
    try:output=parse_inputs(result['output_json']);matched=output_matches(output,cfg['outputs'])
    except (ValueError,TypeError,UnicodeError,RecursionError):matched=False
    result['status']='passed' if matched else 'output_mismatch'
    if not matched:result['error_category']='output_contract_mismatch'
   state='passed' if result.get('status')=='passed' else 'unknown' if result.get('status')=='unknown' else 'failed'
  except BaseException as exc:
   result={'status':'unknown','error_category':'execution_interrupted','cleanup_verified':False};state='unknown'
   if not isinstance(exc,Exception):
    with h.store.lock:
     current=h.store.get(KIND,row['id']);current.update(state=state,result=result,completed_at=h.now());h.store.put(KIND,row['id'],current)
    raise
  with h.store.lock:
   current=h.store.get(KIND,row['id']);latest=h.get_task(item_id)
   if current.get('state')!='executing':raise HTTPException(409,'原样例执行状态已变化，请核对保存的旧回执，不重发。')
   current.update(state=state,result=result,completed_at=h.now(),source_current_at_return=latest.get('status')!='paused' and fingerprint(latest)==row['source_sha256']);h.store.put(KIND,row['id'],current)
   return public(current)
 def recover():
  with h.store.lock:
   for row in h.store.list(KIND):
    if row.get('state')=='executing':row.update(state='unknown',result={'status':'unknown','error_category':'process_interrupted','cleanup_verified':False},completed_at=h.now());h.store.put(KIND,row['id'],row)
 h.code_samples_recover=recover;h.app.include_router(router)
