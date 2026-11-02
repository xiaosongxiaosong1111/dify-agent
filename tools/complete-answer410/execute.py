"""Frozen canonical one-shot. No production Store before explicit new direct approval."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from common import PROJECT,LIMITS,ReadOnly,capture,digest,require,sha

ROOT=Path(__file__).resolve().parent
FROZEN={'common.py','boundary.py','storage_guard.py','contract.py','journey.py','synthetic.py','worker.py','execute.py','freeze.py','rehearse.py','local_readiness.py','README.md','fixture.json','contract.json','plan.json'}
FAILURE_POLICY={'business_rule_failure_only':True,'max_reports':1,'max_management_reads':4,'post_failure_service_requests':0,'post_failure_remote_writes':0,'stop_after_capture':True}
STATE_POLICY={'names':['order_wait_requested','order_wait_consumed'],'type':'boolean','initial_values':[False,False],'owner_ids':'uuid5:sierra:conversation:{task_id}:{name}','only_declaration_ids_change':True,'followup_bypasses_classifier':True,'explicit_post_plan_review':True}

def check_failure_policy(value):
    require(value==FAILURE_POLICY and all(type(value[k]) is int for k in ('max_reports','max_management_reads','post_failure_service_requests','post_failure_remote_writes')) and value['business_rule_failure_only'] is True and value['stop_after_capture'] is True,'Explicit bounded failure diagnostic policy required')

def load(path):
    def pairs(rows):
        value={}
        for k,v in rows:
            require(k not in value,'Duplicate JSON field');value[k]=v
        return value
    raw=Path(path).read_bytes();require(len(raw)<=10_000_000,'Oversize frozen JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Non-finite JSON'))

def validated(root):
    manifest=load(root/'manifest.json');require(manifest.get('schema_version')==1 and manifest.get('batch_id')=='complete-answer410' and set(manifest.get('files',{}))==FROZEN,'Frozen manifest invalid')
    for name,value in manifest['files'].items():
        path=(root/name).resolve();require(path.parent==root.resolve() and not (root/name).is_symlink() and sha(path)==value,'Frozen source changed')
    plan=load(root/'plan.json')
    require(digest(plan.get('state_policy'))==digest(STATE_POLICY),'Exact reviewed state scope required')
    check_failure_policy(plan.get('failure_diagnostic_policy'))
    require(plan.get('source_model_plan_sha256')=='f7ac6d10dd986fffbfbe410ded616d4956ec7253d70fdf194ee49f3c1e39435c' and plan.get('manual_configuration_review') is True and set(plan.get('protected_isolated',{}))=={'391','394','399','401','405','408','409'},'Exact reviewed model source and seven isolated protections required')
    require(plan.get('batch_id')=='complete-answer410' and plan.get('limits')==LIMITS and all(type(v) is int for v in plan['limits'].values()) and plan.get('new_independent_scope') is True and plan.get('old_reservations_preserved') is True and plan.get('model_estimate_book_upper_usd')=='1.155473652' and plan.get('estimated_new_dify_usd')=='0.05' and plan.get('execution_policy')=={'max_started_runs':6,'max_total_minutes':30,'max_reported_cost_usd':None} and plan.get('wall_seconds')==2700,'Frozen scope invalid')
    require(plan.get('new_conservative_upper')=={'model':35,'reads':1469,'login':46,'import':26,'publish':26,'key':26,'run':120},'Cumulative scope invalid')
    require(plan.get('environment_id')=='202bfb35-2f92-47c1-bc1b-eac32082181d' and plan.get('workspace_id')=='c3306c18-ceb2-4bee-b2d1-796ce2048f17' and plan.get('runtime_build')=='0.374.0-fd1d9147a557103e2af2' and plan.get('backend_path')==str(PROJECT/'.runtime/snapshots'/plan['runtime_build']/'backend'),'Frozen target/runtime invalid')
    return plan

def approved(root,plan):
    approval=load(root/'approval.json')
    require(digest(approval.get('state_policy'))==digest(STATE_POLICY),'State routing and owner identity scope require direct approval')
    check_failure_policy(approval.get('failure_diagnostic_policy'))
    require(approval.get('authorization_source')=='direct_human_reply' and approval.get('decision')=='approve' and approval.get('batch_id')==plan['batch_id'] and approval.get('plan_sha256')==sha(root/'plan.json') and approval.get('manifest_sha256')==sha(root/'manifest.json') and approval.get('limits')==LIMITS and all(type(v) is int for v in approval['limits'].values()) and approval.get('new_independent_scope') is True and approval.get('old_reservations_preserved') is True and approval.get('estimated_new_dify_usd')=='0.05' and approval.get('new_conservative_upper')==plan['new_conservative_upper'] and all(isinstance(approval.get(k),str) and approval[k].strip() for k in ('question_ref','reply')),'New direct approval with exact scope/hashes required')
    return approval

def current(root,plan):
    store=ReadOnly(PROJECT/'data');require(capture(store)==plan['protected_data'],'Original data changed')
    require(len(store.list('task'))==25,'Original Task count changed')
    require(all(t.get('status') not in {'running','planning','interviewing','importing'} and not t.get('active_interview_id') and not any(r.get('status')=='pending' for r in t.get('runs',[])) for t in store.list('task')),'An original Task is active')
    env=store.get('environment',plan['environment_id']);require(env and digest(env)==plan['environment_sha256'] and env.get('console_workspace_id')==plan['workspace_id'],'Connection/workspace changed')
    for name,value in plan['consumed_files'].items():
        path=(PROJECT/name).resolve();require(path.is_relative_to(PROJECT/'work') and sha(path)==value,'Old consumed source/receipt changed')
    verify_isolated(plan)
    return env

def verify_isolated(plan):
    roots={'391':'work/chatflow-model391/live-output/data','394':'work/clarified-chatflow394/live-output/data','399':'work/bounded-chatflow399/live-output/data','401':'work/reviewed-chatflow401/live-output/data','405':'work/offline-candidate405/data','408':'work/reviewed-planning408/live-output/data','409':'work/offline-candidate409/data'}
    require(all(capture(ReadOnly(PROJECT/path))==plan['protected_isolated'][name] for name,path in roots.items()),'Old isolated Task/fees/credentials/assets changed')

def runtime_check(plan):
    require(sha(PROJECT/'runtime-process.ps1')==plan['runtime_process_sha256'],'Runtime helper changed')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**kw):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
    with opener.open('http://127.0.0.1:8765/api/runtime',timeout=10) as r:runtime=json.load(r)
    require(runtime.get('build_id')==plan['runtime_build'] and runtime.get('version')=='0.374.0','Managed runtime changed')
    folder=PROJECT/'.runtime/snapshots'/plan['runtime_build'];require(sha(folder/'runtime-manifest.json')==plan['runtime_manifest_sha256'],'Runtime manifest changed')
    for name,value in load(folder/'runtime-manifest.json')['files'].items():
        source=(PROJECT/name).resolve();saved=(folder/name).resolve();require(source.is_relative_to(PROJECT) and saved.is_relative_to(folder) and sha(source)==value and sha(saved)==value,'Source/snapshot mismatch')
    pid=int((PROJECT/'data/server.pid').read_text('ascii').strip());require(pid>0,'PID unavailable')
    script="$ErrorActionPreference='Stop'; Set-Location -LiteralPath 'E:\\workSpace\\dify-agent'; . .\\runtime-process.ps1; $p=Get-CimInstance Win32_Process -Filter 'ProcessId = "+str(pid)+"'; if(-not $p -or -not (Test-SierraCommandLine ([string]$p.CommandLine) 'E:\\workSpace\\dify-agent')){throw 'Not owned'}; @{executable=$p.ExecutablePath;command=$p.CommandLine} | ConvertTo-Json -Compress"
    encoded=base64.b64encode(script.encode('utf-16-le')).decode()
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));require(result.returncode==0,'PID ownership unavailable')
    process=json.loads(result.stdout.decode('utf-8-sig'));require(Path(process['executable']).resolve()==PROJECT/'.venv/Scripts/python.exe' and str(folder/'backend').lower() in process['command'].lower(),'Wrong executable/snapshot')
    return {'verified_pid':pid,'runtime_build':runtime['build_id'],'source_files_matched':runtime['file_count']}

def authorized(root,plan):
    require(root==PROJECT/'work/complete-answer410' and not sys.flags.optimize,'Only canonical unoptimized live worker')
    require(validated(root)==plan,'Plan changed');approved(root,plan);current(root,plan)
    record=load(root/'attempt.json')
    require(record.get('state')=='admitted' and record.get('plan_sha256')==sha(root/'plan.json') and record.get('approval_sha256')==sha(root/'approval.json'),'No current one-shot admission')
    with (root/'worker-started.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'plan_sha256':record['plan_sha256'],'single_worker':True},f)

def claim(root,record):
    with (root/'attempt.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['validate','live']);args=parser.parse_args()
    require(ROOT==PROJECT/'work/complete-answer410' and not sys.flags.optimize,'Use canonical frozen package')
    plan=validated(ROOT)
    if args.action=='validate':print(json.dumps({'state':'validated','plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json'),'approval_required':True}));return
    approved(ROOT,plan);require(not (ROOT/'attempt.json').exists() and not (ROOT/'worker-started.json').exists(),'Batch already consumed; no replay')
    env=current(ROOT,plan);runtime=runtime_check(plan)
    from local_readiness import check
    readiness=check(env['base_url'])
    record={'state':'admitted','batch_id':plan['batch_id'],'plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json'),'approval_sha256':sha(ROOT/'approval.json'),'runtime':runtime,'readiness':readiness,'automatic_retry':False}
    claim(ROOT,record)
    try:
        from worker import run
        result=run('live',ROOT/'live-output',plan);record.update(state=result['state'],dispatch_counts=result['dispatch_counts'])
    except BaseException as exc:record.update(state='stopped',failure_type=type(exc).__name__)
    finally:
        temp=ROOT/'attempt-writing.tmp';temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(temp,ROOT/'attempt.json')
    require(record['state']=='passed','Consumed batch stopped; no retry/regrant without new direct scope')

if __name__=='__main__':main()
