"""New tasks choose a reviewable graph before configuration/build; no silent fallback."""
import copy,hashlib,json
from uuid import UUID
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,Field
from .plan_drafts import DraftRoute,inspect_text
from .plan_text_codec import render

NOTE='这是基础线性草稿：开始→可选知识检索→一个LLM→输出。需求只写进提示词，不自动展开无命中分支、循环、批量、接口、审批或失败处理；不代表这些要求已经实现。若需要上述行为，请使用模型规划或编辑完整流程，不能为通过校验而省略需求。'

def needed(task):
    return task.get('plan_review_required') is True and task.get('app_type') in {'workflow','advanced-chat'} and not task.get('workflow_plan') and not task.get('dsl_reference')

def require(task):
    if needed(task):raise HTTPException(422,'请先在流程页生成、核对并保存完整流程；当前没有显式计划，不能用基础线性模板代替业务分支。仅需线性步骤时可明确准备基础草稿，核对后保存。')

def linear_plan(task):
    from .dsl import compile_dsl
    from .dsl_roundtrip import parse
    from .workflow_plan import validate_plan
    if task.get('app_type') not in {'workflow','advanced-chat'}:raise ValueError('基础线性草稿仅适用于Workflow／Chatflow，不更改应用类型。')
    if task.get('workflow_plan') or task.get('dsl_reference') or task.get('artifact') or task.get('dify_app_id'):raise ValueError('已有流程、来源DSL或成果，请保留当前内容；不会准备替代草稿覆盖。')
    content,validation=compile_dsl(task)
    if not validation['valid']:raise ValueError('当前配置无法准备完整线性草稿，请先核对模型、知识库与参数。')
    root=parse(content,task['app_type']);graph=root['workflow']['graph'];nodes=[]
    for node in graph['nodes']:
        data=node['data'];kind=data['type']
        if kind=='start':cfg={'variables':copy.deepcopy(data['variables'])}
        elif kind=='llm':
            cfg={'system_prompt':next(p['text'] for p in data['prompt_template'] if p['role']=='system'),'user_prompt':next(p['text'] for p in data['prompt_template'] if p['role']=='user')}
            if data['context']['enabled']:cfg['context_variable_selector']=copy.deepcopy(data['context']['variable_selector'])
        elif kind=='knowledge-retrieval':
            # Explicit graph; model and retrieval choices continue to inherit current task configuration.
            cfg={'dataset_source':'task','query_variable_selector':copy.deepcopy(data['query_variable_selector'])}
        elif kind=='end':cfg={'outputs':copy.deepcopy(data['outputs'])}
        elif kind=='answer':cfg={'answer':data['answer']}
        else:raise ValueError('基础模板出现未适配节点，未生成部分草稿。')
        nodes.append({'id':node['id'],'type':kind,'title':data['title'],'config':cfg})
    plan={'schema_version':1,'nodes':nodes,'edges':[{'source':e['source'],'target':e['target']} for e in graph['edges']]}
    result=validate_plan(task,plan)
    if not result['valid']:raise ValueError('当前完整线性草稿未通过结构检查，请使用完整规划或核对配置；未保存部分内容。')
    text=render(plan);inspect_text(text)
    return plan,text

def register(h):
    class Preview(BaseModel):
        model_config=ConfigDict(extra='forbid')
        revision:StrictInt=Field(ge=1)
        request_nonce:UUID
    router=APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/linear-plan-preview')
    def preview(item_id:str,payload:Preview):
        with h.store.lock:
            task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
            try:plan,text=linear_plan(task)
            except (ValueError,KeyError,TypeError,StopIteration,UnicodeError,OverflowError,RecursionError):raise HTTPException(422,'无法完整准备基础线性草稿，请核对当前模型、配置及来源；已有内容保持，不回显输入或降级。') from None
            return {'task_id':item_id,'revision':task['revision'],'app_type':task['app_type'],'request_nonce':str(payload.request_nonce),'plan_text':text,
                    'preview_token':hashlib.sha256(json.dumps({'revision':task['revision'],'requirements':task['requirements'],'configuration':task['configuration'],'plan':plan},ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
                    'note':NOTE,'verification':'local_linear_template_preview','task_changed':False,'model_called':False,'network_requested':False,'business_verified':False}
    h.app.include_router(router)
