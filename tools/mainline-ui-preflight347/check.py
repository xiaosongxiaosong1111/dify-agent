"""One blank-task UI chain with controlled model replies; no physical model or Dify HTTP."""
import argparse,contextlib,copy,hashlib,json,os,socket,sqlite3,subprocess,sys,tempfile,threading,time
from pathlib import Path
if sys.flags.optimize:raise SystemExit('Preflight requires normal assertion-enabled Python')
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--playwright',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
assert Path(args.playwright).is_absolute() and Path(args.playwright).is_dir(),'Use explicit installed Playwright path'
output=Path(args.output).resolve();assert output.is_relative_to((PROJECT/'work').resolve()) and output!=(PROJECT/'work').resolve()
output.mkdir(parents=True,exist_ok=False);fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));calls=[]
sys.path[:0]=[str(PROJECT/'tools/public-batch-platform342'),str(PROJECT/'backend')]
from data_guard import capture
class ReadOnly:
 root=PROJECT/'data'
 @contextlib.contextmanager
 def connect(self):
  db=sqlite3.connect((self.root/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True)
  try:yield db
  finally:db.close()
before=capture(ReadOnly()) if (PROJECT/'data/flowcraft.sqlite3').exists() else None
with tempfile.TemporaryDirectory(dir=output,prefix='workspace-') as workspace:
 assert Path(workspace).resolve().is_relative_to(output)
 os.environ['FLOWCRAFT_DATA_DIR']=workspace
 import httpx,uvicorn
 from app import main
 from app.intake import topics
 from fastapi.testclient import TestClient
 def forbid(*a,**kw):raise AssertionError('Physical HTTP/Dify/model forbidden in local mainline preflight')
 httpx.HTTPTransport.handle_request=forbid;httpx.AsyncHTTPTransport.handle_async_request=forbid;main.DifyClient.request=forbid
 async def model(*a,**kw):
  tasks=main.store.list('task');assert len(tasks)==1;task=tasks[0];assert len(calls)<5,'Unexpected extra model/retry in controlled journey'
  if task['status']=='interviewing':
   users=[(i,m) for i,m in enumerate(task['messages']) if m.get('role')=='user' and m.get('purpose')!='discussion'];index,user=users[-1]
   if len(users)==1:
    rows=[{'topic':t['id'],'status':'needs_input','detail':'公开隔离问答，尚需用户明确。','evidence':[]} for t in topics(task)]
    questions=[{'topic':key,'question':'请明确'+key+'。','recommendation':'请按公开合成需求补齐，不默认采纳。','reason':'避免提前构建。','experience':'回答后继续。','cost':'本次为受控替身，不证明真实费用。','manual_work':'需要明确说明。'} for key in ('goal','input','output')]
    value={'message':'尚未搭建，请明确目标、输入和输出。','requirements_patch':{},'intake_review':{'schema_version':1,'checks':rows,'questions':questions}}
   else:
    requirements=copy.deepcopy(fixture['requirements'])
    if '修改无命中' in user['content']:requirements['exceptions']=requirements['exceptions'].replace(fixture['plan']['nodes'][4]['config']['template'],fixture['changed_fallback'])
    hypothetical={**task,'requirements':requirements}
    rows=[{'topic':t['id'],'status':'complete','detail':'受控合成来源已明确，仍需人工确认，不是实际模型质量或资源验收。','evidence':[{'kind':'message','id':str(index),'quote':requirements.get(t['id'],requirements['rules'])}]} for t in topics(hypothetical)]
    value={'message':'公开合成说明已整理，仍需确认需求、流程与配置；未导入或运行。','requirements_patch':requirements,'intake_review':{'schema_version':1,'checks':rows,'questions':[]}}
   kind='interview'
  else:
   assert task['status']=='planning';value=copy.deepcopy(fixture['plan'])
   if fixture['changed_fallback'] in task['requirements']['exceptions']:value['nodes'][4]['config']['template']=fixture['changed_fallback']
   kind='plan'
  calls.append({'kind':kind,'task_id':task['id'],'revision':task['revision'],'synthetic_usage':True})
  return json.dumps(value,ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
 main.call_model=model
 api=TestClient(main.app)
 r=api.post('/api/providers',json={'name':'公开隔离替身','provider':'custom','base_url':'https://example.invalid/v1','model':'static-fixture','api_key':'NOT_A_REAL_KEY','role':'main','pricing':{'input_per_million_usd':1,'output_per_million_usd':2}});assert r.status_code in (200,201),r.text
 assert main.store.list('task')==[],'Only settings may be seeded before browser creates blank task'
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 server=uvicorn.Server(uvicorn.Config(main.app,host='127.0.0.1',port=port,log_level='error',timeout_graceful_shutdown=3));thread=threading.Thread(target=server.run,daemon=True);thread.start()
 try:
  for _ in range(100):
   if server.started:break
   assert thread.is_alive();time.sleep(.1)
  assert server.started
  (output/'info.json').write_text(json.dumps({'base':f'http://127.0.0.1:{port}','fixture':fixture,'output':str(output)}),'utf-8')
  result=subprocess.run(['node',str(ROOT/'journey.cjs'),args.playwright,str(output/'info.json')],cwd=PROJECT,timeout=240)
  tasks=main.store.list('task');state={'tasks':len(tasks),'controlled_model_calls':calls,'physical_model_dify_http':0,'original_data_kept':before is None or capture(ReadOnly())==before}
  if tasks:
   t=tasks[0];state['task']={k:t.get(k) for k in ('id','revision','status','requirements_confirmed','configuration_confirmed','plan_stale','plan_source')};state['task']['intake_required']=t.get('intake_required');state['versions']=len(t.get('versions',[]));state['planning_runs']=[{k:r.get(k) for k in ('kind','status','stop_reason','revision','result_revision')} for r in t.get('planning_runs',[])]
  (output/'backend-proof.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),'utf-8')
  assert result.returncode==0 and len(tasks)==1 and len(calls)==5 and state['original_data_kept'],state
  from verify_delivery import verify
  verify(output,fixture)
  assert tasks[0]['intake_required'] is True and tasks[0]['plan_review_required'] is True and not tasks[0].get('dify_app_id') and not tasks[0]['runs']
 finally:server.should_exit=True;thread.join(timeout=10);assert not thread.is_alive()
assert before is None or capture(ReadOnly())==before
print(json.dumps({'state':'passed','physical_model_dify_http':0,'controlled_model_calls':len(calls),'production_preserved':True}))
