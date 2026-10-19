"""Inspect already-read evidence of one original generated file Schema check."""
import re
from .file_run import KIND,canonical,digest
from .run_diagnostics import remote_id,safe_text
from .file_schema_guard import metadata,validate_saved
from .diagnostic_graph_source import fingerprint

NOTE='仅核对原批准方案、执行图及这次已采集的节点状态，不追加Dify请求、不重新执行代码或模型、不改方案／原运行／验收。节点成功不证明本机输出合规或业务值真实；节点失败也可能是沙箱等原因，不能据此猜具体字段错误。当前来源另以诊断来源卡判断。'

def audit(h,task,run,report,detail,trace):
 rows=[p for p in h.store.list(KIND) if isinstance(p,dict) and p.get('task_id')==task['id'] and p.get('run_id')==run['id'] and p.get('plan_schema_version') in {7,9}]
 if not rows:return None
 value={'schema_version':1,'state':'insufficient','plan_id':None,'plan_revision':None,'guard_node_id':None,'observed_status':None,'guard_status_observed':False,'execution_graph_matches_original':False,'business_verified':False,'run_state_changed':False,'plan_changed':False,'verification':'observed_file_guard_node_status_only','note':NOTE}
 def unknown(message):return {**value,'message':message}
 if len(rows)!=1:return unknown('原运行的文件Schema检查方案不唯一，不能任选。')
 p=rows[0]
 if not canonical(p.get('id')) or type(p.get('revision')) is not int or p['revision']<1:return unknown('原方案标识或修订不完整。')
 value.update(plan_id=p['id'],plan_revision=p['revision'])
 if any(p.get(k) is not True for k in ('strict_guard_approved','model_egress_approved','unpriced_model_cost_approved','dispatched')) or type(p.get('attempts')) is not int or p['attempts']!=1 or any(p.get(k)!=run.get(k) for k in ('revision','app_id','environment_id','environment_binding')):return unknown('缺少原检查／模型批准、唯一派发或一致目标，不使用当前方案代替。')
 try:
  if digest(p.get('input'))!=digest(run.get('input')):return unknown('原运行与文件方案输入不一致。')
  flow=p.get('data_flow');output=flow['structured_output'];guard=flow['strict_guard']
  combined=p.get('plan_schema_version')==9
  count=6 if combined else 5;guard_index=count-2
  if flow.get('schema_version')!=(8 if combined else 6) or flow.get('scenario')!=('document_list_model_guarded_object' if combined else 'document_model_guarded_object') or flow.get('output_kind')!='json-object' or flow.get('model_egress') is not True or type(flow.get('planned_llm_node_executions')) is not int or flow['planned_llm_node_executions']!=1 or flow.get('node_types')!=(['start','document-extractor','code','llm','code','end'] if combined else ['start','document-extractor','llm','code','end']):return unknown('原文件方案不是完整带Schema检查的对象路线。')
  if combined:
   from .file_join import policy
   join=flow['join_policy']
   if p.get('join_policy_approved') is not True or not isinstance(join,dict) or join.get('verification')!='canonical_code_and_binding_static_only' or not isinstance(join.get('node_id'),str) or join['node_id']==guard['node_id']:return unknown('原多文档方案缺少独立拼接批准或完整声明。')
   policy(join['policy'])
  validate_saved(guard,output['node_id'],output['schema'])
 except (ValueError,KeyError,TypeError,RecursionError):return unknown('原完整检查代码、Schema或绑定声明无法核对。')
 gid=guard['node_id']
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',gid) or safe_text(gid)!=gid:return unknown('原校验节点标识不适合安全展示。')
 value['guard_node_id']=gid
 saved=run.get('result');data=saved.get('data') if isinstance(saved,dict) else None;rid=remote_id(saved,'workflow')
 if not rid or not isinstance(data,dict) or not canonical(p.get('published_workflow_id')) or data.get('workflow_id')!=p['published_workflow_id'] or report.get('remote_run_id')!=rid or not isinstance(detail,dict) or detail.get('id')!=rid:return unknown('原运行／发布身份与本次详情未可靠关联，节点同名不作为证明。')
 source=report.get('source_graph');execution=source.get('execution') if isinstance(source,dict) else None
 graph=detail.get('graph');actual=fingerprint(graph)
 if not actual or actual!=execution or actual.get('digest')!=p.get('graph_digest') or actual.get('node_count')!=count or actual.get('edge_count')!=count-1:return unknown('本次实际执行核心图未匹配原批准完整节点图。')
 try:
  by_kind={n['data']['type']:n for n in graph['nodes'] if n['data']['type']!='code'}
  guard_node=next(n for n in graph['nodes'] if n['id']==gid)
  if set(by_kind)!={'start','document-extractor','llm','end'} or by_kind['llm']['id']!=output['node_id'] or guard_node['data']['type']!='code':raise ValueError()
  outputs=by_kind['end']['data']['outputs']
  if len(outputs)!=1 or outputs[0]['variable']!=output['output_variable'] or digest(metadata(guard_node,by_kind['llm'],output['schema'],outputs[0]['value_selector']))!=digest(guard):raise ValueError()
  before=[by_kind['start']['id'],by_kind['document-extractor']['id']]
  if combined:
   from .file_join import from_native
   join_node=next(n for n in graph['nodes'] if n['id']==join['node_id'])
   if join_node['data']['type']!='code' or digest(from_native(join_node['data']))!=digest(join['policy']) or join_node['data']['variables'][0]['value_selector']!=[by_kind['document-extractor']['id'],'text']:raise ValueError()
   before.append(join['node_id'])
  chain=before+[by_kind['llm']['id'],gid,by_kind['end']['id']]
  if len(set(chain))!=count or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',nid) or safe_text(nid)!=nid for nid in chain):raise ValueError()
  if {(e['source'],e['target']) for e in graph['edges']}!=set(zip(chain,chain[1:])):raise ValueError()
 except (ValueError,TypeError,KeyError,RecursionError,StopIteration):return unknown('原检查节点、代码、对象绑定或完整顺序链不一致。')
 value['execution_graph_matches_original']=True
 nodes=report.get('nodes');raw=trace.get('data') if isinstance(trace,dict) else None
 if report.get('trace_state')!='read' or report.get('truncated') is not False or not isinstance(nodes,list) or not isinstance(raw,list) or set(trace)!={'data'} or report.get('node_count')!=len(nodes) or len(raw)!=len(nodes) or not 1<=len(nodes)<=count or type(detail.get('total_steps')) is not int or detail['total_steps']!=len(nodes):return unknown('轨迹缺失、截断、有未知分页或总步骤不符，不用部分记录推定检查状态。')
 status=detail.get('status')
 if status not in {'succeeded','failed','stopped','partial-succeeded'} or report.get('remote_status')!=status:return unknown('本次远端尚非一致终态，保留证据不足。')
 types={n['id']:n['data']['type'] for n in graph['nodes']};observed={}
 for node,original in zip(nodes,raw):
  if not isinstance(node,dict) or not isinstance(original,dict) or original.get('workflow_run_id',rid)!=rid or original.get('id')!=node.get('id') or original.get('node_id')!=node.get('node_id') or original.get('status')!=node.get('status'):return unknown('节点记录与本次运行或安全摘要未可靠对应。')
  nid=node.get('node_id')
  if nid not in types or nid in observed or node.get('node_type')!=types[nid] or node.get('status') not in {'succeeded','failed','exception','stopped'}:return unknown('节点标识、类型、重复记录或状态不完整，不猜重试或执行。')
  observed[nid]=node
 if gid not in observed or len(observed)<guard_index+1 or set(observed)!=set(chain[:len(observed)]) or any(observed[nid].get('status')!='succeeded' or observed[nid].get('error') for nid in chain[:guard_index]):return unknown('缺少原校验节点及其成功前置完整集合，不能推定已检查。')
 guard_status=observed[gid].get('status')
 if guard_status=='succeeded' and not observed[gid].get('error'):
  if status=='succeeded' and (len(observed)!=count or any(n.get('status')!='succeeded' or n.get('error') for n in observed.values())):return unknown('远端成功状态与完整节点成功记录不一致。')
  return {**value,'state':'observed_succeeded','observed_status':'succeeded','guard_status_observed':True,'message':'原轨迹记录该Schema检查节点成功；本机输出、后续终点及客户业务仍分别核对，不改变原结果。'}
 if guard_status in {'failed','exception'} and status!='succeeded' and len(observed)==guard_index+1:return {**value,'state':'observed_failed','observed_status':guard_status,'guard_status_observed':True,'message':'原轨迹记录该Schema检查节点失败；不能据此判断具体字段，也可能是沙箱等原因。不修改规则、补默认或重跑。'}
 return unknown('校验节点或后继状态互相矛盾，不能推定Schema通过或失败原因。')
