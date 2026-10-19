"""Fixed native extraction status only; never copy business output or reason."""
def extract(row):
 if row.get('node_type')=='http-request':
  outputs=row.get('outputs');truncated=row.get('outputs_truncated');code=outputs.get('status_code') if isinstance(outputs,dict) else None
  known=(truncated is None or truncated is False) and type(code) is int and 100<=code<=599
  return {'http_status_code':code if known else None,'http_status_class':('2xx' if 200<=code<=299 else 'non_2xx') if known else 'unknown','basis':'native_http_status_code','note':'仅原生HTTP状态码，不保存URL、请求头、返回体、文件或实际输入；2xx不证明业务成功，未知不按成功或失败处理。'}
 if row.get('node_type')!='parameter-extractor':return None
 outputs=row.get('outputs');truncated=row.get('outputs_truncated')
 flag=outputs.get('__is_success') if isinstance(outputs,dict) else None
 status='unknown'
 if (truncated is None or truncated is False) and type(flag) in (int,float) and flag in (0,1):status='extracted' if flag==1 else 'not_extracted'
 return {'extraction_status':status,'basis':'native_extraction_flag','note':'仅原生提取标识，不证明业务非空、格式、真实性或验收；不保存实际参数或__reason。未知不按成功或失败处理。'}

def finding(node):
 observations=node.get('observations') or {}
 if node.get('status')=='succeeded' and observations.get('http_status_class')=='non_2xx':
  return {'category':'http_response_business_check','title':'HTTP节点执行完成，响应不是2xx','basis':'native_http_status_code','confidence':'已记录','node_type':'http-request','node_id':node['node_id'],'execution_id':node['id'],'recommendation':f"已记录HTTP状态码 {observations['http_status_code']}。本机目标版本关闭重试且无异常策略时，非2xx可仍为节点成功；请核对已确认的可接受状态码、返回体和业务分支。404无记录、304未修改等也可能是明确业务结果，不能自动把整体或样例改判失败。2xx同样不保证业务正确；更改重试会改变请求次数及费用，不能为消除提示而自动启用重试或改验收。"}
 if node.get('status')!='succeeded' or (node.get('observations') or {}).get('extraction_status')!='not_extracted':return None
 return {'category':'extraction_not_completed','title':'节点执行完成，但参数未提取成功','basis':'native_extraction_flag','confidence':'已记录','node_type':'parameter-extractor','node_id':node['node_id'],'execution_id':node['id'],'recommendation':'原生 __is_success=0；默认空值、0或False不能当成真实参数。核对当前成功检查与已确认的失败分支（追问、明确无法处理等）；若业务原本期望追问，可按该样例验收，不擅自把运行改判失败。不要删除检查、编造参数或只靠节点执行成功计业务成功。标识为1也仍须业务值校验；这里只提示，不改方案或重跑。'}
