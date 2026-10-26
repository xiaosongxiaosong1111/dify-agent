"""Read saved per-item outcome arrays only; never execute or regrade them."""
import hashlib,json,math,re
from fastapi import APIRouter,HTTPException,Response,Request
from .case_sets import revision_number
from .plan_text_codec import parse
from .plan_drafts import inspect_text
LIMIT=2_000_000
PAGE=20
ERRORS={'ValueError','TypeError','ZeroDivisionError','KeyError','IndexError','OverflowError'}
NOTE='仅核对所选保存字段中的逐项声明，不对照原始输入总数、节点轨迹、输出Schema或完整业务；ok不是样例成绩。旧修订/App不继承当前验收，记录可能不覆盖原批全部输入；不重试、重评或运行。'

def fail():raise HTTPException(422,'所选字段不是完整可核对的逐项结果协议，或超出1000项/2MB/数值结构范围；未截断、补项、丢弃失败或回显原值。')
def encoded(value):
 try:raw=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
 except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):fail()
 if len(raw)>LIMIT:fail()
 return raw

def outcomes(value):
 raw=encoded(value)
 if isinstance(value,str):
  try:
   wrapper=parse('{"items":'+value+'}')
   if set(wrapper)!={'items'}:fail()
   value=wrapper['items']
  except ValueError:fail()
 if not isinstance(value,list) or len(value)>1000:fail()
 expected=None
 for i,row in enumerate(value):
  if not isinstance(row,dict):fail()
  fields=set(row)
  if fields not in ({'index','ok','value','error_category'},{'index','ok','value','error_category','failed_stage'}):fail()
  if expected is None:expected=fields
  if fields!=expected or type(row['index']) is not int or row['index']!=i or type(row['ok']) is not bool:fail()
  if row['ok']:
   if row['error_category'] is not None or type(row['value']) not in (str,int,float,dict) or ('failed_stage' in row and row['failed_stage'] is not None):fail()
  elif row['value'] is not None or not isinstance(row['error_category'],str) or row['error_category'] not in ERRORS or ('failed_stage' in row and (type(row['failed_stage']) is not int or row['failed_stage']<1 or row['failed_stage']>1000)):fail()
  stack=[(row['value'],0)];count=0
  while stack:
   item,depth=stack.pop();count+=1
   if depth>16 or count>20000:fail()
   if type(item)is int and abs(item)>9007199254740991:fail()
   if type(item)is float and not math.isfinite(item):fail()
   if isinstance(item,dict):
    if any(not isinstance(k,str) for k in item):fail()
    stack.extend((v,depth+1) for v in item.values())
   elif isinstance(item,list):stack.extend((v,depth+1) for v in item)
   elif item is not None and type(item) not in (str,int,float,bool):fail()
 try:inspect_text(raw.decode('utf-8'));inspect_text(encoded(value).decode('utf-8'))
 except HTTPException:raise HTTPException(422,'所选完整结果疑似含凭据或超出结构/编码核对范围，未显示、脱敏冒充完整结果或导出原值。') from None
 return value,raw

