"""Unconfirmed local editing progress, separate from adopted plans and fees."""
import copy,json,re
from fastapi import HTTPException,APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
from .dsl import _contains_secret_key

LIMIT=2_000_000
_SECRET=re.compile(r'\b(?:sk-|app-|dataset-)[A-Za-z0-9_-]{12,}\b|(?i:Bearer)\s+[A-Za-z0-9_.-]{16,}')
_ASSIGNMENT=re.compile(r'''(?i)(?<![\w-])(?:["']?(?:api[_-]?key|authorization|password|(?:access[_-]?|auth[_-]?)?token|secret(?:[_-]?key)?|private[_-]?key)["']?\s*[:=]\s*)(?:["'][^"']+["']|[A-Za-z0-9_-]{8,})''')

class DraftRoute(APIRoute):
 def get_route_handler(self):
  original=super().get_route_handler()
  async def guarded(request):
   try:return await original(request)
   except RequestValidationError as exc:
    # Default validation errors echo input, and invalid Unicode can even make
    # the default JSON error renderer fail. Keep this policy route-local.
    messages=[]
    for error in exc.errors():
     field=(error.get('loc') or [None])[-1];kind=error.get('type')
     if field=='text' and kind=='string_unicode':message='text 包含非法 Unicode，请修正文字。'
     elif field=='text':message='text 必须是最多 2 MB 的文字。'
     elif field=='revision':message='revision 须为至少 1 的整数，不能是布尔值。'
     elif field=='draft_revision':message='draft_revision 须为非负整数，不能是布尔值。'
     else:message='请求结构或字段无效，请按流程草稿接口格式填写。'
     messages.append(message)
    return JSONResponse(status_code=422,content={'detail':'流程草稿请求无效：'+' '.join(dict.fromkeys(messages))})
  return guarded

class DraftVersion(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 draft_revision:StrictInt=Field(ge=0)

class SaveDraft(DraftVersion):
 text:StrictStr=Field(max_length=LIMIT)

def inspect_text(text):
 try:size=len(text.encode('utf-8'))
 except UnicodeError:raise HTTPException(422,'草稿包含非法 Unicode，未保存；请修正文字。') from None
 if not text.strip() or size>LIMIT:raise HTTPException(422,'流程草稿须为非空、最多 2 MB 的文字；丢弃请使用明确的丢弃操作。')
 # Scan escaped forms without changing the stored text, including partial JSON.
 scanned=re.sub(r'\\u([0-9a-fA-F]{4})',lambda m:chr(int(m.group(1),16)),text).replace('\\"','"').replace("\\'","'")
 if _SECRET.search(scanned) or _ASSIGNMENT.search(scanned):raise HTTPException(422,'流程草稿疑似包含明文凭据，未保存；请使用无密钥配置或 Dify 秘密变量，错误不回显原文。')
 try:
  def no_constant(value):raise ValueError()
  def unique(pairs):
   result={}
   for key,value in pairs:
    if key in result:raise ValueError()
    result[key]=value
   return result
  parsed=json.loads(text,parse_constant=no_constant,object_pairs_hook=unique)
 except (ValueError,RecursionError):return size,'incomplete_or_invalid'
 # A valid JSON document still must not hide credentials behind escapes.
 budget=[40000]
 def scan(value,depth=0):
  budget[0]-=1
  if budget[0]<0 or depth>60:raise HTTPException(422,'流程草稿超过结构检查上限，未保存；请缩小本次编辑范围。')
  if isinstance(value,str) and (_SECRET.search(value) or _ASSIGNMENT.search(value)):raise HTTPException(422,'流程草稿疑似包含明文凭据，未保存；错误不回显原文。')
  if isinstance(value,dict):
   for child in value.values():scan(child,depth+1)
  elif isinstance(value,list):
   for child in value:scan(child,depth+1)
 scan(parsed)
 if _contains_secret_key(parsed):raise HTTPException(422,'流程草稿含凭据字段，未保存；错误不回显原文。')
 return size,'json_object' if isinstance(parsed,dict) else 'json_non_object'

class PlanDrafts:
 def __init__(self,h):self.h=h
 def state(self,task):
  stored=self.h.store.get('plan_draft',task['id'])
  record=stored if stored and stored.get('text') is not None else None
  stale=bool(record and (record.get('revision')!=task['revision'] or record.get('app_type')!=task['app_type']))
  return {'record':copy.deepcopy(record),'draft_revision':(stored or {}).get('draft_revision',0),'stale':stale,
          'blocker':'草稿来自旧修订或不同应用类型，仅作参考；只能主动载入为未确认编辑，不能沿用旧确认或验证。' if stale else None}
 def register(self):
  h=self.h
  router=APIRouter(route_class=DraftRoute)
  @router.get('/api/tasks/{item_id}/plan-draft')
  def read(item_id:str):
   with h.store.lock:return self.state(h.get_task(item_id))
  def check(item_id,payload):
   task=h.get_task(item_id);h.require_revision(task,payload.revision)
   old=h.store.get('plan_draft',item_id)
   if payload.draft_revision!=(old or {}).get('draft_revision',0):raise HTTPException(409,'流程草稿已被其他操作更新，未覆盖；请读取最新草稿再决定，不自动合并或重试。')
   return task
  @router.put('/api/tasks/{item_id}/plan-draft')
  def save(item_id:str,payload:SaveDraft):
   size,state=inspect_text(payload.text)
   with h.store.lock:
    task=check(item_id,payload)
    record={'id':item_id,'revision':task['revision'],'draft_revision':payload.draft_revision+1,'app_type':task['app_type'],'text':payload.text,'byte_count':size,'json_state':state,'updated_at':h.now(),'verification':'unconfirmed_local_draft'}
    h.store.put('plan_draft',item_id,record);return self.state(task)
  @router.delete('/api/tasks/{item_id}/plan-draft')
  def discard(item_id:str,payload:DraftVersion):
   with h.store.lock:
    task=check(item_id,payload)
    # Keep a tombstone counter; an old tab cannot recreate version zero.
    h.store.put('plan_draft',item_id,{'id':item_id,'revision':task['revision'],'draft_revision':payload.draft_revision+1,'app_type':task['app_type'],'text':None,'updated_at':h.now(),'verification':'discarded_local_draft'})
    return self.state(task)
  h.app.include_router(router)
