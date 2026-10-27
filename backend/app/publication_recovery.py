"""Explicit local recovery from operator-registered zero-dispatch evidence; never replay old writes."""
import copy,hashlib,hmac,json,time,uuid
from typing import Literal
from fastapi import APIRouter,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt,StrictStr,Field
from .dsl_roundtrip import digest,parse

EVIDENCE='publication_dispatch_evidence'
RECOVERY='publication_recovery'
NOTE='仅核对本机已提交报告与冻结回执的一致性，由登记操作者作事后证据声明；不是独立网络审计或平台当前状态证明。旧unknown保留，不重放旧请求；新发布仍须原入口重新核草稿/未发布状态并明确确认、遵守资源费用范围。'


def fail():raise HTTPException(409,'恢复依据不存在、已变更、过期、被占用或不适用于当前未知发布；原记录和保护锁保持。')
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def signed(h,value):
 value=copy.deepcopy(value);value.pop('seal',None);return value|{'seal':h.store.cipher.encrypt(canonical(value)).decode('ascii')}
def verified(h,value):
 try:
  if not isinstance(value,dict) or not isinstance(value.get('seal'),str) or len(value['seal'])>180000:fail()
  body={k:v for k,v in value.items() if k!='seal'}
  if not hmac.compare_digest(h.store.cipher.decrypt(value['seal'].encode('ascii')),canonical(body)):fail()
  return copy.deepcopy(value)
 except HTTPException:raise
 except Exception:fail()


def facts(h,task):
 try:return _facts(h,task)
 except (OSError,ValueError,TypeError,KeyError,UnicodeError):fail()

def _facts(h,task):
 from .workflow_publication import core,KIND
 if task.get('app_type')!='workflow' or not task.get('dify_app_id') or task.get('status')=='paused':fail()
 rows=[r for r in h.store.list(KIND) if r.get('app_id')==task['dify_app_id'] and r.get('environment_id')==task.get('environment_id') and r.get('write_attempted')]
 if len(rows)!=1:fail()
 row=rows[0]
 if row.get('task_id')!=task['id'] or row.get('revision')!=task['revision'] or row.get('state')!='unknown' or row.get('write_attempted') is not True:fail()
 env=h.environment(task);artifact=task.get('artifact') or {};path=h.artifact_path(task)
 raw=path.read_bytes();file_hash=hashlib.sha256(raw).hexdigest();graph=digest(core(parse(raw.decode('utf-8'),'workflow')['workflow']))
 old_binding=row.get('binding') or {}
 if artifact.get('revision')!=task['revision'] or artifact.get('sha256')!=file_hash or row.get('artifact_sha256')!=file_hash or row.get('graph_digest')!=graph or old_binding.get('environment')!=h.env_snapshot(env):fail()
 runs=[r for r in task.get('runs',[]) if r.get('kind')=='publish' and r.get('publication_id')==row['id']]
 if len(runs)!=1 or runs[0].get('status')!='unknown' or runs[0].get('write_attempted') is not True:fail()
 run=runs[0]
 if run.get('revision')!=task['revision'] or run.get('app_id')!=task['dify_app_id'] or run.get('environment_id')!=env['id']:fail()
 return {'task_id':task['id'],'revision':task['revision'],'app_id':task['dify_app_id'],'app_type':'workflow','environment_id':env['id'],'environment':h.env_snapshot(env),'artifact_sha256':file_hash,'graph_digest':graph,'pause_generation':task.get('pause_generation',0),'publication_id':row['id'],'publication_sha256':digest(row),'run_sha256':digest(run)}


