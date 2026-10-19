"""Explicit local policy edits, preserving all other draft content."""
import copy,json
from uuid import UUID
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,Field
from .file_join import policy,JoinPolicy,from_native,code
from .file_join import JoinRoute
from .structured_guard import digest

def inspect(task,plan,node_id):
 from .workflow_plan import validate_plan
 if task['app_type']!='workflow':raise ValueError('拼接政策编辑只适配Workflow根节点，不改变应用类型。')
 if len(json.dumps(plan,ensure_ascii=False,allow_nan=False).encode('utf-8'))>2_000_000:raise ValueError('流程草稿超过2MB，不截断。')
 checked=validate_plan(task,plan)
 if not checked['valid']:raise ValueError('请先处理当前流程问题，未覆盖原内容：'+'；'.join(checked['errors']))
 targets=[n for n in plan['nodes'] if n['id']==node_id and n['type']=='code']
 if len(targets)!=1:raise ValueError('请选择当前唯一根拼接代码节点，不猜容器或其他代码。')
 node=targets[0];old=from_native(node['config'])
 extractor=next(n for n in plan['nodes'] if n['id']==node['config']['variables'][0]['value_selector'][0])
 start_id,variable=extractor['config']['variable_selector'];start=next(n for n in plan['nodes'] if n['id']==start_id)
 field=next(v for v in start['config']['variables'] if v['variable']==variable)
 return node,old,start,field

def candidate(task,plan,node_id,value):
 from .workflow_plan import validate_plan
 node,old,start,field=inspect(task,plan,node_id);value=policy(value)
 if old==value:raise ValueError('所选政策没有改变，不生成重复修改。')
 result=copy.deepcopy(plan);target=next(n for n in result['nodes'] if n['id']==node_id);target['config']['code']=code(value)
 new_start=next(n for n in result['nodes'] if n['id']==start['id']);new_field=next(v for v in new_start['config']['variables'] if v['variable']==field['variable'])
 new_field['max_length']=value['max_files']
 checked=validate_plan(task,result)
 if not checked['valid']:raise ValueError('候选流程没有通过完整静态校验，未采用：'+'；'.join(checked['errors']))
 return {'plan':result,'previous_policy':old,'policy':value,'file_variable':field['variable'],'source_plan_sha256':digest(plan),'candidate_plan_sha256':digest(result),'updated_nodes':1+int(old['max_files']!=value['max_files']),'changed_edges':0,'added_nodes':0}

class Inspect(BaseModel):
 model_config=ConfigDict(extra='forbid')
 revision:StrictInt=Field(ge=1)
 plan:dict
 node_id:StrictStr=Field(min_length=1,max_length=256)
 request_nonce:UUID
class Preview(Inspect):
 policy:JoinPolicy

class FileJoinPolicy:
 def __init__(self,h):self.h=h
 def register(self):
  h=self.h;router=APIRouter(route_class=JoinRoute)
  def prepare(item_id,payload,preview):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task)
    try:
     if preview:result=candidate(task,payload.plan,payload.node_id,payload.policy.model_dump())
     else:
      _,old,_,field=inspect(task,payload.plan,payload.node_id)
      result={'policy':old,'file_variable':field['variable'],'source_plan_sha256':digest(payload.plan)}
    except (TypeError,RecursionError,UnicodeError):raise HTTPException(422,'草稿结构或编码无法完整校对，未修改原内容。') from None
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    return {**result,'task_id':item_id,'revision':task['revision'],'node_id':payload.node_id,'request_nonce':str(payload.request_nonce),'verification':'local_policy_static_only','network_requested':False,'model_called':False,'task_changed':False}
  @router.post('/api/tasks/{item_id}/file-join-policy/inspect')
  def read(item_id:str,payload:Inspect):return prepare(item_id,payload,False)
  @router.post('/api/tasks/{item_id}/file-join-policy/preview')
  def preview(item_id:str,payload:Preview):return prepare(item_id,payload,True)
  h.app.include_router(router)
