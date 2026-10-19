"""Bounded draft proposal for explicit per-item calculation failures as data.

Not an execution sandbox. No customer code, model or Dify runs here.
"""
import ast,copy,hashlib,json,re
from .workflow_plan import validate_plan
from .plan_text_codec import render
from .iteration_object_contract import MARKER as OBJECT_MARKER, SUMMARY_MARKER as OBJECT_SUMMARY_MARKER, schema_contract, schema_from_text, wrapped_object

MARKER='# Sierra per-item outcomes v1\n'
ERRORS=['ValueError','TypeError','ZeroDivisionError','KeyError','IndexError','OverflowError']
PROTOCOL_MARKERS=(MARKER,'# Sierra iteration result summary v1\n',OBJECT_MARKER,OBJECT_SUMMARY_MARKER,'# Sierra calculation chain outcomes v1\n','# Sierra calculation chain summary v1\n','# Sierra typed calculation chain outcomes v1\n','# Sierra typed calculation chain summary v1\n')
CALLS=set(ERRORS)|{'str','int','float','bool','len','abs','round','min','max','sum','range','enumerate','sorted','all','any','list','dict','tuple','set','isinstance'}
METHODS={'strip','lstrip','rstrip','lower','upper','replace','split','join','startswith','endswith','count','find','isdigit','isalpha','get','append'}
FORBIDDEN=(ast.ImportFrom,ast.Global,ast.Nonlocal,ast.ClassDef,ast.AsyncFunctionDef,ast.Lambda,ast.With,ast.AsyncWith,ast.Await,ast.Yield,ast.YieldFrom,ast.Delete)


def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def has_protocol(plan):
 if not isinstance(plan,dict):return False
 from .iteration import plan_nodes
 return any(n.get('type')=='code' and isinstance(n.get('config'),dict) and isinstance(n['config'].get('code'),str) and n['config']['code'].startswith(PROTOCOL_MARKERS) for n in plan_nodes(plan))


def semantic_digest(plan):
 if not isinstance(plan,dict):return digest(None)
 from .iteration import plan_nodes
 value=copy.deepcopy(plan)
 for n in plan_nodes(value):n.pop('title',None)
 return digest(value)


def requires_requirement_review(previous,current):
 # A marker only causes conservative review; it never grants trust or execution.
 return (has_protocol(previous) or has_protocol(current)) and semantic_digest(previous)!=semantic_digest(current)


def check(code,arg,key,allow_json=False):
 if not isinstance(code,str) or len(code.encode('utf-8'))>8000:raise ValueError('本批只包装8000字节内、单一main函数的明确计算代码。')
 if code.startswith(MARKER):raise ValueError('已有逐项结果封装，不重复包装。')
 try:tree=ast.parse(code)
 except SyntaxError:raise ValueError('原代码语法不完整，先修正再准备失败策略。') from None
 functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
 if len(functions)!=1 or functions[0].name!='main':raise ValueError('本批只支持一个main函数，不猜辅助函数、递归或动态调用。')
 fn=functions[0];args=fn.args
 if fn.decorator_list or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults or len(args.args)!=1 or args.args[0].arg!=arg:raise ValueError('本批函数须有唯一明确输入，不改变调用方式或默认参数。')
 for node in tree.body:
  if node is fn or isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):continue
  if allow_json and isinstance(node,ast.Import) and len(node.names)==1 and node.names[0].name=='json' and node.names[0].asname is None:continue
  raise ValueError('本批不包装模块状态、未知导入或额外顶层行为。')
 local={arg}|{n.id for n in ast.walk(fn) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store)}
 allowed=local|CALLS|({'json'} if allow_json else set())
 for node in ast.walk(tree):
  if isinstance(node,FORBIDDEN) or isinstance(node,ast.Import) and not (allow_json and node in tree.body and len(node.names)==1 and node.names[0].name=='json' and node.names[0].asname is None):raise ValueError('代码超出本批单函数计算范围，不把外部／动态行为当作可恢复计算。')
  if isinstance(node,ast.FunctionDef) and node is not fn:raise ValueError('本批不包装嵌套函数或递归。')
  if isinstance(node,ast.Name) and (node.id.startswith('__') or node.id.startswith('_sierra_') or isinstance(node.ctx,ast.Load) and node.id not in allowed):raise ValueError('代码含未明确的名称、动态调用或保留符号，未生成封装。')
  if isinstance(node,ast.Attribute) and not (node.attr in METHODS or allow_json and isinstance(node.value,ast.Name) and node.value.id=='json' and node.attr=='loads'):raise ValueError('代码属性访问不在本批明确计算范围内。')
  if isinstance(node,ast.Call) and not (isinstance(node.func,ast.Name) and node.func.id in CALLS or isinstance(node.func,ast.Attribute)):raise ValueError('本批不包装动态函数调用。')
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id not in CALLS:raise ValueError('本批只支持明确的计算内建函数。')
  if isinstance(node,ast.Return) and (not isinstance(node.value,ast.Dict) or len(node.value.keys)!=1 or not isinstance(node.value.keys[0],ast.Constant) or node.value.keys[0].value!=key):raise ValueError('原代码须明确返回唯一声明字段，不删除额外字段或猜动态返回结构。')
 return fn


