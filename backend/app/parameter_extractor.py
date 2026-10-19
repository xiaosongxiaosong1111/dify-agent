"""Text parameter extraction with a mandatory explicit success/failure gate."""
import copy,re
from .model_parameters import validate_node_model,resolve_node_model
from .conversation import memory_configuration

TYPES={'string','number','boolean','array[string]','array[number]','array[boolean]'}
NOTE='原生参数提取可能整体节点成功却返回 __is_success=0 及默认值；必须检查成功标识后才使用业务参数。required 只约束原生提取，不保证业务非空、格式或真实性，成功后仍需必要业务校验。'

def validate(cfg):
 errors=[]
 if set(cfg)-{'query','parameters','instruction','reasoning_mode','model','failure_policy'}:errors.append('参数提取含未适配设置；首批仅文字、prompt推理、固定参数，不支持图片／独立记忆／动态参数或其他模式。')
 query=cfg.get('query')
 if not isinstance(query,list) or len(query)!=2 or not all(isinstance(x,str) and x for x in query):errors.append('参数提取须明确 query=[上游节点ID,文字变量]。')
 parameters=cfg.get('parameters');names=[]
 if not isinstance(parameters,list) or not 1<=len(parameters)<=20:errors.append('参数提取需要 1—20 个明确参数。');parameters=[]
 for parameter in parameters:
  if not isinstance(parameter,dict) or set(parameter)-{'name','type','description','required','options'}:errors.append('每个参数只支持 name/type/description/required/可选options。');continue
  name=parameter.get('name');kind=parameter.get('type')
  if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',name) or name.startswith('__'):errors.append('参数名须为 1—64 位英文标识符，双下划线为原生状态字段保留。')
  else:names.append(name)
  if not isinstance(kind,str) or kind not in TYPES:errors.append('参数类型仅支持 string/number/boolean 及对应数组，不猜bool/select或对象结构。')
  if type(parameter.get('required')) is not bool:errors.append('每个参数须明确 required 布尔值，不能猜是否必需。')
  description=parameter.get('description')
  if not isinstance(description,str) or not 0<len(description.strip())<=2000 or '{{#' in description:errors.append('参数 description 须为 1—2000 字符的实际规则，不支持动态模板。')
  options=parameter.get('options')
  if options is not None and (kind!='string' or not isinstance(options,list) or not 1<=len(options)<=20 or not all(isinstance(v,str) and 0<len(v)<=128 for v in options) or len(options)!=len(set(options))):errors.append('options 仅用于文字参数，须为 1—20 个唯一非空文字枚举。')
 if len(names)!=len(set(names)):errors.append('参数名重复，不能覆盖输出。')
 if cfg.get('reasoning_mode')!='prompt':errors.append('首批提取须明确 reasoning_mode=prompt，不假设模型支持工具调用。')
 instruction=cfg.get('instruction','')
 if not isinstance(instruction,str) or len(instruction)>10000 or '{{#' in instruction:errors.append('提取 instruction 须为最多10000字符文字，不支持动态模板。')
 policy=cfg.get('failure_policy')
 if not isinstance(policy,dict) or set(policy)!={'behavior','guard_node_id','success_case_id'} or policy.get('behavior')!='explicit_success_branch' or not all(isinstance(policy.get(k),str) and policy[k] for k in ('guard_node_id','success_case_id')):errors.append('请明确 failure_policy 的成功检查节点／成功case，不能把默认值当提取成功。')
 if 'model' in cfg:
  try:validate_node_model(cfg['model'])
  except ValueError as exc:errors.append(str(exc))
 return errors

def output_types(cfg):
 result={'__is_success':'number','__reason':None,'__usage':'object'}
 for p in cfg.get('parameters',[]) if isinstance(cfg.get('parameters'),list) else []:
  if isinstance(p,dict) and isinstance(p.get('name'),str) and isinstance(p.get('type'),str) and p['type'] in TYPES:result[p['name']]=p['type']
 return result

