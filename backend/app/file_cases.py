"""Local fixed file checks. Definitions contain fingerprints, never remote IDs."""
import copy,json,uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field
from .file_run import FileProof,gates,profile,digest,KIND as RUN_KIND
from .file_formats import descriptor
from .file_join import JoinRoute
from .runtime_files import unique,FileRoute
from .evaluation import validate_test_cases,EQUALITY_VERSION
from .acceptance import same_json

KIND='runtime_file_cases'
NOTE='文件指纹只证明本机原始字节相同，不证明提取结果或业务正确。样例独立保存，不改变任务修订、成果或上传记录；修改样例集后旧方案与旧通过结论失效。执行仍须准备并明确批准单次文件运行。'

def inputs(text):
 try:
  if len(text.encode('utf-8'))>64000:raise ValueError()
  value=json.loads(text,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
  json.dumps(value,allow_nan=False)
  if not isinstance(value,dict):raise ValueError()
  return value
 except (ValueError,UnicodeError,RecursionError):raise HTTPException(422,'输入须为64000字节内、无重复键及非有限值的严格JSON对象，未修复或回显原文。') from None

def scope(proof):
 context=copy.deepcopy(proof.context);context['data_flow']['extraction']=None
 context['data_flow'].pop('resolved_branch',None)
 return digest(context)

def template(proof):
 value=copy.deepcopy(proof.values)
 for field in proof.context['fields']:
  if field['type']=='file' and field.get('required') is False and (field['variable'] not in value or value[field['variable']] is None):continue
  items=[r for r in proof.files if r['variable']==field['variable']]
  refs=[{'sierra_file_fixture':{'sha256':r['content_sha256'],'size':r['size'],'extension':descriptor(r['filename'])['extension']}} for r in items]
  value[field['variable']]=refs if field['type']=='file-list' else refs[0]
 return value

def current(h,task,row):
 if not row:return True
 try:
  _,_,context=profile(h,task);context['data_flow']['extraction']=None;context['data_flow'].pop('resolved_branch',None)
  return row['binding_digest']==digest(context) and row['revision']==task['revision']
 except (HTTPException,ValueError,OSError,KeyError):return False

def definitions(cases):
 return [{**copy.deepcopy(c),'definition_text':json.dumps(c,ensure_ascii=False,allow_nan=False,indent=2),'input_text':json.dumps(c['input'],ensure_ascii=False,allow_nan=False,indent=2),'expectation_text':json.dumps(c['expectation'],ensure_ascii=False,allow_nan=False,indent=2)} for c in cases]

def view(h,task,row):
 return {'task_id':task['id'],'revision':task['revision'],'catalog_revision':row['catalog_revision'] if row else 0,'cases':definitions(row['cases']) if row else [],'stale':not current(h,task,row),'artifact_sha256':row['artifact_sha256'] if row else None,'archived_catalogs':len(row.get('history',[])) if row else 0,'note':NOTE,'verification':'declared_file_checks_only','network_requested':False,'task_changed':False}

def bind(h,task,proof,case_id,catalog_revision):
 row=h.store.get(KIND,task['id'])
 if not row or row['catalog_revision']!=catalog_revision or row['binding_digest']!=scope(proof):raise HTTPException(409,'文件样例集、成果或连接已改变；请读取当前样例并重新准备，不沿用旧批准。')
 case=next((c for c in row['cases'] if c['id']==case_id),None)
 if not case:raise HTTPException(404,'当前文件样例不存在。')
 value=template(proof)
 if not same_json(case['input'],value):raise HTTPException(422,'当前文件的指纹、大小、后缀、顺序／重复次数或非文件参数与固定样例不符；未替换、补文件或派发。')
 return {'schema_version':1,'catalog_revision':catalog_revision,'binding_digest':row['binding_digest'],'case':copy.deepcopy(case),'input_digest':digest(proof.values)}

def check_frozen(h,task,proof,frozen):
 latest=bind(h,task,proof,frozen['case']['id'],frozen['catalog_revision'])
 if not same_json(latest,frozen):raise HTTPException(409,'文件样例定义已改变，未派发原方案。')

def matching(row,case,run):
 frozen=run.get('file_case') or {}
 return frozen.get('schema_version')==1 and frozen.get('catalog_revision')==row['catalog_revision'] and frozen.get('binding_digest')==row['binding_digest'] and same_json(frozen.get('case'),case) and frozen.get('input_digest')==digest(run.get('input'))

def summary(h,task):
 row=h.store.get(KIND,task['id'])
 if not row:return []
 fresh=current(h,task,row);rows=[]
 for case in row['cases']:
  run=next((r for r in reversed(task.get('runs',[])) if r.get('kind')=='run' and (r.get('file_case') or {}).get('case',{}).get('id')==case['id']),None)
  status,method,detail='not_run','none','当前文件样例尚未运行。'
  if not fresh:status,detail='needs_review','文件样例集属于旧成果／连接，须明确建立当前样例集；旧结论不计通过。'
  elif run:
   if run.get('revision')!=task['revision'] or run.get('environment_id')!=task.get('environment_id') or not matching(row,case,run):status,detail='needs_review','运行不匹配当前样例集、输入或成果，不能沿用旧结论。'
   elif run['status'] in {'pending','unknown','failed'}:status,detail={'pending':'running','unknown':'unknown','failed':'failed'}[run['status']],run.get('error') or '文件运行尚未确认完成。'
   elif run['status']=='success':
    evaluation=run.get('file_case_evaluation') or {};status=evaluation.get('status','needs_review');method='rule';detail=evaluation.get('details') or '没有记录文件样例输出检查。'
    if status not in {'passed','failed','needs_review'}:status='needs_review'
    if case['expectation']['mode']=='equals' and type(case['expectation'].get('expected')) in (dict,list) and (type(evaluation.get('comparison_version')) is not int or evaluation['comparison_version']!=EQUALITY_VERSION):status,detail='needs_review','历史对象／数组等值规则需要重新核对，未自动重算或重跑。'
    review=run.get('file_case_review') or {}
    if case['expectation']['mode']=='manual' and evaluation.get('mode')=='manual' and review.get('source')=='user' and review.get('decision') in {'passed','failed'}:status,method,detail=review['decision'],'human',review['reason']
   else:status,detail='needs_review','平台状态不构成文件样例输出验收。'
  rows.append({'id':'file:'+case['id'],'name':case['name']+' · 文件样例','required':case['required'],'status':status,'method':method,'details':detail,'run_id':run['id'] if run else None,'source':'file_case','case_id':case['id'],'catalog_revision':row['catalog_revision'],'manual':case['expectation']['mode']=='manual'})
 return rows

class Capture(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 catalog_revision:StrictInt=Field(ge=0)
 input_text:StrictStr=Field(min_length=2,max_length=64000)
 name:StrictStr=Field(min_length=1,max_length=120)
 expectation:dict
 required:StrictBool=True
 case_id:StrictStr|None=None
 replace_stale:StrictBool=False
class Change(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 catalog_revision:StrictInt=Field(ge=1)
class Review(Change):
 decision:StrictStr
 reason:StrictStr=Field(min_length=1,max_length=2000)

class CaseRoute(JoinRoute):
 def get_route_handler(self):
  return FileRoute.get_route_handler(self) if self.methods <= {'GET','HEAD'} else super().get_route_handler()

class FileCases:
 def __init__(self,h):self.h=h
 def register(self):
  h=self.h;router=APIRouter(route_class=CaseRoute)
  def editable(task,revision,catalog_revision):
   h.require_revision(task,revision);h.require_idle(task)
   if any(r.get('task_id')==task['id'] and r.get('state') in {'verifying','executing'} for r in h.store.list(RUN_KIND)):raise HTTPException(409,'文件方案正在核对或运行，请等待原请求后修改样例。')
   row=h.store.get(KIND,task['id'])
   if (row['catalog_revision'] if row else 0)!=catalog_revision:raise HTTPException(409,'文件样例集已更新，请先重新读取；未覆盖其他修改。')
   return row
  @router.get('/api/tasks/{item_id}/file-cases')
  def read(item_id:str):
   with h.store.lock:
    task=h.get_task(item_id);return {**view(h,task,h.store.get(KIND,item_id)),'results':summary(h,task)}
  @router.post('/api/tasks/{item_id}/file-cases/capture')
  def capture(item_id:str,payload:Capture):
   values=inputs(payload.input_text)
   with h.store.lock:
    task=h.get_task(item_id);old=editable(task,payload.revision,payload.catalog_revision);gates(h,task);proof=FileProof(h,task,values)
    stale=bool(old and old['binding_digest']!=scope(proof))
    if stale and not payload.replace_stale:raise HTTPException(409,'旧文件样例集已过期；请明确选择归档旧集并为当前成果新建样例集。')
    if stale and payload.case_id:raise HTTPException(409,'不能把旧样例直接改绑到新成果，请为当前成果新建样例。')
    case={'id':payload.case_id or str(uuid.uuid4()),'name':payload.name.strip(),'input':template(proof),'expectation':payload.expectation,'required':payload.required}
    try:
     if len(json.dumps(case,ensure_ascii=False,allow_nan=False).encode('utf-8'))>64000:raise ValueError()
    except (ValueError,UnicodeError,RecursionError):raise HTTPException(422,'单个文件样例须为64000字节内的完整JSON值，未截断。') from None
    if set(payload.expectation)-{'mode','target','expected','description'}:raise HTTPException(422,'预期规则包含未支持字段，未忽略。')
    checked=validate_test_cases([case],'workflow')
    if not checked['valid']:raise HTTPException(422,'；'.join(checked['errors']))
    cases=copy.deepcopy(old['cases']) if old and not stale else []
    if payload.case_id:
     index=next((i for i,c in enumerate(cases) if c['id']==payload.case_id),None)
     if index is None:raise HTTPException(404,'要修改的当前文件样例不存在。')
     cases[index]=case
    else:
     if len(cases)>=20:raise HTTPException(422,'每个成果最多20个固定文件样例，未删除原样例。')
     cases.append(case)
    history=copy.deepcopy(old.get('history',[])) if old else []
    if old:history.append({k:copy.deepcopy(v) for k,v in old.items() if k!='history'})
    row={'task_id':item_id,'revision':task['revision'],'catalog_revision':payload.catalog_revision+1,'binding_digest':scope(proof),'artifact_sha256':proof.context['artifact_sha256'],'cases':cases,'history':history[-20:],'updated_at':h.now(),**{k:proof.context[k] for k in ('environment_id','environment_url','environment_version','app_id')}}
    h.store.put(KIND,item_id,row);return {**view(h,task,row),'results':summary(h,task),'saved_case_id':case['id']}
  @router.post('/api/tasks/{item_id}/file-cases/{case_id}/remove')
  def remove(item_id:str,case_id:str,payload:Change):
   with h.store.lock:
    task=h.get_task(item_id);row=editable(task,payload.revision,payload.catalog_revision)
    if not row or not any(c['id']==case_id for c in row['cases']):raise HTTPException(404,'当前文件样例不存在。')
    prior={k:copy.deepcopy(v) for k,v in row.items() if k!='history'};row.setdefault('history',[]).append(prior);row['history']=row['history'][-20:]
    row['cases']=[c for c in row['cases'] if c['id']!=case_id];row['catalog_revision']+=1;row['updated_at']=h.now();h.store.put(KIND,item_id,row)
    return {**view(h,task,row),'results':summary(h,task)}
  @router.post('/api/tasks/{item_id}/file-cases/runs/{run_id}/review')
  def review(item_id:str,run_id:str,payload:Review):
   with h.store.lock:
    task=h.get_task(item_id);row=editable(task,payload.revision,payload.catalog_revision)
    run=next((r for r in task['runs'] if r['id']==run_id),None)
    case=next((c for c in (row or {}).get('cases',[]) if c['id']==(run or {}).get('file_case',{}).get('case',{}).get('id')),None)
    if not row or not current(h,task,row) or not case or not run or run.get('kind')!='run' or run.get('status')!='success' or run.get('revision')!=task['revision'] or run.get('environment_id')!=task.get('environment_id') or not matching(row,case,run):raise HTTPException(409,'只可复核与当前文件样例集及成果匹配的成功运行。')
    if case['expectation']['mode']!='manual' or run.get('file_case_evaluation',{}).get('mode')!='manual':raise HTTPException(422,'人工意见不能覆盖自动文件检查规则。')
    if payload.decision not in {'passed','failed'} or not payload.reason.strip():raise HTTPException(422,'请选择通过／不通过并填写人工判断理由。')
    value={'decision':payload.decision,'reason':payload.reason.strip(),'source':'user','created_at':h.now()};run.setdefault('file_case_review_history',[]).append(value);run['file_case_review']=value;h.save_task(task)
    return {**view(h,task,row),'results':summary(h,task)}
  h.app.include_router(router)
