"""Static admission for a bounded pure-computation sample, never host execution."""
import ast,json,math
from decimal import Decimal,DecimalException
CODE_BYTES=32768
INPUT_BYTES=65536
OUTPUT_BYTES=32768
MODULES={'json':{'loads','dumps'},'math':{'ceil','floor','trunc','sqrt','isqrt','fabs','pow','exp','log','log10','sin','cos','tan','radians','degrees','isfinite','isnan','isinf','copysign','fmod','fsum','prod','gcd','lcm','pi','e','tau','inf','nan'}}
ATTRIBUTES=set(['strip', 'lstrip', 'rstrip', 'upper', 'lower', 'casefold', 'replace', 'split', 'rsplit', 'splitlines', 'join', 'startswith', 'endswith', 'find', 'rfind', 'index', 'rindex', 'count', 'isalnum', 'isalpha', 'isdigit', 'isdecimal', 'isspace', 'islower', 'isupper', 'capitalize', 'title', 'swapcase', 'center', 'ljust', 'rjust', 'zfill', 'removeprefix', 'removesuffix', 'encode', 'decode', 'hex', 'fromhex', 'append', 'extend', 'insert', 'pop', 'remove', 'clear', 'copy', 'sort', 'reverse', 'get', 'keys', 'values', 'items', 'setdefault', 'update', 'popitem', 'fromkeys', 'add', 'discard', 'intersection', 'union', 'difference', 'symmetric_difference', 'issubset', 'issuperset', 'isdisjoint', 'difference_update', 'intersection_update', 'symmetric_difference_update', 'bit_count', 'bit_length', 'conjugate', 'is_integer', 'as_integer_ratio', 'real', 'imag', 'numerator', 'denominator', 'args', 'add_note'])|set().union(*MODULES.values())
DENIED={'eval','exec','compile','open','input','globals','locals','vars','getattr','setattr','delattr','dir','type','object','super','help','breakpoint','BaseException','SystemExit','KeyboardInterrupt','exit','quit'}
BUILTINS=('abs','all','any','bool','bytes','dict','divmod','enumerate','filter','float','format','frozenset','int','isinstance','issubclass','iter','len','list','map','max','min','next','ord','chr','pow','range','repr','reversed','round','set','slice','sorted','str','sum','tuple','zip','print','ArithmeticError','AssertionError','Exception','IndexError','KeyError','MemoryError','OverflowError','RuntimeError','StopIteration','TypeError','ValueError','ZeroDivisionError')
def fail(message):raise ValueError(message)
def validate_code(code):
 if not isinstance(code,str) or not code.strip() or len(code.encode('utf-8'))>CODE_BYTES:fail('代码须为32KB内的完整Python文字。')
 try:tree=ast.parse(code)
 except (SyntaxError,ValueError,RecursionError):fail('Python语法无法读取，未执行。')
 nodes=list(ast.walk(tree))
 if len(nodes)>4096:fail('代码结构超过受限样例范围。')
 for n in nodes:
  if isinstance(n,(ast.ClassDef,ast.AsyncFunctionDef,ast.AsyncFor,ast.AsyncWith,ast.With,ast.Await,ast.Yield,ast.YieldFrom,ast.Global,ast.Nonlocal,ast.Delete,ast.TryStar,ast.Match)):fail('受限样例只支持同步纯计算函数，不支持类、异步、上下文、模式匹配或动态全局绑定。')
  if isinstance(n,ast.Name) and (n.id.startswith('__') or n.id in DENIED):fail('代码包含本机纯计算样例未开放的名称。')
  if isinstance(n,ast.Attribute) and (n.attr not in ATTRIBUTES or not isinstance(n.ctx,ast.Load)):fail('代码包含未开放的属性、反射或属性修改，未执行；仅支持明确的JSON/数学和常见内置数据方法。')
  if isinstance(n,ast.FunctionDef) and (n.decorator_list or n.name.startswith('__') or n.name in DENIED):fail('受限样例不支持装饰器或动态入口。')
  if isinstance(n,ast.arg) and (n.arg.startswith('__') or n.arg in DENIED):fail('参数名不在受限样例范围。')
  if isinstance(n,ast.ExceptHandler) and n.type is None:fail('受限样例不允许捕获全部底层终止信号。')
  if isinstance(n,(ast.Import,ast.ImportFrom)):
   if isinstance(n,ast.Import):allowed=all(a.name in MODULES for a in n.names)
   else:allowed=n.level==0 and n.module in MODULES and all(a.name in MODULES[n.module] for a in n.names)
   if not allowed or any((a.asname or a.name).startswith('__') or (a.asname or a.name) in DENIED for a in n.names):fail('受限样例只开放math及json的明确计算接口，不支持其他导入。')
 for n in tree.body:
  if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef)):continue
  if isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str):continue
  if isinstance(n,(ast.Assign,ast.AnnAssign)):
   try:ast.literal_eval(n.value)
   except (ValueError,TypeError,RecursionError):fail('模块顶层只支持字面常量、导入和函数定义。')
   continue
  fail('模块顶层只支持字面常量、导入和函数定义。')
 return tree

def wire_float(text):
 value=float(text)
 try:
  if not math.isfinite(value) or Decimal(text)!=Decimal(str(value)):fail('样例JSON小数会在往返时改变数值，未舍入。')
 except DecimalException:fail('样例JSON小数超出核对范围。')
 return value

def unique(pairs):
 value={}
 for k,v in pairs:
  if k in value:fail('样例JSON含重复键。')
  value[k]=v
 return value

def json_value(value,depth=0):
 if depth>32:fail('样例JSON嵌套超过32层。')
 if value is None or type(value) in (str,bool,int):return
 if type(value)is float and math.isfinite(value):return
 if isinstance(value,list):
  for v in value:json_value(v,depth+1)
  return
 if isinstance(value,dict) and all(isinstance(k,str) for k in value):
  for v in value.values():json_value(v,depth+1)
  return
 fail('样例必须为有限数和普通JSON值，不转换自定义对象。')

def parse_inputs(text):
 try:
  if not isinstance(text,str) or len(text.encode('utf-8'))>INPUT_BYTES:fail('样例参数超过64KB。')
  value=json.loads(text,object_pairs_hook=unique,parse_float=wire_float,parse_constant=lambda _:fail('样例不能含非有限数。'))
  if not isinstance(value,dict):fail('样例输入须为JSON对象。')
  json_value(value);return value
 except (UnicodeError,RecursionError,OverflowError):fail('样例JSON编码或嵌套无法核对。')

def output_matches(value,declaration):
 if not isinstance(value,dict) or set(value)!=set(declaration):return False
 def match(v,kind):
  if kind=='string':return type(v)is str
  if kind=='number':return type(v)in(int,float) and (type(v)is int or math.isfinite(v))
  if kind=='boolean':return type(v)is bool
  if kind=='object':return type(v)is dict
  if kind in ('array[string]','array[number]','array[boolean]','array[object]'):return type(v)is list and all(match(x,kind[6:-1]) for x in v)
  return False
 return all(isinstance(schema,dict) and match(value[k],schema.get('type')) for k,schema in declaration.items())
