"""Exact optional-file presence branch, no model/custom code or path deletion."""
from .document_extractor import EDITOR_FIELDS
from .node_policy import FIELDS,require_native
from .optional_file import require_native as require_presence
from .file_run_flow import FEATURES

def describe(root):
 graph=root['workflow']['graph'];nodes=graph['nodes']
 if sorted(n['data']['type'] for n in nodes)!=['document-extractor','end','end','if-else','start'] or any(n.get('parentId') for n in nodes):raise ValueError('可选文件试跑首批仅五个根节点：开始、独立文件存在判断、单文件提取、文字结果结束及无文件说明结束；不删除其他路径、容器、模型或代码。')
 features=root['workflow'].get('features')
 if not isinstance(features,dict) or set(features)!=FEATURES or any(not isinstance(features[k],dict) or features[k].get('enabled') is not False for k in FEATURES-{'opening_statement','suggested_questions'}):raise ValueError('可选文件试跑要求已知全局功能明确关闭，不猜隐藏数据流。')
 if root['workflow'].get('environment_variables')!=[] or root['workflow'].get('conversation_variables')!=[]:raise ValueError('可选文件试跑不带环境／会话变量，不隐式加入其他上下文。')
 allowed={'start':{'variables'},'if-else':{'cases'},'document-extractor':{'variable_selector','is_array_file'},'end':{'outputs'}}
 for node in nodes:
  data=node['data']
  if data.get('version','1')!='1' or set(data)-EDITOR_FIELDS-FIELDS-allowed[data['type']]:raise ValueError('可选文件节点含未知版本或执行字段，未删字段后运行。')
 require_native(root);require_presence(root)
 start=next(n for n in nodes if n['data']['type']=='start');guard=next(n for n in nodes if n['data']['type']=='if-else');extract=next(n for n in nodes if n['data']['type']=='document-extractor')
 fields=start['data'].get('variables');files=[v for v in fields if isinstance(v,dict) and v.get('type')=='file'] if isinstance(fields,list) else []
 if len(files)!=1 or len(fields)!=2 or files[0].get('required') is not False:raise ValueError('本批可选文件图须恰有一个可选单文件及一个明确缺失说明参数；其他入口不省略。')
 field=files[0];selector=[start['id'],field['variable']]
 if extract['data'].get('variable_selector')!=selector or extract['data'].get('is_array_file') is not False:raise ValueError('可选文件提取须绑定该根单文件，数组或未知来源不猜。')
 cases=guard['data'].get('cases');case=cases[0] if isinstance(cases,list) and len(cases)==1 and isinstance(cases[0],dict) else {};conditions=case.get('conditions');condition=conditions[0] if isinstance(conditions,list) and len(conditions)==1 and isinstance(conditions[0],dict) else {}
 cid=case.get('case_id',case.get('id'));op=condition.get('comparison_operator')
 if not isinstance(cid,str) or not cid or set(case)-{'case_id','id','logical_operator','conditions'} or any(case[k]!=cid for k in ('case_id','id') if k in case) or not isinstance(case.get('logical_operator'),str) or case['logical_operator'] not in {'and','or'} or condition.get('varType')!='file' or condition.get('variable_selector')!=selector or not isinstance(op,str) or op not in {'exists','not exists'} or condition.get('value') not in ('',None) or set(condition)-{'id','variable_selector','comparison_operator','varType','value'}:raise ValueError('可选文件试跑须有完整单条件exists／not exists判断，不猜多case、多条件、冲突标识或未知字段。')
 present_handle=cid if op=='exists' else 'false';missing_handle='false' if op=='exists' else cid
 ends=[n for n in nodes if n['data']['type']=='end'];present=[];missing=[]
 for end in ends:
  outputs=end['data'].get('outputs')
  if not isinstance(outputs,list) or len(outputs)!=1 or not isinstance(outputs[0],dict) or set(outputs[0])-{'variable','value_selector','value_type'} or not isinstance(outputs[0].get('variable'),str) or not outputs[0]['variable'] or outputs[0].get('value_type','string')!='string':raise ValueError('可选文件的两个结束节点须各有一个明确文字输出，不返回原文件对象或猜其他类型。')
  if outputs[0].get('value_selector')==[extract['id'],'text']:present.append(end)
  else:missing.append(end)
 if len(present)!=1 or len(missing)!=1:raise ValueError('须分别保留提取结果与无文件说明结束，不把两条路径合并或删除。')
 present=present[0];missing=missing[0];fallback=next(v for v in fields if v is not field);default=fallback.get('default');length=fallback.get('max_length')
 if fallback.get('type') not in {'text-input','paragraph'} or fallback.get('required') is not False or not isinstance(default,str) or not default.strip() or len(default)>2000 or '\x00' in default or type(length) is not int or not 1<=length<=2000 or len(default)>length:raise ValueError('无文件说明须是可选文字参数，明确非空默认值与1—2000字符上限；不隐式采用空值或改变默认说明。')
 try:default.encode('utf-8')
 except UnicodeError:raise ValueError('缺失说明默认值须为有效UTF-8，不修复或忽略字符。') from None
 if missing['data']['outputs'][0].get('value_selector')!=[start['id'],fallback['variable']] or missing['data']['outputs'][0]['variable']!=present['data']['outputs'][0]['variable']:raise ValueError('无文件结束须直接返回明确说明参数，且与提取路径使用同一输出名。')
 edges=graph.get('edges',[]);expected={(start['id'],guard['id'],'source'),(guard['id'],extract['id'],present_handle),(guard['id'],missing['id'],missing_handle),(extract['id'],present['id'],'source')}
 if len(edges)!=4 or {(e.get('source'),e.get('target'),e.get('sourceHandle','source')) for e in edges}!=expected:raise ValueError('可选文件图须严格按存在／缺失两条展示路径连接，不保留隐藏支线或绕回提取。')
 return {'schema_version':4,'scenario':'document_optional_extraction','node_types':['start','if-else','document-extractor','end','end'],'file_variable':field['variable'],'model_egress':False,'model_node':None,'prompt_template':[],'prompt_input_variables':[],'planned_llm_node_executions':0,'provider_endpoint_verified':False,'provider_internal_retries_verified':False,'cost_estimate_usd':None,'hard_cost_cap':False,'output_kind':'text','extraction':None,'join_policy':None,'resolved_branch':None,'optional_file':{'start_node_id':start['id'],'guard_node_id':guard['id'],'extract_node_id':extract['id'],'present_end_node_id':present['id'],'missing_end_node_id':missing['id'],'comparison_operator':op,'present_handle':present_handle,'missing_handle':missing_handle,'missing_message_variable':fallback['variable'],'missing_message_default':default,'missing_message_max_length':length,'output_variable':present['data']['outputs'][0]['variable'],'verification':'exact_presence_branch_static_only'}}

