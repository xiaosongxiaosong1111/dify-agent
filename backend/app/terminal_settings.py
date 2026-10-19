"""Terminal fields for the pinned collecting/answer adapters, no execution."""
TYPES={'string','number','integer','secret','boolean','object','file','array','array[string]','array[number]','array[object]','array[boolean]','array[file]','any','array[any]'}

def validate(kind,config):
 errors,warnings=[],[]
 allowed={'outputs'} if kind=='end' else {'answer'}
 if set(config)-allowed:errors.append('终点配置含未适配字段；不能忽略固定值、额外变量或其他输出模式后算完成。')
 if kind=='answer':return errors,warnings
 rows=config.get('outputs')
 if not isinstance(rows,list):return errors,warnings
 if len(rows)>64:errors.append('终点最多支持 64 个返回字段；不会截断剩余字段。')
 names=set()
 for i,row in enumerate(rows[:64]):
  if not isinstance(row,dict):continue
  if set(row)-{'variable','value_selector','value_type'}:errors.append(f'outputs[{i}] 含未适配字段；常量或其他输出模式须先明确方案，不静默省略。')
  name=row.get('variable')
  if isinstance(name,str):
   if not name.strip() or len(name)>128:errors.append(f'outputs[{i}] 返回字段须为非空且最多 128 字符的名称，不自动改名。')
   elif name in names:errors.append('终点返回字段名称重复，Dify 会覆盖同名结果；请明确唯一名称，不自动删除或重命名。')
   names.add(name)
  if 'value_type' in row:
   value=row['value_type'];normalized=value.lower() if isinstance(value,str) and value.startswith('Array[') else value
   if not isinstance(normalized,str) or normalized not in TYPES:errors.append(f'outputs[{i}].value_type 与 Dify 1.17.1 原生枚举不兼容，不自动替换。')
   elif normalized=='secret':warnings.append('终点 value_type=secret 只是声明，Dify 原样收集上游输出，不自动脱敏；须明确敏感数据处理规则并验证，不把声明当作隐藏输出。')
 return list(dict.fromkeys(errors)),list(dict.fromkeys(warnings))
