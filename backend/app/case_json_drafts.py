"""Independent case JSON text checkpoints; never adopt or execute them."""
import copy,hmac
from fastapi import APIRouter,HTTPException,Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
from .case_json_editor import describe,LIMIT
from .plan_drafts import inspect_text

KIND='case_json_draft'
MAX_SAFE=9007199254740991
NOTE='仅保存独立未确认文字副本，不保证JSON完整或可采用；不进入正式样例或模型上下文，不改变任务、确认、预算或运行。恢复须主动放入编辑框，旧来源仅作参考，正式保存仍须当前来源及样例校验。'

def safe_text(text):
    try:
        size,_=inspect_text(text)
        return size
    except HTTPException:
        raise HTTPException(422,'样例JSON草稿须为非空、2MB范围内可完整核对的安全文字；超限、坏编码或疑似凭据未保存，不回显原文。') from None

class Version(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1,le=MAX_SAFE)
    draft_revision:StrictInt=Field(ge=0,le=MAX_SAFE)

class Save(Version):
    source_token:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    text:StrictStr=Field(max_length=LIMIT)

class DraftRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:response=await original(request)
            except RequestValidationError:return JSONResponse(status_code=422,content={'detail':'样例JSON草稿请求须明确当前修订、草稿版本及所需来源，不接受未知字段；未回显输入。'},headers={'Cache-Control':'no-store'})
            response.headers['Cache-Control']='no-store';return response
        return guarded

def register(h):
    router=APIRouter(route_class=DraftRoute)
    def stored(task):
        value=h.store.get(KIND,task['id'])
        if value is not None and (not isinstance(value,dict) or value.get('id')!=task['id'] or type(value.get('draft_revision'))is not int or not 0<=value['draft_revision']<=MAX_SAFE):raise HTTPException(422,'已保存草稿身份或版本无法完整核对，未当作没有草稿。')
        return value
    def state(task,value):
        record=copy.deepcopy(value) if value and value.get('text') is not None else None
        if record:
            if not isinstance(record.get('text'),str) or record.get('verification')!='unconfirmed_case_json_text':raise HTTPException(422,'已保存草稿结构无法完整核对，未载入或修改。')
            safe_text(record['text'])
        try:token=describe(task)['source_token']
        except HTTPException:token=None
        current=bool(record and record.get('source_token')==token and record.get('revision')==task['revision'] and record.get('app_type')==task['app_type'])
        return {'schema_version':1,'task_id':task['id'],'revision':task['revision'],'app_type':task['app_type'],'draft_revision':value['draft_revision'] if value else 0,'record':record,'stale':bool(record and not current),'source_current':current,
                'task_changed':False,'model_called':False,'network_requested':False,'business_verified':False,'note':NOTE}
    def check(item_id,payload):
        task=h.get_task(item_id);h.require_revision(task,payload.revision);old=stored(task)
        if (old['draft_revision'] if old else 0)!=payload.draft_revision:raise HTTPException(409,'已保存JSON草稿版本变化，本页文字保持；请读取最新副本核对，不覆盖或自动重试。')
        if payload.draft_revision>=MAX_SAFE:raise HTTPException(409,'草稿版本计数已到当前完整核对上限，原副本保持，未写入。')
        return task,old
    @router.get('/api/tasks/{item_id}/test-cases/draft')
    def read(item_id:str,revision:int=Query(ge=1)):
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision);return state(task,stored(task))
    @router.put('/api/tasks/{item_id}/test-cases/draft')
    def save(item_id:str,payload:Save):
        size=safe_text(payload.text)
        with h.store.lock:
            task,old=check(item_id,payload)
            if not hmac.compare_digest(describe(task)['source_token'],payload.source_token):raise HTTPException(409,'正式样例保存来源变化，未把草稿关联到新来源；本页文字保持。')
            if old and old.get('text')==payload.text and old.get('source_token')==payload.source_token and old.get('revision')==task['revision']:return state(task,old)
            value={'id':item_id,'revision':task['revision'],'app_type':task['app_type'],'draft_revision':payload.draft_revision+1,'source_token':payload.source_token,'text':payload.text,'byte_count':size,'updated_at':h.now(),'verification':'unconfirmed_case_json_text'}
            h.store.put(KIND,item_id,value);return state(task,value)
    @router.delete('/api/tasks/{item_id}/test-cases/draft')
    def discard(item_id:str,payload:Version):
        with h.store.lock:
            task,old=check(item_id,payload)
            if old and old.get('text') is None:return state(task,old)
            value={'id':item_id,'revision':task['revision'],'app_type':task['app_type'],'draft_revision':payload.draft_revision+1,'text':None,'updated_at':h.now(),'verification':'discarded_case_json_text'}
            h.store.put(KIND,item_id,value);return state(task,value)
    h.app.include_router(router)
