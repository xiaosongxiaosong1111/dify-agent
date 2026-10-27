"""New independent one-shot scope; an approval is mandatory before production Store construction."""
import base64,hashlib,json,os,sqlite3,subprocess,sys,tempfile,urllib.request
from pathlib import Path
from boundary import require
from support import sha,ReadOnly,current,check_consumed
from transport import dispatch
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
LIMITS={'new_tasks':0,'reads':16,'login':1,'import':0,'publish':1,'key':1,'run':1,'model':0}
FROZEN={'execute.py','support.py','boundary.py','boundary_base.py','transport.py','data_guard.py','data_guard_base.py','platform_pipeline.py','local_pipeline.py','synthetic_transport.py','rehearse.py','freeze.py','gates_check.py','candidate.yml','candidate-plan.json','fixture_setup.py','fixture.json','plan.json'}

def validated_plan(root):
 from app.publication_dispatch_receipt import strict_json,safe_path
 manifest=strict_json((root/'manifest.json').read_bytes());require(manifest.get('schema_version')==1 and set(manifest.get('files',{}))==FROZEN,'Frozen file coverage invalid')
 for name,value in manifest['files'].items():require(sha(safe_path(root,name))==value,'Frozen file changed')
 plan=strict_json((root/'plan.json').read_bytes());require(plan.get('schema_version')==1 and plan.get('batch_id')=='existing-batch-platform353' and manifest.get('batch_id')==plan['batch_id'] and plan.get('limits')==LIMITS and all(type(v) is int for v in plan['limits'].values()) and plan.get('wall_seconds')==600,'Frozen scope invalid')
 return plan

def approved(root,plan):
 from app.publication_dispatch_receipt import strict_json
 value=strict_json((root/'approval.json').read_bytes())
 require(value.get('authorization_source')=='direct_human_reply' and value.get('decision')=='approve' and value.get('batch_id')==plan['batch_id'] and value.get('plan_sha256')==sha(root/'plan.json') and value.get('manifest_sha256')==sha(root/'manifest.json') and value.get('limits')==LIMITS and value.get('explicit_zero_dispatch350_transfer_authorized') is True and value.get('old_reservations_preserved') is True and isinstance(value.get('question_ref'),str) and value['question_ref'].strip() and isinstance(value.get('reply'),str) and value['reply'].strip(),'Direct independent scope/transfer approval missing')
 return value

def claim_attempt(root,record):
 with (root/'attempt.json').open('x',encoding='utf-8') as stream:json.dump(record,stream)

def runtime_check(plan):
 require(sha(PROJECT/'runtime-process.ps1')==plan['runtime_process_sha256'],'Runtime process verification helper changed')
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):return None
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect).open('http://127.0.0.1:8765/api/runtime',timeout=10) as response:runtime=json.load(response)
 require(runtime['build_id']==plan['runtime_build'] and runtime['version']=='0.346.0','Managed runtime changed')
 folder=PROJECT/'.runtime/snapshots'/plan['runtime_build'];manifest=folder/'runtime-manifest.json';require(sha(manifest)==plan['runtime_manifest_sha256'],'Runtime manifest changed')
 values=json.loads(manifest.read_text('utf-8'))
 for name,digest in values['files'].items():
  source=(PROJECT/name).resolve();saved=(folder/name).resolve();require(source.is_relative_to(PROJECT.resolve()) and saved.is_relative_to(folder.resolve()) and sha(source)==digest and sha(saved)==digest,'Source/runtime files differ from frozen snapshot')
 pid=int((PROJECT/'data/server.pid').read_text('utf-8').strip());require(pid>0,'Saved PID invalid')
 script="$ErrorActionPreference='Stop'; Set-Location -LiteralPath 'E:\\workSpace\\dify-agent'; . .\\runtime-process.ps1; $p=Get-CimInstance Win32_Process -Filter 'ProcessId = "+str(pid)+"'; if(-not $p -or -not (Test-SierraCommandLine ([string]$p.CommandLine) 'E:\\workSpace\\dify-agent')){throw 'PID ownership mismatch'}; @{executable=$p.ExecutablePath;command=$p.CommandLine} | ConvertTo-Json -Compress"
 encoded=base64.b64encode(script.encode('utf-16-le')).decode();result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));require(result.returncode==0,'Managed PID verification failed')
 process=json.loads(result.stdout.decode('utf-8-sig'));require(Path(process['executable']).resolve()==(PROJECT/'.venv/Scripts/python.exe').resolve() and str(folder/'backend').lower() in process['command'].lower(),'Saved PID is not frozen runtime process')
 return {'verified_pid':pid,'original_runtime_kept':True,'source_manifest_files':len(values['files'])}


