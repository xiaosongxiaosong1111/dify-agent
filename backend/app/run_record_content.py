"""Read bounded saved run values; never re-evaluate, decrypt, or dispatch."""
import hashlib,hmac,json
from typing import Literal
from fastapi import APIRouter,HTTPException,Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from .delivery_bundle import check_text

PARTS={'input':'保存输入','test_case':'运行时样例快照','result':'保存返回','output':'旧输出字段','evaluation':'原评估记录'}
Part=Literal['input','test_case','result','output','evaluation']
LIMIT=2_000_000
NOTE='仅显示所选运行分区已保存JSON值，不是原始网络响应字节；不补其它字段、不重评旧结论，不写入、解密、调用模型或Dify，也不证明当前版本或业务通过。'

def select(task,run_id):
    rows=task.get('runs')
    if not isinstance(rows,list):raise HTTPException(422,'运行记录列表无法可靠核对，未读取其它记录。')
    matches=[r for r in rows if isinstance(r,dict) and r.get('id')==run_id]
    if not matches:raise HTTPException(404,'当前任务没有该运行记录，未读取其它来源。')
    if len(matches)!=1:raise HTTPException(409,'运行记录ID重复，不能可靠定位；未返回正文。')
    return matches[0]

def content(run,part):
    if part not in PARTS:raise HTTPException(422,'运行保存值分区无效。')
    if part not in run:raise HTTPException(404,'该记录没有保存此分区，不以其它字段补齐。')
    try:
        text=json.dumps(run[part],ensure_ascii=False,allow_nan=False,indent=2);raw=text.encode('utf-8');check_text(raw,LIMIT)
    except (HTTPException,ValueError,TypeError,UnicodeError,RecursionError,OverflowError):raise HTTPException(422,'该运行分区超出2MB范围、编码/结构无效或疑似含凭据；未返回部分正文，不回显原值。') from None
    return text,raw

def describe(task,run):
    parts=[]
    for key,label in PARTS.items():
        row={'key':key,'label':label,'state':'missing' if key not in run else 'unavailable','total_chars':None,'total_utf8_bytes':None,'content_sha256':None}
        try:
            text,raw=content(run,key);row.update(state='available',total_chars=len(text),total_utf8_bytes=len(raw),content_sha256=hashlib.sha256(raw).hexdigest())
        except HTTPException:pass
        parts.append(row)
    revision=run.get('revision');run_revision=revision if type(revision)is int and 1<=revision<=9007199254740991 else None
    source={'domain':'saved-run-json-v1','task_id':task['id'],'revision':task['revision'],'app_type':task['app_type'],'run_id':run['id'],'run_identity':{k:run.get(k) for k in ('revision','kind','status','app_type','environment_id','app_id')},'parts':parts}
    try:token=hashlib.sha256(json.dumps(source,sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('ascii')).hexdigest()
    except (ValueError,TypeError,RecursionError,OverflowError):raise HTTPException(422,'运行来源身份无法完整核对，未返回部分索引。') from None
    return {'schema_version':1,'task_id':task['id'],'revision':task['revision'],'app_type':task['app_type'],'run_id':run['id'],'run_revision':run_revision,'source_token':token,'parts':parts,'verification':'saved_run_json_index_only','task_changed':False,'model_called':False,'network_requested':False,'platform_checked':False,'business_verified':False,'note':NOTE}

class ReadRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:response=await original(request)
            except RequestValidationError:return JSONResponse(status_code=422,content={'detail':'运行JSON只读请求须明确当前修订、来源、分区及有效页范围，不回显参数。'},headers={'Cache-Control':'no-store'})
            response.headers['Cache-Control']='no-store';return response
        return guarded

def register(h):
    router=APIRouter(route_class=ReadRoute)
    @router.get('/api/tasks/{item_id}/runs/{run_id}/content-index')
    def index(item_id:str,run_id:str,revision:int=Query(ge=1)):
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision);return describe(task,select(task,run_id))
    @router.get('/api/tasks/{item_id}/runs/{run_id}/content')
    def read(item_id:str,run_id:str,part:Part,revision:int=Query(ge=1),source_token:str=Query(pattern=r'^[a-f0-9]{64}$'),offset:int=Query(default=0,ge=0),limit:int=Query(default=4000,ge=1,le=4000)):
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision);run=select(task,run_id);meta=describe(task,run)
            if not hmac.compare_digest(meta['source_token'],source_token):raise HTTPException(409,'任务或运行保存值来源已变化，请重新读取索引；未返回旧正文。')
            text,raw=content(run,part)
            if offset>=len(text):raise HTTPException(422,'页位置超出该分区的保存正文，未切换来源。')
            chunk=text[offset:offset+limit];end=offset+len(chunk)
            return {**{k:v for k,v in meta.items() if k!='parts'},'verification':'saved_run_json_page_only','source_kind':'saved_run_value_json','part':part,'text':chunk,'offset':offset,'next_offset':end if end<len(text) else None,'total_chars':len(text),'total_utf8_bytes':len(raw),'content_sha256':hashlib.sha256(raw).hexdigest(),'page_sha256':hashlib.sha256(chunk.encode('utf-8')).hexdigest()}
    h.app.include_router(router)
