"""Lossless saved case JSON editing; no execution or readiness grant."""
import hashlib,hmac,json,math
from fastapi import APIRouter,HTTPException,Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
from .evaluation import _json_value_error,validate_test_cases
from .plan_text_codec import unique,wire_float

LIMIT=2_000_000
NOTE='仅编辑已保存样例JSON值，不是最初文件字节；最多2MB及2万个JSON元素，不舍入或转换数值。保存仍经原样例校验并创建新修订，旧确认/验证失效；不运行、不调用模型或Dify，不证明业务通过。'

def checked(value):
    if not isinstance(value,list) or _json_value_error(value):raise ValueError()
    text=json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)
    if len(text.encode('utf-8'))>LIMIT:text=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    if len(text.encode('utf-8'))>LIMIT:raise ValueError()
    return text

def parse(text):
    try:
        if len(text.encode('utf-8'))>LIMIT:raise ValueError()
        value=json.loads(text,object_pairs_hook=unique,parse_float=wire_float,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        checked(value)
        if any(not isinstance(row,dict) for row in value):raise ValueError()
        return value
    except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):
        raise HTTPException(422,'样例原文须为2MB/2万个元素内、无重复键/非有限数/坏编码的完整JSON数组；未修复、舍入、截断或回显原文。') from None

def structured_safe(rows,app_type):
    if not validate_test_cases(rows,app_type)['valid']:return False
    def expectation(e):
        if not isinstance(e,dict):return False
        return set(e)==({'mode','description'} if e.get('mode')=='manual' else {'mode','target','expected'})
    for row in rows:
        if not isinstance(row,dict) or set(row)-{'id','name','required','input','expectation','followups'} or not {'id','name','required','input','expectation'}<=set(row) or not expectation(row['expectation']):return False
        followups=row.get('followups',[])
        if not isinstance(followups,list) or any(not isinstance(t,dict) or set(t)!={'input','expectation'} or not expectation(t['expectation']) for t in followups):return False
    stack=[rows]
    while stack:
        value=stack.pop()
        if type(value)is int and abs(value)>9007199254740991:return False
        if type(value)is float and (not math.isfinite(value) or value.is_integer()):return False
        if isinstance(value,dict):stack.extend(value.values())
        elif isinstance(value,list):stack.extend(value)
    return True

def describe(task):
    try:text=checked(task.get('test_cases',[]))
    except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):raise HTTPException(422,'已保存样例超出完整原文读取范围或编码/结构无法核对；未返回部分正文，不改旧记录。') from None
    raw=text.encode('utf-8');sha=hashlib.sha256(raw).hexdigest()
    source={'domain':'case-editor-v1','task_id':task['id'],'revision':task['revision'],'app_type':task['app_type'],'content_sha256':sha}
    token=hashlib.sha256(json.dumps(source,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    return {'schema_version':1,**{k:v for k,v in source.items() if k!='domain'},'source_token':token,'cases_text':text,'total_utf8_bytes':len(raw),'structured_editing_safe':structured_safe(task.get('test_cases',[]),task['app_type']),
            'verification':'saved_case_json_editor_only','task_changed':False,'network_requested':False,'business_verified':False,'note':NOTE}

class Save(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    source_token:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    cases_text:StrictStr=Field(max_length=LIMIT)

class EditorRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:response=await original(request)
            except RequestValidationError:return JSONResponse(status_code=422,content={'detail':'样例原文编辑请求须明确当前修订、来源指纹和JSON文字，不接受未知字段；未回显输入。'},headers={'Cache-Control':'no-store'})
            response.headers['Cache-Control']='no-store';return response
        return guarded

def register(h):
    router=APIRouter(route_class=EditorRoute)
    @router.get('/api/tasks/{item_id}/test-cases/editor')
    def read(item_id:str,revision:int=Query(ge=1)):
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision);return describe(task)
    @router.post('/api/tasks/{item_id}/test-cases/editor')
    def save(item_id:str,payload:Save):
        cases=parse(payload.cases_text)
        with h.store.lock:
            task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
            if not hmac.compare_digest(describe(task)['source_token'],payload.source_token):raise HTTPException(409,'已保存样例或来源发生变化；原文草稿保持，请核对新记录，不覆盖或自动重试。')
            return h.save_test_cases(item_id,h.TestCasesRequest(revision=payload.revision,cases=cases))
    h.app.include_router(router)
