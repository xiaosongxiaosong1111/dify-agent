"""Read-only draft versus saved plan comparison, without compiling or adopting."""
import hashlib,json
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
from .plan_drafts import DraftRoute
from .plan_text_codec import parse,unique
from .version_restore import equal,canonical
from .version_node_changes import compare

FIELDS={'schema_version':'方案格式版本','nodes':'顶层节点','edges':'顶层连接','instruction':'Agent指令','instructions':'Agent指令','system_prompt':'Agent提示词','model':'模型选择','model_parameters':'模型参数','knowledge':'知识配置','dataset_ids':'知识库选择','tools':'工具声明','memory':'记忆声明'}

class PreviewRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    plan_text:StrictStr


def register(h):
    router=APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/plan/change-preview')
    async def preview(item_id:str,payload:PreviewRequest,request:Request):
        try:
            raw=await request.body()
            if len(raw)>4_100_000:raise ValueError()
            json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
            draft=parse(payload.plan_text)
        except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):raise HTTPException(422,'比较需要2MB内无重复键/非有限数/坏编码的完整计划JSON对象；未修复、保存或回显原文。') from None
        task=h.get_task(item_id);h.require_revision(task,payload.revision)
        saved=task.get('agent_plan' if task['app_type']=='agent' else 'workflow_plan')
        if saved is not None and not isinstance(saved,dict):raise HTTPException(409,'已保存计划结构无法核对，未比较。')
        changed=not equal(saved,draft);left=saved or {};fields=[];other=0
        for key in sorted(set(left)|set(draft)):
            if (key in left)==(key in draft) and equal(left.get(key),draft.get(key)):continue
            if key not in FIELDS:other+=1;continue
            fields.append({'field':FIELDS[key],'change':'added' if key not in left else 'removed' if key not in draft else 'changed'})
        nodes=compare(saved,draft,equal) if task['app_type']!='agent' else None
        if nodes and not nodes['available']:nodes['note']='节点标识/层次无法对应或超出2000节点/21层范围，不能列出部分节点明细；请核对完整编辑器原文。'
        h.require_revision(h.get_task(item_id),task['revision'])
        return {'schema_version':1,'task_id':item_id,'revision':task['revision'],'app_type':task['app_type'],
                'draft_sha256':hashlib.sha256(payload.plan_text.encode('utf-8')).hexdigest(),'saved_plan_sha256':hashlib.sha256(canonical(saved)).hexdigest(),
                'has_saved_plan':saved is not None,'content_changed':changed,'saved_plan_stale':bool(task.get('plan_stale')),
                'field_changes':fields,'other_field_changes':other,'node_changes':nodes,
                'impacts':['若保存推进新修订，当前DSL成果/App绑定与配置确认需重新核对，旧运行不会成为新修订通过。','普通计划保存通常沿用未变的需求确认；逐项失败记录/汇总输出合同变化可能要求重新检查需求。','相同且未过期的计划可能不推进修订；最终以后台保存校验、实际变化和确认门禁为准。','不创建、修改或运行Dify资源；不读取凭据、执行代码或请求模型。'],
                'verification':'draft_change_categories_only','task_modified':False,'network_requested':False,'plan_validated':False,
                'note':'比较当前保存快照与本次编辑原文；仅列位置/字段类别，不判断业务影响或静态有效。节点明细最多30项，其余计数明确；改稿或修订变化须重新比较。'}
    h.app.include_router(router)
