"""Bounded native retrieval facts, without question, content, names or arbitrary metadata."""
import math,uuid

NOTE='仅原生检索result列表及白名单来源ID/分数；片段返回不证明有答案或业务相关性达标，分数跨库/模型不可直接比较，低相关须结合原文与代表问题人工复核。不保存问题、正文、标题、文件或任意metadata；不改验收、阈值或自动重跑。'


def identifier(value,secrets):
 if not isinstance(value,str) or any(isinstance(secret,str) and len(secret)>=4 and secret in value for secret in secrets):return None
 try:return str(uuid.UUID(value)) if len(value)==36 else None
 except (ValueError,TypeError,AttributeError):return None


def score(value):
 if type(value) not in (int,float):return None
 try:return value if math.isfinite(value) and abs(value)<=9007199254740991 else None
 except (ValueError,OverflowError):return None


def extract(row,secrets=()):
 status='unknown';results=None
 if row.get('status') in {'failed','exception'} or row.get('error'):
  status='technical_failure'
 elif row.get('status')=='succeeded' and (row.get('outputs_truncated') is None or row.get('outputs_truncated') is False):
  outputs=row.get('outputs');value=outputs.get('result') if isinstance(outputs,dict) else None
  if isinstance(value,list) and len(value)<=1000 and all(isinstance(v,dict) for v in value):
   results=value;status='returned' if results else 'empty'
 sources=[]
 for index,part in enumerate((results or [])[:20]):
  metadata=part.get('metadata');metadata=metadata if isinstance(metadata,dict) else {}
  sources.append({'position':index+1,**{key:identifier(metadata.get(key),secrets) for key in ('dataset_id','document_id','segment_id')},'score':score(metadata.get('score'))})
 return {'retrieval_status':status,'result_count':len(results) if results is not None else None,'sources':sources,'sources_truncated':results is not None and len(results)>20,'basis':'native_retrieval_result','note':NOTE}


def finding(node):
 observation=node.get('observations') or {};status=observation.get('retrieval_status')
 messages={
  'empty':('retrieval_empty','检索执行成功，本次无命中片段','已记录','原生result是完整空列表；无命中不等于知识库没有答案。核对问题、实际资料/索引、检索配置和已确认的无命中分支；无命中本身也不自动判样例失败，不自动调阈值或重跑。'),
  'returned':('retrieval_returned','检索已返回片段，答案与相关性仍须核对','已记录','核对代表问题、片段原文和白名单来源ID；返回数量或平台分数不能单独证明有答案、高相关或业务通过。低相关需人工判断，不自动改验收或重跑。'),
  'unknown':('retrieval_unknown','检索结果证据不足，不能按无命中处理','未知','结果缺失、非列表、条目不兼容、超出1000项、已截断或节点尚未明确成功；只能说明当前不能核对，不能把缺失当空列表、无答案或检索成功。旧诊断不补猜，需要新采集仍须原资源范围。'),
  'technical_failure':('retrieval_technical_failure','检索节点技术失败，不是无命中','已记录','先按原始失败节点及脱敏错误核对类型、连接、权限、索引或模型条件；技术失败不能用无资料回复掩盖，不通过删除检索、换空默认值或自动重跑绕过。')}
 if status not in messages:return None
 category,title,confidence,recommendation=messages[status]
 return {'category':category,'title':title,'confidence':confidence,'recommendation':recommendation,'basis':'native_retrieval_result','node_type':'knowledge-retrieval','node_id':node['node_id'],'execution_id':node['id']}
