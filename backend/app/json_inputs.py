"""Explicit bounded Workflow JSON-object declarations and offline instance checks."""
import copy,json
from jsonschema import Draft7Validator,SchemaError
from .structured_output import schema_errors
MAX_BYTES=64000
MAX_SAFE=9007199254740991
FIELDS={'variable','label','type','required','hide','description','default','options','max_length','json_schema'}
NOTE='JSON对象入口首批仅根Workflow，按明确Schema本机核对；不补默认、不把JSON文字／数组转成对象。本机预检不证明Dify服务API强制执行Schema；如业务要求所有入口强制，需另加工作流代码方案并确认。实际Dify导入、发布入口、资源权限和业务仍待验证。整数限本批可无损编辑范围，金额可明确使用文本方案，不承诺浮点精度。'

def has_objects(rows):return isinstance(rows,list) and any(isinstance(r,dict) and r.get('type')=='json_object' for r in rows)

def unique(pairs):
 out={}
 for key,value in pairs:
  if key in out:raise ValueError('JSON Schema含重复键，不会覆盖后使用。')
  out[key]=value
 return out

def bad_constant(value):raise ValueError('JSON Schema不能含非有限常量。')

def schema(value):
 try:
  if isinstance(value,str):
   if len(value.encode('utf-8'))>MAX_BYTES:raise ValueError('JSON Schema最多64000字节，不截断。')
   value=json.loads(value,object_pairs_hook=unique,parse_constant=bad_constant)
  if not isinstance(value,dict) or value.get('type')!='object':raise ValueError('JSON入口须明确根object的JSON Schema。')
  errors=schema_errors(value)
  if errors:raise ValueError('JSON入口Schema未适配：'+'；'.join(errors))
  Draft7Validator.check_schema(value)
  return value
 except (SchemaError,UnicodeError,TypeError,RecursionError):raise ValueError('JSON入口Schema结构或编码无效，未使用原文错误回显。') from None
 except json.JSONDecodeError:raise ValueError('JSON入口Schema文字未完成或格式无效，不猜测或改为空对象。') from None

def validate(row):
 errors=[]
 if set(row)-FIELDS:errors.append('JSON对象入口含未适配字段，不会删除约束后生成。')
 if row.get('required') is not True:errors.append('JSON对象入口本批须明确required=true；可选根对象默认与空值类型尚未适配。')
 if row.get('hide',False) is not False:errors.append('JSON对象入口本批须可见，不代填隐藏参数。')
 if row.get('default') is not None:errors.append('JSON对象入口本批不提供默认对象，不自动补业务字段。')
 if row.get('options',[])!=[]:errors.append('JSON对象入口不使用options；字段枚举须明确写入Schema。')
 if row.get('max_length') is not None:errors.append('JSON对象max_length不限制结构大小，本批须省略或null；输入与Schema各最多64000字节。')
 if any(k in row and not isinstance(row[k],str) for k in ('label','description')):errors.append('JSON对象label／description须为文本。')
 try:schema(row.get('json_schema'))
 except ValueError as exc:errors.append(str(exc))
 return errors

def validate_value(schema_value,value):
 if type(value) is not dict:raise ValueError('JSON对象输入须是真正对象，不能用JSON文字、数组、null或布尔代替。')
 try:
  try:encoded=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
  except (ValueError,TypeError,UnicodeError,RecursionError):raise ValueError('JSON对象须为有限、无循环且编码有效的JSON值，不回显原输入。') from None
  if len(encoded)>MAX_BYTES:raise ValueError('JSON对象输入最多64000字节，不截断或拆字段。')
  pending=[value];remaining=20000
  while pending:
   item=pending.pop();remaining-=1
   if remaining<0:raise ValueError('JSON对象输入超过结构检查上限，不显示部分通过。')
   if type(item) is int and not -MAX_SAFE<=item<=MAX_SAFE:raise ValueError('JSON整数超出本批无损编辑范围，不会舍入；请确认文本或其他方案。')
   if isinstance(item,dict):
    if any(not isinstance(k,str) for k in item):raise ValueError('JSON对象的键须为文本。')
    pending.extend(item.values())
   elif isinstance(item,list):pending.extend(item)
   elif item is not None and type(item) not in (str,int,float,bool):raise ValueError('JSON对象输入含非JSON值，不自动转换。')
  parsed=schema(schema_value);error=next(Draft7Validator(parsed).iter_errors(value),None)
  if error is not None:
   pointer='/'+ '/'.join(str(part).replace('~','~0').replace('/','~1') for part in error.absolute_schema_path)
   raise ValueError('JSON对象输入不符合已确认Schema，规则位置'+pointer+'；不回显字段值、不补默认或删除额外字段。')
 except (TypeError,UnicodeError,RecursionError,OverflowError):raise ValueError('JSON对象输入结构／编码无法完整核对，不转换原值。') from None

def native(row):
 value=copy.deepcopy(row);value.setdefault('label',row['variable']);return value
