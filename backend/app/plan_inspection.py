"""Stateless checks of unsaved plan text using the manual-save validators."""
import asyncio
import copy
import hashlib
import json
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
from uuid import UUID
from .plan_drafts import DraftRoute,inspect_text
from .plan_text_codec import parse,unique
from .plan_field_text import normalize


def inspect(task,text):
    value={'valid':False,'errors':[],'warnings':[],'nodes':0,'json_location':None,
           'source_text_sha256':None,'verification':'local_plan_structure_only','task_changed':False,
           'network_requested':False,'code_executed':False,'platform_checked':False,'business_verified':False}
    def fail(message):
        value.update(valid=False,errors=[message],warnings=[],nodes=0)
        return value
    try:encoded=text.encode('utf-8')
    except (UnicodeError,AttributeError):return fail('草稿文字编码无效，未检查或保存。')
    value['source_text_sha256']=hashlib.sha256(encoded).hexdigest()
    if len(encoded)>2000000:return fail('草稿超过2MB UTF8范围，未截断、检查或保存。')
    try:inspect_text(text)
    except HTTPException:return fail('草稿未通过安全文字或结构检查，请核对大小、编码与明文凭据；错误不回显原文。')
    try:plan=normalize(parse(text))
    except ValueError:
        try:json.loads(text)
        except json.JSONDecodeError as exc:value['json_location']={'line':exc.lineno,'column':exc.colno}
        except (ValueError,TypeError,RecursionError):pass
        return fail('草稿须为完整JSON对象，无重复键、非有限数、坏编码或无效字段文字；未修复或保存。')
    try:
        if task.get('app_type')=='agent':
            from .agent_plan import validate_agent_plan
            result=validate_agent_plan(copy.deepcopy(task),plan)
        else:
            from .workflow_plan import validate_plan
            result=validate_plan(copy.deepcopy(task),plan)
        errors=result['errors'];warnings=result['warnings'];nodes=result['nodes']
        if type(result['valid']) is not bool or type(nodes) is not int or nodes<0 or not isinstance(errors,list) or not isinstance(warnings,list):raise ValueError()
        messages=errors+warnings
        if len(messages)>200 or any(not isinstance(m,str) or not m.strip() or len(m)>4000 for m in messages) or len(json.dumps(messages,ensure_ascii=False).encode('utf-8'))>256000:raise ValueError()
        if result['valid']!= (not errors):raise ValueError()
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):return fail('检查结果超出可展示范围或结构无法处理；未返回部分结果，请缩小草稿并逐步核对，不代表代码或业务已验证。')
    value.update(valid=result['valid'],errors=errors,warnings=warnings,nodes=nodes)
    return value


class Payload(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    plan_text:StrictStr=Field(max_length=2000000)
    request_nonce:UUID


def register(h):
    router=APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/plan-check')
    async def check(item_id:str,payload:Payload,request:Request):
        try:
            raw=await request.body()
            if len(raw)>4100000:raise ValueError()
            json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        except (ValueError,TypeError,UnicodeError,RecursionError):raise HTTPException(422,'检查请求须为有界、无重复键的完整JSON，未检查或保存；不回显输入。') from None
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,payload.revision);context=copy.deepcopy(task)
        value=await asyncio.to_thread(inspect,context,payload.plan_text)
        with h.store.lock:h.require_revision(h.get_task(item_id),payload.revision)
        return {**value,'task_id':item_id,'revision':payload.revision,'request_nonce':str(payload.request_nonce)}
    h.app.include_router(router)
