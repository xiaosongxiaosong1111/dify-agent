"""Stateless explanation of supported object rules, not output or platform proof."""
import hashlib
import json
import re
from .structured_output import schema_errors
from .iteration_object_contract import schema_contract

PATH = re.compile(r'^(schema(?:\.properties\[[1-9][0-9]?\]|\.items){0,8}(?:\.(?:type|enum|properties|required|additionalProperties|title|description|minLength|maxLength|minItems|maxItems|minimum|maximum))?)')


def issue(code, path=None, line=None, column=None):
    return {'code':code,'path':path,'line':line,'column':column}


def classify(message):
    match = PATH.match(message)
    path = match[1] if match else None
    if '根类型' in message: code = 'root'
    elif '关键字' in message: code = 'keywords'
    elif '.enum' in message: code = 'enum'
    elif '类型节点' in message: code = 'complexity'
    elif '.properties' in message and '须为最多50' in message: code = 'properties'
    elif 'additionalProperties=false' in message: code = 'closed_object'
    elif '.required' in message: code = 'required'
    elif '.type' in message: code = 'type'
    elif '.title' in message or '.description' in message: code = 'text'
    elif any(key in message for key in ('minLength','maxLength','minItems','maxItems','minimum','maximum','最小值')): code = 'bounds'
    else: code = 'schema'
    return issue(code,path)


def inspect(text):
    source_hash = None
    def result(errors, schema_hash=None):
        return {'valid':not errors,'diagnostics':errors,'source_text_sha256':source_hash,
                'schema_sha256':schema_hash,'verification':'local_object_schema_rules_only',
                'task_changed':False,'network_requested':False,'code_executed':False,
                'platform_checked':False,'business_verified':False}
    if not isinstance(text,str): return result([issue('json')])
    try: raw=text.encode('utf-8')
    except UnicodeError: return result([issue('encoding')])
    source_hash=hashlib.sha256(raw).hexdigest()
    if len(raw)>64000: return result([issue('size')])
    from .plan_drafts import inspect_text
    from fastapi import HTTPException
    try: inspect_text(text)
    except HTTPException as exc:
        return result([issue('credentials' if '凭据' in str(exc.detail) else 'json')])
    class Duplicate(ValueError): pass
    def unique(pairs):
        value={}
        for key,child in pairs:
            if key in value: raise Duplicate()
            value[key]=child
        return value
    def constant(_): raise ValueError()
    try:
        schema=json.loads(text,object_pairs_hook=unique,parse_constant=constant)
        json.dumps(schema,ensure_ascii=False,allow_nan=False).encode('utf-8')
    except json.JSONDecodeError as exc: return result([issue('json',line=exc.lineno,column=exc.colno)])
    except Duplicate: return result([issue('duplicate')])
    except UnicodeError: return result([issue('encoding')])
    except (ValueError,TypeError,OverflowError): return result([issue('finite_json')])
    except RecursionError: return result([issue('complexity')])
    errors=schema_errors(schema)
    if errors:
        return result([issue('too_many')] if len(errors)>20 else [classify(message) for message in errors])
    try: normalized=schema_contract(schema)
    except ValueError: return result([issue('unsafe_integer')])
    canonical=json.dumps(normalized,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode('utf-8')
    return result([],hashlib.sha256(canonical).hexdigest())


def register(host):
    from fastapi import APIRouter,HTTPException
    from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
    from uuid import UUID
    from .plan_drafts import DraftRoute
    class Request(BaseModel):
        model_config=ConfigDict(extra='forbid')
        revision:StrictInt=Field(ge=1)
        schema_text:StrictStr=Field(max_length=64000)
        request_nonce:UUID
    router=APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/object-schema-check')
    def check(item_id:str,payload:Request):
        with host.store.lock:
            task=host.get_task(item_id);host.require_revision(task,payload.revision)
            if task.get('app_type')!='workflow':raise HTTPException(422,'本入口只检查Workflow对象计算规则，不改变应用类型。')
            value=inspect(payload.schema_text)
            return {**value,'task_id':item_id,'revision':payload.revision,'request_nonce':str(payload.request_nonce)}
    host.app.include_router(router)
