"""Fixed public example only. Stateless plan construction, no execution."""
import hashlib,json
from fastapi import APIRouter,HTTPException,Response
from .case_sets import revision_number
from .iteration_outcomes import candidate as outcomes
from .iteration_summary import candidate as summary
from .plan_text_codec import render
from .workflow_plan import compile_workflow_plan
CODE='def main(item: str) -> dict:\n    if item == "ERR":\n        raise ValueError("公开样例受控失败")\n    return {"result": item.strip().upper()}\n'
EXAMPLE={'items_json':'[" a ","ERR","a",""]'}
NOTE='固定公开例子：只有文字完全等于ERR时触发ValueError；其余去两端空白并大写，重复和空文字保留。不执行用户代码、模型或Dify；示例与计数是预期声明，不是平台运行结果。需Dify代码Sandbox及原生迭代能力，安装/运行行为与宿主费用未验收。采纳只填未保存计划，不自动保存、确认、构建、导入或运行；现有Task配置/模拟及费用门禁保持。'

def candidate(policy):
 if policy not in {'continue_known','stop'}:raise HTTPException(422,'请明确选择受控异常继续或遇错终止，不代选失败策略。')
 p={'schema_version':1,'nodes':[
 {'id':'start','type':'start','title':'公开批量输入','config':{'variables':[{'variable':'items_json','type':'paragraph','required':True}]}},
 {'id':'parse','type':'code','title':'严格读取文字数组','config':{'code_language':'python3','code':'import json\ndef main(items_json: str) -> dict:\n    items = json.loads(items_json)\n    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):\n        raise ValueError("输入须为JSON文字数组")\n    return {"items": items}\n','variables':[{'variable':'items_json','value_selector':['start','items_json']}],'outputs':{'items':{'type':'array[string]','children':None}}}},
 {'id':'batch','type':'iteration','title':'逐项公开计算','config':{'iterator_selector':['parse','items'],'iterator_input_type':'array[string]','output_selector':['clean','result'],'output_type':'array[string]','is_parallel':False,'error_handle_mode':'terminated','flatten_output':False,'nodes':[{'id':'clean','type':'code','title':'公开文字计算','config':{'code_language':'python3','code':CODE,'variables':[{'variable':'item','value_selector':['batch','item']}],'outputs':{'result':{'type':'string','children':None}}}}]}},
 {'id':'end','type':'end','config':{'outputs':[{'variable':'results','value_selector':['batch','output']}]}}
 ],'edges':[{'source':'start','target':'parse'},{'source':'parse','target':'batch'},{'source':'batch','target':'end'}]}
 task={'app_type':'workflow','configuration':{},'workflow_plan':p}
 if policy=='continue_known':
  p=json.loads(outcomes(task,p,'batch',True)['plan_text']);task['workflow_plan']=p;p=json.loads(summary(task,p,'batch',True)['plan_text']);task['workflow_plan']=p
 _,checked=compile_workflow_plan(task)
 if not checked['valid']:raise HTTPException(422,'公开批量起步方案静态检查未通过，未返回部分计划。')
 text=render(p)
 return {'plan_text':text,'candidate_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'failure_policy':policy,'example_input':EXAMPLE,'expected':{'total':4,'succeeded':3,'failed':1,'failed_indices':[1]} if policy=='continue_known' else {'declared_behavior':'遇ERR计算异常终止，不返回部分完成汇总；已派发项不承诺即时取消。'},'note':NOTE}

def register(h):
 router=APIRouter()
 @router.get('/api/tasks/{item_id}/public-batch-starter')
 def prepare(response:Response,item_id:str,revision:str|None=None,policy:str='',request_nonce:str=''):
  import uuid
  try:uuid.UUID(request_nonce)
  except (ValueError,TypeError):raise HTTPException(422,'本次公开方案读取标识无效，未返回。') from None
  with h.store.lock:
   task=h.get_task(item_id);h.require_revision(task,revision_number(revision))
   if task['app_type']!='workflow' or task.get('workflow_plan') is not None or task.get('dsl_reference') is not None or task.get('artifact') is not None or task.get('dify_app_id') is not None:raise HTTPException(409,'此起步入口仅空白Workflow；已有流程/引用DSL或其他类型保持，不覆盖后生成。')
   value=candidate(policy);response.headers['Cache-Control']='no-store'
   return {**value,'schema_version':1,'task_id':task['id'],'revision':task['revision'],'request_nonce':request_nonce,'app_type':'workflow','verification':'fixed_public_batch_draft_only','task_changed':False,'network_requested':False,'code_executed':False,'platform_checked':False,'business_verified':False}
 h.app.include_router(router)
