"""Revision-bound local mapping inputs/history; never adopts or writes a Dify app."""
import copy,json,re,sqlite3
from datetime import datetime
from typing import Literal
from fastapi import APIRouter,HTTPException,Path as ApiPath
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictStr,ValidationError,field_validator
from .workflow_environment_mapping import WorkflowMappingRequest,WorkflowMappingRoute,target_model
from .dsl_roundtrip import digest

KIND='workflow_mapping_draft';HISTORY='workflow_mapping_draft_history';SAFE=9007199254740991;MAX_BYTES=8_000_000


class SaveRequest(WorkflowMappingRequest):
    draft_revision:StrictInt=Field(ge=0,lt=SAFE)
    preview_token:StrictStr=Field(pattern='^[0-9a-f]{64}$')


class Record(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:StrictStr=Field(max_length=100)
    task_id:StrictStr=Field(max_length=100)
    app_type:Literal['workflow','advanced-chat']
    draft_revision:StrictInt=Field(gt=0,le=SAFE)
    source_revision:StrictInt=Field(gt=0,le=SAFE)
    payload:WorkflowMappingRequest
    payload_token:StrictStr=Field(pattern='^[0-9a-f]{64}$')
    preview_token:StrictStr=Field(pattern='^[0-9a-f]{64}$')
    target_document_token:StrictStr=Field(pattern='^[0-9a-f]{64}$')
    target_context_token:StrictStr=Field(pattern='^[0-9a-f]{64}$')
    created_at:StrictStr=Field(max_length=64)
    verification:Literal['unconfirmed_workflow_mapping_inputs']

    @field_validator('created_at')
    @classmethod
    def timestamp(cls,text):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})',text) or datetime.fromisoformat(text.replace('Z','+00:00')).utcoffset() is None:raise ValueError('保存时间无效。')
        return text


def safe_payload(payload):
    value=payload.model_dump();raw=json.dumps(value,ensure_ascii=False)
    if re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?i:Bearer\s+[A-Za-z0-9_.-]{16,})',raw):raise ValueError('映射输入疑似含明文凭据，未保存；请仅填写资源标识和用途。')
    for text in value['node_models_json'].values():target_model(text)
    return value


