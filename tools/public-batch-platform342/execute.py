"""Frozen one-shot entry. No approval means no production Store construction or attempt."""
import hashlib,json,os,sys,tempfile,time,subprocess,base64,sqlite3,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
FROZEN={'execute.py','boundary.py','data_guard.py','local_pipeline.py','platform_pipeline.py','synthetic_transport.py','rehearse_platform.py','local_rehearsal.py','freeze_bundle.py','gates_check.py','candidate-plan.json','candidate.yml','fixture.json','plan.json'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
 if not value:raise RuntimeError(message)

def validated_plan(root):
 manifest=json.loads((root/'manifest.json').read_text('utf-8'));require(manifest.get('schema_version')==1 and set(manifest.get('files',{}))==FROZEN,'Manifest schema/file coverage not supported')
 for name,digest in manifest['files'].items():
  path=(root/name).resolve();require(path.is_relative_to(root.resolve()) and path.is_file() and sha(path)==digest,'Frozen package hash mismatch')
 plan=json.loads((root/'plan.json').read_text('utf-8'));require(plan['schema_version']==1 and plan['batch_id']=='public-batch-platform342' and plan['limits']=={'new_tasks':1,'reads':16,'login':1,'import':1,'publish':1,'key':1,'run':1,'model':0} and plan['wall_seconds']==600,'Frozen scope not supported')
 return plan

def approved(root,plan):
 path=root/'approval.json';require(path.is_file(),'Not approved: no human authorization record')
 value=json.loads(path.read_text('utf-8'));require(value.get('authorization_source')=='direct_human_reply' and value.get('decision')=='approve' and value.get('batch_id')==plan['batch_id'] and value.get('plan_sha256')==sha(root/'plan.json') and value.get('manifest_sha256')==sha(root/'manifest.json') and isinstance(value.get('question_ref'),str) and bool(value['question_ref'].strip()) and isinstance(value.get('reply'),str) and bool(value['reply'].strip()),'Approval provenance/scope does not match frozen package')
 return value

async def dispatch(boundary,forward,request):
 response=None
 try:
  entry=boundary.admit(request);boundary.persist()
  response=await forward(request)
  # Native transports return an unread response before AsyncClient attaches its request.
  # Observation needs both the full JSON body and request context for Cookie parsing.
  response.request=request;entry['status']=response.status_code;entry['response_body_read']=False;boundary.persist()
  await response.aread();entry['response_body_read']=True
  return boundary.observed(entry,response)
 except BaseException:
  boundary.halted=True
  if response is not None:
   try:await response.aclose()
   except Exception:pass
  raise
 finally:boundary.persist()

def runtime_check(plan):
 require(sha(PROJECT/'runtime-process.ps1')==plan['runtime_process_sha256'],'Runtime process verification helper changed')
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):return None
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect).open('http://127.0.0.1:8765/api/runtime',timeout=10) as response:runtime=json.load(response)
 require(runtime['build_id']==plan['runtime_build'] and runtime['version']=='0.341.0','Managed runtime changed')
 folder=PROJECT/'.runtime/snapshots'/plan['runtime_build'];manifest=folder/'runtime-manifest.json';require(sha(manifest)==plan['runtime_manifest_sha256'],'Runtime manifest changed')
 values=json.loads(manifest.read_text('utf-8'))
 for name,digest in values['files'].items():
  source=(PROJECT/name).resolve();saved=(folder/name).resolve();require(source.is_relative_to(PROJECT.resolve()) and saved.is_relative_to(folder.resolve()) and sha(source)==digest and sha(saved)==digest,'Source/runtime files differ from frozen snapshot')
 pid=int((PROJECT/'data/server.pid').read_text('utf-8').strip());require(pid>0,'Saved PID invalid')
 script="$ErrorActionPreference='Stop'; Set-Location -LiteralPath 'E:\\workSpace\\dify-agent'; . .\\runtime-process.ps1; $p=Get-CimInstance Win32_Process -Filter 'ProcessId = "+str(pid)+"'; if(-not $p -or -not (Test-SierraCommandLine ([string]$p.CommandLine) 'E:\\workSpace\\dify-agent')){throw 'PID ownership mismatch'}; @{executable=$p.ExecutablePath;command=$p.CommandLine} | ConvertTo-Json -Compress"
 encoded=base64.b64encode(script.encode('utf-16-le')).decode();result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));require(result.returncode==0,'Managed PID verification failed')
 process=json.loads(result.stdout.decode('utf-8-sig'));require(Path(process['executable']).resolve()==(PROJECT/'.venv/Scripts/python.exe').resolve() and str(folder/'backend').lower() in process['command'].lower(),'Saved PID is not frozen runtime process')
 return {'verified_pid':pid,'original_runtime_kept':True,'source_manifest_files':len(values['files'])}

