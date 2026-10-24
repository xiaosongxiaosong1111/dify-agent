"""Guard the flat condition fields actually emitted by the pinned compiler."""
import math,re

OPERATORS={'contains','not contains','start with','end with','is','is not','empty','not empty','in','not in','all of','=','≠','>','<','≥','≤','null','not null','exists','not exists'}
UNARY={'empty','not empty','null','not null','exists','not exists'}
SCALAR={
 'string':{'contains','not contains','start with','end with','is','is not','empty','not empty','in','not in','null','not null'},
 'number':{'=','≠','>','<','≥','≤','empty','not empty','null','not null'},
 'boolean':{'is','is not','null','not null'},
}
_REF=re.compile(r'\{\{#([\w-]+)\.([\w-]+)#\}\}')
BOOLEAN_RHS_ERROR='布尔右值须为明确 true／false 或完整变量模板，不自动把文字变布尔值。'

def validate(config):
 errors=[]
 if set(config)-{'cases'}:errors.append('条件 config 仅支持 cases；旧条件、嵌套或其他配置不会静默忽略。')
 cases=config.get('cases')
 if not isinstance(cases,list):return errors
 if len(cases)>32:errors.append('条件最多支持 32 个分支；不会截断剩余分支。')
 for i,case in enumerate(cases[:32]):
  if not isinstance(case,dict):continue
  prefix=f'cases[{i}]'
  if set(case)-{'case_id','logical_operator','conditions'}:errors.append(f'{prefix} 含未适配字段，不会静默省略。')
  rows=case.get('conditions')
  if not isinstance(rows,list):continue
  if len(rows)>64:errors.append(f'{prefix} 最多支持 64 个条件；不会截断剩余条件。')
  for j,row in enumerate(rows[:64]):
   if not isinstance(row,dict):continue
   label=f'{prefix}.conditions[{j}]'
   if set(row)-{'id','variable_selector','varType','comparison_operator','value'}:errors.append(f'{label} 含未适配字段（嵌套、文件属性或变量右值模式等），不会丢弃后生成。')
   if 'id' in row and (not isinstance(row['id'],str) or not row['id']):errors.append(f'{label}.id 须为非空文字。')
   kind,op,value=row.get('varType'),row.get('comparison_operator'),row.get('value')
   if not isinstance(op,str) or op not in OPERATORS:errors.append(f'{label} 运算不兼容 Dify 1.17.1；空值检查原生标识为 null／not null，不自动转换旧方案。')
   if isinstance(kind,str) and kind in SCALAR and (not isinstance(op,str) or op not in SCALAR[kind]):errors.append(f'{label} 运算与声明的标量类型不一致。')
   if kind=='file':
    if not isinstance(op,str) or op not in {'exists','not exists'}:errors.append(f'{label} 单文件仅支持exists／not exists，不用empty猜文件存在。')
    if value is not None and value!='':errors.append(f'{label} 单文件存在条件的value须为空文本或null，不忽略比较值。')
   if kind=='array[file]':
    if not isinstance(op,str) or op not in {'empty','not empty'}:errors.append(f'{label} 文件列表首批只支持empty／not empty，不读取文件属性或隐式比较对象。')
    if value is not None and value!='':errors.append(f'{label} 文件列表空值检查须明确value为空文本或null，不携带被忽略的比较值。')
   # Dify Condition.value is str | Sequence[str] | bool | None. In
   # particular an unquoted 0/1 must not become a bool through coercion.
   native_value=value is None or isinstance(value,(str,bool)) or isinstance(value,list) and all(isinstance(v,str) for v in value)
   if not native_value:errors.append(f'{label}.value 须为文字、文字数组、明确布尔值或 null；数值比较填写数值文本，不隐式转换。');continue
   texts=[value] if isinstance(value,str) else value if isinstance(value,list) else []
   for text in texts:
    matches=list(_REF.finditer(text))
    if text.count('{{#')!=len(matches):errors.append(f'{label}.value 变量模板格式不完整。')
   if not isinstance(op,str) or op in UNARY:continue
   if kind=='number':
    if not isinstance(value,str):errors.append(f'{label} 数值比较右值须为有限数值文本或完整变量模板。')
    elif '{{#' in value:
     if not _REF.fullmatch(value):errors.append(f'{label} 数值变量右值须为完整单个模板，不能拼接文字。')
    else:
     try:finite=math.isfinite(float(value))
     except (ValueError,OverflowError):finite=False
     if not finite:errors.append(f'{label} 数值比较右值须为有限数值文本。')
   elif kind=='boolean' and type(value) is not bool and not (isinstance(value,str) and _REF.fullmatch(value)):
    errors.append(f'{label} {BOOLEAN_RHS_ERROR}')
   elif kind=='string' and op in {'in','not in'} and not isinstance(value,list):errors.append(f'{label} in／not in 右值须为文字数组。')
   elif kind=='string' and op not in {'in','not in'} and not isinstance(value,str):errors.append(f'{label} 文字比较右值须为文字。')
 return list(dict.fromkeys(errors))

def value_refs(value):
 for text in ([value] if isinstance(value,str) else value if isinstance(value,list) else []):
  if isinstance(text,str):yield from (list(match.groups()) for match in _REF.finditer(text))

def remap_value(value,remap):
 """Only project symbolic references; do not resolve values or rewrite source."""
 def text(v):
  if not isinstance(v,str):return v
  def replace(match):
   selector=remap(list(match.groups()))
   return '{{#'+'.'.join(selector)+'#}}'
  return _REF.sub(replace,v)
 return [text(v) for v in value] if isinstance(value,list) else text(value)
