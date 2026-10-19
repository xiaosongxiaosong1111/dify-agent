"""Pinned native scalar-array operations, explicit order, no host execution."""
import copy,math,re

TYPES={'array[string]','array[number]','array[boolean]'}
FIELDS=('variable','filter_by','order_by','limit','extract_by')
NOTE='原生顺序固定为筛选→按筛后序号提取→排序→数量截取。多条件依次筛选等同AND；按序号提取不是排序后的第N名。空数组输出仍为空；序号超出非空数组长度会失败，不能悄悄改为首项。首末项可能为空，首批只允许引用result数组。'

def validate(cfg):
 errors=[];kind=cfg.get('input_type')
 if set(cfg)-set(FIELDS)-{'input_type'}:errors.append('数组处理存在未适配字段，不能静默省略。')
 if not isinstance(kind,str) or kind not in TYPES:errors.append('input_type须明确为array[string]/array[number]/array[boolean]；对象／文件数组暂不支持。')
 selector=cfg.get('variable')
 if not isinstance(selector,list) or len(selector)!=2 or not all(isinstance(v,str) and v for v in selector):errors.append('variable须为明确的[上游节点ID,数组字段]。')
 for field,keys in [('filter_by',{'enabled','conditions'}),('order_by',{'enabled','key','value'}),('limit',{'enabled','size'}),('extract_by',{'enabled','serial'})]:
  value=cfg.get(field)
  if not isinstance(value,dict) or set(value)!=keys or type(value.get('enabled')) is not bool:errors.append(f'{field}须包含全部明确字段及enabled布尔值，不能使用未知设置。')
 filt=cfg.get('filter_by')
 if isinstance(filt,dict):
  rows=filt.get('conditions')
  if not isinstance(rows,list) or len(rows)>20 or filt.get('enabled') is True and not rows:errors.append('筛选条件须为最多20项数组，启用时至少一项；条件是AND。');rows=[]
  for row in rows:
   if not isinstance(row,dict) or set(row)!={'key','comparison_operator','value'} or row.get('key')!='':errors.append('标量条件须明确空key／comparison_operator／value，不支持对象路径。');continue
   op=row['comparison_operator'];value=row['value']
   if kind=='array[string]':
    if op not in ('contains','not contains','start with','end with','is','is not','empty','not empty') or not isinstance(value,str) or len(value)>2000 or '{{#' in value:errors.append('文字筛选仅支持明确字面值及已适配运算；不支持动态模板或in子串歧义。')
    elif op in ('empty','not empty') and value!='':errors.append('empty/not empty的无效右值必须明确为空，不能保存被忽略的业务值。')
   elif kind=='array[number]':
    try:valid=isinstance(value,str) and len(value)<=100 and bool(re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',value)) and math.isfinite(float(value))
    except (ValueError,OverflowError):valid=False
    if op not in ('=','≠','<','>','≥','≤') or not valid:errors.append('数字筛选须为有限数字的字面字符串及明确比较符；不支持NaN／Infinity／动态模板。')
   elif kind=='array[boolean]' and (op not in ('is','is not') or type(value) is not bool):errors.append('布尔筛选须is/is not及实际布尔值，不把文字false转换成布尔。')
 order=cfg.get('order_by')
 if isinstance(order,dict) and (order.get('key')!='' or order.get('value') not in ('asc','desc')):errors.append('标量排序须明确空key以及asc/desc，文字按原生字符顺序，布尔False在True前。')
 limit=cfg.get('limit')
 if isinstance(limit,dict) and (type(limit.get('size')) is not int or not (0<=limit['size']<=10000 or limit.get('enabled') is False and limit['size']==-1)):errors.append('启用limit.size须为0—10000整数，0明确返回空数组；-1仅可用于明确关闭的原生哨兵，不能启用后截尾。')
 extract=cfg.get('extract_by')
 if isinstance(extract,dict) and (not isinstance(extract.get('serial'),str) or not re.fullmatch(r'[1-9][0-9]{0,4}',extract['serial']) or int(extract['serial'])>10000):errors.append('extract_by.serial须为1—10000的字面序号字符串，关闭时仍须合法。')
 return errors

def native(cfg):return {k:copy.deepcopy(cfg[k]) for k in FIELDS}
