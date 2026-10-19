"""Typed HTTP array extraction or protected single-file iteration item extraction."""
import copy

NOTE='数组文档提取接原生HTTP.files或根Workflow明确文件列表，输出text为逐文件文字数组，空输入返回空数组；单文件接受根Workflow必填单文件、经独立存在分支保护的可选单文件或受保护原生文件迭代item，输出text字符串，缺失或解析失败终止。不能只按标记猜类型。按文件顺序提取，任一文件失败会使节点失败，不跳过坏文件。扫描PDF可能没有文字，不提供OCR；DOC／PPT／PPTX／EPUB／ODT等格式可能经目标Dify配置的Unstructured服务发送文件并产生额外费用，须在资料、环境与资源方案中明确核对。不承诺格式、编码或表格原样保留。HTTP获取、文件下载及解析仍需实际资源／权限／格式核对。当前只适配关闭节点重试、没有异常默认／失败分支的策略；手改存在未适配执行设置须先协商，不删除后当作整批失败。节点策略不承诺底层解析器没有内部恢复。'

def validate(cfg):
 errors=[]
 if set(cfg)!={'variable_selector','input_type','empty_policy'}:errors.append('文档提取须明确variable_selector、input_type、empty_policy；不支持OCR、格式转换、任意解析参数或服务密钥，不能默默省略。')
 selector=cfg.get('variable_selector')
 if not isinstance(selector,list) or len(selector)!=2 or not all(isinstance(v,str) and v for v in selector):errors.append('文档提取须明确[开始节点ID,文件变量]、[HTTP节点ID,files]或受保护文件迭代[item]的两段selector，不能把URL／文字／对象当成文件。')
 if not isinstance(cfg.get('input_type'),str) or cfg.get('input_type') not in {'array[file]','file'}:errors.append('文档提取须明确array[file]或受保护文件迭代item的file类型，不猜未知输入。')
 expected='return_empty_array' if cfg.get('input_type')=='array[file]' else 'fail_if_missing'
 if cfg.get('empty_policy')!=expected:errors.append('文档提取空输入政策与实际类型不符；文件数组须return_empty_array，单文件须fail_if_missing，不能跳过坏文件。')
 return errors

def native(cfg):return {'variable_selector':copy.deepcopy(cfg['variable_selector']),'is_array_file':cfg['input_type']=='array[file]'}

def preserved(data):
 policy_errors=validate_native_policy(data)
 if policy_errors:raise ValueError('实际文档提取配置无法保留：'+'；'.join(policy_errors))
 if type(data.get('is_array_file')) is not bool:raise ValueError('实际文档提取须明确布尔is_array_file标记，并核对真实来源类型；不静默猜测或修正。')
 is_array=data['is_array_file']
 cfg={'variable_selector':copy.deepcopy(data.get('variable_selector')),'input_type':'array[file]' if is_array else 'file','empty_policy':'return_empty_array' if is_array else 'fail_if_missing'}
 errors=validate(cfg)
 if errors:raise ValueError('实际文档提取配置无法保留：'+'；'.join(errors))
 return cfg


# Inert editor metadata is retained; execution policy must match this subset.
EDITOR_FIELDS={'type','title','desc','selected','version','isInIteration','isInLoop','iteration_id','loop_id','width','height','position',
 '_connectedSourceHandleIds','_connectedTargetHandleIds','_targetBranches','_isSingleRun','_runningStatus','_runningBranchId','_singleRunningStatus','_isCandidate','_isBundled','_children','_isEntering','_showAddVariablePopup','_holdAddVariablePopup','_iterationLength','_iterationIndex','_waitingRun','_retryIndex','_dataSourceStartToAdd','_isTempNode','_openInlineAgentPanel','_loopLength','_loopIndex','_dimmed'}

def validate_native_policy(data):
 errors=[]
 if set(data)-EDITOR_FIELDS-{'variable_selector','is_array_file','retry_config','error_strategy','default_value'}:
  errors.append('实际文档提取含未适配的执行／解析或额外字段，原值保持；不会投影丢弃后声称策略已保留。')
 if data.get('version','1')!='1':errors.append('实际文档提取仅适配版本1，不自动升级或删除未知版本。')
 if data.get('error_strategy') is not None:errors.append('文档提取的异常默认／失败分支策略尚未适配，不能当作任一文件失败即整批失败。')
 if data.get('default_value') not in (None,[]):errors.append('文档提取存在未适配的异常默认值，不会忽略或代替解析结果。')
 if 'retry_config' in data:
  retry=data['retry_config']
  if not isinstance(retry,dict) or set(retry)-{'retry_enabled','max_retries','retry_interval'}:
   errors.append('文档提取重试配置结构／字段尚未适配，不会移除后通过。')
  else:
   if type(retry.get('retry_enabled',False)) is not bool or retry.get('retry_enabled',False):errors.append('文档提取已启用或未明确布尔的节点重试尚未适配，次数／费用及失败行为须先协商。')
   if any(type(retry.get(k,0)) is not int or retry.get(k,0)<0 for k in ('max_retries','retry_interval')):errors.append('文档提取未启用重试的次数／间隔仍须为非负整数，不隐式转换。')
 return errors

def require_native_policy(root):
 from .optional_file import require_native
 require_native(root)
 for node in root['workflow']['graph']['nodes']:
  data=node.get('data',{})
  if data.get('type')=='document-extractor':
   errors=validate_native_policy(data)
   if errors:raise ValueError('文档提取实际策略无法按已适配方案执行／导入：'+'；'.join(errors))
