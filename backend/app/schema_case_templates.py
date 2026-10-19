"""Read final declared schemas for explicit acceptance drafts, no execution."""
import copy,hashlib,re
from collections import Counter
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import JSONResponse
from .plan_drafts import DraftRoute
from .dsl_roundtrip import parse
from .node_policy_audit import read_bytes
from .json_inputs import schema,validate as validate_input

NOTE='仅从当前最终Workflow的明确Schema准备未保存验收草稿，不读实际运行输入／输出，不请求模型／Dify。规则来源不是客户业务通过或所有入口强制保证；先核对规则并补场景与真实输入，再主动保存／确认。新增草稿不覆盖旧样例，也不授权试跑。'

def root_node(node):
 data=node['data']
 return not node.get('parentId') and not data.get('isInIteration') and not data.get('isInLoop')


def templates(root):
 nodes=root.get('workflow',{}).get('graph',{}).get('nodes')
 if not isinstance(nodes,list) or not 1<=len(nodes)<=1000:raise ValueError('节点规模未适配')
 if any(not isinstance(n,dict) or not isinstance(n.get('data'),dict) or not isinstance(n.get('id'),str) or not n['id'] for n in nodes):raise ValueError('节点结构无效')
 by_id={n['id']:n for n in nodes}
 if len(by_id)!=len(nodes):raise ValueError('节点ID重复')
 if any(n['data'].get('type')=='trigger-schedule' for n in nodes):raise ValueError('定时流程样例入口尚待明确')
 rows=[]
 for ni,node in enumerate(nodes):
  if node['data'].get('type')!='end':continue
  outputs=node['data'].get('outputs')
  if not isinstance(outputs,list) or not outputs:raise ValueError('结束输出未明确')
  for oi,output in enumerate(outputs):
   if len(rows)>=1000:raise ValueError('输出超过1000项')
   if not isinstance(output,dict):raise ValueError('结束输出结构无效')
   target=output.get('variable');selector=output.get('value_selector');candidate=None;origin=None
   reason='本批仅结束输出直接引用根LLM.structured_output或根JSON对象入口；不猜代码、聚合、容器或嵌套属性的Schema。'
   if isinstance(target,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',target) and root_node(node) and isinstance(selector,list) and len(selector)==2 and all(isinstance(x,str) for x in selector):
    source=by_id.get(selector[0])
    if source and root_node(source):
     data=source['data']
     if data.get('type')=='llm' and selector[1]=='structured_output' and data.get('structured_output_enabled') is True:
      declaration=data.get('structured_output')
      if isinstance(declaration,dict) and set(declaration)=={'schema'}:candidate=declaration['schema'];origin='llm_structured_output'
     elif data.get('type')=='start':
      variables=data.get('variables');matches=[v for v in variables if isinstance(v,dict) and v.get('variable')==selector[1]] if isinstance(variables,list) else []
      if len(matches)==1 and matches[0].get('type')=='json_object' and not validate_input(matches[0]):candidate=matches[0]['json_schema'];origin='json_object_input'
   if candidate is not None:
    try:schema(candidate)
    except ValueError:candidate=None;origin=None;reason='来源Schema超出已适配闭合子集或无效，不会删除规则后准备。'
   rows.append({'row_id':f'{ni}:{oi}','source_path':f'/workflow/graph/nodes/{ni}/data/outputs/{oi}',
                'target':target if isinstance(target,str) else None,'source_selector':copy.deepcopy(selector) if isinstance(selector,list) and len(selector)==2 and all(isinstance(x,str) for x in selector) else None,
                'origin':origin,'schema':copy.deepcopy(candidate),'supported':candidate is not None,'reason':NOTE if candidate is not None else reason})
 if not rows:raise ValueError('未发现明确结束输出')
 targets=Counter(r['target'] for r in rows if r['target'] is not None)
 for row in rows:
  if targets.get(row['target'],0)>1:row.update(supported=False,schema=None,origin=None,reason='多个结束输出使用相同目标名，业务分支及Schema可能不同；须先讨论独立场景，不能任选一路当作通用规则。')
 return {'rows':rows,'total_outputs':len(rows),'candidate_count':sum(r['supported'] for r in rows),'total_nodes':len(nodes),
         'verification':'declared_schema_draft_only','platform_checked':False,'business_verified':False,'credentials_decrypted':False,'network_requested':False,'run_authorized':False,'note':NOTE}


class SchemaCaseTemplates:
 def __init__(self,host):self.h=host
 def register(self):
  h=self.h;router=APIRouter(route_class=DraftRoute)
  @router.get('/api/tasks/{item_id}/schema-case-templates')
  def read(item_id:str,revision:int=Query(ge=1)):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,revision)
    if task['app_type']!='workflow':raise HTTPException(422,'最终Schema验收草稿首批仅Workflow；不能猜Chatflow文字输出Schema或改变应用类型。')
    path=h.artifact_path(task)
    try:
     raw=read_bytes(path);content=raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n');result=templates(parse(content,'workflow'))
    except (ValueError,UnicodeError,KeyError,TypeError,AttributeError,RecursionError):raise HTTPException(422,'当前成果不能完整准备Schema草稿；仅适配2MB、1—1000节点／结束输出、明确直接来源的普通Workflow。不猜测、不显示部分成功或原文错误。') from None
    except OSError:raise HTTPException(503,'最终成果暂不可读，没有读取旧计划或派发。') from None
    latest=h.get_task(item_id);h.require_revision(latest,revision)
    try:
     if h.artifact_path(latest)!=path or read_bytes(path)!=raw:raise HTTPException(409,'读取期间成果改变，请重新读取当前来源。')
    except (ValueError,OSError):raise HTTPException(409,'读取期间成果无法固定，未采用旧来源。') from None
    return JSONResponse({**result,'task_id':item_id,'revision':revision,'source_sha256':hashlib.sha256(content.encode('utf-8')).hexdigest()},headers={'Cache-Control':'no-store'})
  h.app.include_router(router)
