"""Freeze current new source and existing data hashes; never decrypt or dispatch."""
import argparse,json,subprocess
from pathlib import Path
from common import BATCH_ID,LIMITS,ReadOnly,capture,digest,require,sha
from execute import NAMES,UPPER,load

ISOLATED={'391':'work/chatflow-model391/live-output/data','394':'work/clarified-chatflow394/live-output/data','399':'work/bounded-chatflow399/live-output/data','401':'work/reviewed-chatflow401/live-output/data','405':'work/offline-candidate405/data','408':'work/reviewed-planning408/live-output/data','409':'work/offline-candidate409/data','414':'work/autonomous-chatflow414/live-output/data','416':'work/autonomous-chatflow416/live-output/data','418':'work/recovered-chatflow418/live-output/data','420':'work/reviewed-spec-planning420/live-output/data'}
def freeze(project,authorization):
    project=Path(project).resolve();require(project==Path(r'E:\workSpace\dify-agent'),'Original project only')
    source=Path(__file__).resolve().parent;root=project/'work'/BATCH_ID
    require(not root.exists(),'New canonical package only')
    auth=load(authorization)
    require(auth['scope']==BATCH_ID and auth['decision']=='approve' and auth['question_ref']=='call_b4c700f1b4d24950a303b16fbe157440/q0' and auth['reply']=='恢复并批准本批范围' and auth['limits']==LIMITS,'Explicit scope mismatch')
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=project,text=True).strip(),'Clean original checkout required')
    protected=ReadOnly(project/'data');require(len(protected.list('task'))==26 and len(protected.list('environment'))==10 and len(protected.list('provider'))==2,'Original counts changed')
    fixture=load(source/'fixture.json');provider=protected.get('provider',fixture['provider_id']);env=protected.get('environment',fixture['environment_id'])
    require(provider and env and env['console_workspace_id']==fixture['workspace_id'] and env['version']=='1.17.1','Profile/workspace mismatch')
    require(provider.get('protocol','openai-compatible')=='openai-compatible' and provider.get('model')=='deepseek-flash' and isinstance(provider.get('pricing'),dict),'Supported frozen model profile required')
    with protected.connect() as c:secrets={row[0] for row in c.execute('select id from secrets')}
    require(all(fixture['environment_id']+':'+k in secrets for k in ('console_login_email','console_login_password')) and fixture['provider_id']+':api_key' in secrets,'Saved encrypted credentials missing')
    sealed=project/'work/reviewed-spec-planning420/sealed-evidence-sha256.json'
    require(sha(sealed)=='c9d9ef645118610e0fce61f5aed8deeb3e30f7e56b17d2c58511a25e5eef04e0','Old seal changed')
    oldfiles=load(sealed);oldfiles[sealed.relative_to(project).as_posix()]=sha(sealed);require(len(oldfiles)==733 and all(sha(project/n)==v for n,v in oldfiles.items()),'Old evidence changed')
    runtime='0.410.0-88f593682f0b5eb52500';folder=project/'.runtime/snapshots'/runtime
    snapshot=load(folder/'runtime-manifest.json');require(all(sha(project/n)==v and sha(folder/n)==v for n,v in snapshot['files'].items()),'Runtime/source mismatch')
    scope=project/'docs/autonomous-dual-chatflow-resume-plan-20261120.md'
    p={'schema_version':1,'batch_id':BATCH_ID,'approved_plan_commit':auth['approved_plan_commit'],'approved_model_slots':8,'effective_model_http':6,'json_repair_http':0,'limits':LIMITS,'new_conservative_upper':UPPER,'model_estimate_book_upper_usd':'2.755473652','per_model_reserve_usd':'0.100','effective_model_reserve_usd':'0.600','approved_model_reserve_usd':'0.800','dify_estimate_usd':'0.100','billing_hard_cap':False,'wall_seconds':3600,'task_start_cap':12,'task_minutes':45,'runtime_build':runtime,'backend_path':str(folder/'backend'),'runtime_manifest_sha256':sha(folder/'runtime-manifest.json'),'runtime_process_sha256':sha(project/'runtime-process.ps1'),'provider_id':fixture['provider_id'],'provider_sha256':digest(provider),'environment_id':fixture['environment_id'],'protected_data':capture(protected),'isolated_paths':ISOLATED,'protected_isolated':{k:capture(ReadOnly(project/v)) for k,v in ISOLATED.items()},'protected_files':oldfiles,'approved_scope_sha256':sha(scope)}
    root.mkdir()
    for name in NAMES-{'plan.json','approved_scope.md'}:
        file=source/name;require(file.is_file() and not file.is_symlink(),'Required local source missing')
        (root/name).write_bytes(file.read_bytes())
    (root/'approved_scope.md').write_bytes(scope.read_bytes());(root/'plan.json').write_text(json.dumps(p,ensure_ascii=False,sort_keys=True,indent=2),'utf-8')
    manifest={'schema_version':1,'batch_id':BATCH_ID,'files':{n:sha(root/n) for n in sorted(NAMES)}}
    (root/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2),'utf-8')
    approval={'authorization_source':'direct_user_reply','question_ref':auth['question_ref'],'reply':auth['reply'],'decision':'approve','approved_model_slots':8,'limits':LIMITS,'plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json')}
    (root/'approval.json').write_text(json.dumps(approval,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'state':'frozen_approved_not_dispatched','root':str(root),'plan_sha256':approval['plan_sha256'],'manifest_sha256':approval['manifest_sha256']}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project-root',required=True);parser.add_argument('--authorization',required=True);a=parser.parse_args();freeze(a.project_root,a.authorization)
