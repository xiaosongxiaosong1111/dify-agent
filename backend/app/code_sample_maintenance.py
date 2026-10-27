"""Explicit ownership-bound local sample resource maintenance; never executes sample code."""
import asyncio,copy,re,time,uuid
from fastapi import APIRouter,HTTPException,Request
from . import code_sample_docker as d
from .code_samples import KIND as SAMPLE,body,public as sample_public
KIND='code_sample_cleanup'
NOTE='仅核对/停止并移除同Task原样例UUID标签、名称、固定镜像及预览容器ID对应的本机临时资源；不执行代码、不新建资源、不调用Dify/模型，原执行未知和成绩保持。'

def original(h,task_id,sample_id):
 try:
  if str(uuid.UUID(sample_id))!=sample_id:raise ValueError()
 except (ValueError,TypeError):raise HTTPException(422,'样例归属标识无效。') from None
 row=h.store.get(SAMPLE,sample_id)
 if not row or row.get('task_id')!=task_id:raise HTTPException(404,'当前任务没有此本机样例回执。')
 if row.get('state') not in ('passed','failed','unknown'):raise HTTPException(409,'此样例尚未结束或未派发，请等待原回执，不并发维护。')
 if row.get('image_id')!=d.IMAGE or row.get('profile')!=d.PROFILE:raise HTTPException(422,'旧样例镜像/隔离版本未适配，不能猜测归属后删除。')
 return row

def resource(client,operation):
 rc,out,_=client.call('ps','-aq','--filter','name=^/sierra-code-'+operation+'$')
 if rc:raise d.DockerProblem('resource_query_unknown')
 ids=out.decode().split()
 if not ids:return None
 if len(ids)!=1 or not re.fullmatch('[0-9a-f]{12,64}',ids[0]):raise d.DockerProblem('resource_identity_unknown')
 value=client.inspect(ids[0])
 if not client.owned(value,operation) or not re.fullmatch('[0-9a-f]{64}',value.get('id','')):raise d.DockerProblem('resource_owner_mismatch')
 return {k:value.get(k) for k in ('id','name','image','state')}|{'operation_id':operation,'profile':d.PROFILE}

def review(row):
 return {k:copy.deepcopy(row[k]) for k in ('id','task_id','revision','sample_id','sample_revision','node_id','state','resource','review_token','expires_at','result','completed_at') if k in row}|{'verification':'local_sample_resource_only','task_changed':False,'execution_result_changed':False,'code_executed':False,'note':NOTE}

def register(h):
 router=APIRouter()
 @router.get('/api/tasks/{item_id}/code-sample-maintenance')
 def history(item_id:str):
  task=h.get_task(item_id);rows=[r for r in h.store.list(SAMPLE) if r.get('task_id')==item_id][:20]
  samples=[{k:copy.deepcopy(r[k]) for k in ('id','task_id','revision','node_id','state','created_at','completed_at','last_cleanup') if k in r}|{'original_cleanup_verified':(r.get('result') or {}).get('cleanup_verified') is True} for r in rows]
  return {'schema_version':1,'task_id':item_id,'current_revision':task['revision'],'samples':samples,'maintenance':[review(r) for r in h.store.list(KIND) if r.get('task_id')==item_id][:20],'note':NOTE}
 @router.post('/api/tasks/{item_id}/code-sample-maintenance/prepare')
 async def prepare(item_id:str,request:Request):
  value=await body(request,('revision','sample_id'))
  with h.store.lock:
   task=h.get_task(item_id);h.require_revision(task,value['revision']);h.require_idle(task);sample=original(h,item_id,value['sample_id']);stamp=d.digest(sample)
  def inspect():
   with d.LocalDocker() as client:return resource(client,sample['id'])
  try:target=await asyncio.to_thread(inspect)
  except (d.DockerProblem,UnicodeError):raise HTTPException(503,'本机资源缺失/归属或引擎状态无法核实，未准备删除，不据失败查询当作不存在。') from None
  with h.store.lock:
   task=h.get_task(item_id);h.require_revision(task,value['revision']);h.require_idle(task)
   if d.digest(original(h,item_id,sample['id']))!=stamp:raise HTTPException(409,'原样例回执已变化，请重新只读核对，未准备清理。')
   row={'id':str(uuid.uuid4()),'task_id':item_id,'revision':task['revision'],'sample_id':sample['id'],'sample_revision':sample['revision'],'node_id':sample['node_id'],'sample_sha256':stamp,'resource':target,'state':'prepared','created_at':h.now(),'expires_at':time.time()+900}
   row['review_token']=d.digest(row);h.store.put(KIND,row['id'],row);return review(row)
 @router.post('/api/tasks/{item_id}/code-sample-maintenance/confirm')
 async def confirm(item_id:str,request:Request):
  value=await body(request,('revision','proposal_id','review_token','acknowledge_cleanup'))
  if value['acknowledge_cleanup'] is not True:raise HTTPException(422,'请明确确认仅维护这份回执的本机资源，原执行结果保持。')
  with h.store.lock:
   task=h.get_task(item_id);h.require_revision(task,value['revision']);h.require_idle(task);row=h.store.get(KIND,value['proposal_id'])
   if not row or row.get('task_id')!=item_id or row.get('revision')!=value['revision'] or row.get('state')!='prepared' or row.get('review_token')!=value['review_token'] or row.get('expires_at',0)<time.time():raise HTTPException(409,'维护方案已使用、过期或归属不符，未重复派发。')
   if d.digest(original(h,item_id,row['sample_id']))!=row['sample_sha256']:raise HTTPException(409,'原样例状态已变化，旧维护确认失效。')
   row.update(state='executing',started_at=h.now());h.store.put(KIND,row['id'],row)
  def clean():
   with d.LocalDocker() as client:
    current=resource(client,row['sample_id']);prior=row['resource']
    if current is None:return {'status':'verified_absent','verified':True,'removed':False}
    if prior is None or current['id']!=prior['id']:return {'status':'resource_changed','verified':False,'removed':False}
    rc,_,_=client.call('rm','--force',current['id'])
    if rc:return {'status':'removal_unknown','verified':False,'removed':False}
    after=resource(client,row['sample_id'])
    return {'status':'removed' if after is None else 'removal_unknown','verified':after is None,'removed':after is None}
  try:result=await asyncio.to_thread(clean)
  except BaseException as exc:
   result={'status':'maintenance_interrupted','verified':False,'removed':False}
   if not isinstance(exc,Exception):
    with h.store.lock:
     row.update(state='unknown',result=result,completed_at=h.now());h.store.put(KIND,row['id'],row)
    raise
  with h.store.lock:
   saved=h.store.get(KIND,row['id'])
   if saved.get('state')!='executing':raise HTTPException(409,'维护状态已变化，请读取原回执，不重复删除。')
   saved.update(state='verified' if result['verified'] else 'unknown',result=result,completed_at=h.now());h.store.put(KIND,row['id'],saved)
   sample=h.store.get(SAMPLE,row['sample_id']);sample['last_cleanup']={'id':row['id'],'verified':result['verified'],'status':result['status'],'completed_at':saved['completed_at']};h.store.put(SAMPLE,sample['id'],sample)
   return review(saved)
 def recover():
  with h.store.lock:
   for row in h.store.list(KIND):
    if row.get('state')=='executing':row.update(state='unknown',result={'status':'process_interrupted','verified':False,'removed':False},completed_at=h.now());h.store.put(KIND,row['id'],row)
 h.code_sample_maintenance_recover=recover;h.app.include_router(router)
