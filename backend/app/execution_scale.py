"""Preview logical graph-node visits, never supplier calls, price or readiness."""
import hashlib
from uuid import UUID
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictStr
from .plan_drafts import DraftRoute,inspect_text
from .plan_text_codec import parse,render
from .workflow_plan import validate_plan

GROUPS={'model_nodes':{'llm','question-classifier','parameter-extractor'},
        'retrieval_nodes':{'knowledge-retrieval'},'http_nodes':{'http-request'}}
NOTES=[
 '只计算当前编辑器声明节点；未检查最终DSL、Dify手改保留、发布图或插件隐含节点，不代表目标应用实际次数。所有分支保守相加，不包含编译增加的保护节点。',
 '迭代项数是你本次手填的假设，不读取输入、文件或历史输出，也不约束实际运行；未知项数不能记为0。',
 '循环按声明loop_count计算上界，提前达标、无进展、失败或未走到该分支可能减少执行。并行不减少总次数，不据此估时。',
 '逻辑模型节点一次执行可能有多次API请求、结构修复或插件内部重试；HTTP声明尝试量另按首次加已启用的节点重试计算，不包含重定向、客户端/代理重试、代码或插件内部请求。这里不是API请求次数上界。检索、Embedding、rerank及HTTP也可能另计费。',
 '不读取价格、不估Token或美元、不抵扣预算、不批准或派发。没有模型节点也不能证明托管平台或外部服务免费；原资源与费用确认仍独立。',
]


def http_attempts(nodes,item_counts):
 from .http_execution import DEFAULT_RETRY
 rows=[]
 def visit(node,scope,multiplier):
  if node['type']!='http-request':return
  retry=node['config'].get('retry_config',DEFAULT_RETRY);factor=1+retry['max_retries'] if retry['retry_enabled'] else 1
  rows.append({'node_id':node['id'],'scope_id':scope,'logical_visits':multiplier,'attempts_per_visit':factor,
               'max_attempts':None if multiplier is None else multiplier*factor,
               'retry_enabled':retry['retry_enabled'],'max_retries':retry['max_retries'],'retry_interval_ms':retry['retry_interval']})
 for node in nodes:
  visit(node,None,1)
  if node['type'] in {'iteration','loop'}:
   multiplier=item_counts.get(node['id']) if node['type']=='iteration' else node['config']['loop_count']
   for child in node['config']['nodes']:visit(child,node['id'],multiplier)
 return {'total':None if any(row['max_attempts'] is None for row in rows) else sum(row['max_attempts'] for row in rows),
         'nodes':rows,'basis':'declared_http_node_retries_only','actual_http_requests_known':False,'internal_requests_counted':False}


def estimate(task,plan,item_counts):
 if task.get('app_type') not in {'workflow','advanced-chat'}:
  raise ValueError('此预览只计算Workflow／Chatflow显式流程；Agent自主轮次与工具请求不能用此图次数代替。')
 if not isinstance(item_counts,dict) or any(not isinstance(k,str) or type(v)is not int or not 0<=v<=100000 for k,v in item_counts.items()):
  raise ValueError('迭代假设须为节点ID到0—100000整数的映射，不接受布尔、负数或价格。')
 if not validate_plan(task,plan)['valid']:
  raise ValueError('当前完整流程尚未通过静态检查；先核对节点、模型声明与引用，不返回部分次数。')
 raw=render(plan).encode('utf-8');nodes=plan['nodes']
 expected={n['id'] for n in nodes if n['type']=='iteration'}
 if set(item_counts)-expected:raise ValueError('项数只能对应当前根迭代节点，不接受旧节点、循环轮数或隐藏覆盖。')
 totals={k:0 for k in GROUPS};declared=len(nodes);unknown=False;containers=[]
 for n in nodes:
  for group,kinds in GROUPS.items():
   if n['type'] in kinds and totals[group] is not None:totals[group]+=1
  if n['type'] not in {'iteration','loop'}:continue
  cfg=n['config'];body=cfg['nodes'];kind=n['type']
  multiplier=item_counts.get(n['id']) if kind=='iteration' else cfg['loop_count']
  local={g:sum(c['type'] in kinds for c in body) for g,kinds in GROUPS.items()}
  for group,count in local.items():
   if count and multiplier is None:totals[group]=None
   elif totals[group] is not None:totals[group]+=count*(multiplier or 0)
  if multiplier is None:unknown=True
  else:declared+=len(body)*multiplier
  containers.append({'node_id':n['id'],'node_type':kind,'body_declared_nodes':len(body),
                     'multiplier':multiplier,'basis':'manual_item_count' if kind=='iteration' and multiplier is not None else 'unknown_item_count' if kind=='iteration' else 'declared_loop_count',
                     'body_nodes_per_round':local})
 return {'schema_version':1,'app_type':task['app_type'],
         'source_plan_sha256':hashlib.sha256(raw).hexdigest(),'item_counts':dict(item_counts),
         'declared_root_nodes':len(nodes),'max_declared_node_visits':None if unknown else declared,
         'max_resource_node_visits':totals,'containers':containers,'has_unknown_item_count':unknown,
         'http_attempts':http_attempts(nodes,item_counts),
         'actual_api_calls_known':False,'cost_estimate_available':False,'cost_usd':None,
         'source_kind':'editor_plan_only','final_dsl_checked':False,
         'verification':'local_declared_node_visits_only','task_changed':False,'network_requested':False,
         'business_verified':False,'notes':list(NOTES)}


def register(host):
 class Preview(BaseModel):
  model_config=ConfigDict(extra='forbid')
  revision:StrictInt=Field(ge=1)
  plan_text:StrictStr=Field(max_length=2_000_000)
  item_counts:dict[StrictStr,StrictInt]=Field(default_factory=dict)
  request_nonce:UUID
 router=APIRouter(route_class=DraftRoute)
 @router.post('/api/tasks/{item_id}/execution-scale')
 def read(item_id:str,payload:Preview):
  with host.store.lock:
   task=host.get_task(item_id);host.require_revision(task,payload.revision)
   try:
    inspect_text(payload.plan_text);plan=parse(payload.plan_text)
    result=estimate(task,plan,payload.item_counts)
   except (TypeError,KeyError,RecursionError,UnicodeError,OverflowError):
    raise HTTPException(422,'流程结构超出本次规模预览范围，未保存、读取输入或执行。') from None
   except ValueError as exc:raise HTTPException(422,str(exc)) from None
   return {**result,'task_id':item_id,'revision':payload.revision,'request_nonce':str(payload.request_nonce)}
 host.app.include_router(router)
