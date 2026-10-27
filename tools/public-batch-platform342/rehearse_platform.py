import os,sys,json,tempfile,copy,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1];mode=sys.argv[1] if len(sys.argv)==2 else 'success'
sys.path.insert(0,str(PROJECT/'work/branch-mainline289'));from support import snapshot
before=snapshot();assert before==json.loads((PROJECT/'work/branch-mainline289/post-success-snapshot.json').read_text('utf-8'))
with tempfile.TemporaryDirectory(dir=ROOT,prefix='platform-rehearse-') as folder:
 os.environ['FLOWCRAFT_DATA_DIR']=folder;sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
 import httpx
 from fastapi.testclient import TestClient
 from app import main
 from app.storage import Store
 from app.dsl_roundtrip import parse,digest
 from app.workflow_publication import core
 from boundary import Boundary,require
 from synthetic_transport import SyntheticDify
 from platform_pipeline import run
 from execute import dispatch
 from data_guard import capture,guarded_store,verify
 record={'mode':mode,'state':'preflight','real_http':0,'model_http':0};fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));graph_digest=digest(core(parse((ROOT/'candidate.yml').read_text('utf-8'),'workflow')['workflow']))
 with TestClient(main.app) as api:
  env=api.post('/api/environments',json={'name':'公开隔离来源','base_url':'https://public-dify.invalid','version':'1.17.1','service_app_id':'11111111-1111-4111-8111-111111111111','service_api_key':'app-PUBLICOLDKEY-FIXTURE'}).json()
  current=main.store.get('environment',env['id']);current.update(console_workspace_id='22222222-2222-4222-8222-222222222222',console_login_binding={'base_url':current['base_url'],'version':current['version'],'workspace_id':'22222222-2222-4222-8222-222222222222'})
  main.store.put_with_secrets('environment',env['id'],current,{'console_login_email':'public@example.invalid','console_login_password':'public-fixture-only'})
  for i in range(16):assert api.post('/api/tasks',json={'name':'公开保护任务'+str(i),'app_type':'workflow','environment_id':env['id']}).status_code==201
  main.get_settings();old=capture(main.store);boundary=Boundary(current['base_url'],current['console_workspace_id'],graph_digest,fixture,record,[current['service_app_id']]);Guarded=guarded_store(Store,old,env['id'],boundary,current,fixture['task_name']);store=Guarded(Path(folder));main.store=store
  fake=SyntheticDify(boundary,mode)
  def forbidden(*a,**kw):raise RuntimeError('Physical transport/model forbidden')
  httpx.HTTPTransport.handle_request=forbidden;main.call_model=forbidden
  async def physical(request):
   response=await fake(request)
   if mode=='lost_key_reply' and request.method=='POST' and request.url.path.endswith('/api-keys'):raise httpx.ReadTimeout('PUBLIC_SYNTHETIC_LOST_REPLY',request=request)
   return response
  async def transport(own,request):return await dispatch(boundary,physical,request)
  httpx.AsyncHTTPTransport.handle_async_request=transport
  try:
   task,raw=run(api,env['id'],record);require(mode=='success','Injected failure unexpectedly passed');(ROOT/'rehearse-failure-items.json').write_bytes(raw)
   require(len(store.list('task'))==17 and not main.budgets.get(task['id'])['entries'],'Unexpected task/model budget effect')
  except Exception as exc:
   record.update(state='stopped_needs_review',error_type=type(exc).__name__)
   if mode=='success':
    (ROOT/'rehearse-success-failed.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');raise
  if mode!='success':
   expected={'wrong_workspace':('reconnect',0,0,0,0),'fail_login':('reconnect',0,0,0,0),'import_401':('import',1,0,0,0),'fail_publish':('publish',1,1,0,0),'fail_key':('create_key',1,1,1,0),'lost_key_reply':('create_key',1,1,1,0),'fail_run':('run',1,1,1,1),'bad_output':('run',1,1,1,1)}[mode]
   require(record['state']=='stopped_needs_review' and record['phase']==expected[0] and tuple(boundary.counts[k] for k in ('import','publish','key','run'))==expected[1:],'Failure did not stop at intended stage/count')
   require(boundary.counts['login']==1,'Unexpected login dispatch/retry')
   if mode in ('wrong_workspace','fail_login'):require(store.owner is None and len(store.list('task'))==16,'Task created despite failed admission')
   if mode in ('fail_key','lost_key_reply'):require(store.list('app_runtime_key_creation')[0]['state']=='unknown','Uncertain key write was not kept unknown')
   if mode=='import_401':require(boundary.halted and boundary.counts['login']==1,'Authentication retry was not stopped')
  record['protection']=verify(store,old,env['id']);record['simulated_dify_dispatches']=len(record['dispatches']);record['live_attempt_created']=False
assert not Path(folder).exists() and snapshot()==before
record['production16_snapshot_kept']=True
record['program_sha256']={f.name:__import__('hashlib').sha256(f.read_bytes()).hexdigest() for f in ROOT.glob('*.py')}
(ROOT/('rehearse-'+mode+'-proof.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');print(json.dumps({'state':record['state'],'simulated':record['dispatch_counts'],'real_http':0}))