def register_evidence(h,summary,actor,note):
 from .plan_drafts import inspect_text
 import re
 expected={'schema_version','task_id','revision','app_id','publication_id','environment_id','graph_digest','source_commit','report_path','report_sha256','batch_id','plan_sha256','manifest_sha256','approval_sha256','attempt_sha256','publish_dispatches'}
 if not isinstance(summary,dict) or set(summary)!=expected or summary.get('schema_version')!=1 or type(summary.get('publish_dispatches')) is not int or summary['publish_dispatches']!=0:fail()
 for key in ('graph_digest','report_sha256','plan_sha256','manifest_sha256','approval_sha256','attempt_sha256'):
  if not isinstance(summary.get(key),str) or not re.fullmatch('[0-9a-f]{64}',summary[key]):fail()
 if not re.fullmatch('[0-9a-f]{40}',summary.get('source_commit','')) or not re.fullmatch(r'docs/[A-Za-z0-9_/-]+[.]json',summary.get('report_path','')) or not re.fullmatch('[a-z0-9-]{1,100}',summary.get('batch_id','')):fail()
 if actor not in ('user','agent_delegated') or not isinstance(note,str) or not note.strip() or len(note)>1000:raise HTTPException(422,'请明确登记操作者和事后核对说明，不填写凭据。')
 inspect_text(note)
 with h.store.lock:
  task=h.get_task(summary['task_id']);h.require_idle(task);binding=facts(h,task)
  for key in ('revision','app_id','publication_id','graph_digest','environment_id'):
   if summary.get(key)!=binding[key]:fail()
  source=digest(summary)
  for old in h.store.list(EVIDENCE):
   if old.get('task_id')==task['id'] and old.get('source_sha256')==source:
    old=verified(h,old)
    if old.get('binding')!=binding:fail()
    return old,False
  value={'id':str(uuid.uuid4()),'task_id':task['id'],'revision':task['revision'],'app_id':binding['app_id'],'publication_id':binding['publication_id'],'binding':binding,'source':copy.deepcopy(summary),'source_sha256':source,'state':'registered','issuer':actor,'issuer_note':note,'created_at':h.now(),'verification':'local_committed_receipt_consistency_only'}
  row=signed(h,value);h.store.put(EVIDENCE,row['id'],row);return row,True


def matching_evidence(h,task,evidence_id):
 row=verified(h,h.store.get(EVIDENCE,evidence_id))
 if row.get('task_id')!=task['id'] or row.get('state')!='registered' or row.get('binding')!=facts(h,task):fail()
 return row


def require_recovery(h,task,recovery_id,publication_id):
 if not recovery_id or not publication_id:fail()
 row=verified(h,h.store.get(RECOVERY,recovery_id))
 if row.get('task_id')!=task['id'] or row.get('binding')!=facts(h,task) or row.get('expires_at',0)<=time.time():fail()
 evidence=matching_evidence(h,task,row['evidence_id'])
 if row.get('evidence_sha256')!=evidence['source_sha256'] or row.get('state') not in ('ready','reserved') or (row['state']=='reserved' and row.get('publication_proposal_id')!=publication_id):fail()
 return row


def reserve(h,task,recovery_id,publication_id):
 row=require_recovery(h,task,recovery_id,publication_id);row.update(state='reserved',publication_proposal_id=publication_id,reserved_at=h.now());return signed(h,row)
def consume(h,task,recovery_id,publication_id):
 row=require_recovery(h,task,recovery_id,publication_id)
 if row['state']!='reserved' or row.get('publication_proposal_id')!=publication_id:fail()
 row.update(state='consumed',consumed_at=h.now());return signed(h,row)


def public(h,row,task):
 try:
  value=verified(h,row)
  try:
   current=value.get('binding')==facts(h,task)
   if value.get('evidence_id'):
    evidence=matching_evidence(h,task,value['evidence_id']);current=current and evidence['source_sha256']==value['evidence_sha256']
  except HTTPException:current=False
  keys=('id','task_id','revision','app_id','publication_id','state','expires_at','created_at','confirmed_at','issuer','issuer_note','actor','actor_note','source_sha256','evidence_id','publication_proposal_id','verification','evidence_sha256')
  out={k:copy.deepcopy(value[k]) for k in keys if k in value}
  if value.get('source'):out['source']={k:copy.deepcopy(value['source'][k]) for k in ('source_commit','report_path','report_sha256','batch_id','plan_sha256','manifest_sha256','approval_sha256','attempt_sha256','publish_dispatches')}
  if value.get('state')=='prepared' and current:out['review_token']=digest({k:v for k,v in value.items() if k!='seal'})
  return out|{'current_source':current,'note':NOTE,'network_requested':False,'original_unknown_changed':False,'external_execution_authorized':False}
 except (HTTPException,OSError,ValueError,TypeError):
  return {'id':row.get('id') if isinstance(row,dict) else None,'state':'unusable','current_source':False,'note':'本机证据完整性或当前来源无法核对，未解除未知保护。','network_requested':False,'original_unknown_changed':False,'external_execution_authorized':False}

