"""Common execution fields must not vanish through native graph projection."""
FIELDS={'retry_config','error_strategy','default_value'}

def validate(data):
 errors=[]
 if data.get('error_strategy') is not None:errors.append('节点错误策略（异常默认／失败分支）尚未适配，不会删除执行策略后声称原流程已保留。')
 if data.get('default_value') not in (None,[]):errors.append('节点存在未适配的异常默认值，不能把替代结果当作正常输出。')
 if 'retry_config' in data:
  retry=data['retry_config']
  if not isinstance(retry,dict) or set(retry)-{'retry_enabled','max_retries','retry_interval'}:errors.append('节点重试配置结构或字段未适配，不会投影丢弃。')
  else:
   if type(retry.get('retry_enabled',False)) is not bool or retry.get('retry_enabled',False):errors.append('当前节点已启用或未明确布尔的原生重试尚未适配；调用次数、费用及失败行为须先协商。')
   if any(type(retry.get(k,0)) is not int or retry.get(k,0)<0 for k in ('max_retries','retry_interval')):errors.append('关闭节点重试时，原次数／间隔仍须为非负整数，不隐式转换。')
 return errors

def validate_ir(kind,config):
 if kind!='http-request' and FIELDS.intersection(config):return ['当前节点计划不支持retry_config／error_strategy／default_value，不能省略配置后生成；原生手改保留仅支持已关闭的已知设置。']
 return []

def require_native(root):
 workflow=root.get('workflow') if isinstance(root,dict) else None
 graph=workflow.get('graph') if isinstance(workflow,dict) else None
 rows=graph.get('nodes') if isinstance(graph,dict) else None
 if not isinstance(rows,list):raise ValueError('实际工作流节点数组无效，不能核对执行策略。')
 issues=[]
 for index,node in enumerate(rows):
  data=node.get('data') if isinstance(node,dict) else None
  if not isinstance(data,dict):raise ValueError(f'实际节点 /workflow/graph/nodes/{index}/data 结构无效，不能核对执行策略。')
  kind=data.get('type')
  if kind=='http-request':
   from .http_execution import preserved
   try:preserved(data)
   except ValueError as exc:issues.append(f'实际节点 /workflow/graph/nodes/{index}/data 的HTTP执行策略未适配：'+str(exc))
  else:
   errors=validate(data)
   if kind=='code':
    from .file_join import validate_native
    errors+=validate_native(data)
   if errors:issues.append(f'实际节点 /workflow/graph/nodes/{index}/data 的执行策略未适配：'+'；'.join(errors))
 if issues:raise ValueError('\n'.join(issues))
