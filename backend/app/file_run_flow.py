"""Exact declared file data flows; no rewriting or inferred provider endpoints."""
import copy,re
from .document_extractor import EDITOR_FIELDS
from .model_parameters import validate_node_model
from .node_policy import FIELDS as POLICY_FIELDS,require_native

REF=re.compile(r'\{\{#([\w-]+)\.([\w-]+)#\}\}')
LLM_FIELDS=EDITOR_FIELDS|POLICY_FIELDS|{'model','prompt_template','context','vision','variables','memory','structured_output_enabled','structured_output'}
FEATURES={'file_upload','opening_statement','retriever_resource','sensitive_word_avoidance','suggested_questions','suggested_questions_after_answer','speech_to_text','text_to_speech'}

def describe(root):
 graph=root['workflow']['graph'];nodes=graph['nodes'];kinds=[n['data']['type'] for n in nodes]
 if any(v.get('type')=='file' and v.get('required') is False for n in nodes if n['data'].get('type')=='start' for v in n['data'].get('variables',[]) if isinstance(v,dict)):
  from .optional_file_run_flow import describe as optional_flow
  return optional_flow(root)
 from .structured_guard import MARKER
 combined=sorted(kinds)==['code','code','document-extractor','end','llm','start']
 code_model_flow=sorted(kinds)==['code','document-extractor','end','llm','start']
 codes=[n for n in nodes if n['data']['type']=='code']
 guards=[n for n in codes if isinstance(n['data'].get('code'),str) and n['data']['code'].startswith(MARKER)]
 model_flow=combined or code_model_flow or sorted(kinds)==['document-extractor','end','llm','start']
 structured=model_flow and next(n for n in nodes if n['data']['type']=='llm')['data'].get('structured_output_enabled') is True
 if combined and (not structured or len(guards)!=1):raise ValueError('六节点文件流程须明确启用对象输出、保留唯一Sierra Schema检查及独立规范拼接节点，不猜代码用途。')
 guard_flow=structured and (combined or code_model_flow and len(guards)==1)
 join_flow=combined or code_model_flow and not guard_flow
 guard_node=guards[0] if guard_flow else None
 join_node=next((n for n in codes if not guard_flow or n is not guard_node),None) if join_flow else None
 if not model_flow and sorted(kinds)!=['document-extractor','end','start']:raise ValueError('文件试跑支持三节点文档提取、四节点单文件LLM、五节点列表规范拼接或单文件Schema检查，以及六节点列表拼接后Schema检查；HTTP、自定义代码、分支、迭代、多个模型或其他节点不会被删除后执行。')
 if any(n.get('parentId') for n in nodes):raise ValueError('本批文件试跑仅根节点，不省略容器或上下文后执行。')
 if any(n['data'].get('version','1')!='1' for n in nodes):raise ValueError('本批文件流程只适配原生版本1节点，不忽略未知版本后运行。')
 features=root['workflow'].get('features')
 if not isinstance(features,dict) or set(features)!=FEATURES or any(not isinstance(features[k],dict) or features[k].get('enabled') is not False for k in FEATURES-{'opening_statement','suggested_questions'}):raise ValueError('本批文件流程要求全局上传、引用、敏感词、后续建议及语音功能明确关闭，且无未知特性；这些功能可能改变数据流，不自动关闭或猜默认。根文件变量不受全局上传开关代替。')
 if root['workflow'].get('environment_variables')!=[] or root['workflow'].get('conversation_variables')!=[]:raise ValueError('本批文件流程须无环境／会话变量，不隐式带入额外上下文或猜受保护值相等。')
 by_kind={n['data']['type']:n for n in nodes};start=by_kind['start'];extract=by_kind['document-extractor'];end=by_kind['end']
 fields=[v for v in start['data'].get('variables',[]) if v.get('type') in {'file','file-list'}]
 if len(fields)!=1:raise ValueError('文件试跑须有唯一明确的根文件变量，不猜文件或混用来源。')
 field=fields[0]
 if extract['data'].get('variable_selector')!=[start['id'],field['variable']]:raise ValueError('文档提取来源须为当前唯一文件变量。')
 join_policy=None
 if join_flow:
  from .file_join import from_native
  join=join_node;value=from_native(join['data'])
  if field['type']!='file-list' or field.get('max_length')!=value['max_files'] or extract['data'].get('is_array_file') is not True or join['data']['variables'][0]['value_selector']!=[extract['id'],'text']:raise ValueError('拼接输入／数组类型／数量与明确的文件列表声明不一致，不替换绑定。')
  join_policy={'node_id':join['id'],'policy':value,'verification':'canonical_code_and_binding_static_only'}
 chain=[start,extract]+([join_node] if join_flow else [])+([by_kind['llm']] if model_flow else [])+([guard_node] if guard_flow else [])+[end]
 edges=graph.get('edges',[]);expected={(a['id'],b['id']) for a,b in zip(chain,chain[1:])}
 if len(edges)!=len(expected) or {(e.get('source'),e.get('target')) for e in edges}!=expected:raise ValueError('本批文件试跑须按展示的顺序单一路径执行，不改变连接或忽略其他路径。')
 require_native(root)
 output_source=chain[-2];outputs=end['data'].get('outputs')
 output_schema=None
 if structured:
  from .json_inputs import schema
  declaration=by_kind['llm']['data'].get('structured_output')
  if not isinstance(declaration,dict) or set(declaration)!={'schema'}:raise ValueError('结构化文件LLM须带完整明确Schema，不省略未知字段。')
  output_schema=schema(declaration['schema'])
  allowed_selectors=[[by_kind['llm']['id'],'structured_output']]+([[guard_node['id'],'result']] if guard_flow else [])
  if not isinstance(outputs,list) or len(outputs)!=1 or not isinstance(outputs[0],dict) or outputs[0].get('value_selector') not in allowed_selectors or outputs[0].get('value_type','object')!='object':raise ValueError('结构化文件试跑仅一个结束输出，返回该LLM.structured_output对象或明确生成校验的result，不猜JSON文字或嵌套字段。')
 elif not isinstance(outputs,list) or not outputs or any(not isinstance(v,dict) or v.get('value_selector')!=[output_source['id'],'text'] for v in outputs):raise ValueError('本批结束输出须直接引用最后提取／LLM节点的text，不将文件对象或其他来源当作结果。')
 result={'schema_version':3,'extraction':None,'join_policy':join_policy,'scenario':'document_list_model' if join_flow else 'document_model' if model_flow else 'document_extraction','node_types':[n['data']['type'] for n in chain],'file_variable':field['variable'],'model_egress':model_flow,'model_node':None,'prompt_template':[],'prompt_input_variables':[],'planned_llm_node_executions':int(model_flow),'provider_endpoint_verified':False,'provider_internal_retries_verified':False,'cost_estimate_usd':None,'hard_cost_cap':False,'output_kind':'text-array' if field['type']=='file-list' and not model_flow else 'text'}
 if structured:
  import json
  result.update(schema_version=7 if join_flow else 5,scenario='document_list_model_object' if join_flow else 'document_model_object',output_kind='json-object',structured_output={'node_id':by_kind['llm']['id'],'output_variable':outputs[0]['variable'],'schema':copy.deepcopy(output_schema),'schema_text':json.dumps(output_schema,ensure_ascii=False,allow_nan=False,indent=2),'verification':'declared_schema_and_local_instance_check_only'})
 if guard_flow:
  from .file_schema_guard import metadata
  result.update(schema_version=8 if combined else 6,scenario='document_list_model_guarded_object' if combined else 'document_model_guarded_object',strict_guard=metadata(guard_node,by_kind['llm'],output_schema,outputs[0]['value_selector']))
 if not model_flow:return result
 if not join_flow and field['type']!='file':raise ValueError('直接进入LLM的路线仅适配单文件；文件列表须使用五节点规范拼接并明确分隔和长度政策，不擅自合并后发送。')
 data=by_kind['llm']['data']
 if set(data)-LLM_FIELDS:raise ValueError('文件LLM含未适配执行字段，不能省略字段后声称已完整展示数据流。')
 validate_node_model(data.get('model'))
 if not isinstance(data.get('title',by_kind['llm']['id']),str):raise ValueError('模型节点标题须为文字，不能转换未知结构。')
 if data.get('context')!={'enabled':False,'variable_selector':[]} or data.get('vision')!={'enabled':False} or data.get('variables',[])!=[] or data.get('memory') is not None:raise ValueError('文件LLM本批仅关闭检索上下文、视觉和记忆的文字提示词，不删除额外输入后运行。')
 if not structured and (data.get('structured_output_enabled',False) is not False or data.get('structured_output') not in (None,{}, {'schema':{}})):raise ValueError('文件LLM本批返回text；结构化输出的运行与验收尚待适配，不自动关闭。')
 prompts=data.get('prompt_template');refs=[];texts=[]
 if not isinstance(prompts,list) or not 1<=len(prompts)<=20:raise ValueError('文件LLM须有1—20条明确文字提示词，不截断。')
 for prompt in prompts:
  if not isinstance(prompt,dict) or set(prompt)-{'role','text','id','edition_type'} or prompt.get('role') not in {'system','user','assistant'} or not isinstance(prompt.get('text'),str) or prompt.get('edition_type','basic')!='basic':raise ValueError('文件LLM只支持完整展示的基础文字消息，不忽略未知附件、Jinja或提示词字段。')
  if 'id' in prompt and (not isinstance(prompt['id'],str) or not 1<=len(prompt['id'])<=200):raise ValueError('提示词ID结构未适配，原值不改。')
  text=prompt['text'];texts.append(text);refs.extend(REF.findall(text));rest=REF.sub('',text)
  if '{{#' in rest or '#}}' in rest:raise ValueError('提示词含未适配的变量引用，不猜实际数据去向。')
 try:
  if len(''.join(texts).encode('utf-8'))>64000:raise ValueError()
 except (ValueError,UnicodeError):raise ValueError('文件LLM提示词最多64000字节，须为有效UTF-8，不截断。') from None
 prompt_source=join_node if join_flow else extract
 allowed={(start['id'],v['variable']) for v in start['data'].get('variables',[]) if v.get('type') not in {'file','file-list'}}|{(prompt_source['id'],'text')}
 if (prompt_source['id'],'text') not in refs or any(ref not in allowed for ref in refs):raise ValueError('提示词须明确引用本次最终提取／拼接文字，且只能额外引用当前非文件开始变量；不把原文件、环境或系统变量隐式送出。')
 result.update(model_node={'id':by_kind['llm']['id'],'title':data.get('title',by_kind['llm']['id']),'model':copy.deepcopy(data['model'])},prompt_template=copy.deepcopy(prompts),prompt_input_variables=sorted({name for node,name in refs if node==start['id']}))
 return result