def guards(nodes,successors):
 errors=[];targets={}
 for node in nodes.values():
  if node['type']!='parameter-extractor':continue
  nid=node['id'];policy=node['config'].get('failure_policy')
  if not isinstance(policy,dict):continue
  guard_id=policy.get('guard_node_id');guard=nodes.get(guard_id) if isinstance(guard_id,str) else None;success_id=policy.get('success_case_id')
  if not guard or guard['type']!='if-else' or successors.get(nid)!=[(guard_id,'source')]:errors.append(f'提取 {nid} 须唯一直接接声明的成功检查 IF，不能绕过检查。');continue
  cases=guard['config'].get('cases')
  valid=isinstance(cases,list) and len(cases)==1 and isinstance(cases[0],dict) and cases[0].get('case_id')==success_id and cases[0].get('logical_operator')=='and'
  conditions=cases[0].get('conditions') if valid else None
  valid=valid and isinstance(conditions,list) and len(conditions)==1 and isinstance(conditions[0],dict)
  c=conditions[0] if valid else {}
  if not valid or c.get('variable_selector')!=[nid,'__is_success'] or c.get('varType')!='number' or c.get('comparison_operator')!='=' or c.get('value')!='1':errors.append(f'提取 {nid} 成功检查须为 __is_success 数值等于文字1；其他业务条件应在成功分支另行检查。');continue
  next_nodes=[target for target,handle in successors.get(guard_id,[]) if handle==success_id]
  if len(next_nodes)==1:targets[nid]=next_nodes[0]
  else:errors.append(f'提取 {nid} 缺少唯一成功出口。')
 return errors,targets

def native(cfg,task_config,mode):
 result={k:copy.deepcopy(cfg[k]) for k in ('query','parameters','reasoning_mode')};result.update(instruction=cfg.get('instruction',''),model=resolve_node_model(cfg,task_config),vision={'enabled':False})
 memory=memory_configuration(mode,task_config)
 if memory is not None:result['memory']=memory
 return result

def preserved(data,mode,node_id,graph):
 # Reuse the exact supported model/vision/history checks; the temporary
 # classifier DTO is only a validation carrier and is never written back.
 from .question_classifier import preserved as text_model_preserved
 carrier={'classes':[{'id':'a','name':'a'},{'id':'b','name':'b'}],'query_variable_selector':data.get('query'),'model':data.get('model'),'instruction':data.get('instruction')}
 for field in ('vision','memory'):
  if field in data:carrier[field]=data[field]
 checked=text_model_preserved(carrier,mode)
 outgoing=[e for e in graph['edges'] if e.get('source')==node_id]
 if len(outgoing)!=1 or outgoing[0].get('sourceHandle','source')!='source':raise ValueError('实际提取节点须唯一直接连接成功检查，不能改写或补造保护。')
 guard_id=outgoing[0]['target'];matches=[n for n in graph['nodes'] if n.get('id')==guard_id]
 if len(matches)!=1 or matches[0].get('data',{}).get('type')!='if-else':raise ValueError('实际提取缺少 IF 成功检查，不能自动插入后宣称保留。')
 cases=matches[0]['data'].get('cases')
 case_id=cases[0].get('case_id',cases[0].get('id')) if isinstance(cases,list) and len(cases)==1 and isinstance(cases[0],dict) else None
 cfg={'query':copy.deepcopy(data.get('query')),'parameters':copy.deepcopy(data.get('parameters')),'reasoning_mode':data.get('reasoning_mode'),'model':checked['model'],'instruction':checked['instruction'],'failure_policy':{'behavior':'explicit_success_branch','guard_node_id':guard_id,'success_case_id':case_id}}
 errors=validate(cfg)
 if errors:raise ValueError('实际提取配置不能安全保留：'+'；'.join(errors))
 return cfg
