"""Opt-in task message transport windows; old full Task reads remain unchanged."""
import hashlib,hmac,json,re
from fastapi import APIRouter,HTTPException
from .message_original_pages import ReadRoute

PAGE=50


def token(task,start,end,count):
    try:
        digest=hashlib.sha256(json.dumps({'task_id':task['id'],'revision':task['revision'],'start':start,'end':end,'anchor_count':count},sort_keys=True,separators=(',',':')).encode())
        for message in task['messages'][start:end]:
            raw=json.dumps(message,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
            digest.update(len(raw).to_bytes(8,'big'));digest.update(raw)
        return digest.hexdigest()
    except (ValueError,TypeError,UnicodeError,OverflowError,RecursionError):raise HTTPException(422,'当前消息窗口来源无法完整编码，未用部分记录代替。') from None


def window(task,start,end,count):
    return {'schema_version':1,'task_id':task['id'],'revision':task['revision'],'state_sequence':task.get('state_sequence',0),'start':start,'end':end,'anchor_count':count,'total_messages':len(task['messages']),'source_token':token(task,start,end,count),
            'page_limit':PAGE,'verification':'current_saved_message_window_only','task_modified':False,'model_called':False,'external_network_requested':False,
            'note':'仅当次读取的当前消息窗口，原索引保持；不代表全部历史已读或所有页是同一不可变快照。后续翻页核对所持窗口未变化，后来追加允许；更早新页按读取时的当前记录核对。模型上下文及后台原话保持。'}


def messages(task):
    if not isinstance(task.get('messages'),list):raise HTTPException(409,'保存的任务历史结构无法核对，未当作空历史。')
    return task['messages']


def task_view(task):
    count=len(messages(task));start=max(0,count-PAGE);meta=window(task,start,count,count)
    return {**task,'messages':task['messages'][start:count],'message_count':count,'message_window':meta}


def register(h):
    router=APIRouter(route_class=ReadRoute)
    @router.post('/api/tasks/{item_id}/history/window')
    def read(item_id:str,payload:dict):
        latest=set(payload)=={'revision','cursor','latest'} and payload.get('latest') is True
        if not latest and set(payload)!={'revision','cursor','start','end'}:raise HTTPException(422,'窗口请求须明确当前修订、持有窗口及新范围，不接受额外字段。')
        revision=payload['revision'];start=0 if latest else payload['start'];end=0 if latest else payload['end'];cursor=payload['cursor']
        if type(revision)is not int or revision<1 or type(start)is not int or type(end)is not int or start<0 or end<start or end-start>PAGE:raise HTTPException(422,'窗口范围须为非负整数、最多50条，不自动改位置。')
        if not isinstance(cursor,dict) or set(cursor)!={'start','end','anchor_count','source_token'}:raise HTTPException(422,'持有的消息窗口指纹结构无法核对。')
        a,b,count=cursor['start'],cursor['end'],cursor['anchor_count'];given=cursor['source_token']
        if any(type(v)is not int or v<0 for v in (a,b,count)) or a>b or b-a>PAGE or b>count or count>0 and (a==b or not latest and start==end) or not isinstance(given,str) or not re.fullmatch('[a-f0-9]{64}',given) or end>count:raise HTTPException(422,'持有窗口或目标位置超出原已知范围，未读取其它位置。')
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision);rows=messages(task)
            if count>len(rows):raise HTTPException(409,'保存的历史条数已缩短，请重新读取任务，未沿用旧位置。')
            if not hmac.compare_digest(token(task,a,b,count),given):raise HTTPException(409,'持有窗口的原话或标签已变化，请重新读取任务，未采用旧页。')
            if latest:count=len(rows);start=max(0,count-PAGE);end=count
            return {**window(task,start,end,count),'messages':rows[start:end]}
    h.app.include_router(router)
