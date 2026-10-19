"""Independent human review drafts, scoped to one model candidate; no adoption."""
import copy
from fastapi import HTTPException
from .material_text_drafts import SaveRequest,VersionRequest


def register(h):
    def owned(item_id,material_id,plan_id):
        task,material=h.image_previews.owned(item_id,material_id)
        record=h.image_executions.record(item_id,material_id,plan_id)
        if not record.get('candidate') or not record.get('candidate_token'):
            raise HTTPException(422,'当前图像记录没有可核对候选，不关联其他记录。')
        return task,material,record

    def state(task,material,plan,draft):
        record=copy.deepcopy(draft) if draft and draft.get('status')!='deleted' else None
        return {'draft_revision':draft['draft_revision'] if draft else 0,'record':record,
                'can_restore_text':bool(record and record['candidate_token']==plan['candidate_token'] and record['source_sha256']==material.get('sha256') and material.get('status')=='needs_input' and plan.get('status') in {'candidate_ready','paused_candidate'}),
                'revision_changed':bool(record and record['task_revision']!=task['revision']),
                'note':'仅保存对这次模型候选的人工修改；不采用正文、不进模型上下文、不确认来源、不调用模型。旧修订恢复只恢复文字，不能复用采用确认。'}

    @h.app.get('/api/tasks/{item_id}/materials/{material_id}/image-interpretation/{plan_id}/review-draft')
    def read(item_id:str,material_id:str,plan_id:str):
        with h.store.lock:
            task,material,plan=owned(item_id,material_id,plan_id)
            return state(task,material,plan,h.store.get('image_review_draft',plan_id))

    def write(item_id,material_id,plan_id,payload,remove=False):
        with h.store.lock:
            task,material,plan=owned(item_id,material_id,plan_id);h.require_idle(task);h.require_revision(task,payload.revision)
            old=h.store.get('image_review_draft',plan_id);current=old['draft_revision'] if old else 0
            if payload.draft_revision!=current:raise HTTPException(409,'候选审核草稿已被另一页面保存，输入保持；请只读刷新，不覆盖较新副本。')
            if material.get('sha256')!=payload.source_sha256 or plan['source']['sha256']!=payload.source_sha256:raise HTTPException(409,'候选原材料摘要变化，不能关联草稿到新来源。')
            if remove:
                if not old or old.get('status')=='deleted':return state(task,material,plan,old)
                value={**old,'draft_revision':current+1,'status':'deleted','text':None,'coverage_note':None,'updated_at':h.now()}
            else:
                if material.get('status')!='needs_input' or plan.get('status') not in {'candidate_ready','paused_candidate'}:raise HTTPException(422,'候选已采用或不再待核对，不保存新审核草稿。')
                if old and old.get('status')!='deleted' and all(old.get(k)==v for k,v in {'text':payload.text,'coverage_note':payload.coverage_note,'task_revision':task['revision'],'source_sha256':payload.source_sha256,'candidate_token':plan['candidate_token']}.items()):return state(task,material,plan,old)
                value={'id':plan_id,'plan_id':plan_id,'task_id':item_id,'material_id':material_id,'candidate_token':plan['candidate_token'],'draft_revision':current+1,'task_revision':task['revision'],'source_sha256':payload.source_sha256,'status':'unconfirmed','text':payload.text,'coverage_note':payload.coverage_note,'updated_at':h.now()}
            h.store.put('image_review_draft',plan_id,value)
            return state(task,material,plan,value)

    @h.app.put('/api/tasks/{item_id}/materials/{material_id}/image-interpretation/{plan_id}/review-draft')
    def save(item_id:str,material_id:str,plan_id:str,payload:SaveRequest):return write(item_id,material_id,plan_id,payload)
    @h.app.delete('/api/tasks/{item_id}/materials/{material_id}/image-interpretation/{plan_id}/review-draft')
    def discard(item_id:str,material_id:str,plan_id:str,payload:VersionRequest):return write(item_id,material_id,plan_id,payload,True)
