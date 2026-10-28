"""One bounded local browser workspace using unchanged product API and a guarded Store."""
import copy,json,os,socket,subprocess,sys,tempfile,threading,time
from decimal import Decimal
from pathlib import Path
from guard import Boundary,guarded_store,capture,verify,require,digest,resource_graph,known_apps
from reviews import Reviews
from transport import dispatch
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
MODEL_PHASES=('vague_interview','complete_interview','first_plan','changed_interview','changed_plan')
PHASES=('vague_interview','complete_interview','first_plan','original_import','original_publish','original_key','original_hit','original_miss','changed_interview','changed_plan','modified_import','modified_publish','modified_key','modified_hit','modified_miss')

def run(mode,output,playwright,plan=None,record=None,save_callback=None):
 live=mode=='live';output=Path(output);fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));record=record if record is not None else {'state':'preflight','mode':mode,'physical_http':0,'automatic_retry':False,'business_acceptance_complete':False};record['model_requests']=[]
 save_lock=threading.RLock()
 def save():
  with save_lock:
   temp=output/'progress-writing.tmp';temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(temp,output/'progress.json')
   if save_callback:save_callback()
 sys.path.insert(0,str(PROJECT/'backend'))
 with tempfile.TemporaryDirectory(dir=output,prefix='module-') as folder:
  os.environ['FLOWCRAFT_DATA_DIR']=folder
  import httpx,uvicorn
  from fastapi import Request,HTTPException
  from fastapi.responses import JSONResponse
  from fastapi.testclient import TestClient
  from app import main as h
  h.c1_fixture=fixture
  from app.storage import Store
  from app.planning import reserve_cost,PlanningStopped
  if live:
   require(ROOT==PROJECT/'work/c1-resume360','Live worker is only the frozen canonical package')
   from execute import authorize_worker
   authorize_worker(plan,record)
   store=Store(PROJECT/'data');environment=store.get('environment',plan['environment_id']);provider=store.get('provider',plan['provider_id']);h.DATA_ROOT=store.root;h.store=store
  else:
   with TestClient(h.app) as api:
    environment=api.post('/api/environments',json={'name':'公开合成专用来源','base_url':'https://public-dify.invalid','version':'1.17.1','console_token':'PUBLIC_OLD_CONSOLE_TOKEN','csrf_token':'PUBLIC_OLD_CSRF_TOKEN','service_api_key':'app-PUBLIC_OLD_RUNTIME_KEY','service_app_id':'11111111-1111-4111-8111-111111111111'}).json();environment=h.store.get('environment',environment['id']);environment.update(console_workspace_id='22222222-2222-4222-8222-222222222222',console_login_binding={'base_url':environment['base_url'],'version':'1.17.1','workspace_id':'22222222-2222-4222-8222-222222222222'});h.store.put_with_secrets('environment',environment['id'],environment,{'console_login_email':'public@example.invalid','console_login_password':'PUBLIC_SYNTHETIC_ONLY'})
    provider=api.post('/api/providers',json={'name':'公开合成模型','provider':'deepseek','base_url':'https://api.deepseek.com','model':'deepseek-flash','api_key':'PUBLIC_SYNTHETIC_ONLY','role':'main','pricing':{'input_per_million_usd':0.3,'output_per_million_usd':1.2}}).json();provider=h.store.get('provider',provider['id'])
    for i in range(17):require(api.post('/api/tasks',json={'name':'公开保护Task'+str(i),'app_type':'workflow','environment_id':environment['id']}).status_code==201,'Fixture Task')
    seed=api.post('/api/tasks',json={'name':fixture['task_name'],'app_type':'workflow','environment_id':environment['id']}).json();seed_id=seed['id']
    configuration=copy.deepcopy(fixture['configuration']);configuration['assistant_provider_id']=provider['id']
    seed=api.patch('/api/tasks/'+seed_id,json={'expected_revision':seed['revision'],'configuration':configuration}).json()
    seed=api.post('/api/tasks/'+seed_id+'/test-cases',json={'revision':seed['revision'],'cases':fixture['cases']}).json()
    require('revision' in seed,'Synthetic case preparation failed')
    r=api.patch('/api/tasks/'+seed_id+'/execution-limits',json={'max_started_runs':4,'max_total_minutes':20,'max_reported_cost_usd':None,'revision':seed['revision'],'policy_revision':0,'note':'公开合成旧批策略，不派发运行。','acknowledge_scope':True})
    require(r.status_code==200,'Synthetic limits preparation failed')
    previous_model=h.call_model
    async def previous_failure(*a,**kw):return json.dumps({'message':'公开旧失败候选','requirements_patch':{'knowledge':'拟议知识库检索'},'intake_review':{'schema_version':1,'checks':[],'questions':[]}}),{'prompt_tokens':100,'completion_tokens':100}
    h.call_model=previous_failure
    try:r=api.post('/api/tasks/'+seed_id+'/messages',json={'content':'我想从零做公开合成售后问答，请先追问。'})
    finally:h.call_model=previous_model
    require(r.status_code==200 and r.json().get('interview_attempts'),'Synthetic original failure missing')
   store=h.store
  initial_task=store.get('task',plan['target_task_id'] if live else seed_id);initial_budget=store.get('task_budget',initial_task['id'])
  from reuse_policy import validate_start
  validate_start(initial_task,initial_budget,store.get('execution_limits',initial_task['id']),fixture,environment['id'],provider['id'])
  before=capture(store);boundary=Boundary(environment,provider,fixture,record,known_apps(store));boundary.owner=initial_task['id'];boundary.owner_configured=True;record['task_id']=boundary.owner;Guarded=guarded_store(Store,before,environment,provider,boundary,fixture,initial_task,initial_budget);h.store=Guarded(store.root);store=h.store;boundary.store=store;boundary.persist=save;boundary.stop_requested=lambda:(output/'stop.json').exists();reviews=Reviews(output,h,record,live,save)
  original_budget=h.budgets.call
  async def budget_call(item_id,revision,kind,selected,key,messages,**kwargs):
   phase=record.get('phase');require(key==store.secret(provider['id'],'api_key'),'Model credential/profile mismatch');require(item_id==boundary.owner and selected==provider and phase in MODEL_PHASES and all(x['phase']!=phase for x in record['model_requests']) and len(record['model_requests'])<5,'Unexpected model phase or repeat')
   require(kwargs.get('max_tokens')==6000 and kwargs.get('timeout',0)<=120 and not kwargs.get('stream'),'Model token/timeout/stream boundary')
   cost=reserve_cost(messages,provider['pricing'],6000);require(cost<=Decimal('.055') and cost+sum((Decimal(x['reserved_estimate_usd']) for x in record['model_requests']),Decimal(0))<=Decimal('.275'),'Model estimate boundary')
   entry={'phase':phase,'messages_sha256':digest(messages),'reserved_estimate_usd':str(cost)};record['model_requests'].append(entry);boundary.model_pending=entry;save();return await original_budget(item_id,revision,kind,selected,key,messages,**kwargs)
  h.budgets.call=budget_call
  def forbid(*a,**kw):raise RuntimeError('Synchronous physical HTTP forbidden')
  original_transport=httpx.AsyncHTTPTransport.handle_async_request;httpx.HTTPTransport.handle_request=forbid
  from synthetic import Synthetic
  synthetic=Synthetic(h,boundary,fixture,mode)
  async def physical(request):return await synthetic(request)
  async def transport(own,request):return await dispatch(boundary,(lambda req:original_transport(own,req)) if live else physical,request)
  httpx.AsyncHTTPTransport.handle_async_request=transport
  h.app.middleware_stack=None  # Rebuild the disposable worker's stack before its server starts.
  # Filter only read-only workspace indexes, keeping the batch UI off unrelated private Tasks/profiles.
  @h.app.middleware('http')
  async def restrict(request:Request,call_next):
   path=request.url.path
   if request.method=='GET' and path=='/api/environments':return JSONResponse([h.env_public(store.get('environment',environment['id']))])
   if request.method=='GET' and path=='/api/providers':return JSONResponse([h.provider_public(provider)])
   if request.method=='GET' and path in ('/api/tasks/summaries','/api/tasks'):
    return JSONResponse(([h.get_task(boundary.owner)] if path=='/api/tasks' else [x for x in store.task_summaries() if x['id']==boundary.owner]) if boundary.owner else [])
   if request.method!='GET' and path.startswith('/api/') and (boundary.halted or boundary.stop_requested()):return JSONResponse(status_code=409,content={'detail':'本独立批已停止，不重试。'})
   if path.startswith('/api/tasks/') and path.split('/')[3] not in ('summaries',boundary.owner):return JSONResponse(status_code=404,content={'detail':'本批仅展示新任务，不读取其他任务正文。'})
   response=await call_next(request)
   if request.method!='GET' and path.startswith('/api/') and response.status_code>=400:
    expected=path.endswith('/plan/generate') and response.status_code==422 and record.get('phase')=='changed_plan' and h.get_task(boundary.owner)['planning_runs'][-1]['status']=='paused'
    if not expected:boundary.halted=True;record['api_failure']={'path':path,'status':response.status_code};save()
   return response
  @h.app.post('/__batch/phase')
  def phase(value:dict):
   name=value.get('phase');require(name in PHASES and value.get('task_id')==boundary.owner,'Wrong phase source')
   previous=record.get('phase');expected=PHASES[0] if previous=='reconnect' else PHASES[PHASES.index(previous)+1] if previous in PHASES and previous!=PHASES[-1] else None
   require(name==expected,'Phase skipped/repeated');task=h.get_task(boundary.owner)
   if name in ('complete_interview','first_plan','original_import','changed_plan','modified_import'):
    required={'complete_interview':'vague_interview','first_plan':'complete_interview','original_import':'first_plan','changed_plan':'changed_interview','modified_import':'changed_plan'}[name];require(required in record.get('reviews',{}),'Explicit local content review missing')
   if name=='changed_interview':
    runs=[r for r in task['runs'] if r.get('kind')=='run'];require(len(runs)==2 and all(r['status']=='success' and r['evaluation']['status']=='passed' and any(d.get('trace_state')=='read' and d.get('source_graph',{}).get('matched') is True for d in r.get('diagnostics',[])) for r in runs),'Original two cases and trace must pass before new model calls')
   if name.endswith('_import'):
    from app.workflow_publication import core
    from app.dsl_roundtrip import parse
    which='first_plan' if name=='original_import' else 'changed_plan';require(digest(task['workflow_plan'])==record['reviewed_plan_digests'][which],'Current plan differs from reviewed model candidate');record['approved_graph_digest']=digest(resource_graph(parse(h.artifact_path(task).read_text('utf-8'),'workflow'),fixture,'original' if name=='original_import' else 'modified'))
   record['phase']=name;save();return {'phase':name,'network_requested':False}
  @h.app.post('/__batch/review-stage')
  def review(value:dict):require(value.get('task_id')==boundary.owner and value.get('stage')==record.get('phase'),'Review phase mismatch');return reviews.prepare(value['stage'])
  @h.app.get('/__batch/review-stage')
  def poll(stage:str):return reviews.poll(stage)
  record['phase']='reconnect';save()
  try:
   with TestClient(h.app) as api:
    base='/api/environments/'+environment['id']+'/saved-login/';r=api.post(base+'reconnect-plan',json={});require(r.status_code==200,'Reconnect plan failed');p=r.json();r=api.post(base+'reconnect',json={'plan_id':p['id'],'review_token':p['review_token'],'confirm_reconnect':True});require(r.status_code==200 and r.json()['record']['state']=='succeeded','Reconnect failed')
  except BaseException as exc:
   boundary.halted=True;record.update(state='stopped_needs_review',error_type=type(exc).__name__,protection=verify(store,before,environment,boundary));save();raise
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  server=uvicorn.Server(uvicorn.Config(h.app,host='127.0.0.1',port=port,log_level='error',timeout_graceful_shutdown=3));thread=threading.Thread(target=server.run,daemon=True);thread.start()
  try:
   for _ in range(150):
    if server.started:break
    require(thread.is_alive(),'Worker failed to start');time.sleep(.1)
   require(server.started,'Local worker not ready');info={'base':'http://127.0.0.1:'+str(port),'fixture':fixture,'target_task_id':boundary.owner,'environment_id':environment['id'],'provider_id':provider['id'],'output':str(output)};(output/'info.json').write_text(json.dumps(info,ensure_ascii=False),'utf-8')
   record['state']='browser_started';save();result=subprocess.run(['node',str(ROOT/'journey.cjs'),playwright,str(output/'info.json')],cwd=PROJECT,timeout=1800);require(result.returncode==0,'Browser chain failed')
   task=h.get_task(boundary.owner);runs=[r for r in task['runs'] if r.get('kind')=='run'];require(len(runs)==4 and all(r['status']=='success' and r['evaluation']['status']=='passed' for r in runs),'Four declared cases not passed');require(boundary.counts['model']==5 and len(boundary.apps)==2 and all(v['counts']=={'publish':1,'key':1,'run':2} for v in boundary.apps.values()) and len(record.get('reviews',{}))==5,'Full chain counts/reviews not reached')
   from verify_delivery import verify as delivery_verify
   record['delivery']=delivery_verify(output,fixture,boundary.owner,environment['id'],boundary.apps)
   record.update(state='passed',protection=verify(store,before,environment,boundary),business_acceptance_complete=False);save()
  except BaseException as exc:
   boundary.halted=True;record.update(state='stopped_needs_review',error_type=type(exc).__name__)
   try:record['protection']=verify(store,before,environment,boundary)
   except Exception as check:record['protection_error_type']=type(check).__name__
   save();raise
  finally:
   server.should_exit=True;thread.join(timeout=10);require(not thread.is_alive(),'Worker did not exit');boundary.login_tokens=None
   for value in boundary.apps.values():value['key']=None
 return record