def claim_attempt(root,record):
 path=root/'attempt.json'
 with path.open('x',encoding='utf-8') as stream:json.dump(record,stream)
 return path

def main():
 require(ROOT==PROJECT/'work/batch-platform342','Only the canonical one-shot directory may execute live')
 require(not sys.flags.optimize and sys.argv[1:]==['live'],'Only explicit unoptimized live entry is accepted')
 plan=validated_plan(ROOT);approved(ROOT,plan)
 attempt=ROOT/'attempt.json';record={'batch_id':plan['batch_id'],'state':'admission_started','phase':'preflight','model_http':0,'business_acceptance_complete':False,'automatic_retry':False,'plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json')}
 claim_attempt(ROOT,record)
 def save():
  temporary=ROOT/'attempt-writing.tmp';temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(temporary,attempt)
 store=None;boundary=None
 try:
  record['runtime']=runtime_check(plan);save()
  frozen=json.loads((PROJECT/'work/tool-probe291/before.json').read_text('utf-8'))['consumed124_files'];require(frozen==plan['consumed124_files'] and all(sha(PROJECT/'work/branch-mainline289'/name)==value for name,value in frozen.items()),'Consumed124 package changed')
  sys.path.insert(0,str(PROJECT/'work/branch-mainline289'));from support import snapshot
  baseline=snapshot();require(baseline==plan['legacy_snapshot'],'Original production snapshot changed')
  with tempfile.TemporaryDirectory(dir=ROOT,prefix='live-module-') as folder:
   os.environ['FLOWCRAFT_DATA_DIR']=folder;sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
   import httpx
   from fastapi.testclient import TestClient
   from app import main as h
   from app.storage import Store
   from boundary import Boundary,canonical
   from data_guard import guarded_store,capture,verify
   from platform_pipeline import run
   data=PROJECT/'data'
   with sqlite3.connect((data/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
    raw=db.execute('SELECT value FROM objects WHERE kind=? AND id=?',('environment',plan['environment_id'])).fetchone();require(raw is not None,'Dedicated environment missing');environment=json.loads(raw[0]);tasks=[json.loads(row[0]) for row in db.execute("SELECT value FROM objects WHERE kind='task'")]
   require(len(tasks)==16 and all(t.get('status') not in h.BUSY and not t.get('active_interview_id') and not t.get('active_image_operation_id') and all(r.get('status')!='pending' for r in t.get('runs',[])) for t in tasks),'Original tasks not idle')
   require({k:environment.get(k) for k in plan['environment_binding']}==plan['environment_binding'],'Original connection binding changed')
   fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));boundary=Boundary(environment['base_url'],plan['workspace_id'],plan['graph_digest'],fixture,record,plan['original_app_ids']);boundary.persist=save
   Guarded=guarded_store(Store,plan['protected_data'],environment['id'],boundary,environment,fixture['task_name']);store=Guarded(data);require(capture(store)==plan['protected_data'],'Protected data/ciphertext/files changed');h.store=store;h.DATA_ROOT=data
   for old_task in tasks:h.require_idle(old_task)
   def forbid(*a,**kwargs):raise RuntimeError('Synchronous HTTP and all model calls forbidden')
   original=httpx.AsyncHTTPTransport.handle_async_request;httpx.HTTPTransport.handle_request=forbid;h.call_model=forbid
   async def actual(transport,request):return await dispatch(boundary,lambda req:original(transport,req),request)
   httpx.AsyncHTTPTransport.handle_async_request=actual
   with TestClient(h.app) as api:task,export=run(api,environment['id'],record)
   require(not boundary.halted and boundary.counts['import']==boundary.counts['publish']==boundary.counts['key']==boundary.counts['run']==1 and boundary.app==task['dify_app_id'],'Expected one newly delivered App/run')
   (ROOT/'live-failure-items.json').write_bytes(export);record['protection']=verify(store,plan['protected_data'],environment['id'])
  record['state']='passed';save()
 except BaseException as exc:
  record.update(state='stopped_needs_review',error_type=type(exc).__name__)
  if boundary is not None:boundary.halted=True
  if store is not None:
   try:
    from data_guard import verify
    record['protection']=verify(store,plan['protected_data'],plan['environment_id'])
   except BaseException as check:record['protection_error_type']=type(check).__name__
  save();raise SystemExit('本批已停止且禁止重放；仅核对本机安全回执，未自动修复或重试。') from None
 finally:
  if boundary is not None:boundary.key=None;boundary.login_tokens=None
 print('本批声明规则及来源核对完成，非完整业务验收；安全回执已保存。')

if __name__=='__main__':
 try:main()
 except (RuntimeError,ValueError,FileNotFoundError,FileExistsError):raise SystemExit('授权、冻结包或一次性入口不可用，未开启新的真实阶段；已有消费回执时禁止重放。') from None
