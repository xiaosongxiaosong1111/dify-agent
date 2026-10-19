"""Explicit, bounded missing-node proposal; never silently repair a plan."""
import copy
import hashlib
from .plan_drafts import inspect_text
from .plan_text_codec import parse,render
from .workflow_plan import validate_plan

ERROR='这里只能补充根Workflow的一个明确缺失文档提取节点：已有开始/结束、两条连接和唯一text输出，以及一个必填单文件。其它图、列表/可选文件或多个文件须继续人工设计，不会省略后放行。'


def prepare(task,text,missing_node_id,input_variable):
    if task.get('app_type')!='workflow':raise ValueError('此建议仅适用于用户选择的Workflow，不改变应用类型。')
    inspect_text(text);plan=parse(text)
    nodes=plan.get('nodes');edges=plan.get('edges')
    if not isinstance(nodes,list) or len(nodes)!=2 or not all(isinstance(n,dict) for n in nodes) or not isinstance(edges,list) or len(edges)!=2 or not all(isinstance(e,dict) for e in edges):raise ValueError(ERROR)
    starts=[n for n in nodes if n.get('type')=='start'];ends=[n for n in nodes if n.get('type')=='end']
    if len(starts)!=1 or len(ends)!=1:raise ValueError(ERROR)
    start,end=starts[0],ends[0]
    ids=[start.get('id'),end.get('id')]
    if not all(isinstance(i,str) and i for i in ids) or len(set(ids))!=2 or not isinstance(missing_node_id,str) or not missing_node_id or missing_node_id in ids:raise ValueError(ERROR)
    if any(not isinstance(e.get(k),str) for e in edges for k in ('source','target')):raise ValueError(ERROR)
    if {(e.get('source'),e.get('target')) for e in edges}!={(start['id'],missing_node_id),(missing_node_id,end['id'])}:raise ValueError(ERROR)
    cfg=start.get('config');end_cfg=end.get('config')
    if not isinstance(cfg,dict) or not isinstance(end_cfg,dict):raise ValueError(ERROR)
    variables=cfg.get('variables');outputs=end_cfg.get('outputs')
    if not isinstance(variables,list) or not all(isinstance(v,dict) for v in variables) or not isinstance(outputs,list) or len(outputs)!=1 or not isinstance(outputs[0],dict) or outputs[0].get('value_selector')!=[missing_node_id,'text']:raise ValueError(ERROR)
    files=[v for v in variables if v.get('type') in ('file','file-list')]
    if len(files)!=1 or files[0].get('type')!='file' or files[0].get('required') is not True or not isinstance(input_variable,str) or not input_variable or files[0].get('variable')!=input_variable:raise ValueError(ERROR)
    added={'id':missing_node_id,'type':'document-extractor','title':'提取文档文字','config':{'variable_selector':[start['id'],input_variable],'input_type':'file','empty_policy':'fail_if_missing'}}
    proposal=copy.deepcopy(plan);position=nodes.index(start)+1;proposal['nodes'].insert(position,added)
    check=validate_plan(copy.deepcopy(task),proposal)
    if not check['valid']:raise ValueError('补充后仍未通过完整计划校验；未返回部分修复或改变其它配置，请先修正原稿或协商范围。')
    stripped=copy.deepcopy(proposal);stripped['nodes'].pop(position)
    if stripped!=plan:raise ValueError('原节点或连接无法原样保留，未准备建议。')
    output=render(proposal)
    return {'plan_text':output,'source_text_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'proposal_sha256':hashlib.sha256(output.encode('utf-8')).hexdigest(),'added_node_id':missing_node_id,
            'file_selector':[start['id'],input_variable],'failure_policy':'fail_if_missing',
            'verification':'local_missing_extractor_proposal_only','original_nodes_preserved':True,'original_edges_preserved':True,
            'task_changed':False,'network_requested':False,'code_executed':False,'platform_checked':False,'business_verified':False}


def register(h):
    import asyncio,json
    from uuid import UUID
    from fastapi import APIRouter,HTTPException,Request
    from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field
    from .plan_drafts import DraftRoute
    from .plan_text_codec import unique
    class Payload(BaseModel):
        model_config=ConfigDict(extra='forbid')
        revision:StrictInt=Field(ge=1)
        plan_text:StrictStr=Field(max_length=2000000)
        missing_node_id:StrictStr=Field(min_length=1,max_length=256)
        input_variable:StrictStr=Field(min_length=1,max_length=64)
        acknowledge_extraction:StrictBool
        request_nonce:UUID
    router=APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/missing-document-extractor')
    async def proposal(item_id:str,payload:Payload,request:Request):
        if not payload.acknowledge_extraction:raise HTTPException(422,'请先确认缺少的节点类型、所选文件来源与缺失失败政策；不自动修复。')
        try:
            raw=await request.body()
            if len(raw)>4100000:raise ValueError()
            json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        except (ValueError,TypeError,UnicodeError,RecursionError):raise HTTPException(422,'请求须为有界、无重复键的完整JSON，未准备或保存建议；不回显输入。') from None
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,payload.revision);context=copy.deepcopy(task)
        try:value=await asyncio.to_thread(prepare,context,payload.plan_text,payload.missing_node_id,payload.input_variable)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
        except (TypeError,KeyError,IndexError,RecursionError,OverflowError):raise HTTPException(422,'草稿结构无法按本次单节点方案处理；原稿保持，没有准备部分修复。') from None
        with h.store.lock:h.require_revision(h.get_task(item_id),payload.revision)
        return {**value,'task_id':item_id,'revision':payload.revision,'request_nonce':str(payload.request_nonce)}
    h.app.include_router(router)
