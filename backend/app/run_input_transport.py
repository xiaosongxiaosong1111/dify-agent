"""Reject ambiguous JSON before run handlers, permissions, writes or dispatch."""
import json,math
from decimal import Decimal,InvalidOperation
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

MAX_BYTES=8_000_000
class AmbiguousInput(ValueError):pass

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise AmbiguousInput('请求JSON包含重复字段（含转义后同名），未选择末值；请明确保留哪一项，未派发。')
        result[key]=value
    return result

def constant(_):raise AmbiguousInput('请求JSON包含非有限数字，未采用或派发。')

def number(text):
    value=float(text)
    if not math.isfinite(value):raise AmbiguousInput('请求JSON数字溢出或非有限，未采用或派发。')
    if Decimal(text)!=Decimal(str(value)):raise AmbiguousInput('请求JSON数字解析后会改变数值（舍入或非零下溢），请明确数值表示；未采用或派发。')
    return value

def validate(raw):
    if len(raw)>MAX_BYTES:raise AmbiguousInput('试跑请求超过8MB线格式检查范围，未处理或派发；请缩小输入。')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=constant,parse_float=number)
        if not isinstance(value,dict):raise AmbiguousInput('试跑请求须为完整JSON对象，未处理或派发。')
        pending=[value];seen=0
        while pending:
            current=pending.pop();seen+=1
            if seen>100000:raise AmbiguousInput('试跑请求超过10万个值的结构检查范围，未处理或派发。')
            if isinstance(current,str):current.encode('utf-8')
            elif isinstance(current,dict):
                for key in current:key.encode('utf-8')
                if len(current)+seen+len(pending)>100000:raise AmbiguousInput('试跑请求超过结构检查范围，未处理或派发。')
                pending.extend(current.values())
            elif isinstance(current,list):
                if len(current)+seen+len(pending)>100000:raise AmbiguousInput('试跑请求超过结构检查范围，未处理或派发。')
                pending.extend(current)
        return value
    except AmbiguousInput:raise
    except (ValueError,UnicodeError,RecursionError,OverflowError,InvalidOperation):
        raise AmbiguousInput('试跑请求JSON格式、编码或数值范围无法核对，未处理或派发；不回显输入。') from None

class RunInputRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:validate(await request.body())
            except AmbiguousInput as exc:return JSONResponse(status_code=422,content={'detail':str(exc)})
            try:return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422,content={'detail':'试跑请求字段无效，请核对修订、样例标识、成果摘要及输入对象；不回显输入，未派发。'})
        return guarded
