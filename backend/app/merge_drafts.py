"""Local progress records; saving a draft never approves a preserved document."""
import copy,json,re
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt,Field


class ParallelDraft(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason:str=Field(max_length=2000)
    ack:StrictBool


class LoopDraft(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason:str=Field(max_length=2000)
    progress_variables:list[str]=Field(max_length=12)
    no_progress_limit:StrictInt=Field(ge=2,le=10)
    ack:StrictBool


class DraftRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    draft_revision:StrictInt
    reference_id:str
    document_token:str
    choices:dict[str,str]=Field(default_factory=dict)
    parallel_draft:dict[str,ParallelDraft]=Field(default_factory=dict)
    loop_draft:dict[str,LoopDraft]=Field(default_factory=dict)


class MergeDrafts:
    def __init__(self,h):self.h=h

    def state(self,task):
        record=self.h.store.get('merge_draft',task['id'])
        if not record:return {'record':None,'stale':False,'blocker':None,'draft_revision':0}
        error=None
        if record['revision']!=task['revision'] or record['reference_id']!=(task.get('dsl_reference') or {}).get('id'):error='合并草稿所属修订或实际文件引用已变化，仅可查看旧进度；请重新分析，不能沿用确认。'
        else:
            try:
                current=self.h.dsl_preview(task,record['choices'])
                if current['document_token']!=record['document_token']:error='最终文件或生成方案已变化，草稿只可参考；请重新核对当前连接、代码和条件。'
            except HTTPException as exc:error=str(exc.detail)
        return {'record':copy.deepcopy(record),'stale':bool(error),'blocker':error,'draft_revision':record['draft_revision']}

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/dsl-merge/draft')
        def read(item_id:str):
            with h.store.lock:return self.state(h.get_task(item_id))

        @h.app.put('/api/tasks/{item_id}/dsl-merge/draft')
        def save(item_id:str,payload:DraftRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
                old=h.store.get('merge_draft',item_id)
                if payload.draft_revision!=(old or {}).get('draft_revision',0):raise HTTPException(409,'合并草稿已被其他操作更新，请读取后处理，不能覆盖旧版本。')
                if payload.reference_id!=(task.get('dsl_reference') or {}).get('id'):raise HTTPException(409,'实际文件引用已变化，请重新分析后保存草稿。')
                preview=h.dsl_preview(task,payload.choices)
                if payload.document_token!=preview['document_token']:raise HTTPException(409,'当前最终文件与所编辑草稿的摘要不同，请重新分析；不会把旧声明当作已确认。')
                draft={key:value.model_dump() for key,value in payload.parallel_draft.items()}
                loop_draft={key:value.model_dump() for key,value in payload.loop_draft.items()}
                if set(draft)-{c['id'] for c in preview['parallel_candidates']}:raise HTTPException(422,'并行草稿只能引用当前文件的实际并行容器。')
                found={c['id']:c for c in preview['loop_candidates']}
                if set(loop_draft)-set(found):raise HTTPException(422,'循环草稿只能引用当前文件中的实际循环。')
                for nid,value in loop_draft.items():
                    labels=value['progress_variables']
                    if len(set(labels))!=len(labels) or set(labels)-set(found[nid]['variables']):raise HTTPException(422,'循环草稿进度字段须来自当前实际用户状态且唯一；未选完可留空，不猜测业务进度。')
                if len(json.dumps({'parallel':draft,'loop':loop_draft},ensure_ascii=False).encode())>64000:raise HTTPException(422,'容器保留草稿超过64000字节，请缩小范围。')
                if any(re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?i:Bearer)\s+[A-Za-z0-9_.-]{16,}',v['reason']) for v in [*draft.values(),*loop_draft.values()]):raise HTTPException(422,'草稿说明疑似包含明文凭据，请移除后保存；错误不回显其值。')
                record={'id':item_id,'revision':task['revision'],'draft_revision':payload.draft_revision+1,'reference_id':payload.reference_id,'document_token':payload.document_token,'choices':copy.deepcopy(payload.choices),'parallel_draft':draft,'loop_draft':loop_draft,'updated_at':h.now(),'verification':'unconfirmed_local_draft'}
                h.store.put('merge_draft',item_id,record)
                return self.state(task)