def resolve(flow,values,files):
 optional=flow['optional_file'];name=flow['file_variable'];state='omitted' if name not in values else 'explicit_null' if values[name] is None else 'uploaded_file';present=state=='uploaded_file'
 if len(files)!=(1 if present else 0):raise ValueError('文件存在路径与可信文件数量不一致，不猜输入或忽略坏文件。')
 text=values.get(optional['missing_message_variable'])
 if text is None:text=optional['missing_message_default']
 if not isinstance(text,str) or len(text)>optional['missing_message_max_length'] or '\x00' in text:raise ValueError('本次无文件说明须符合文字上限且不含NUL，不依赖平台隐式清洗。')
 try:text.encode('utf-8')
 except UnicodeError:raise ValueError('本次无文件说明编码无效，未忽略字符。') from None
 active=[optional['start_node_id'],optional['guard_node_id']]+([optional['extract_node_id'],optional['present_end_node_id']] if present else [optional['missing_end_node_id']])
 skipped=[optional['missing_end_node_id']] if present else [optional['extract_node_id'],optional['present_end_node_id']]
 return {'file_input_state':state,'expected_path':'file_present' if present else 'file_missing','expected_node_ids':active,'skipped_node_ids':skipped,'expected_end_node_id':optional['present_end_node_id'] if present else optional['missing_end_node_id'],'expected_outputs':None if present else {optional['output_variable']:text},'actual_path_verified':False}
