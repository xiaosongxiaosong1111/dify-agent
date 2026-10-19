"""Explicit text classification branches for pinned Dify 1.17.1."""
import copy,re
from .model_parameters import validate_node_model,resolve_node_model
from .conversation import memory_configuration

FALLBACK_NOTE='Dify 1.17.1 对可解析 JSON 缺少分类字段或未知标量 category_id，会选择 classes 第一项；JSON 解析、返回字段格式／供应商错误可能直接失败，并非所有异常都回退。没有置信度输出或阈值保证，首项回退须纳入配置及样例确认。'

def validate(cfg):
 errors=[]
 if not isinstance(cfg,dict):return ['分类配置必须是对象。']
 if set(cfg)-{'classes','query_variable_selector','instruction','model','unmatched_policy'}:errors.append('分类节点存在未适配配置；首批不支持置信度阈值、文件／图片、独立记忆或自定义未匹配处理，不会静默省略。')
 classes=cfg.get('classes');ids=[];names=[]
 if not isinstance(classes,list) or not 2<=len(classes)<=20:errors.append('分类需要 2—20 项，保留明确的类别顺序。');classes=[]
 for row in classes:
  if not isinstance(row,dict) or set(row)-{'id','name','label'}:errors.append('分类项只支持 id／name／可选 label。');continue
  key=row.get('id')
  if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key) or key in {'source','false','true'}:errors.append('分类 id 须为 1—64 字符的字母／数字／下划线／连字符，不能用 source／false／true。')
  else:ids.append(key)
  name=row.get('name');label=row.get('label','')
  if not isinstance(name,str) or not 0<len(name.strip())<=2000 or '{{#' in name:errors.append('类别 name 须为 1—2000 字符的实际分类说明；首批不支持动态类别模板。')
  else:names.append(name.strip())
  if not isinstance(label,str) or len(label)>128 or '{{#' in label:errors.append('类别 label 须为最多 128 字符的文字，不支持动态模板。')
 if len(ids)!=len(set(ids)):errors.append('分类 id 重复，无法明确路由。')
 if len(names)!=len(set(names)):errors.append('分类说明重复，模型无法据此区分类别，请澄清分类规则。')
 selector=cfg.get('query_variable_selector')
 if not isinstance(selector,list) or len(selector)!=2 or not all(isinstance(x,str) and x for x in selector):errors.append('分类必须明确 query_variable_selector=[节点ID,文字字段]，不自动选择问题。')
 instruction=cfg.get('instruction','')
 if not isinstance(instruction,str) or len(instruction)>10000 or '{{#' in instruction:errors.append('分类 instruction 须为最多 10000 字符的文字；首批不支持动态模板。')
 policy=cfg.get('unmatched_policy')
 if not isinstance(policy,dict) or set(policy)!={'behavior','class_id'} or policy.get('behavior')!='first_class' or not ids or policy.get('class_id')!=ids[0]:errors.append('请明确 unmatched_policy={behavior:first_class,class_id:首项ID}，符合原生未匹配回退；不能编造 error／阈值路由。')
 if 'model' in cfg:
  try:validate_node_model(cfg['model'])
  except ValueError as exc:errors.append(str(exc))
 return errors

def branches(cfg):
 return {c['id'] for c in cfg.get('classes',[]) if isinstance(c,dict) and isinstance(c.get('id'),str)} if isinstance(cfg.get('classes'),list) else set()

def native(cfg,task_config,mode):
 result={'query_variable_selector':copy.deepcopy(cfg['query_variable_selector']),'classes':copy.deepcopy(cfg['classes']),'instruction':cfg.get('instruction',''),'model':resolve_node_model(cfg,task_config),'vision':{'enabled':False},'_targetBranches':[{'id':c['id'],'name':c.get('label') or c['name']} for c in cfg['classes']]}
 memory=memory_configuration(mode,task_config)
 if memory is not None:result['memory']=memory
 return result

def preserved(data,mode):
 vision=data.get('vision')
 if 'vision' in data and vision is None:raise ValueError('分类 vision=null 不是可核对的原生默认，不能当作已关闭。')
 if vision is not None and (not isinstance(vision,dict) or vision.get('enabled') is not False):raise ValueError('分类保留首批只支持明确关闭视觉的文字节点。')
 memory=data.get('memory')
 if memory is not None:
  from .conversation import memory_configuration
  window=memory.get('window') if isinstance(memory,dict) else None
  size=window.get('size') if isinstance(window,dict) else None
  if mode!='advanced-chat' or type(size) is not int or not 2<=size<=51 or memory!=memory_configuration(mode,{'conversation_memory':True,'memory_turns':size-1}):raise ValueError('分类记忆仅保留标准 Chatflow 有界历史结构；独立／无界／自定义模板未适配，不会丢弃记忆。')
 classes=copy.deepcopy(data.get('classes'));first=classes[0].get('id') if isinstance(classes,list) and classes and isinstance(classes[0],dict) else None
 instruction=data.get('instruction')
 if instruction is not None and not isinstance(instruction,str):raise ValueError('分类 instruction 原值不是文字，不能按空指令忽略。')
 cfg={'classes':classes,'query_variable_selector':copy.deepcopy(data.get('query_variable_selector')),'instruction':instruction if instruction is not None else '', 'model':copy.deepcopy(data.get('model')),'unmatched_policy':{'behavior':'first_class','class_id':first}}
 errors=validate(cfg)
 if errors:raise ValueError('分类实际配置不在保留范围：'+'；'.join(errors))
 return cfg
