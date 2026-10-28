"""Canonical new C1 one-shot. No production Store until a new complete direct approval."""
import argparse,base64,json,os,subprocess,sys,urllib.request
from pathlib import Path
from guard import require
from support import sha,current,ReadOnly
from local_readiness import NotReady
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
LIMITS={'new_tasks':0,'model':5,'reads':48,'login':1,'import':2,'publish':2,'key':2,'run':4}
FROZEN={'execute.py','support.py','freeze.py','guard.py','transport.py','worker.py','synthetic.py','rehearse.py','reviews.py','submit_review.py','verify_delivery.py','gates_check.py','journey.cjs','interview-result.cjs','fixture.json','plan.json','reuse_policy.py','reuse_checks.py','local_readiness.py'}

def validated(root):
 sys.path.insert(0,str(PROJECT/'backend'))
 from app.publication_dispatch_receipt import strict_json,safe_path
 manifest=strict_json((root/'manifest.json').read_bytes());require(manifest.get('schema_version')==1 and set(manifest.get('files',{}))==FROZEN,'Frozen file set invalid')
 for name,value in manifest['files'].items():require(sha(safe_path(root,name))==value,'Frozen source changed')
 plan=strict_json((root/'plan.json').read_bytes());require(plan.get('schema_version')==1 and plan.get('batch_id')=='c1-resume360' and manifest.get('batch_id')==plan['batch_id'] and plan.get('limits')==LIMITS and all(type(v) is int for v in plan['limits'].values()) and plan.get('wall_seconds')==1800 and plan.get('max_each_model_estimate_usd')=='0.055' and plan.get('max_new_model_estimate_usd')=='0.275' and plan.get('target_task_id')=='aa827c91-b683-4a34-9e7f-fa0789f5c252' and all(type(v) is int for k,v in plan.get('explicit_regrant',{}).items() if k!='from_batch') and plan.get('explicit_regrant')=={'from_batch':'c1-existing357','model':5,'reads':48,'import':2,'publish':2,'key':2,'run':4,'new_model_slots':0,'new_reads':0,'new_login':1},'Frozen scope invalid')
 return plan

def approved(root,plan):
 from app.publication_dispatch_receipt import strict_json
 value=strict_json((root/'approval.json').read_bytes())
 require(value.get('authorization_source')=='direct_human_reply' and value.get('decision')=='approve' and value.get('batch_id')==plan['batch_id'] and value.get('plan_sha256')==sha(root/'plan.json') and value.get('manifest_sha256')==sha(root/'manifest.json') and value.get('limits')==LIMITS and all(type(v) is int for v in value['limits'].values()) and value.get('new_independent_scope') is True and value.get('old_reservations_preserved') is True and value.get('model_estimate_book_upper_usd')=='0.755473652' and value.get('explicit_regrant')==plan['explicit_regrant'] and all(type(v) is int for k,v in value['explicit_regrant'].items() if k!='from_batch') and value.get('target_task_id')==plan['target_task_id'] and isinstance(value.get('question_ref'),str) and value['question_ref'].strip() and isinstance(value.get('reply'),str) and value['reply'].strip(),'Explicit regrant and new login approval missing')
 return value

def claim(root,value):
 with (root/'attempt.json').open('x',encoding='utf-8') as f:json.dump(value,f)

