"""Bounded local rejection reasons, never instance values or exception text."""
import hashlib

KEYWORDS={'type','required','additionalProperties','enum','minimum','maximum','minItems','maxItems','minLength','maxLength'}
MESSAGES={
 'output_fields':'平台成功回执的输出字段不符合结束声明；不展示未知字段名或值。',
 'object_required':'结束输出须为真正JSON对象；不将JSON文字、数组、null或布尔转换为对象。',
 'json_value_invalid':'输出不是可完整编码的有限JSON值；未展示原值或异常正文。',
 'size_limit':'输出对象超过64000字节；未截断、拆字段或保留原值。',
 'structure_limit':'输出对象超过20000实例值的结构检查上限；不把部分结果算作通过。',
 'integer_range':'输出整数超出本批无损编辑范围±9007199254740991；未舍入或改成其他类型。',
 'schema_rule':'输出对象未通过已确认Schema规则；不补默认、删除字段或重跑。',
 'unknown':'本机未能安全细分此次对象拒绝原因；不展示原值或异常正文。',
}
ERRORS={
 'JSON对象输入须是真正对象，不能用JSON文字、数组、null或布尔代替。':'object_required',
 'JSON对象须为有限、无循环且编码有效的JSON值，不回显原输入。':'json_value_invalid',
 'JSON对象输入结构／编码无法完整核对，不转换原值。':'json_value_invalid',
 'JSON对象的键须为文本。':'json_value_invalid',
 'JSON对象输入含非JSON值，不自动转换。':'json_value_invalid',
 'JSON对象输入最多64000字节，不截断或拆字段。':'size_limit',
 'JSON对象输入超过结构检查上限，不显示部分通过。':'structure_limit',
 'JSON整数超出本批无损编辑范围，不会舍入；请确认文本或其他方案。':'integer_range',
}
PREFIX='JSON对象输入不符合已确认Schema，规则位置'
SUFFIX='；不回显字段值、不补默认或删除额外字段。'

def paths(schema):
 result=set();pending=[(schema,'',0)];count=0
 while pending:
  row,path,depth=pending.pop();count+=1
  if count>200 or depth>8 or not isinstance(row,dict):raise ValueError('原Schema结构不能完整核对。')
  for key in KEYWORDS.intersection(row):result.add(path+'/'+key)
  if row.get('type')=='object':
   for key,child in row.get('properties',{}).items():pending.append((child,path+'/properties/'+key.replace('~','~0').replace('/','~1'),depth+1))
  elif row.get('type')=='array':pending.append((row['items'],path+'/items',depth+1))
 return result

def safe_pointer(value):
 try:return isinstance(value,str) and len(value.encode('utf-8'))<=1000 and value.isprintable()
 except UnicodeError:return False

def make(schema,schema_text,error=None):
 code='output_fields' if error=='output_fields' else ERRORS.get(str(error),'unknown');pointer=None
 text=str(error)
 if text.startswith(PREFIX) and text.endswith(SUFFIX):
  candidate=text[len(PREFIX):-len(SUFFIX)]
  if candidate in paths(schema):
   code='schema_rule'
   if safe_pointer(candidate):pointer=candidate
 message=MESSAGES[code]+(' 规则路径：'+pointer if pointer is not None else '')
 return {'schema_version':1,'category':code,'schema_pointer':pointer,'message':message,'schema_text_sha256':hashlib.sha256(schema_text.encode('utf-8')).hexdigest(),'output_retained':False,'automatic_retry':False,'business_verified':False,'verification':'local_file_output_contract_rejection_only'}

def valid(value,schema,schema_text):
 if not isinstance(value,dict) or set(value)!={'schema_version','category','schema_pointer','message','schema_text_sha256','output_retained','automatic_retry','business_verified','verification'} or type(value.get('schema_version')) is not int or value['schema_version']!=1:return False
 code=value.get('category');pointer=value.get('schema_pointer')
 if not isinstance(code,str) or code not in MESSAGES or any(value.get(k) is not False for k in ('output_retained','automatic_retry','business_verified')) or value.get('verification')!='local_file_output_contract_rejection_only' or value.get('schema_text_sha256')!=hashlib.sha256(schema_text.encode('utf-8')).hexdigest():return False
 if pointer is not None and (code!='schema_rule' or not safe_pointer(pointer) or pointer not in paths(schema)):return False
 return value.get('message')==MESSAGES[code]+(' 规则路径：'+pointer if pointer is not None else '')