NUMBER_GUARD = "type(result['result']) in (int, float) and -float('inf') < result['result'] < float('inf') and (type(result['result']) is not int or -9007199254740991 <= result['result'] <= 9007199254740991)"


def wrapped(code,result_type='string',result_schema=None):
 if result_type=='object':return wrapped_object(code,result_schema)
 if result_schema is not None:raise ValueError('文字或数值结果不接收对象Schema，不忽略额外合同。')
 if result_type not in {'string','number'}:raise ValueError('只包装已声明的文字或数值结果，不猜对象或数组合同。')
 fn=check(code,'item','result');lines=code.splitlines(keepends=True);line=lines[fn.lineno-1]
 renamed,n=re.subn(r'^def[ \t]+main(?=[ \t]*\()', 'def _sierra_calculate',line,count=1)
 if n!=1:raise ValueError('函数头写法尚未适配，原文保持。')
 lines[fn.lineno-1]=renamed
 suffix="""
def main(item: str, sierra_index: int) -> dict:
    if not isinstance(item, str) or type(sierra_index) is not int or sierra_index < 0:
        raise TypeError('Declared iteration input or index mismatch')
    try:
        result = _sierra_calculate(item)
    except (ValueError, TypeError, ZeroDivisionError, KeyError, IndexError, OverflowError) as _sierra_error:
        return {'outcome': {'index': sierra_index, 'ok': False, 'value': None, 'error_category': type(_sierra_error).__name__}}
    if not isinstance(result, dict) or set(result) != {'result'} or not isinstance(result['result'], str):
        raise TypeError('Declared string output mismatch')
    return {'outcome': {'index': sierra_index, 'ok': True, 'value': result['result'], 'error_category': None}}
"""
 if result_type=='number':
  suffix=suffix.replace("not isinstance(result['result'], str)","not ("+NUMBER_GUARD+")").replace('Declared string output mismatch','Declared finite safe numeric output mismatch')
 return MARKER+''.join(lines)+'\n'+suffix


