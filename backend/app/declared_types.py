"""Infer only explicit selector declarations; no business values or model calls."""
KNOWN={'string','number','boolean','object','file','array[string]','array[number]','array[boolean]','array[object]','array[file]'}

def resolve(nodes,selector,scope=None,mode=None):
 if not isinstance(selector,list) or len(selector)!=2 or not all(isinstance(v,str) for v in selector):return None
 key=tuple(selector)
 if scope and key in scope:return scope[key] if isinstance(scope[key],str) and scope[key] in KNOWN else None
 if selector==['sys','query']:return 'string' if mode=='advanced-chat' else None
 node=nodes.get(selector[0],{});cfg=node.get('config');field=selector[1]
 if not isinstance(cfg,dict):return None
 kind=node.get('type')
 if not isinstance(kind,str):return None
 if kind=='llm':
  if field=='structured_output':
   from .structured_output import output_type
   return output_type(cfg)
  return {'text':'string','usage':'object','finish_reason':'string'}.get(field)
 if kind=='question-classifier':return {'class_id':'string','class_name':'string','class_label':'string','usage':'object'}.get(field)
 if kind=='parameter-extractor':
  from .parameter_extractor import output_types
  return output_types(cfg).get(field)
 if kind=='list-operator':
  value=cfg.get('input_type');return value if field=='result' and isinstance(value,str) and value in {'array[string]','array[number]','array[boolean]'} else None
 if kind=='document-extractor':return ('string' if cfg.get('input_type')=='file' else 'array[string]' if cfg.get('input_type')=='array[file]' else None) if field=='text' else None
 if kind=='template-transform':return 'string' if field=='output' else None
 if kind=='knowledge-retrieval':return 'array[object]' if field=='result' else None
 if kind=='http-request':return {'body':'string','status_code':'number','headers':'object','files':'array[file]'}.get(field)
 if kind=='variable-aggregator' or kind=='iteration':
  value=cfg.get('output_type');return value if field=='output' and isinstance(value,str) and value in KNOWN else None
 if kind=='code':
  schema=cfg.get('outputs',{});value=schema.get(field) if isinstance(schema,dict) else None
  value=value.get('type') if isinstance(value,dict) else None
  return value if isinstance(value,str) and value in KNOWN else None
 if kind=='start':
  from .start_inputs import declared_type
  return declared_type(cfg.get('variables'),field)
 if kind=='loop':
  rows=cfg.get('loop_variables');found=[v for v in rows if isinstance(v,dict) and v.get('label')==field] if isinstance(rows,list) else []
  value=found[0].get('var_type') if len(found)==1 else None
  return value if isinstance(value,str) and value in {'string','number','boolean'} else None
 return None

def container_scope(node,outer,scope=None,mode=None):
 result={}
 if not isinstance(node.get('id'),str):return result
 # Only explicit known outside declarations. Actual dominance is still validated.
 for source in outer.values():
  cfg=source.get('config',{})
  if not isinstance(cfg,dict) or not isinstance(source.get('type'),str):continue
  fields=[]
  if source.get('type')=='code' and isinstance(cfg.get('outputs'),dict):fields=list(cfg['outputs'])
  elif source.get('type')=='start' and isinstance(cfg.get('variables'),list):fields=[v.get('variable') for v in cfg['variables'] if isinstance(v,dict)]
  elif source.get('type')=='loop' and isinstance(cfg.get('loop_variables'),list):fields=[v.get('label') for v in cfg['loop_variables'] if isinstance(v,dict)]
  elif source.get('type')=='document-extractor':fields=['text']
  elif source.get('type')=='list-operator':fields=['result']
  elif source.get('type')=='parameter-extractor':
   from .parameter_extractor import output_types
   fields=list(output_types(cfg))
  else:fields={'llm':['text','usage','finish_reason'],'question-classifier':['class_id','class_name','class_label','usage'],'template-transform':['output'],'knowledge-retrieval':['result'],'http-request':['body','status_code','files'],'iteration':['output'],'variable-aggregator':['output']}.get(source.get('type'),[])
  if source.get('type')=='llm' and cfg.get('structured_output_enabled') is True:fields=[*fields,'structured_output']
  for field in fields:
   if isinstance(field,str):result[(source['id'],field)]=resolve(outer,[source['id'],field],scope,mode)
 if mode=='advanced-chat':result[('sys','query')]='string'
 cfg=node.get('config',{});nid=node['id']
 if node.get('type')=='iteration':
  kind=cfg.get('iterator_input_type');actual=resolve(outer,cfg.get('iterator_selector'),scope,mode)
  result[(nid,'item')]=kind[6:-1] if isinstance(kind,str) and kind in {'array[string]','array[number]','array[object]','array[file]'} and kind==actual else None
  result[(nid,'index')]='number'
 elif node.get('type')=='loop':
  rows=cfg.get('loop_variables',[])
  if isinstance(rows,list):
   for row in rows:
    if isinstance(row,dict) and isinstance(row.get('label'),str):result[(nid,row['label'])]=resolve(outer,[nid,row['label']],scope,mode)
 return result
