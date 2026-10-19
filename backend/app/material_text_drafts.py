"""Independent, unconfirmed text drafts with monotonic CAS and source binding."""
import copy,re
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field

NOTE='草稿仅绑定登记的材料摘要，未核对原文件内容或业务覆盖，不进入模型上下文；正式采用仍需原文件及人工来源确认。'


class VersionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    draft_revision:StrictInt=Field(ge=0)
    source_sha256:StrictStr=Field(pattern=r'^[0-9a-f]{64}$')


class SaveRequest(VersionRequest):
    text:StrictStr=Field(max_length=100000)
    coverage_note:StrictStr=Field(max_length=2000)


class MaterialTextDrafts:
    def __init__(self,host):self.h=host

    def owned(self,item_id,material_id):
        task=self.h.get_task(item_id)
        material=next((m for m in task['materials'] if m['id']==material_id),None)
        if not material:raise HTTPException(404,'当前任务没有这份材料，未读取或写入其他任务的草稿。')
        return task,material

    def key(self,item_id,material_id):return f'{item_id}:{material_id}'

    def state(self,task,material,value):
        record=copy.deepcopy(value) if value and value.get('status')!='deleted' else None
        sha=material.get('sha256');known=isinstance(sha,str) and re.fullmatch(r'[0-9a-f]{64}',sha) is not None
        return {'draft_revision':value['draft_revision'] if value else 0,'record':record,
                'can_restore_text':bool(record and known and record['source_sha256']==sha and material.get('status')=='needs_input'),
                'revision_changed':bool(record and record['task_revision']!=task['revision']),
                'note':NOTE}

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/materials/{material_id}/text-draft')
        def read(item_id:str,material_id:str):
            with h.store.lock:
                task,material=self.owned(item_id,material_id)
                return self.state(task,material,h.store.get('material_text_draft',self.key(item_id,material_id)))

        def write(item_id,material_id,payload,remove=False):
            with h.store.lock:
                task,material=self.owned(item_id,material_id);h.require_idle(task);h.require_revision(task,payload.revision)
                key=self.key(item_id,material_id);old=h.store.get('material_text_draft',key)
                current=old['draft_revision'] if old else 0
                if payload.draft_revision!=current:raise HTTPException(409,'保存草稿版本已变化，当前输入保持；请只读刷新后明确处理，不覆盖新副本。')
                if material.get('sha256')!=payload.source_sha256:raise HTTPException(409,'登记原材料摘要已变化，不能把草稿关联到新来源。')
                if remove:
                    if not old or old.get('status')=='deleted':return self.state(task,material,old)
                    value={'id':key,'task_id':item_id,'material_id':material_id,'draft_revision':current+1,'task_revision':task['revision'],'source_sha256':payload.source_sha256,'status':'deleted','text':None,'coverage_note':None,'updated_at':h.now()}
                else:
                    if material.get('status')!='needs_input':raise HTTPException(422,'材料已有可用正文或不处于待补充状态，未覆盖原材料或保存新草稿。')
                    if old and old.get('status')!='deleted' and old['text']==payload.text and old['coverage_note']==payload.coverage_note and old['source_sha256']==payload.source_sha256 and old['task_revision']==task['revision']:
                        return self.state(task,material,old)
                    value={'id':key,'task_id':item_id,'material_id':material_id,'draft_revision':current+1,'task_revision':task['revision'],'source_sha256':payload.source_sha256,'status':'unconfirmed','text':payload.text,'coverage_note':payload.coverage_note,'updated_at':h.now()}
                h.store.put('material_text_draft',key,value)
                return self.state(task,material,value)

        @h.app.put('/api/tasks/{item_id}/materials/{material_id}/text-draft')
        def save(item_id:str,material_id:str,payload:SaveRequest):return write(item_id,material_id,payload)
        @h.app.delete('/api/tasks/{item_id}/materials/{material_id}/text-draft')
        def discard(item_id:str,material_id:str,payload:VersionRequest):return write(item_id,material_id,payload,True)
