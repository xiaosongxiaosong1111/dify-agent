"""Bounded literal lookup of saved messages; no model, writes or approvals."""
import hashlib
import hmac
import json
import re
from fastapi import HTTPException

MAX_MESSAGES=1000
MAX_HITS=20
MAX_TEXT=100000
MAX_SCANNED_CHARACTERS=1000000


def _scope(h,item_id,payload,allowed):
    if set(payload)-allowed:raise HTTPException(422,'历史查询包含未支持字段。')
    revision=payload.get('revision')
    if type(revision) is not int or revision<1:raise HTTPException(422,'任务修订必须是正整数。')
    task=h.get_task(item_id);h.require_revision(task,revision)
    if not isinstance(task.get('messages'),list):raise HTTPException(409,'当前任务历史结构无法核对，请读取原任务记录。')
    return task


def _text(message):
    if not isinstance(message,dict) or message.get('role') not in ('user','assistant'):return None
    for field in ('content','text'):
        value=message.get(field)
        if isinstance(value,str) and value:return value
    return None


def _revision(value):return value if type(value) is int and value>0 else None


def _describe(task,index,message,text):
    row={'message_index':index,'source_id':f'message:{index}','role':message['role'],
         'purpose':message.get('purpose') if message.get('purpose') in ('review','discussion') else 'unknown',
         'record_source':message.get('source') if message.get('source') in ('model','system','user') else 'unknown',
         'context_revision':_revision(message.get('context_revision')),'result_revision':_revision(message.get('result_revision')),
         'source_length':len(text),'content_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest()}
    row['source_token']=hashlib.sha256(json.dumps({'task_id':task['id'],**row},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()
    return row


def _flags(task):
    return {'schema_version':1,'task_id':task['id'],'revision':task['revision'],
            'verification':'saved_message_lookup_only','task_modified':False,'model_called':False,'external_network_requested':False,'business_verified':False}


def register(h):
    @h.app.post('/api/tasks/{item_id}/history/search')
    def search(item_id:str,payload:dict):
        task=_scope(h,item_id,payload,{'revision','query','role','before_index'})
        query=payload.get('query');role=payload.get('role','all')
        if not isinstance(query,str) or not query.strip() or len(query)>200:raise HTTPException(422,'查询词须为1到200字符的非空文字；按原样区分大小写查找。')
        if role not in ('all','user','assistant'):raise HTTPException(422,'历史角色筛选无法核对。')
        messages=task['messages'];end=payload.get('before_index',len(messages))
        if type(end) is not int or end<0:raise HTTPException(422,'历史窗口位置须为非负整数。')
        if end>len(messages):raise HTTPException(409,'历史窗口已变化，请从最新窗口重新查找。')
        cursor=end;hits=[];characters=0;unavailable=0;budget_reached=False
        while cursor>0 and end-cursor<MAX_MESSAGES and len(hits)<MAX_HITS:
            index=cursor-1;message=messages[index];text=_text(message)
            if text is None:unavailable+=1;cursor=index;continue
            if role!='all' and message['role']!=role:cursor=index;continue
            if len(text)>MAX_TEXT:unavailable+=1;cursor=index;continue
            if characters+len(text)>MAX_SCANNED_CHARACTERS:budget_reached=True;break
            cursor=index;characters+=len(text);position=text.find(query)
            if position<0:continue
            row=_describe(task,index,message,text);start=max(0,position-80);stop=min(len(text),start+400)
            row.update(match_start=position,preview=text[start:stop],preview_start=start,preview_end=stop,preview_complete=start==0 and stop==len(text))
            hits.append(row)
        h.require_revision(h.get_task(item_id),task['revision'])
        return {**_flags(task),'query':query,'role_filter':role,'total_messages':len(messages),'window_end':end,
                'next_before_index':cursor if cursor>0 else None,'has_earlier':cursor>0,'scanned_records':end-cursor,
                'scanned_characters':characters,'unavailable_records':unavailable,'character_limit_reached':budget_reached,
                'hits':hits,'note':'仅对当次保存快照作字面查找，区分大小写；最多1000条、100万字符、20个命中。超10万字符或无法核对的记录不查正文；更早或后来追加的内容尚未查，不代表不存在。助手建议和历史原话都不是本次采纳或执行批准。'}

    @h.app.post('/api/tasks/{item_id}/history/message')
    def read(item_id:str,payload:dict):
        task=_scope(h,item_id,payload,{'revision','message_index','source_token','center'})
        index=payload.get('message_index');token=payload.get('source_token');center=payload.get('center',0)
        if type(index) is not int or index<0 or type(center) is not int or center<0:raise HTTPException(422,'原话位置或片段中心须为非负整数。')
        if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{64}',token):raise HTTPException(422,'原话定位指纹无法核对。')
        if index>=len(task['messages']):raise HTTPException(404,'本任务未找到该历史位置。')
        message=task['messages'][index];text=_text(message)
        if text is None:raise HTTPException(409,'该记录没有可核对的用户或助手原话。')
        if len(text)>MAX_TEXT:raise HTTPException(413,'原话超过当前10万字符读取范围，请在原任务另行留存和核对；本次未截断作为完整原文。')
        row=_describe(task,index,message,text)
        if not hmac.compare_digest(row['source_token'],token):raise HTTPException(409,'历史原话或来源标签已变化，请重新查找；未采用旧片段。')
        if center>len(text):raise HTTPException(422,'片段位置超出当前原话范围。')
        start=max(0,center-1000);stop=min(len(text),start+4000)
        h.require_revision(h.get_task(item_id),task['revision'])
        return {**_flags(task),**row,'content':text,'quote_text':text[start:stop],'quote_start':start,'quote_end':stop,
                'quote_complete':start==0 and stop==len(text),'note':'已核对本任务保存的原话及定位指纹；引用片段最多4000字符，范围单列。它不是完整历史已被模型阅读、建议已采纳或资源执行批准的证明。'}