def authorize_worker(plan,record):
 require(ROOT==PROJECT/'work/c1-resume360' and not sys.flags.optimize,'Wrong live worker directory')
 require(validated(ROOT)==plan,'Live plan changed');approved(ROOT,plan)
 saved=json.loads((ROOT/'attempt.json').read_text('utf-8'));require(all(saved.get(k)==record.get(k) for k in ('batch_id','plan_sha256','manifest_sha256','approval_sha256')) and saved.get('state')=='admission_started' and saved.get('phase')=='preflight' and saved.get('approval_sha256')==sha(ROOT/'approval.json'),'Live worker has no current consumed admission')
 current(PROJECT,plan)
 with (ROOT/'worker-started.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'approval_sha256':saved['approval_sha256'],'worker_started_once':True},f)

def runtime_check(plan):
 require(sha(PROJECT/'runtime-process.ps1')==plan['runtime_process_sha256'],'Runtime process verification helper changed')
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):return None
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect).open('http://127.0.0.1:8765/api/runtime',timeout=10) as response:runtime=json.load(response)
 require(runtime['build_id']==plan['runtime_build'] and runtime['version']=='0.348.0','Managed runtime changed')
 folder=PROJECT/'.runtime/snapshots'/plan['runtime_build'];manifest=folder/'runtime-manifest.json';require(sha(manifest)==plan['runtime_manifest_sha256'],'Runtime manifest changed')
 values=json.loads(manifest.read_text('utf-8'))
 for name,digest in values['files'].items():
  source=(PROJECT/name).resolve();saved=(folder/name).resolve();require(source.is_relative_to(PROJECT.resolve()) and saved.is_relative_to(folder.resolve()) and sha(source)==digest and sha(saved)==digest,'Source/runtime files differ from frozen snapshot')
 pid=int((PROJECT/'data/server.pid').read_text('utf-8').strip());require(pid>0,'Saved PID invalid')
 script="$ErrorActionPreference='Stop'; Set-Location -LiteralPath 'E:\\workSpace\\dify-agent'; . .\\runtime-process.ps1; $p=Get-CimInstance Win32_Process -Filter 'ProcessId = "+str(pid)+"'; if(-not $p -or -not (Test-SierraCommandLine ([string]$p.CommandLine) 'E:\\workSpace\\dify-agent')){throw 'PID ownership mismatch'}; @{executable=$p.ExecutablePath;command=$p.CommandLine} | ConvertTo-Json -Compress"
 encoded=base64.b64encode(script.encode('utf-16-le')).decode();result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));require(result.returncode==0,'Managed PID verification failed')
 process=json.loads(result.stdout.decode('utf-8-sig'));require(Path(process['executable']).resolve()==(PROJECT/'.venv/Scripts/python.exe').resolve() and str(folder/'backend').lower() in process['command'].lower(),'Saved PID is not frozen runtime process')
 from local_readiness import check
 env=ReadOnly(PROJECT/'data').get('environment',plan['environment_id']);readiness=check(env['base_url'])
 return {'local_dify_readiness':readiness,'verified_pid':pid,'original_runtime_kept':True,'source_manifest_files':len(values['files'])}


def main():
 require(ROOT==PROJECT/'work/c1-resume360' and not sys.flags.optimize,'Source/optimized entry cannot execute live')
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['live']);parser.add_argument('--playwright',required=True);args=parser.parse_args()
 plan=validated(ROOT);approved(ROOT,plan);require(args.playwright==plan['playwright_path'] and Path(args.playwright).is_absolute() and Path(args.playwright).is_dir(),'Use frozen absolute Playwright module path')
 current(PROJECT,plan);admission_runtime=runtime_check(plan)
 record={'batch_id':plan['batch_id'],'state':'admission_started','phase':'preflight','automatic_retry':False,'business_acceptance_complete':False,'plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json'),'approval_sha256':sha(ROOT/'approval.json')};claim(ROOT,record)
 def save():
  path=ROOT/'attempt-writing.tmp';path.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(path,ROOT/'attempt.json')
 try:
  record['runtime']=admission_runtime;current(PROJECT,plan);save()
  output=ROOT/'live-output';output.mkdir(exist_ok=False)
  from worker import run
  run('live',output,args.playwright,plan,record,save)
 except BaseException as exc:
  record.update(state='stopped_needs_review',error_type=type(exc).__name__);save();raise SystemExit('C1独立批已停止并永久消费，不重放或阶段重试；核对安全回执和旧预留。') from None
 print('C1原空需求任务两版固定公开主链已完成；真实语义与25项最终结论仍按实际证据逐项核对。')
if __name__=='__main__':
 try:main()
 except NotReady as exc:raise SystemExit(str(exc)) from None
 except (RuntimeError,ValueError,OSError,KeyError):raise SystemExit('新直接范围、冻结或一次入口无效，未开启新真实阶段，不自动重试。') from None