class RecoveryRoute(APIRoute):
 def get_route_handler(self):
  original=super().get_route_handler()
  async def handler(request):
   try:return await original(request)
   except RequestValidationError:return JSONResponse(status_code=422,content={'detail':'恢复请求须为有效修订/记录标识、真实布尔确认及明确操作者，不接受额外字段或明文凭据；未出站。'})
  return handler
class Prepare(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt
 evidence_id:StrictStr
class Confirm(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt
 recovery_id:StrictStr
 review_token:StrictStr
 acknowledge_no_dispatch:StrictBool
 acknowledge_new_attempt:StrictBool
 actor:Literal['user','agent_delegated']='user'
 actor_note:StrictStr=Field(min_length=1,max_length=1000)


def register(h):
 router=APIRouter(route_class=RecoveryRoute)
 @router.get('/api/tasks/{item_id}/publication-recovery')
 def history(item_id:str):
  with h.store.lock:
   task=h.get_task(item_id)
   return {'task_id':item_id,'revision':task['revision'],'app_id':task.get('dify_app_id'),'evidence':[public(h,r,task) for r in h.store.list(EVIDENCE) if r.get('task_id')==item_id][:20],'recoveries':[public(h,r,task) for r in h.store.list(RECOVERY) if r.get('task_id')==item_id][:20],'note':NOTE,'network_requested':False}
 @router.post('/api/tasks/{item_id}/publication-recovery/prepare')
 def prepare(item_id:str,payload:Prepare):
  with h.store.lock:
   task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);evidence=matching_evidence(h,task,payload.evidence_id);binding=facts(h,task)
   for old in h.store.list(RECOVERY):
    if old.get('task_id')!=item_id:continue
    old=verified(h,old)
    if old.get('binding')!=binding:continue
    if old.get('state') in ('prepared','ready') and old.get('expires_at',0)>time.time():return public(h,old,task)
    if old.get('state')=='reserved':
     pub=h.store.get('workflow_publication',old.get('publication_proposal_id'))
     if not pub or pub.get('write_attempted') or (pub.get('state')!='failed' and pub.get('expires_at',0)>time.time()):fail()
   row=signed(h,{'id':str(uuid.uuid4()),'task_id':item_id,'revision':task['revision'],'app_id':task['dify_app_id'],'publication_id':binding['publication_id'],'evidence_id':evidence['id'],'evidence_sha256':evidence['source_sha256'],'binding':binding,'state':'prepared','created_at':h.now(),'expires_at':time.time()+900})
   h.store.put(RECOVERY,row['id'],row);return public(h,row,task)
 @router.post('/api/tasks/{item_id}/publication-recovery/confirm')
 def confirm(item_id:str,payload:Confirm):
  from .plan_drafts import inspect_text
  if payload.acknowledge_no_dispatch is not True or payload.acknowledge_new_attempt is not True or not payload.actor_note.strip():raise HTTPException(422,'须分别确认原请求未派发和仅准备一次新的发布核对；不授予平台操作范围。')
  inspect_text(payload.actor_note)
  with h.store.lock:
   task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);row=verified(h,h.store.get(RECOVERY,payload.recovery_id))
   if row.get('state')!='prepared' or row.get('task_id')!=item_id or row.get('expires_at',0)<=time.time() or payload.review_token!=digest({k:v for k,v in row.items() if k!='seal'}):fail()
   evidence=matching_evidence(h,task,row['evidence_id'])
   if row['binding']!=facts(h,task) or row['evidence_sha256']!=evidence['source_sha256']:fail()
   row.update(state='ready',confirmed_at=h.now(),actor=payload.actor,actor_note=payload.actor_note)
   row=signed(h,row);h.store.put(RECOVERY,row['id'],row);return public(h,row,task)
 h.app.include_router(router)
