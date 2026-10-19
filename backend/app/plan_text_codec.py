"""Lossless integer JSON transport for explicit plan editing, no execution."""
import json
MAX_BYTES=2_000_000

def unique(pairs):
 value={}
 for key,item in pairs:
  if key in value:raise ValueError('流程JSON含重复键，未选择其中一个值。')
  value[key]=item
 return value

def parse(text):
 try:
  if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_BYTES:raise ValueError()
  value=json.loads(text,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
  if not isinstance(value,dict):raise ValueError()
  json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
  return value
 except (ValueError,UnicodeError,TypeError,RecursionError,OverflowError):raise ValueError('计划须为2MB内无重复键、非有限数或坏编码的完整JSON对象；不舍入、修复或回显原文。') from None

def render(value):
 if value is None:return None
 text=json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)
 # Whitespace must not make an otherwise readable plan impossible to read back.
 if len(text.encode('utf-8'))>MAX_BYTES:text=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
 parse(text)
 return text