class WorkflowMappingDrafts:
    def __init__(self,h):self.h=h

    def record(self,kind,key,task_id):
        with self.h.store.connect() as db:
            row=db.execute('SELECT CASE WHEN length(CAST(value AS BLOB))<=? THEN value ELSE NULL END FROM objects WHERE kind=? AND id=?',(MAX_BYTES,kind,key)).fetchone()
        if row is None:return None
        if row[0] is None:raise HTTPException(409,'已存流程映射进度过大，未截断读取或覆盖。')
        try:
            raw=json.loads(row[0]);value=Record.model_validate(raw)
            safe_payload(value.payload)
            if value.id!=task_id or value.task_id!=task_id or value.source_revision!=value.payload.revision or digest(raw['payload'])!=value.payload_token:raise ValueError('bad_owner_or_digest')
            # Added default request fields must not rewrite the identity of an old saved input.
            result=value.model_dump();result['payload']=copy.deepcopy(raw['payload']);return result
        except (ValidationError,ValueError,TypeError,OverflowError,UnicodeError):raise HTTPException(409,'已存流程映射结构、归属或摘要异常，原记录保持；不回显或自动覆盖。') from None

    def current(self,task):
        record=self.record(KIND,task['id'],task['id'])
        if record is None:
            prefix=task['id']+':'
            with self.h.store.connect() as db:
                orphan=db.execute('SELECT 1 FROM objects WHERE kind=? AND substr(id,1,?)=? LIMIT 1',(HISTORY,len(prefix),prefix)).fetchone()
            if orphan:raise HTTPException(409,'存在流程映射历史但当前进度缺失，不能按版本0覆盖；请先核对原记录。')
        return record

    def state(self,task,chosen=None):
        if task['app_type'] not in {'workflow','advanced-chat'}:raise HTTPException(422,'流程映射进度只属于Workflow/Chatflow，不转换应用类型。')
        current=self.current(task);counter=current['draft_revision'] if current else 0;record=current if chosen is None else chosen
        result={'draft_revision':counter,'record':copy.deepcopy(record),'stale':False,'blocker':None,'restorable':False,'restore_inputs':None,'confirmed':False,'can_apply':False,'can_download':False,
                'note':'仅保存完整候选的输入与摘要，不保存旧输出DSL；任务、凭据与审批不变。恢复只填本页，旧勾选与目标容器复核不沿用，须按当前来源和目标重新预览。'}
        if record is None:return result
        try:
            if record['app_type']!=task['app_type']:raise HTTPException(409,'已存输入的应用类型与当前任务不同，不能恢复或转换。')
            payload=WorkflowMappingRequest.model_validate(record['payload'])
            preview=self.h.workflow_environment_mapping.prepare(task,payload,require_idle=False)
            if any(preview[key]!=record[stored] for key,stored in (('preview_token','preview_token'),('document_token','target_document_token'),('target_context_token','target_context_token'))):raise HTTPException(409,'来源、目标环境或完整候选已变化，旧输入只可参考；请重新填写并预览。')
            restore=copy.deepcopy(record['payload']);restore.update(acknowledge_unverified_target=False,acknowledge_retained_external_settings=False,acknowledge_dependency_consolidation=False,target_document_token=None,target_parallel_reviews={},target_loop_reviews={})
            result.update(restorable=True,restore_inputs=restore)
        except HTTPException as exc:result.update(stale=True,blocker=str(exc.detail))
        except (ValidationError,ValueError,KeyError,TypeError,AttributeError,OverflowError):result.update(stale=True,blocker='已存输入不能按当前完整来源重新核对，仅供参考，不自动恢复。')
        return result

    def register(self):
        h=self.h;router=APIRouter(route_class=WorkflowMappingRoute)
        @router.get('/api/tasks/{item_id}/workflow-environment-mapping/draft')
        def read(item_id:str):
            with h.store.lock:return self.state(h.get_task(item_id))

        @router.put('/api/tasks/{item_id}/workflow-environment-mapping/draft')
        def save(item_id:str,payload:SaveRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
                old=self.current(task);counter=old['draft_revision'] if old else 0
                if counter!=payload.draft_revision:raise HTTPException(409,'流程映射进度已被其他操作更新，请读取核对；不会覆盖已存版本。')
                preview=h.workflow_environment_mapping.prepare(task,payload)
                if preview['preview_token']!=payload.preview_token:raise HTTPException(409,'完整流程映射候选已变化，请重新预览后保存。')
                try:inputs=safe_payload(WorkflowMappingRequest.model_validate(payload.model_dump(include=set(WorkflowMappingRequest.model_fields))))
                except (ValidationError,ValueError,UnicodeError,OverflowError):raise HTTPException(422,'映射输入无法安全完整保存，请核对完整模型JSON和说明，不填写凭据；不回显输入。') from None
                if 'acknowledge_dependency_consolidation' not in payload.model_fields_set:inputs.pop('acknowledge_dependency_consolidation',None)
                token=digest(inputs)
                logical_token=digest(safe_payload(WorkflowMappingRequest.model_validate(inputs)))
                if old and digest(safe_payload(WorkflowMappingRequest.model_validate(old['payload'])))==logical_token and old['preview_token']==payload.preview_token:return self.state(task)
                record=Record(id=item_id,task_id=item_id,app_type=task['app_type'],draft_revision=counter+1,source_revision=task['revision'],payload=inputs,payload_token=token,
                    preview_token=preview['preview_token'],target_document_token=preview['document_token'],target_context_token=preview['target_context_token'],created_at=h.now(),verification='unconfirmed_workflow_mapping_inputs').model_dump()
                record['payload']=inputs
                if len(json.dumps(record,ensure_ascii=False).encode('utf-8'))>MAX_BYTES:raise HTTPException(422,'完整流程映射输入超出8MB保存上限，未截断或部分保存。')
                rows=[]
                if old:
                    key=item_id+':'+str(counter);existing=self.record(HISTORY,key,item_id)
                    if existing is not None and digest(existing)!=digest(old):raise HTTPException(409,'对应旧历史内容冲突，不覆盖历史或当前进度。')
                    if existing is None:rows.append((HISTORY,key,old))
                rows.append((KIND,item_id,record))
                try:h.store.put_many(rows)
                except sqlite3.Error:raise HTTPException(503,'本机流程映射进度保存未提交，原版本保持；请核对本机存储后主动继续。') from None
                return self.state(task)

        @router.get('/api/tasks/{item_id}/workflow-environment-mapping/draft/history/{draft_revision}')
        def history(item_id:str,draft_revision:int=ApiPath(gt=0,le=SAFE)):
            with h.store.lock:
                task=h.get_task(item_id);record=self.record(HISTORY,item_id+':'+str(draft_revision),item_id)
                if record is None:raise HTTPException(404,'没有属于当前任务的该流程映射历史版本。')
                if record['draft_revision']!=draft_revision:raise HTTPException(409,'历史键与流程映射版本不一致，原记录保持。')
                return {**self.state(task,record),'historical':True}
        h.app.include_router(router)
