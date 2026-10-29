"""Declared order-branch case drafts from an exact saved starter, no runs."""
import copy
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from .after_sales_starter import prepare as starter
from .mock_order import read_existing, PREFIX, NOT_FOUND_REPLY
from .plan_drafts import DraftRoute
from .plan_text_codec import parse, render, unique

NOTE=('仅为匹配的售后人工模板准备订单支路样例草稿，不推断资料问答或澄清路径已覆盖。'
      '分类/提取仍需真实验证，模型可能未按预期分流；这些输入和固定预期不是通过结论。'
      '逐项选择后只追加未保存样例，实际运行次数/费用仍须原批准，不自动提高上限。')


def propose(task,dependency,continuation_order_id=None):
    if task.get('app_type')!='advanced-chat' or task.get('dsl_reference') or task.get('dsl_overlay'):
        raise ValueError('仅支持无保留DSL覆盖的匹配售后Chatflow人工模板，不换类型或推断手改语义。')
    graph=task.get('workflow_plan')
    if not isinstance(graph,dict):raise ValueError('尚无完整售后模板。')
    text=render(graph);saved=read_existing(task,text,'order_lookup',dependency)
    nodes={n['id']:n for n in graph['nodes']}
    messages={key:nodes[node]['config']['template'] for key,node in
        [('no_hit_reply','no_hit'),('missing_order_reply','missing_order'),('clarify_reply','clarify')]}
    context=copy.deepcopy(task)
    for key in ('workflow_plan','agent_plan','artifact','dify_app_id','dsl_reference','dsl_overlay'):context[key]=None
    expected,_=starter(context,{'source_text':'','dependency':dependency,'records_text':saved['records_text'],**messages})
    if parse(expected)!=graph:raise ValueError('当前完整图与固定售后模板不一致；保留手改，不猜样例输入或路径。')
    records=json.loads(saved['records_text']);rows=[]
    def row(scenario,name,query,reply):
        rows.append({'scenario':scenario,'name':name,'input':{'query':query},
            'expectation':{'mode':'equals','target':'answer','expected':reply},'required':True})
    for order_id,value in records.items():row('found:'+order_id,'模拟订单命中 '+order_id,'查询订单 '+order_id,PREFIX+value)
    missing='UNLISTED-DEMO';index=0
    while missing in records:index+=1;missing='UNLISTED-DEMO_'+str(index)
    row('not_found','模拟订单不存在','查询订单 '+missing,NOT_FOUND_REPLY)
    row('missing_order','未提供订单号时追问','我想查询订单状态，但尚未提供订单号。',messages['missing_order_reply'])
    if continuation_order_id is not None:
        if ((task.get('configuration') or {}).get('conversation_memory') is not True
                or not isinstance(continuation_order_id,str) or continuation_order_id not in records):
            raise ValueError('接续样例须明确选已有合成订单，并先声明保存对话记忆；不改配置或猜订单。')
        row('missing_then_found:'+continuation_order_id,'缺号追问后补订单 '+continuation_order_id,
            '我想查询订单状态，但尚未提供订单号。',messages['missing_order_reply'])
        rows[-1]['followups']=[{'input':{'query':continuation_order_id},
            'expectation':{'mode':'equals','target':'answer','expected':PREFIX+records[continuation_order_id]}}]
    return rows,hashlib.sha256(text.encode()).hexdigest()


def register(h):
    class Payload(BaseModel):
        model_config=ConfigDict(extra='forbid')
        revision:StrictInt=Field(ge=1)
        dependency:StrictStr=Field(min_length=1,max_length=2000)
        request_nonce:UUID
        continuation_order_id:StrictStr|None=Field(default=None,min_length=1,max_length=64,pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    router=APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/after-sales-cases-preview')
    async def read(item_id:str,payload:Payload,request:Request):
        try:
            raw=await request.body()
            if len(raw)>20000:raise ValueError()
            json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        except (ValueError,UnicodeError,RecursionError):raise HTTPException(422,'样例草稿请求须无重复字段或坏编码，不回显输入。') from None
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task)
            artifact=task.get('artifact') or {}
            if not task.get('requirements_confirmed') or not task.get('configuration_confirmed') or task.get('plan_stale') or artifact.get('revision')!=task['revision'] or (artifact.get('validation') or {}).get('valid') is not True:
                raise HTTPException(422,'请先确认当前方案并构建有效静态成果，再读取样例；不从旧成果猜测。')
            if payload.continuation_order_id is not None and task.get('app_type')!='advanced-chat':
                raise HTTPException(422,'连续订单草稿仅用于明确选择的Chatflow，不切换应用类型或要求Workflow启用记忆。')
            if payload.continuation_order_id is not None and (task.get('configuration') or {}).get('conversation_memory') is not True:
                raise HTTPException(422,'准备缺号后补号的两轮样例，须先明确启用并保存对话记忆，再复核构建；这里不修改记忆或保证分类效果。')
            try:
                rows,plan_sha=propose(task,payload.dependency,payload.continuation_order_id)
                path=h.artifact_path(task);folder=(h.DATA_ROOT/task['id']).resolve()
                if path.is_symlink() or path.resolve().parent!=folder or folder.parent!=h.DATA_ROOT.resolve():raise ValueError()
                with path.open('rb') as stream:source=stream.read(2_000_001)
                if len(source)>2_000_000:raise ValueError()
                built,_=h.compile_current(task)
                if source.decode('utf-8').replace('\r\n','\n')!=built:raise ValueError()
                sha=hashlib.sha256(source).hexdigest()
                if artifact.get('sha256') is not None and artifact['sha256']!=sha:raise ValueError()
                if path.read_bytes()!=source:raise ValueError()
            except (ValueError,KeyError,TypeError,UnicodeError,OSError,RecursionError):
                raise HTTPException(422,'当前完整计划/成果不是可确认的售后模板，或合成表及绑定不匹配；原内容保持，不返回部分样例。') from None
            return {'schema_version':1,'task_id':item_id,'revision':task['revision'],'request_nonce':str(payload.request_nonce),
                'dependency':payload.dependency,'artifact_sha256':sha,'plan_sha256':plan_sha,'rows':rows,
                'continuation_order_id':payload.continuation_order_id,
                'note':NOTE+('本次另含缺号后仅补所选订单号的两轮样例：同一会话共两次Service请求，每轮可能调用分类/提取模型并收费；记忆已声明不等于实际理解通过，不增加次数或费用上限。' if payload.continuation_order_id is not None else ''),
                'verification':'declared_mock_order_case_drafts_only','task_changed':False,'network_requested':False,
                'model_called':False,'code_executed':False,'business_verified':False}
    h.app.include_router(router)