def main():
 require(ROOT==PROJECT/'work/batch-platform353' and not sys.flags.optimize and sys.argv[1:]==['live'],'Only canonical explicit live entry accepted')
 sys.path.insert(0,str(PROJECT/'backend'))
 plan=validated_plan(ROOT);approved(ROOT,plan)
 record={'batch_id':plan['batch_id'],'state':'admission_started','phase':'preflight','model_http':0,'automatic_retry':False,'business_acceptance_complete':False,'plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json'),'approval_sha256':sha(ROOT/'approval.json'),'task_id':plan['task_id'],'revision':plan['revision'],'existing_app_id':plan['app_id'],'old_publication_id':plan['old_publication_id'],'evidence_id':plan['evidence_id']};claim_attempt(ROOT,record)
 def save():
  temp=ROOT/'attempt-writing.tmp';temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(temp,ROOT/'attempt.json')
 store=None;boundary=None;source_task=None
 try:
  record['runtime']=runtime_check(plan);check_consumed(PROJECT,plan);current(plan,ReadOnly(PROJECT/'data'));save()
  with tempfile.TemporaryDirectory(dir=ROOT,prefix='isolated-import-') as folder:
   os.environ['FLOWCRAFT_DATA_DIR']=folder;sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
   import httpx
   from fastapi.testclient import TestClient
   from app import main as h
   from app.storage import Store
   from app.publication_recovery import matching_evidence
   from boundary import Boundary
   from data_guard import guarded_store,verify
   from platform_pipeline import run
   readonly=ReadOnly(PROJECT/'data');source_task,environment,evidence=current(plan,readonly)
   fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));boundary=Boundary(environment['base_url'],plan['workspace_id'],plan['graph_digest'],fixture,record,plan['app_id'],plan['task_id'],plan['evidence_id']);boundary.persist=save
   Guarded=guarded_store(Store,plan['protected_data'],environment['id'],boundary,environment,source_task,evidence);store=Guarded(PROJECT/'data');boundary.store=store;h.store=store;h.DATA_ROOT=store.root
   current(plan,store);matching_evidence(h,source_task,evidence['id']);h.require_idle(source_task)
   require(h.execution_limits.preflight(source_task,1)['limits_allow_requested_runs'],'Whole run capacity unavailable')
   def forbid(*a,**kw):raise RuntimeError('Synchronous HTTP and all model calls forbidden')
   original=httpx.AsyncHTTPTransport.handle_async_request;httpx.HTTPTransport.handle_request=forbid;h.call_model=forbid
   async def actual(transport,request):return await dispatch(boundary,lambda req:original(transport,req),request)
   httpx.AsyncHTTPTransport.handle_async_request=actual
   with TestClient(h.app) as api:task,export=run(api,plan,record)
   require(not boundary.halted and boundary.counts['import']==0 and all(boundary.counts[k]==1 for k in ('login','publish','key','run')) and task['id']==source_task['id'] and task['dify_app_id']==source_task['dify_app_id'],'Expected existing-App completion not observed')
   record['protection']=verify(store,plan['protected_data'],environment['id'],source_task);(ROOT/'live-failure-items.json').write_bytes(export)
  record['state']='passed';save()
 except BaseException as exc:
  record.update(state='stopped_needs_review',error_type=type(exc).__name__)
  if boundary is not None:boundary.halted=True
  if store is not None:
   try:
    from data_guard import verify
    record['protection']=verify(store,plan['protected_data'],plan['environment_id'],source_task)
   except BaseException as check:record['protection_error_type']=type(check).__name__
  save();raise SystemExit('新独立批已停止，禁止重放或阶段重试；旧unknown和预留保持，仅核对安全回执。') from None
 finally:
  if boundary is not None:boundary.key=None;boundary.login_tokens=None
 print('现有App的公开四项及失败原索引下载已核对；不代表全部业务验收。')

if __name__=='__main__':
 try:main()
 except (RuntimeError,ValueError,OSError,KeyError):raise SystemExit('独立授权、冻结包或一次入口不可用；没有开启新真实阶段，不自动重试。') from None
