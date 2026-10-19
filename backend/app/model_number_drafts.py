"""Local unconfirmed numeric text progress, separate from business configuration."""
import copy,re
from datetime import datetime
from fastapi import APIRouter,HTTPException,Path as ApiPath
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictStr,ValidationError,field_validator
from typing import Literal
from .agent_environment_mapping import MappingRoute
from .dsl_roundtrip import digest
from .model_parameters import validate_model_parameters
from .run_input_transport import validate as exact_json,AmbiguousInput

KIND='model_number_draft';HISTORY='model_number_draft_history';SAFE=9007199254740991


def numeric_text(text):
    if len(text)>2048 or re.fullmatch(r'[0-9eE+.\- ]*',text) is None:raise ValueError('数字草稿只保存2048字以内的数字符号与空格，不保存其他文字、凭据或多行内容。')
    return text


class NumberRoute(MappingRoute):
    field_error='数字草稿字段无效，请核对任务修订、草稿版本和数字文字；不回显输入，未修改配置。'
    def transport_error(self,exc):return str(exc).replace('试跑请求','数字草稿请求').replace('派发','保存草稿')


class ContextRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(gt=0,le=SAFE)
    model_context_json:StrictStr=Field(max_length=40000)


class SaveRequest(ContextRequest):
    draft_revision:StrictInt=Field(ge=0,le=SAFE)
    temperature_text:StrictStr=Field(max_length=2048)
    max_tokens_text:StrictStr=Field(max_length=2048)
    _texts=field_validator('temperature_text','max_tokens_text')(numeric_text)


class RestoreRequest(ContextRequest):
    source_draft_revision:StrictInt=Field(gt=0,le=SAFE)
    record_token:StrictStr=Field(pattern=r'^[0-9a-f]{64}$')


class Record(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:StrictStr
    task_id:StrictStr
    draft_revision:StrictInt=Field(gt=0,le=SAFE)
    task_revision:StrictInt=Field(gt=0,le=SAFE)
    model_context_token:StrictStr=Field(pattern=r'^[0-9a-f]{64}$')
    temperature_text:StrictStr=Field(max_length=2048)
    max_tokens_text:StrictStr=Field(max_length=2048)
    created_at:StrictStr=Field(max_length=64)
    verification:Literal['unconfirmed_model_number_text']
    _texts=field_validator('temperature_text','max_tokens_text')(numeric_text)

    @field_validator('created_at')
    @classmethod
    def timestamp(cls,text):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})',text) or datetime.fromisoformat(text.replace('Z','+00:00')).utcoffset() is None:raise ValueError('草稿时间格式无效。')
        return text


