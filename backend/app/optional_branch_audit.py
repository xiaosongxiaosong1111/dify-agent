"""Compare already-requested node evidence with one original optional-file plan."""
import re
from .file_run import KIND,canonical
from .run_diagnostics import remote_id,safe_text

NOTE='仅比较原批准文件方案与这次采集的完整节点集合，不额外读取平台、不修改方案／运行／验收或重跑。集合一致不证明执行时间顺序、文件完整文字或客户业务正确；当前成果／发布来源另按诊断来源卡判断。'

def audit(h,task,run,report,detail,trace):
 rows=[r for r in h.store.list(KIND) if isinstance(r,dict) and r.get('task_id')==task['id'] and r.get('run_id')==run['id'] and r.get('plan_schema_version')==5]
 if not rows:return None
 result={'schema_version':1,'state':'insufficient','plan_id':None,'plan_revision':None,'expected_path':None,'expected_node_ids':[],'observed_node_ids':[],'missing_node_ids':[],'unexpected_node_ids':[],'node_set_matches':False,'execution_order_verified':False,'business_verified':False,'run_state_changed':False,'plan_changed':False,'verification':'observed_optional_node_set_only','note':NOTE}
 def unknown(message):return {**result,'message':message}
 if len(rows)!=1:return unknown('原运行关联的可选文件方案不唯一，不能任选一份。')
 p=rows[0]
 if not canonical(p.get('id')) or type(p.get('revision')) is not int or p['revision']<1:return unknown('原方案标识或修订不完整。')
 result.update(plan_id=p['id'],plan_revision=p['revision'])
 if p.get('optional_branch_approved') is not True or p.get('dispatched') is not True or p.get('attempts')!=1 or any(p.get(k)!=run.get(k) for k in ('revision','app_id','environment_id','environment_binding')) or p.get('input')!=run.get('input'):return unknown('缺少唯一原批准、派发或一致输入／目标快照，不采用当前新方案代替。')
 flow=p.get('data_flow')
 if not isinstance(flow,dict):return unknown('原方案缺少数据流。')
 o=flow.get('optional_file');r=flow.get('resolved_branch')
 if flow.get('schema_version')!=4 or flow.get('scenario')!='document_optional_extraction' or not isinstance(o,dict) or not isinstance(r,dict):return unknown('旧方案缺少完整分支绑定。')
 keys=['start_node_id','guard_node_id','extract_node_id','present_end_node_id','missing_end_node_id'];ids=[o.get(k) for k in keys]
 if any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',x) or safe_text(x)!=x for x in ids) or len(set(ids))!=5:return unknown('原节点标识不完整或不适合安全比较。')
 present=r.get('expected_path')=='file_present'
 if r.get('expected_path') not in {'file_present','file_missing'}:return unknown('原方案没有明确预计分支。')
 expected=ids[:2]+([ids[2],ids[3]] if present else [ids[4]])
 skipped=[ids[4]] if present else ids[2:4]
 if r.get('expected_node_ids')!=expected or r.get('skipped_node_ids')!=skipped or r.get('expected_end_node_id')!=expected[-1]:return unknown('原方案节点集合与分支声明不一致。')
 result.update(expected_path=r['expected_path'],expected_node_ids=expected)
 saved=run.get('result');data=saved.get('data') if isinstance(saved,dict) else None;rid=remote_id(saved,'workflow')
 if not rid or not isinstance(data,dict) or not p.get('published_workflow_id') or data.get('workflow_id')!=p['published_workflow_id'] or report.get('remote_run_id')!=rid or not isinstance(detail,dict) or detail.get('id')!=rid:return unknown('缺少原运行／发布UUID与本次详情的可靠关联；节点ID相同不能代替来源。')
 source=report.get('source_graph',{});execution=source.get('execution') if isinstance(source,dict) else None
 if not isinstance(execution,dict) or execution.get('digest')!=p.get('graph_digest') or execution.get('node_count')!=5 or execution.get('edge_count')!=4:return unknown('本次实际执行核心图未匹配原批准完整两路图，不能比较预计选路。')
 nodes=report.get('nodes');raw=trace.get('data') if isinstance(trace,dict) else None
 if report.get('trace_state')!='read' or report.get('truncated') is not False or not isinstance(nodes,list) or not isinstance(raw,list) or set(trace)!={'data'} or report.get('node_count')!=len(nodes) or len(raw)!=len(nodes) or not 1<=len(nodes)<=5:return unknown('轨迹缺失、截断、带未知分页或数量不完整，不以部分节点证明选路。')
 if detail.get('status')!='succeeded' or report.get('remote_status')!='succeeded' or type(detail.get('total_steps')) is not int or detail['total_steps']!=len(nodes):return unknown('远端尚非成功终态或总步骤数与轨迹不一致，不能证明完整节点集合。')
 types=dict(zip(ids,['start','if-else','document-extractor','end','end']));observed=[]
 for n in nodes:
  if not isinstance(n,dict) or not isinstance(n.get('node_id'),str) or n['node_id'] not in types or n.get('node_type')!=types[n['node_id']] or n.get('status')!='succeeded' or n.get('error'):return unknown('节点标识、类型或成功状态与原图不一致，证据不足，不推定业务失败。')
  observed.append(n['node_id'])
 if len(set(observed))!=len(observed):return unknown('同一根节点出现多条执行记录，不能忽略重复或猜重试。')
 missing=[x for x in expected if x not in observed];unexpected=[x for x in ids if x in observed and x not in expected];matches=not missing and not unexpected
 return {**result,'state':'matched' if matches else 'different','observed_node_ids':observed,'missing_node_ids':missing,'unexpected_node_ids':unexpected,'node_set_matches':matches,'message':'采集节点集合与原批准预计分支一致；未核对时间顺序，不自动改变运行或验收。' if matches else '完整采集节点集合与原批准预计分支有差异，请核对原轨迹；不自动换分支、修改DSL或重跑。'}
