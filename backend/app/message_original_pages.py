"""Read one saved message in bounded pages, bound to its actual source."""
import hmac,re
from fastapi import APIRouter,HTTPException
from fastapi.responses import JSONResponse
from .plan_drafts import DraftRoute
from .provider_tool_probe import strict_json
from .history_search import _text,_describe

MAX_BYTES=2_000_000
PAGE=4000
LABELS=('role','purpose','record_source','context_revision','result_revision')
ERROR='原话分页请求必须是有限、无重复键的明确JSON对象，未读取或回显输入。'


class ReadRoute(DraftRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:
                raw=await request.body()
                if len(raw)>8192 or not isinstance(strict_json(raw),dict):raise ValueError()
            except (ValueError,TypeError,UnicodeError,RecursionError):return JSONResponse(status_code=422,content={'detail':ERROR},headers={'Cache-Control':'no-store'})
            response=await original(request);response.headers['Cache-Control']='no-store';return response
        return guarded


def digest(value):return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None


def register(h):
    router=APIRouter(route_class=ReadRoute)
    @router.post('/api/tasks/{item_id}/history/message-page')
    def read(item_id:str,payload:dict):
        if set(payload)!={'revision','message_index','content_sha256','labels','source_token','offset'}:raise HTTPException(422,ERROR)
        revision=payload['revision'];index=payload['message_index'];offset=payload['offset'];token=payload['source_token'];labels=payload['labels']
        if type(revision)is not int or revision<1 or type(index)is not int or index<0 or type(offset)is not int or offset<0 or not digest(payload['content_sha256']):raise HTTPException(422,ERROR)
        if token is not None and not digest(token) or offset>0 and token is None:raise HTTPException(422,'后续分页须携带首次核对的来源指纹，未跳过核对。')
        if not isinstance(labels,dict) or set(labels)!=set(LABELS):raise HTTPException(422,ERROR)
        if labels['role'] not in ('user','assistant') or labels['purpose'] not in ('review','discussion','unknown') or labels['record_source'] not in ('user','model','system','unknown'):raise HTTPException(422,ERROR)
        if any(v is not None and (type(v)is not int or v<1) for v in (labels['context_revision'],labels['result_revision'])):raise HTTPException(422,ERROR)
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision);messages=task.get('messages')
            if not isinstance(messages,list):raise HTTPException(409,'保存的历史结构无法核对，未猜测原话。')
            if index>=len(messages):raise HTTPException(404,'本任务没有该原话位置。')
            message=messages[index];text=_text(message)
            if text is None:raise HTTPException(409,'此位置没有可核对的用户或助手文字。')
            try:
                if len(text)>MAX_BYTES:raise HTTPException(413,'原话超过本入口2MB UTF8完整核对范围，未截断冒充全文。')
                raw=text.encode('utf-8')
                if len(raw)>MAX_BYTES:raise HTTPException(413,'原话超过本入口2MB UTF8完整核对范围，未截断冒充全文。')
                source=_describe(task,index,message,text)
            except UnicodeError:raise HTTPException(422,'原话编码无法完整核对，未替换坏字符或回显正文。') from None
            if not hmac.compare_digest(source['content_sha256'],payload['content_sha256']) or {key:source[key] for key in LABELS}!=labels:raise HTTPException(409,'原话或来源标签与本页记录已不同，请刷新任务，未采用旧定位。')
            if token is not None and not hmac.compare_digest(source['source_token'],token):raise HTTPException(409,'原话定位指纹已变化，请重新核对，未沿用旧页。')
            if offset>=len(text):raise HTTPException(422,'分页位置超出当前原话，未改到其它位置。')
            end=min(len(text),offset+PAGE)
            return {'schema_version':1,'task_id':task['id'],'revision':revision,**source,'source_bytes':len(raw),
                    'verification':'saved_message_page_only','task_modified':False,'model_called':False,'external_network_requested':False,'business_verified':False,
                    'content_chunk':text[offset:end],'page_start':offset,'page_end':end,'page_size_limit':PAGE,
                    'complete_message':offset==0 and end==len(text),'has_previous':offset>0,'has_next':end<len(text),
                    'note':'仅核对本条保存原话及当前页；范围为Unicode码点，不代表其余页已读、模型已读、建议已采纳或执行获批。原话/标签变化需重新读取，后来追加的消息不会改变此条来源。'}
    h.app.include_router(router)