def candidate(task,plan,node_id,acknowledge=False,result_schema=None):
 if type(acknowledge)is not bool or not acknowledge:raise ValueError('须明确同意将所列计算异常作为逐项失败数据继续；系统／沙箱等未捕获错误仍终止。')
 if task.get('app_type')!='workflow':raise ValueError('本批只适配Workflow，不更换应用类型。')
 render(plan)
 if not validate_plan(task,plan)['valid']:raise ValueError('先修正当前完整流程，未生成失败继续方案。')
 nodes=plan['nodes'];kinds=sorted(n['type'] for n in nodes)
 if kinds!=['code','end','iteration','start']:raise ValueError('本批仅明确JSON文字解析→单函数计算迭代→结束，不省略模型、HTTP、分支或其他节点。')
 selected=[n for n in nodes if n['id']==node_id and n['type']=='iteration']
 if len(selected)!=1:raise ValueError('须明确唯一根迭代节点，不自动选择。')
 parent=selected[0];cfg=parent['config'];body=cfg['nodes']
 if len(body)!=1 or body[0]['type']!='code':raise ValueError('本批正文须为一个Python计算节点，不捕获多节点／外部副作用。')
 child=body[0];cc=child['config'];outer=next(n for n in nodes if n['type']=='code');oc=outer['config'];end=next(n for n in nodes if n['type']=='end')
 result_type=(cc.get('outputs') or {}).get('result',{}).get('type')
 if result_type not in {'string','number','object'} or cc.get('code_language')!='python3' or cc.get('variables')!=[{'variable':'item','value_selector':[node_id,'item']}] or cc.get('outputs')!={'result':{'type':result_type,'children':None}} or cfg.get('iterator_input_type')!='array[string]' or cfg.get('output_selector')!=[child['id'],'result'] or cfg.get('output_type')!='array['+result_type+']':raise ValueError('本批只包装item文字→唯一result文字、数值或明确Schema对象，须与原输出声明一致，不能省略或改写其他输入输出。')
 if cfg.get('iterator_selector')!=[outer['id'],'items'] or oc.get('code_language')!='python3' or oc.get('outputs')!={'items':{'type':'array[string]','children':None}} or len(oc.get('variables',[]))!=1:raise ValueError('本批输入须为明确单一JSON解析输出items，不猜文件或对象来源。')
 check(oc.get('code'),oc['variables'][0]['variable'],'items',True)
 if len(end['config'].get('outputs',[]))!=1 or end['config']['outputs'][0].get('value_selector')!=[node_id,'output'] or {tuple((e['source'],e['target'])) for e in plan['edges']}!={(next(n for n in nodes if n['type']=='start')['id'],outer['id']),(outer['id'],node_id),(node_id,end['id'])}:raise ValueError('本批须直连唯一结束；改变数组结果类型需先讨论其他下游消费，不自动改提示词或业务代码。')
 if result_type=='object':result_schema=schema_contract(result_schema)
 elif result_schema is not None:raise ValueError('文字或数值结果不接收对象Schema，不忽略额外合同。')
 code=wrapped(cc['code'],result_type,result_schema);result=copy.deepcopy(plan);target=next(n for n in result['nodes'] if n['id']==node_id)['config'];child_cfg=target['nodes'][0]['config']
 child_cfg.update(code=code,variables=[{'variable':'item','value_selector':[node_id,'item']},{'variable':'sierra_index','value_selector':[node_id,'index']}],outputs={'outcome':{'type':'object','children':None}})
 target.update(output_selector=[child['id'],'outcome'],output_type='array[object]')
 if not validate_plan(task,result)['valid']:raise ValueError('新结果形状与完整流程不兼容，原计划保持。')
 text=render(result)
 return {'plan_text':text,'source_plan_sha256':digest(plan),'candidate_plan_sha256':digest(result),'original_code_sha256':hashlib.sha256(cc['code'].encode()).hexdigest(),'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'node_id':node_id,'code_node_id':child['id'],'native_error_handle_mode':'terminated','caught_error_classes':list(ERRORS),'value_type':result_type,'result_schema_sha256':digest(result_schema) if result_schema is not None else None,'output_type':'array[object]','verification':'local_iteration_outcome_draft_only','platform_checked':False,'business_verified':False,'task_changed':False,'network_requested':False,'note':'仅未保存方案：结果改为每项index／ok／value／error_category对象，保留原0基索引及成功结果原类型（文字、有限数值或符合明确Schema的对象），不复制原输入或异常正文。数值不接收布尔、非有限数或超安全范围整数，对象逐项不超过64000 UTF-8字节／20000值／16层；不转换、补默认、删字段，合同不符仍终止；所列六种计算异常返回失败对象继续；未知／沙箱／超时等仍终止，已派发项不保证即时取消。不是原生continue-on-error或丢弃失败项；原父节点terminated、并发和不展开设置保留。并非通用沙箱证明，未在本机执行用户代码或在Dify试跑；采用后须保存、确认新结果合同及试跑。'}


def register(host):
 from fastapi import APIRouter,HTTPException
 from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field
 from uuid import UUID
 from .plan_drafts import DraftRoute,inspect_text
 from .plan_text_codec import parse

 class Preview(BaseModel):
  model_config=ConfigDict(extra='forbid')
  revision:StrictInt=Field(ge=1)
  plan_text:StrictStr=Field(max_length=2_000_000)
  node_id:StrictStr=Field(min_length=1,max_length=256)
  acknowledge_result_contract:StrictBool
  request_nonce:UUID
  result_schema_text:StrictStr|None=Field(default=None,max_length=64000)

 router=APIRouter(route_class=DraftRoute)
 @router.post('/api/tasks/{item_id}/iteration-outcomes')
 def prepare(item_id:str,payload:Preview):
  with host.store.lock:
   task=host.get_task(item_id);host.require_revision(task,payload.revision)
   try:
    inspect_text(payload.plan_text)
    plan=parse(payload.plan_text)
    if payload.result_schema_text is not None:inspect_text(payload.result_schema_text)
    schema=schema_from_text(payload.result_schema_text) if payload.result_schema_text is not None else None
    result=candidate(task,plan,payload.node_id,payload.acknowledge_result_contract,schema)
   except (TypeError,KeyError,RecursionError,UnicodeError,OverflowError):
    raise HTTPException(422,'草稿结构或编码超出此批范围，未修改原稿或执行代码。') from None
   except ValueError as exc:
    raise HTTPException(422,str(exc)) from None
   return {**result,'task_id':item_id,'revision':payload.revision,'request_nonce':str(payload.request_nonce)}
 host.app.include_router(router)
