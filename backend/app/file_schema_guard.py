"""Exact generated schema guard disclosure for supported file/model flows."""
import copy,hashlib,json
from .structured_guard import guard_code,digest,validate_native

VERIFICATION='canonical_code_and_binding_static_only'
FAILURE='fail_workflow_no_defaults_no_retry'

def metadata(node,source,schema,selector):
 data=node['data'];source_id=source['id']
 if not isinstance(node.get('id'),str) or not node['id'] or node['id']==source_id:raise ValueError('文件Schema校验须有唯一独立节点ID。')
 errors=validate_native(data)
 if errors:raise ValueError('文件Schema校验未保留原失败保护：'+'；'.join(errors))
 if data.get('type')!='code' or data.get('code_language')!='python3' or data.get('variables')!=[{'variable':'data','value_selector':[source_id,'structured_output']}] or data.get('outputs')!={'result':{'type':'object','children':None}} or data.get('code')!=guard_code(schema):raise ValueError('文件试跑只适配完整Sierra v1生成Schema检查代码及原对象绑定；手改代码、语言、Schema或输入输出不能沿用原保护。')
 if any(data.get(k) is not None and data.get(k) is not False for k in ('isInIteration','isInLoop')) or any(data.get(k) is not None for k in ('iteration_id','loop_id')):raise ValueError('文件Schema校验须为根节点，不借用容器状态。')
 if selector not in ([source_id,'structured_output'],[node['id'],'result']):raise ValueError('文件Schema校验结束须返回原模型对象或此校验的result，不推断其他字段。')
 return {'node_id':node['id'],'source_node_id':source_id,'input_variable':'data','output_variable':'result','end_selector':copy.deepcopy(selector),'recipe':'sierra_strict_schema_guard_v1','schema_sha256':digest(schema),'schema_text_sha256':hashlib.sha256(json.dumps(schema,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')).hexdigest(),'code_sha256':hashlib.sha256(data['code'].encode('utf-8')).hexdigest(),'code_text':data['code'],'failure_behavior':FAILURE,'verification':VERIFICATION,'platform_checked':False,'business_verified':False}

def validate_saved(value,source_id,schema):
 """Validate the full original declaration without implying actual node execution."""
 if not isinstance(value,dict) or not isinstance(value.get('node_id'),str) or not value['node_id'] or value['node_id']==source_id:raise ValueError('原文件Schema校验声明不完整。')
 node={'id':value['node_id'],'data':{'type':'code','code_language':'python3','code':guard_code(schema),'variables':[{'variable':'data','value_selector':[source_id,'structured_output']}],'outputs':{'result':{'type':'object','children':None}}}}
 if digest(value)!=digest(metadata(node,{'id':source_id},schema,value.get('end_selector'))):raise ValueError('原文件Schema校验的完整代码、绑定或失败规则不匹配。')
