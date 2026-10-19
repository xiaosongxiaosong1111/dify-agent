"""Bounded index and explicit single-snapshot reads, no restore or execution."""
import copy
from fastapi import APIRouter,HTTPException
from .file_cases import KIND,CaseRoute,definitions
from .acceptance import same_json

TARGET=('environment_id','environment_url','environment_version','app_id')
def metadata(row):
 target={k:row[k] for k in TARGET if k in row}
 return {k:copy.deepcopy(row.get(k)) for k in ('task_id','revision','catalog_revision','artifact_sha256','updated_at')}|{'case_count':len(row['cases']),'target':target if len(target)==len(TARGET) else None,'target_recorded':len(target)==len(TARGET),'historical':True,'executable':False}
def delta(before,after):
 old={c['id']:c for c in before['cases']};new={c['id']:c for c in after['cases']}
 return {'added':[{'id':k,'name':c['name']} for k,c in new.items() if k not in old],'removed':[{'id':k,'name':c['name']} for k,c in old.items() if k not in new],'changed':[{'id':k,'name':c['name'],'fields':[f for f in ('name','input','expectation','required') if not same_json(c.get(f),old[k].get(f))]} for k,c in new.items() if k in old and not same_json(c,old[k])],'source_binding_changed':before.get('binding_digest')!=after.get('binding_digest'),'next_catalog_revision':after['catalog_revision']}
def envelope(task,row):
 return {'task_id':task['id'],'revision':task['revision'],'current_catalog_revision':row['catalog_revision'] if row else 0,'verification':'historical_file_case_definitions_only','network_requested':False,'task_changed':False,'restored':False,'workflow_runs':0,'note':'这里只读保留的文件样例定义，不恢复、不改绑当前成果、不准备或执行试跑，也不沿用历史通过结论。早期快照缺少目标详情时明确显示未知，不能用当前连接补猜。'}

class FileCaseHistory:
 def __init__(self,h):self.h=h
 def register(self):
  h=self.h;router=APIRouter(route_class=CaseRoute)
  @router.get('/api/tasks/{item_id}/file-cases/history')
  def index(item_id:str):
   with h.store.lock:
    task=h.get_task(item_id);row=h.store.get(KIND,item_id);history=(row or {}).get('history',[])[-20:];records=[]
    for i,entry in enumerate(history):records.append({**metadata(entry),'changes_to_next':delta(entry,history[i+1] if i+1<len(history) else row)})
    return {**envelope(task,row),'records':list(reversed(records)),'history_limit':20,'older_history_may_be_missing':len(history)==20}
  @router.get('/api/tasks/{item_id}/file-cases/history/{catalog_revision}')
  def detail(item_id:str,catalog_revision:int):
   with h.store.lock:
    task=h.get_task(item_id);row=h.store.get(KIND,item_id)
    found=next((r for r in (row or {}).get('history',[])[-20:] if r['catalog_revision']==catalog_revision),None)
    if not found:raise HTTPException(404,'保留历史中没有该文件样例集；可能已超出最近20份范围，未返回其他版本代替。')
    return {**envelope(task,row),'snapshot':{**metadata(found),'cases':definitions(found['cases'])}}
  h.app.include_router(router)