def snapshot(h,item_id,run_id,revision,field,source=None):
 task=h.get_task(item_id);h.require_revision(task,revision_number(revision))
 if task.get('app_type')!='workflow':raise HTTPException(422,'逐项结果首批仅明确Workflow记录，不改变应用类型。')
 runs=[r for r in task.get('runs',[]) if isinstance(r,dict) and r.get('id')==run_id]
 if len(runs)!=1:raise HTTPException(404,'未找到本任务唯一运行记录，未读取其它任务。')
 run=runs[0];case=run.get('test_case')
 if case is not None and not isinstance(case,dict):fail()
 if run.get('kind')!='run' or run.get('status')!='success' or run.get('app_type')!='workflow' or type(run.get('revision'))is not int or not 1<=run['revision']<=9007199254740991 or run['revision']>task['revision'] or 'conversation_context' in run or run.get('file_case') is not None or (case or {}).get('followups'):
  raise HTTPException(422,'只读取有明确修订和类型的成功普通单轮Workflow结果；未知、失败、文件与会话记录不改为完成批次。')
 result=run.get('result')
 if not isinstance(result,dict):fail()
 outputs=result.get('data',{});outputs=outputs.get('outputs') if isinstance(outputs,dict) else None
 if not isinstance(field,str) or not field or len(field)>128 or not field.isprintable() or not isinstance(outputs,dict) or field not in outputs:raise HTTPException(422,'请明确选择实际保存输出中的一个顶层字段，不解释点号或猜测缺失字段。')
 rows,raw=outcomes(outputs[field]);metadata={k:run.get(k) for k in ('id','revision','app_id','environment_id')}
 if any(v is not None and (not isinstance(v,str) or len(v)>200 or not v.isprintable()) for k,v in metadata.items() if k!='revision'):fail()
 if not run_id.isascii() or not task['id'].isascii():fail()
 try:inspect_text(encoded(metadata).decode('utf-8'))
 except HTTPException:fail()
 identity=encoded({'task_id':task['id'],'run':metadata,'field':field,'raw_sha256':hashlib.sha256(raw).hexdigest()});token=hashlib.sha256(identity).hexdigest()
 if source is not None and (not re.fullmatch('[a-f0-9]{64}',source) or source!=token):raise HTTPException(409,'所选完整结果来源已变化，请主动重新读取；未导出或沿用旧页。')
 return {'schema_version':1,'task_id':task['id'],'revision':task['revision'],'run_id':run_id,'record':metadata,'field':field,'source_sha256':token,'total':len(rows),'succeeded':sum(r['ok'] for r in rows),'failed':sum(not r['ok'] for r in rows),'verification':'saved_per_item_flags_only','task_changed':False,'network_requested':False,'business_verified':False,'note':NOTE},rows

def query(request,allowed):
 if set(request.query_params)-allowed or any(len(request.query_params.getlist(k))!=1 for k in request.query_params):raise HTTPException(422,'查询字段须明确且唯一，不接受重复或未适配条件。')

def register(h):
 router=APIRouter()
 @router.get('/api/tasks/{item_id}/runs/{run_id}/iteration-results')
 def page(request:Request,response:Response,item_id:str,run_id:str,revision:str|None=None,field:str|None=None,state:str='all',offset:str='0',source:str|None=None):
  query(request,{'revision','field','state','offset','source'});response.headers['Cache-Control']='no-store'
  if not re.fullmatch(r'0|[1-9][0-9]{0,3}',offset):raise HTTPException(422,'分页位置须为明确的非负整数。')
  offset=int(offset)
  if state not in {'all','failed'} or offset<0 or offset>1000 or offset%PAGE:raise HTTPException(422,'请使用全部或失败筛选及20项分页边界。')
  if offset and source is None:raise HTTPException(422,'后续页须核对完整结果来源，不自动拼接不同来源。')
  with h.store.lock:
   value,rows=snapshot(h,item_id,run_id,revision,field,source);selected=rows if state=='all' else [r for r in rows if not r['ok']]
   if offset>=len(selected) and offset!=0:raise HTTPException(422,'分页已超出所选结果范围，不显示部分完成。')
   preview=[]
   for row in selected[offset:offset+PAGE]:
    text=json.dumps(row['value'],ensure_ascii=False,allow_nan=False,indent=2);preview.append({'index':row['index'],'ok':row['ok'],'error_category':row['error_category'],'failed_stage':row.get('failed_stage'),'value_preview':text[:2000],'value_characters':len(text),'value_truncated':len(text)>2000})
   return {**value,'state':state,'offset':offset,'page_size':PAGE,'selected_total':len(selected),'rows':preview}
 @router.get('/api/tasks/{item_id}/runs/{run_id}/iteration-results/export')
 def export(request:Request,item_id:str,run_id:str,revision:str|None=None,field:str|None=None,state:str='all',source:str|None=None):
  query(request,{'revision','field','state','source'})
  if state not in {'all','failed'} or source is None:raise HTTPException(422,'导出须明确筛选并核对已读取的完整结果来源。')
  with h.store.lock:
   value,rows=snapshot(h,item_id,run_id,revision,field,source);selected=rows if state=='all' else [r for r in rows if not r['ok']];raw=encoded({**value,'state':state,'selected_total':len(selected),'items':selected})
   return Response(raw,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="sierra-items-{state}.json"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Sierra-Task-ID':item_id,'X-Sierra-Revision':str(value['revision']),'X-Sierra-Run-ID':run_id,'X-Sierra-Source-SHA256':value['source_sha256'],'X-Sierra-Content-SHA256':hashlib.sha256(raw).hexdigest()})
 h.app.include_router(router)
