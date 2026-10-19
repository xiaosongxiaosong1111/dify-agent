"""Local mapping previews; no upload, request, model or persistence."""
import copy,json,hashlib,re
from types import SimpleNamespace
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
from .file_cases import KIND,scope,definitions
from .file_run import FileProof,profile,gates
from .runtime_files import KIND as UPLOAD,canonical
from .file_formats import descriptor,FORMATS
from .file_cases import CaseRoute

class Match(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 catalog_revision:StrictInt=Field(ge=1)
 selections:dict[StrictStr,StrictStr]=Field(default_factory=dict)

def preview(h,task,case_id,payload):
 gates(h,task);_,_,context=profile(h,task)
 identity=SimpleNamespace(context=context)
 catalog=h.store.get(KIND,task['id'])
 if not catalog or catalog['catalog_revision']!=payload.catalog_revision or catalog['binding_digest']!=scope(identity):raise HTTPException(409,'文件样例集或成果／连接已改变，请重新读取并匹配。')
 case=next((c for c in catalog['cases'] if c['id']==case_id),None)
 if not case:raise HTTPException(404,'当前文件样例不存在。')
 records=[r for r in h.store.list(UPLOAD) if r.get('task_id')==task['id'] and r.get('revision')==task['revision']]
 if len(records)>500:raise HTTPException(422,'当前修订上传记录超过500项，本机匹配范围不足，未截断或自动选取；可继续手动指定可信引用。')
 values=copy.deepcopy(case['input']);slots=[];unresolved=False;missing=False
 for field in context['fields']:
  name=field['variable'];value=values.get(name)
  if field['type']=='file' and field.get('required') is False and (name not in values or value is None):continue
  items=value if field['type']=='file-list' else [value]
  if not isinstance(items,list) or field['type']=='file-list' and len(items)>field['max_length']:raise HTTPException(422,'固定样例文件结构与当前入口不符，未修复。')
  resolved=[]
  for index,item in enumerate(items):
   f=item.get('sierra_file_fixture') if isinstance(item,dict) and set(item)=={'sierra_file_fixture'} else None
   if not isinstance(f,dict) or set(f)!={'sha256','size','extension'} or not isinstance(f['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',f['sha256']) or type(f['size']) is not int or not 1<=f['size']<=2_000_000 or f['extension'] not in FORMATS:raise HTTPException(422,'固定样例缺少完整文件指纹，未猜测或读取正文。')
   candidates=[]
   for row in records:
    if row.get('state')!='uploaded' or row.get('attempts')!=1 or row.get('remote_upload_observed') is not True or not canonical(row.get('id')) or not canonical(row.get('remote_id')) or not canonical(row.get('remote_created_by')):continue
    if row.get('variable')!=name or row.get('input_kind')!=field['type'] or any(row.get(k)!=context[k] for k in ('environment_id','environment_url','environment_version','app_id','credential_stamp','environment_binding','artifact_sha256')):continue
    try:ext=descriptor(row.get('filename'))['extension']
    except ValueError:continue
    if row.get('content_sha256')==f['sha256'] and type(row.get('size')) is int and row['size']==f['size'] and ext==f['extension']:candidates.append({k:row[k] for k in ('id','filename','size','content_sha256')})
   candidates.sort(key=lambda r:r['id']);key=f'{name}:{index}';selected=payload.selections.get(key)
   if selected is not None and not any(c['id']==selected for c in candidates):raise HTTPException(409,'所选上传记录已不匹配当前文件位置，未替换成其他记录。')
   chosen=selected or (candidates[0]['id'] if len(candidates)==1 else None)
   slots.append({'key':key,'variable':name,'position':index+1,'fixture':copy.deepcopy(f),'candidates':candidates,'selected_id':chosen})
   if chosen:resolved.append({'sierra_file_id':chosen})
   else:unresolved=True;missing=missing or not candidates
  values[name]=resolved if field['type']=='file-list' else (resolved[0] if resolved else None)
 if set(payload.selections)-{s['key'] for s in slots}:raise HTTPException(422,'选择包含未声明的文件位置，未忽略。')
 text=None
 if not unresolved:
  proof=FileProof(h,task,values)
  if scope(proof)!=catalog['binding_digest']:raise HTTPException(409,'匹配期间文件上下文改变，请重新匹配。')
  text=json.dumps(values,ensure_ascii=False,allow_nan=False,indent=2)
  if len(text.encode('utf-8'))>64000:raise HTTPException(422,'匹配输入超过文件试跑字节上限，未截断。')
 return {'schema_version':1,'task_id':task['id'],'revision':task['revision'],'catalog_revision':catalog['catalog_revision'],'case_id':case_id,'case':definitions([case])[0],'artifact_sha256':context['artifact_sha256'],'state':'missing_files' if missing else 'needs_selection' if unresolved else 'ready','slots':slots,'input_text':text,'input_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest() if text is not None else None,'verification':'local_uploaded_fingerprint_match_only','network_requested':False,'task_changed':False,'file_uploaded':False,'workflow_runs':0,'note':'只匹配当前任务／修订／成果／变量／原目标及凭据下上传成功的记录，不读取正文或查询远端有效期。相同指纹多条记录须明确选择，不猜最新；重复位置和空数组保持。预览可主动采纳为完整输入；不会上传、准备批准或派发运行。实际试跑仍重新核对可信文件证明与固定样例。'}

class FileCaseMapping:
 def __init__(self,h):self.h=h
 def register(self):
  h=self.h;router=APIRouter(route_class=CaseRoute)
  @router.post('/api/tasks/{item_id}/file-cases/{case_id}/match')
  def match(item_id:str,case_id:str,payload:Match):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,payload.revision)
    return preview(h,task,case_id,payload)
  h.app.include_router(router)
