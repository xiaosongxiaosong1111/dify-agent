"""Explicit history selection; never edit saved words or replace current requirements."""
import hashlib
from .discussion_mode import history_content,requirement_user

TEXT_LIMIT=24000
OLD_MESSAGE_LIMIT=6000
DISCUSSION_PREFIX='【只读讨论记录，未作为需求或批准】\n'


def assemble_history(task,*,compact=False):
    all_messages=task.get('messages',[]);start=max(0,len(all_messages)-12)
    candidates=[];invalid=0
    for index,message in enumerate(all_messages[start:],start):
        if not isinstance(message,dict) or message.get('role') not in ('user','assistant'):continue
        text=message.get('content','')
        if not isinstance(text,str):invalid+=1;continue
        try:encoded=text.encode('utf-8')
        except UnicodeError:invalid+=1;continue
        candidates.append((index,message,text,hashlib.sha256(encoded).hexdigest()))
    current=next((row[0] for row in reversed(candidates) if row[1]['role']=='user'),None)
    selected={};remaining=TEXT_LIMIT
    if compact:
        order=sorted(candidates,key=lambda row:(row[0]!=current,row[1]['role']!='user',-row[0]))
        for index,message,text,digest in order:
            size=len(text) if index==current else min(len(text),OLD_MESSAGE_LIMIT,remaining)
            if size>remaining or not size:continue
            selected[index]=text[:size];remaining-=size
    else:selected={index:text for index,_,text,_ in candidates}
    messages=[];entries=[]
    for index,message,text,digest in candidates:
        if index not in selected:continue
        excerpt=selected[index];eligible=requirement_user(message)
        source_id=str(index) if eligible else None
        truncated=len(excerpt)<len(text)
        entry={'history_index':index,'source_id':source_id,'role':message['role'],'full_length':len(text),'included_length':len(excerpt),'excerpt_truncated':truncated,'source_sha256':digest}
        label=('需求证据ID message:'+source_id) if eligible else '对话索引'+str(index)+'（非需求证据）'
        label='【'+label+'；'+('只提供原话前缀片段' if truncated else '本条原话完整')+'；保存原话摘要 '+digest+'】\n'
        value=history_content({**message,'content':excerpt},current_revision=task['revision'])
        if value.startswith(DISCUSSION_PREFIX):value=DISCUSSION_PREFIX+label+value[len(DISCUSSION_PREFIX):]
        else:value=label+value
        messages.append({'role':message['role'],'content':value});entries.append(entry)
    summary={'schema_version':1,'mode':'bounded_excerpts' if compact else 'recent_full','recent_message_count':len(candidates),
             'included_count':len(entries),'omitted_count':len(candidates)-len(entries),'truncated_count':sum(r['excerpt_truncated'] for r in entries),
             'invalid_history_count':invalid,'messages_outside_recent_window':start,'history_text_characters':sum(r['included_length'] for r in entries),
             'history_text_limit':TEXT_LIMIT if compact else None,'current_user_message_complete':current in selected and len(selected[current])==len(next(r[2] for r in candidates if r[0]==current)),
             'entries':entries,'note':'这是组装的历史范围，不证明模型实际阅读或语义正确。当前完整需求、配置、系统契约和本轮用户原话保留；旧记录仍在本机，较早历史/片段未完整提供时不得假称已全面核对。正文字符不是token数或账单，标签/来源元数据及材料另计。'}
    return messages,summary