class ModelNumberDrafts:
    def __init__(self,h):self.h=h

    def context(self,task):
        h=self.h;cfg=task.get('configuration');env_id=task.get('environment_id');env=h.store.get('environment',env_id) if env_id else None
        try:
            if type(task.get('revision')) is not int or not 1<=task['revision']<=SAFE or not isinstance(cfg,dict) or not isinstance(cfg.get('dify_model_provider'),str) or not isinstance(cfg.get('dify_model'),str):raise ValueError()
            parameters=copy.deepcopy(cfg.get('model_parameters',{}));validate_model_parameters(parameters)
            return {'app_type':task['app_type'],'environment_id':env_id,'environment':{k:env.get(k) for k in ('base_url','version','connection_revision')} if isinstance(env,dict) else None,
                    'dify_model_provider':cfg['dify_model_provider'],'dify_model':cfg['dify_model'],'model_parameters':parameters}
        except (ValueError,KeyError,TypeError,OverflowError):raise HTTPException(422,'当前已存模型上下文无法完整核对，不能绑定数字草稿；原任务和文字保持。') from None

    def verify_context(self,task,payload):
        self.h.require_revision(task,payload.revision)
        try:client=exact_json(payload.model_context_json.encode('utf-8'));current=self.context(task);matches=digest(client)==digest(current)
        except (AmbiguousInput,ValueError,TypeError,UnicodeError,OverflowError):raise HTTPException(422,'模型上下文JSON无法完整核对，不回显输入或修改配置。') from None
        if not matches:raise HTTPException(409,'所选模型、环境或扩展参数与后台已存配置不同，请先保存有效模型配置再留存数字进度；本页文字保持。')
        return digest(current)

    def checked(self,record,task_id):
        try:value=Record.model_validate(record)
        except (ValidationError,ValueError,TypeError):raise HTTPException(409,'已存数字草稿结构异常，原记录保留，不读取或自动覆盖未知内容。') from None
        if value.id!=task_id or value.task_id!=task_id:raise HTTPException(409,'数字草稿归属异常，不读取或覆盖其他任务内容。')
        return value.model_dump()

    def current(self,task_id):
        record=self.h.store.get(KIND,task_id)
        if record is not None:return self.checked(record,task_id)
        prefix=task_id+':'
        with self.h.store.connect() as db:
            if db.execute('SELECT 1 FROM objects WHERE kind=? AND substr(id,1,?)=? LIMIT 1',(HISTORY,len(prefix),prefix)).fetchone():raise HTTPException(409,'数字草稿当前记录缺失但历史仍存在，不将版本重置为零或覆盖。')
        return None

    def state(self,task,chosen=None):
        current=self.current(task['id']);counter=current['draft_revision'] if current else 0;record=current if chosen is None else self.checked(chosen,task['id']);context_token=digest(self.context(task))
        if record and record['draft_revision']>counter:raise HTTPException(409,'数字草稿历史与当前版本不一致，不自动恢复。')
        stale=bool(record and (record['task_revision']!=task['revision'] or record['model_context_token']!=context_token))
        return {'task_id':task['id'],'revision':task['revision'],'draft_revision':counter,'model_context_token':context_token,
                'record':record,'record_token':digest(record) if record else None,'stale':stale,'restorable':bool(record and not stale),
                'blocker':'任务修订或已存模型／环境已变化，旧数字草稿只可参考，不沿用旧上下文恢复。' if stale else None,
                'configuration_applied':False,'task_modified':False,'note':'只保存两个数字的未确认文字，不保存其他未存配置；读取不覆盖本页，恢复仍须明确核对，不自动应用或确认。'}

    def register(self):
        h=self.h;router=APIRouter(route_class=NumberRoute)
        @router.get('/api/tasks/{item_id}/model-number-draft')
        def read(item_id:str):
            with h.store.lock:return self.state(h.get_task(item_id))

        @router.put('/api/tasks/{item_id}/model-number-draft')
        def save(item_id:str,payload:SaveRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);token=self.verify_context(task,payload);old=self.current(item_id);counter=old['draft_revision'] if old else 0
                if payload.draft_revision!=counter:raise HTTPException(409,'数字草稿已被其他操作更新，请先读取比较；不覆盖最新进度。')
                if old and old['task_revision']==task['revision'] and old['model_context_token']==token and old['temperature_text']==payload.temperature_text and old['max_tokens_text']==payload.max_tokens_text:return self.state(task)
                if counter>=SAFE:raise HTTPException(409,'数字草稿版本已超出可精确处理范围，不继续覆盖。')
                record={'id':item_id,'task_id':item_id,'draft_revision':counter+1,'task_revision':task['revision'],'model_context_token':token,
                        'temperature_text':payload.temperature_text,'max_tokens_text':payload.max_tokens_text,'created_at':h.now(),'verification':'unconfirmed_model_number_text'}
                self.checked(record,item_id);rows=[]
                if old:
                    key=item_id+':'+str(counter);prior=h.store.get(HISTORY,key)
                    if prior is not None and digest(prior)!=digest(old):raise HTTPException(409,'数字草稿旧版本历史冲突，不覆盖原历史。')
                    if prior is None:rows.append((HISTORY,key,old))
                rows.append((KIND,item_id,record));h.store.put_many(rows)
                return self.state(task)

        @router.get('/api/tasks/{item_id}/model-number-draft/history/{draft_revision}')
        def history(item_id:str,draft_revision:int=ApiPath(gt=0,le=SAFE)):
            with h.store.lock:
                task=h.get_task(item_id);record=h.store.get(HISTORY,item_id+':'+str(draft_revision))
                if record is None:raise HTTPException(404,'没有当前任务的该数字草稿历史。')
                checked=self.checked(record,item_id)
                if checked['draft_revision']!=draft_revision:raise HTTPException(409,'数字草稿历史版本不一致，不读取未知记录。')
                return {**self.state(task,checked),'historical':True}

        @router.post('/api/tasks/{item_id}/model-number-draft/restore-preview')
        def restore(item_id:str,payload:RestoreRequest):
            with h.store.lock:
                task=h.get_task(item_id);self.verify_context(task,payload);current=self.current(item_id)
                record=current if current and current['draft_revision']==payload.source_draft_revision else h.store.get(HISTORY,item_id+':'+str(payload.source_draft_revision))
                if record is None:raise HTTPException(404,'该数字草稿已不可读取，不猜测或生成替代文字。')
                state=self.state(task,record)
                if not state['restorable'] or state['record_token']!=payload.record_token or state['record']['draft_revision']!=payload.source_draft_revision:raise HTTPException(409,'数字草稿或上下文已变化，不能恢复旧预览；原文字保持。')
                return {'task_id':item_id,'revision':task['revision'],'source_draft_revision':payload.source_draft_revision,'record_token':payload.record_token,
                        'temperature_text':state['record']['temperature_text'],'max_tokens_text':state['record']['max_tokens_text'],'configuration_applied':False,'task_modified':False}
        h.app.include_router(router)
