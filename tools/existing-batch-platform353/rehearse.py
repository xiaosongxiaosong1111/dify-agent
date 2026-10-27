"""Complete same-API sequence against a synthetic existing imported Task. No physical HTTP."""
import argparse,copy,json,os,socket,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
p=argparse.ArgumentParser();p.add_argument('mode',choices=['success','fail_login','wrong_workspace','changed_draft','already_published','fail_publish','lost_publish_reply','fail_key','lost_key_reply','fail_run','bad_output','tamper_evidence']);p.add_argument('--output',required=True);args=p.parse_args()
out=Path(args.output).resolve();assert out.is_relative_to(PROJECT/'work');out.mkdir(exist_ok=False,parents=True)
from support import ReadOnly,sha
from data_guard import capture,guarded_store,verify
before=capture(ReadOnly(PROJECT/'data')) if (PROJECT/'data/flowcraft.sqlite3').exists() else None
with tempfile.TemporaryDirectory(dir=out,prefix='isolated-') as folder:
 os.environ['FLOWCRAFT_DATA_DIR']=folder
 import httpx
 from fastapi.testclient import TestClient
 from app import main
 from app.storage import Store
 from app.dsl_roundtrip import parse,digest
 from app.workflow_publication import core
 from app.dify import DifyError
 from app.publication_recovery import register_evidence
 from boundary import Boundary,require
 from fixture_setup import LocalPipeline
 from synthetic_transport import SyntheticDify
 from platform_pipeline import run
 from transport import dispatch
 def forbid(*a,**k):raise RuntimeError('Physical HTTP/model forbidden')
 httpx.HTTPTransport.handle_request=forbid;httpx.AsyncHTTPTransport.handle_async_request=forbid;main.call_model=forbid
 with TestClient(main.app) as api:
  env=api.post('/api/environments',json={'name':'公开隔离已导入来源','base_url':'https://public-dify.invalid','version':'1.17.1','service_app_id':str(uuid.uuid4()),'service_api_key':'app-PUBLICOLDKEY-FIXTURE','console_token':'PUBLIC_OLD_CONSOLE_TOKEN','csrf_token':'PUBLIC_OLD_CSRF_TOKEN'}).json()
  environment=main.store.get('environment',env['id']);workspace=str(uuid.uuid4());environment.update(console_workspace_id=workspace,console_login_binding={'base_url':environment['base_url'],'version':environment['version'],'workspace_id':workspace})
  main.store.put_with_secrets('environment',env['id'],environment,{'console_login_email':'public@example.invalid','console_login_password':'public-fixture-only'})
  for i in range(16):assert api.post('/api/tasks',json={'name':'公开保护任务'+str(i),'app_type':'workflow','environment_id':env['id']}).status_code==201
  task=LocalPipeline(api,env['id'],{}).prepare();native=parse(main.artifact_path(task).read_text('utf-8'),'workflow');app=str(uuid.uuid4());task.update(dify_app_id=app,status='imported');task['runs'].append({'id':str(uuid.uuid4()),'kind':'import','status':'success','revision':task['revision'],'environment_id':env['id'],'result':{'app_id':app},'dsl_baseline':copy.deepcopy(native)})
  main.store.put('task',task['id'],task)
  original_request=main.DifyClient.request
  async def fixture_request(self,method,path,**kw):
   if method=='POST':raise DifyError('Synthetic admission stopped before physical HTTP')
   return copy.deepcopy(native['workflow'])|{'hash':'synthetic-old-native'} if path.endswith('/draft') else None
  main.DifyClient.request=fixture_request
  proposal=api.post(f"/api/tasks/{task['id']}/workflow-publication/prepare",json={'revision':task['revision']}).json()
  r=api.post(f"/api/tasks/{task['id']}/workflow-publication/confirm",json={'revision':task['revision'],'proposal_id':proposal['id'],'review_token':proposal['review_token'],'confirm_publish':True});assert r.status_code==502
  main.DifyClient.request=original_request
  source_task=main.store.get('task',task['id']);publication=main.store.get('workflow_publication',proposal['id']);summary={'schema_version':1,'task_id':task['id'],'revision':task['revision'],'app_id':app,'publication_id':proposal['id'],'environment_id':env['id'],'graph_digest':publication['graph_digest'],'source_commit':'a'*40,'report_path':'docs/synthetic.json','batch_id':'synthetic','publish_dispatches':0,**{k:'b'*64 for k in ('report_sha256','plan_sha256','manifest_sha256','approval_sha256','attempt_sha256')}}
  evidence,_=register_evidence(main,summary,'agent_delegated','仅隔离合成证据，不是平台事实。')
  main.get_settings();old=capture(main.store);record={'state':'preflight','mode':args.mode,'physical_http':0,'model_http':0};fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'))
  boundary=Boundary(environment['base_url'],workspace,publication['graph_digest'],fixture,record,app,task['id'],evidence['id'])
  Guarded=guarded_store(Store,old,env['id'],boundary,environment,source_task,evidence);store=Guarded(Path(folder));main.store=store;boundary.store=store
  fake=SyntheticDify(boundary,args.mode);fake.draft=copy.deepcopy(native['workflow'])|{'hash':'public-native-draft'}
  if args.mode=='changed_draft':fake.draft['graph']['nodes'][0]['data']['title']='changed'
  if args.mode=='already_published':fake.published=copy.deepcopy(fake.draft)|{'id':str(uuid.uuid4())}
  if args.mode=='tamper_evidence':
   e=store.get('publication_dispatch_evidence',evidence['id']);e['issuer_note']='tampered'
   with store.connect() as db:db.execute('UPDATE objects SET value=? WHERE kind=? AND id=?',(json.dumps(e),'publication_dispatch_evidence',evidence['id']))
  async def physical(request):
   response=await fake(request)
   if (args.mode=='lost_key_reply' and request.method=='POST' and request.url.path.endswith('/api-keys')) or (args.mode=='lost_publish_reply' and request.method=='POST' and request.url.path.endswith('/workflows/publish')):raise httpx.ReadTimeout('SYNTHETIC_LOST_REPLY',request=request)
   return response
  async def transport(own,request):return await dispatch(boundary,physical,request)
  httpx.AsyncHTTPTransport.handle_async_request=transport
  plan={'task_id':task['id'],'revision':task['revision'],'app_id':app,'environment_id':env['id'],'evidence_id':evidence['id']}
  try:
   result,raw=run(api,plan,record);require(args.mode=='success','Injected failure unexpectedly passed');(out/'failure-items.json').write_bytes(raw)
  except Exception as exc:
   record.update(state='stopped_needs_review',error_type=type(exc).__name__)
   if args.mode=='success':
    (out/'failed.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');raise
  if args.mode!='success':
   expected={'fail_login':('reconnect',0,0,0),'wrong_workspace':('reconnect',0,0,0),'tamper_evidence':('local_recovery',0,0,0),'changed_draft':('publish',0,0,0),'already_published':('publish',0,0,0),'fail_publish':('publish',1,0,0),'lost_publish_reply':('publish',1,0,0),'fail_key':('create_key',1,1,0),'lost_key_reply':('create_key',1,1,0),'fail_run':('run',1,1,1),'bad_output':('run',1,1,1)}[args.mode]
   require(record['phase']==expected[0] and tuple(boundary.counts[k] for k in ('publish','key','run'))==expected[1:],'Wrong failure stop phase/count')
  if args.mode=='tamper_evidence':
   # Fixture corruption is deliberate; restore its exact original bytes only in this disposable workspace.
   with store.connect() as db:db.execute('UPDATE objects SET value=? WHERE kind=? AND id=?',(json.dumps(evidence),'publication_dispatch_evidence',evidence['id']))
  record['protection']=verify(store,old,env['id'],source_task)
  require(boundary.counts['import']==0 and boundary.counts['login']==1 and len(store.list('task'))==17,'Unexpected Task/import/login')
  require(store.get('workflow_publication',publication['id'])==publication,'Original unknown changed')
  record.update(new_tasks=0,new_apps=0,original_unknown_kept=True,actual_platform_acceptance=False,source_sha256={f.name:sha(f) for f in ROOT.iterdir() if f.is_file()})
assert not Path(folder).exists()
if before is not None:assert capture(ReadOnly(PROJECT/'data'))==before
(out/'proof.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');print(json.dumps({'mode':args.mode,'state':record['state'],'simulated':record['dispatch_counts'],'physical_http':0}))
