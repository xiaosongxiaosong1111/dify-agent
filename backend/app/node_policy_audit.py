"""Read-only complete policy issues for a current final artifact, no environment."""
import hashlib
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import JSONResponse
from .plan_drafts import DraftRoute
from .dsl_roundtrip import parse
from .node_policy import validate,FIELDS

LIMIT=2_000_000
KINDS={'start','llm','code','template-transform','http-request','if-else','list-operator','document-extractor','iteration','iteration-start','loop','loop-start','loop-end','variable-aggregator','knowledge-retrieval','parameter-extractor','question-classifier','end','answer','assigner','human-input','trigger-schedule'}

def audit(root):
 graph=root.get('workflow',{}).get('graph',{});nodes=graph.get('nodes')
 if not isinstance(nodes,list) or not 1<=len(nodes)<=1000:raise ValueError('节点数组无效或超过1000项；不会截断后当作完整检查。')
 rows=[]
 for index,node in enumerate(nodes):
  data=node.get('data') if isinstance(node,dict) else None
  if not isinstance(data,dict):raise ValueError('存在节点数据结构无效，检查未完成，不显示部分成功。')
  kind=data.get('type');kind=kind if isinstance(kind,str) and kind in KINDS else 'other'
  if kind=='http-request':
   from .http_execution import preserved
   try:preserved(data);issues=[]
   except ValueError as exc:issues=[str(exc)]
  elif kind=='document-extractor':
   from .document_extractor import validate_native_policy
   issues=validate_native_policy(data)
  else:issues=validate(data)
  retry=data.get('retry_config');enabled=retry.get('retry_enabled',False) if isinstance(retry,dict) else None
  declared='unspecified' if 'retry_config' not in data else 'disabled' if type(enabled) is bool and not enabled else 'enabled' if enabled is True else 'invalid'
  rows.append({'node_index':index,'node_kind':kind,'source_path':f'/workflow/graph/nodes/{index}/data','declared_retry':declared,'explicit_settings':sorted(FIELDS.intersection(data)),'issues':issues})
 return {'nodes':rows,'total_nodes':len(rows),'decision_nodes':sum(bool(r['issues']) for r in rows),'issue_count':sum(len(r['issues']) for r in rows),'verification':'local_execution_policy_only','platform_checked':False,'business_verified':False,'credentials_decrypted':False,'network_requested':False,'run_authorized':False,'note':'仅核对本机最终成果中的已适配节点执行设置；不是节点完整兼容、实际平台配置、文件权限、费用上限或业务验收。没有请求模型／Dify或改变Task。已派发项、供应商／解析器内部恢复和容器调用次数仍须另核对；此结果不能授权运行或自动取消功能。'}


def read_bytes(path):
 with path.open('rb') as handle:raw=handle.read(LIMIT+1)
 if len(raw)>LIMIT:raise ValueError('最终成果超过2MB，本机策略检查未完成，不截断。')
 return raw

class NodePolicyAudit:
 def __init__(self,host):self.h=host
 def register(self):
  h=self.h;router=APIRouter(route_class=DraftRoute)
  @router.get('/api/tasks/{item_id}/node-policy-audit')
  def read(item_id:str,revision:int=Query(ge=1)):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,revision)
    if task['app_type'] not in {'workflow','advanced-chat'}:raise HTTPException(422,'节点执行设置检查仅适配Workflow／Chatflow，不改变应用类型。')
    path=h.artifact_path(task)
    try:
     raw=read_bytes(path);content=raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n');root=parse(content,task['app_type']);result=audit(root)
    except (UnicodeError,KeyError,TypeError,AttributeError,RecursionError):raise HTTPException(422,'成果编码或节点结构无法完整核对；不显示原文或部分成功。') from None
    except ValueError as exc:
     # Parser errors may embed YAML values. Never return them here.
     raise HTTPException(422,'当前本机检查只适配2MB以内、1—1000节点的完整DSL，请核对结构／大小；未改变文件或运行。') from None
    except OSError:raise HTTPException(503,'本机成果暂时不可读，检查状态未知；没有改文件或派发。') from None
    latest=h.get_task(item_id);h.require_revision(latest,revision)
    try:
     if h.artifact_path(latest)!=path or read_bytes(path)!=raw:raise HTTPException(409,'读取期间最终成果改变，请重新读取，不沿用旧检查。')
    except (OSError,ValueError):raise HTTPException(409,'读取期间成果不可固定，请重新核对；未显示旧结果。') from None
    return JSONResponse({**result,'task_id':item_id,'revision':revision,'source_sha256':hashlib.sha256(content.encode('utf-8')).hexdigest(),'checked_at':h.now()},headers={'Cache-Control':'no-store'})
  h.app.include_router(router)
