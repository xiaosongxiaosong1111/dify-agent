"""Explicit local adoption of the exact reviewed native model, no external actions."""
import copy,uuid
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
from .dsl_roundtrip import digest


class ModelAdoptionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(gt=0)
    reference_id:str=Field(min_length=1,max_length=100)
    merge_token:str=Field(pattern=r'^[0-9a-f]{64}$')
    document_token:str=Field(pattern=r'^[0-9a-f]{64}$')
    draft_revision:StrictInt=Field(ge=0)
    choices:dict[str,str]=Field(default_factory=dict,max_length=1000)
    acknowledge_pending_resource_review:StrictBool=False


class AgentModelAdoption:
    def __init__(self,h):self.h=h

    def register(self):
        h=self.h
        @h.app.post('/api/tasks/{item_id}/dsl-merge/model-configuration')
        def adopt(item_id:str,payload:ModelAdoptionRequest):
            with h.store.lock:
                task=copy.deepcopy(h.get_task(item_id));h.require_idle(task);h.require_revision(task,payload.revision)
                if task['app_type']!='agent':raise HTTPException(422,'此入口只采用原生Agent预览模型，不转换应用类型。')
                if payload.acknowledge_pending_resource_review is not True:raise HTTPException(422,'请明确确认采用完整预览模型参数，并知悉目标环境可用性与费用仍需核对；此操作不是资源批准。')
                saved=h.store.get('merge_draft',item_id)
                if payload.draft_revision!=(saved or {}).get('draft_revision',0):raise HTTPException(409,'已存合并草稿已更新，请读取核对后再采用模型配置，不覆盖其他进度。')
                preview=h.dsl_preview(task,payload.choices)
                if preview['reference_id']!=payload.reference_id or preview['merge_token']!=payload.merge_token or preview['document_token']!=payload.document_token:
                    raise HTTPException(409,'来源、生成方案或最终预览已变化，请重新分析并核对模型。')
                if preview['unresolved']:raise HTTPException(422,'仍有冲突未明确选择，不能猜测要采用哪一套模型。')
                if payload.choices:
                    if not saved or saved.get('revision')!=task['revision'] or saved.get('reference_id')!=payload.reference_id or saved.get('document_token')!=payload.document_token or digest(saved.get('choices'))!=digest(payload.choices):
                        raise HTTPException(422,'请先保存本次冲突选择为合并草稿，再采用模型；已存草稿会保留为历史参考，新修订仍须重新分析。')
                comparison=preview.get('agent_model_comparison')
                if not comparison or comparison.get('available') is not True:
                    raise HTTPException(422,'当前没有不同且可完整表达的预览模型，不生成部分配置或重复采用。')
                configuration=copy.deepcopy(comparison['current_configuration'])
                previous_revision=task['revision']
                h.invalidate(task,'明确采用预览模型配置前保存',preserve_requirements=True)
                # Whole model_parameters mapping replaces the prior model extras.
                task['configuration'].update(configuration)
                task.setdefault('model_configuration_adoptions',[]).append({
                    'id':str(uuid.uuid4()),'revision':task['revision'],'previous_revision':previous_revision,
                    'reference_id':payload.reference_id,'document_token':payload.document_token,
                    'configuration_sha256':digest(configuration),'choices':copy.deepcopy(payload.choices),
                    'source':'merged_dsl_preview_model','verification':'local_configuration_only',
                    'pending_resource_review':True,'created_at':h.now()})
                task['messages'].append({'role':'assistant','source':'system','content':
                    '已按你的明确选择，将合并预览中的完整模型参数采用到本机任务配置。'+
                    '原DSL引用、历史与已存冲突选择仍保留；本次推进修订，旧保留方案、配置确认、产物和运行证据不能沿用。'+
                    '请重新分析保留方案，并核对目标模型可用性、资源说明与费用后再确认配置；其他未适配功能仍须处理。',
                    'created_at':h.now()})
                return h.save_task(task)
