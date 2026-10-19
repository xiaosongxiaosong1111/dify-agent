"""Require a necessary file-presence branch before nullable root extraction."""
from .extraction_safety import reachable

NOTE='可选单文件先用exists／not exists判存在；只有明确存在的路径才能提取，缺失路径须另定业务行为。存在不证明归属、远端有效期、格式或文字完整。五根节点纯提取／明确说明图可另准备分支试跑方案并单独确认，其他条件文件图不猜；不沿用普通文件试跑批准。'

def config(node):return node['config'] if isinstance(node.get('config'),dict) else {}

def graph_errors(nodes,edges):
 by_id={n.get('id'):n for n in nodes if isinstance(n,dict) and isinstance(n.get('id'),str)}
 starts=[n for n in by_id.values() if n.get('type')=='start'];optional={}
 for start in starts:
  rows=config(start).get('variables',[])
  for row in rows if isinstance(rows,list) else []:
   if isinstance(row,dict) and isinstance(row.get('variable'),str) and row.get('type')=='file' and row.get('required') is False:optional[(start['id'],row['variable'])]=row
 if not optional:return []
 errors=[];successors={nid:[] for nid in by_id}
 for edge in edges:
  if isinstance(edge,dict) and isinstance(edge.get('source'),str) and isinstance(edge.get('target'),str) and edge['source'] in by_id and edge['target'] in by_id:successors[edge['source']].append((edge['target'],edge.get('source_handle','source')))
 for consumer in by_id.values():
  if consumer.get('type')!='document-extractor':continue
  selector=config(consumer).get('variable_selector')
  if not isinstance(selector,list) or len(selector)!=2 or not all(isinstance(x,str) for x in selector) or tuple(selector) not in optional:continue
  if consumer.get('parentId') is not None:
   errors.append(f'可选文件提取 {consumer["id"]} 的容器内存在保护尚未适配，不能借根分支推定内层路径。');continue
  source=selector[0];protected=False
  for guard in by_id.values():
   cases=config(guard).get('cases')
   if guard.get('type')!='if-else' or guard.get('parentId') is not None or not isinstance(cases,list) or len(cases)!=1 or not isinstance(cases[0],dict):continue
   case=cases[0];conditions=case.get('conditions')
   if not isinstance(case.get('logical_operator'),str) or case['logical_operator'] not in {'and','or'} or not isinstance(conditions,list) or len(conditions)!=1 or not isinstance(conditions[0],dict):continue
   c=conditions[0];op=c.get('comparison_operator');cid=case.get('case_id')
   if set(c)-{'id','variable_selector','varType','comparison_operator','value'} or c.get('variable_selector')!=selector or c.get('varType')!='file' or not isinstance(op,str) or op not in {'exists','not exists'} or c.get('value') not in ('',None) or not isinstance(cid,str) or not cid:continue
   handle=cid if op=='exists' else 'false';exits=[(target,h) for target,h in successors[guard['id']] if h==handle]
   if len(exits)!=1:continue
   normal=reachable(source,successors);bypass=reachable(source,successors,(guard['id'],exits[0][0],handle))
   if consumer['id'] in normal and consumer['id'] not in bypass:protected=True;break
  if not protected:errors.append(f'可选单文件提取 {consumer["id"]} 必须受同一根文件变量的独立exists／not exists分支保护；缺失路径不得绕回提取，不猜多条件或多case含义。')
 return errors

def require_native(root):
 graph=root['workflow']['graph'];nodes=[]
 if not any(n.get('data',{}).get('type')=='start' and isinstance(n['data'].get('variables'),list) and any(isinstance(r,dict) and r.get('type')=='file' and r.get('required') is False for r in n['data']['variables']) for n in graph['nodes']):return
 for node in graph['nodes']:
  data=node['data'];cfg={}
  if data.get('type')=='start':cfg={'variables':data.get('variables',[])}
  elif data.get('type')=='if-else':
   cases=data.get('cases',[]);cfg={'cases':[{**c,'case_id':c.get('case_id',c.get('id'))} if isinstance(c,dict) else c for c in cases] if isinstance(cases,list) else cases}
  elif data.get('type')=='document-extractor':cfg={'variable_selector':data.get('variable_selector')}
  nodes.append({'id':node['id'],'type':data.get('type'),'config':cfg,'parentId':node.get('parentId')})
 edges=[{'source':e.get('source'),'target':e.get('target'),'source_handle':e.get('sourceHandle','source')} for e in graph['edges']]
 errors=graph_errors(nodes,edges)
 if any(n['type']=='start' and isinstance(config(n).get('variables'),list) and any(isinstance(r,dict) and r.get('type')=='file' and r.get('required') is False for r in config(n)['variables']) for n in nodes):
  from .node_policy import validate
  for node in graph['nodes']:
   data=node['data']
   if data.get('type') in {'start','if-else','document-extractor','end'} and data.get('version','1')!='1':errors.append('可选文件的入口、存在判断、提取与结束仅适配原生版本1，不投影丢弃未知版本。')
   if data.get('type')=='if-else':
    from .document_extractor import EDITOR_FIELDS
    from .node_policy import FIELDS
    errors.extend(validate(data))
    if set(data)-EDITOR_FIELDS-FIELDS-{'cases'}:errors.append('文件存在判断含未知执行或旧条件字段，不省略后声称存在保护已核对。')
 if errors:raise ValueError('；'.join(errors))
