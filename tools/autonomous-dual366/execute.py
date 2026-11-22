"""Pending freeze and once-only live admission for batch 366; no source-tree live entry."""
import argparse,hashlib,json,os,re,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
BATCH='autonomous-dual366'
NAMES={'common.py','boundary.py','boundary_checks.py','storage_guard.py','reviews.py','reviews_checks.py','pagination.py','pagination_checks.py','candidate.py','journey.py','worker.py','synthetic.py','runtime_reference.py','execute.py','freeze.py','rehearse.py','README.md','fixture.json','profile.json','approved_scope.md','plan.json'}
LIMITS={'new_tasks':1,'model':6,'reads':128,'login':1,'import':2,'publish':2,'key':2,'run':14}
UPPER={'model':57,'reads':1725,'login':48,'import':30,'publish':30,'key':30,'run':148}
OLD_REF='call_b4c700f1b4d24950a303b16fbe157440/q0'
APPROVAL_KEYS={'authorization_source','scope','decision','reply','question_ref','plan_sha256','manifest_sha256','limits','approved_model_slots'}
PROFILE_KEYS={'schema_version','batch_id','approval_scope','approval_phrase','approval_question_suffix','limits','new_conservative_upper','approved_model_slots','effective_model_http','json_repair_http','per_model_reserve_usd','model_total_usd','model_estimate_book_upper_usd','dify_estimate_usd','combined_estimate_usd','billing_hard_cap','wall_seconds','task_start_cap','task_minutes','runtime_build','runtime_version','runtime_file_count','runtime_pid_observed','source_commit','source_dir','source_normalization','source_pins','expected_counts','workspace_id','environment_id','provider_id','provider_model','provider_protocol','console_version','proposal_doc','protected_old_count','protected_337_count','protected_total_count','sealed_index_sha256','isolated_paths'}
PLAN_KEYS={'schema_version','batch_id','approval_state','proposal_state','source_commit','source_commit_base','source_dir','source_normalization','source_pins','frozen_source_files','proposal_doc','proposal_sha256','approved_scope_sha256','limits','new_conservative_upper','approved_model_slots','effective_model_http','json_repair_http','per_model_reserve_usd','model_total_usd','model_estimate_book_upper_usd','dify_estimate_usd','combined_estimate_usd','billing_hard_cap','wall_seconds','task_start_cap','task_minutes','runtime_build','runtime_version','runtime_file_count','runtime_pid','runtime_manifest_sha256','runtime_process_sha256','backend_path','provider_id','provider_sha256','environment_id','protected_data','isolated_paths','protected_isolated','protected_files','protected_old_count','protected_337_count','protected_total_count','sealed_index_sha256','known_apps'}

def require(value,message):
    if not value:raise RuntimeError(message)

def sha_bytes(value):return hashlib.sha256(value).hexdigest()
def sha(path):return sha_bytes(Path(path).read_bytes())
def _hex(value):return isinstance(value,str) and bool(re.fullmatch(r'[0-9a-f]{64}',value))
def _githex(value):return isinstance(value,str) and bool(re.fullmatch(r'[0-9a-f]{40}',value))
def _int(value,label):
    require(type(value) is int,label+' must be int');return value
def _strict(value,expected,label):
    require(isinstance(value,dict) and set(value)==set(expected),label+' fields changed')
    require(all(type(value[key]) is int and value[key]==expected[key] for key in expected),label+' must be exact ints')
def digest(value):return sha_bytes(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())

def load(path):
    def pairs(rows):
        result={}
        for k,v in rows:require(k not in result,'Duplicate JSON field');result[k]=v
        return result
    raw=Path(path).read_bytes();require(len(raw)<=12000000,'JSON too large')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Non-finite JSON'))

def _common():
    from common import ReadOnly,capture,known_apps
    return ReadOnly,capture,known_apps

def _canonical(root):
    raw=Path(root);require(not raw.is_symlink() and raw.resolve()==PROJECT/'work'/BATCH and not sys.flags.optimize,'Canonical nonoptimized root required')
    require(PROJECT==Path(r'E:\workSpace\dify-agent'),'Original project only')
    return raw.resolve()

def _profile(root):
    p=load(root/'profile.json');require(isinstance(p,dict) and set(p)==PROFILE_KEYS,'Profile fields changed')
    require(_int(p['schema_version'],'schema_version')==1 and p['batch_id']==BATCH and p['approval_scope']==BATCH and p['approval_phrase']=='允许独立366完整新范围' and p['approval_question_suffix']=='/q0','Profile identity changed')
    _strict(p['limits'],LIMITS,'limits');_strict(p['new_conservative_upper'],UPPER,'new_conservative_upper')
    require(_int(p['approved_model_slots'],'approved_model_slots')==6 and _int(p['effective_model_http'],'effective_model_http')==6 and _int(p['json_repair_http'],'json_repair_http')==0,'Profile limits changed')
    require((p['per_model_reserve_usd'],p['model_total_usd'],p['model_estimate_book_upper_usd'],p['dify_estimate_usd'],p['combined_estimate_usd'])==('0.100','0.600','3.355473652','0.100','0.700'),'Profile cost changed')
    require(p['billing_hard_cap'] is False and _int(p['wall_seconds'],'wall_seconds')==3600 and _int(p['task_start_cap'],'task_start_cap')==12 and _int(p['task_minutes'],'task_minutes')==45,'Profile time changed')
    require(p['runtime_build']=='0.410.0-23c94dbe89553f265c3b' and p['runtime_version']=='0.410.0' and _int(p['runtime_file_count'],'runtime_file_count')==298 and _int(p['runtime_pid_observed'],'runtime_pid_observed')>0,'Profile runtime changed')
    require(len(p['source_pins'])==15 and all(_hex(v) for v in p['source_pins'].values()) and p['source_dir']=='tools/autonomous-dual337' and p['source_normalization']=='crlf_to_lf' and _githex(p['source_commit']),'Profile source changed')
    _strict(p['expected_counts'],{'task':26,'environment':10,'provider':2},'expected_counts')
    require((_int(p['protected_old_count'],'protected_old_count'),_int(p['protected_337_count'],'protected_337_count'),_int(p['protected_total_count'],'protected_total_count'))==(733,24,758) and p['sealed_index_sha256']=='c9d9ef645118610e0fce61f5aed8deeb3e30f7e56b17d2c58511a25e5eef04e0','Profile protection changed')
    return p

def validate_plan(p,prof):
    require(isinstance(p,dict) and set(p)==PLAN_KEYS,'Plan fields changed')
    require(_int(p['schema_version'],'schema_version')==1 and p['batch_id']==BATCH and p['approval_state']=='pending' and p['proposal_state']=='proposed_not_approved','Plan is not a pending proposal')
    require(_githex(p['source_commit']) and p['source_commit_base']==prof['source_commit'] and p['source_dir']==prof['source_dir'] and p['source_normalization']==prof['source_normalization'],'Plan source commit changed')
    require(p['source_pins']==prof['source_pins'] and set(p['frozen_source_files'])==NAMES-{'plan.json'} and all(_hex(v) for v in p['frozen_source_files'].values()),'Plan source files changed')
    require(p['proposal_doc']==prof['proposal_doc'] and _hex(p['proposal_sha256']) and p['approved_scope_sha256']==p['proposal_sha256'],'Plan proposal binding changed')
    _strict(p['limits'],LIMITS,'limits');_strict(p['new_conservative_upper'],UPPER,'new_conservative_upper')
    require(_int(p['approved_model_slots'],'approved_model_slots')==6 and _int(p['effective_model_http'],'effective_model_http')==6 and _int(p['json_repair_http'],'json_repair_http')==0,'Plan limits changed')
    require((p['per_model_reserve_usd'],p['model_total_usd'],p['model_estimate_book_upper_usd'],p['dify_estimate_usd'],p['combined_estimate_usd'])==('0.100','0.600','3.355473652','0.100','0.700') and p['billing_hard_cap'] is False,'Plan cost changed')
    require(_int(p['wall_seconds'],'wall_seconds')==3600 and _int(p['task_start_cap'],'task_start_cap')==12 and _int(p['task_minutes'],'task_minutes')==45,'Plan time changed')
    require((p['runtime_build'],p['runtime_version'],_int(p['runtime_file_count'],'runtime_file_count'))==(prof['runtime_build'],prof['runtime_version'],prof['runtime_file_count']) and _int(p['runtime_pid'],'runtime_pid')>0 and _hex(p['runtime_manifest_sha256']) and _hex(p['runtime_process_sha256']),'Plan runtime changed')
    require(p['backend_path']==str(PROJECT/'.runtime/snapshots'/prof['runtime_build']/'backend'),'Plan backend path changed')
    require(p['provider_id']==prof['provider_id'] and p['environment_id']==prof['environment_id'] and _hex(p['provider_sha256']),'Plan public identity changed')
    require(p['isolated_paths']==prof['isolated_paths'] and set(p['protected_isolated'])==set(prof['isolated_paths']),'Plan protected roots changed')
    require(len(p['protected_files'])==758 and (_int(p['protected_old_count'],'protected_old_count'),_int(p['protected_337_count'],'protected_337_count'),_int(p['protected_total_count'],'protected_total_count'))==(733,24,758) and p['sealed_index_sha256']==prof['sealed_index_sha256'],'Plan protection counts changed')
    require(isinstance(p['protected_data'],dict) and isinstance(p['known_apps'],list),'Plan protected captures changed')

def verify_frozen(root,p):
    root=_canonical(root);prof=_profile(root);validate_plan(p,prof)
    manifest=load(root/'manifest.json');require(_int(manifest.get('schema_version'),'manifest schema_version')==1 and manifest.get('batch_id')==BATCH and set(manifest.get('files',{}))==NAMES,'Manifest identity changed')
    for name,value in manifest['files'].items():
        path=root/name;require(not path.is_symlink() and path.resolve().parent==root and path.is_file() and sha(path)==value,'Frozen source changed: '+name)
    require(load(root/'plan.json')==p,'Plan bytes changed')
    require(all(sha(root/name)==value for name,value in p['frozen_source_files'].items()),'Plan source digest changed')
    for name,value in p['source_pins'].items():
        if name not in {'common.py','worker.py'}:require(sha(root/name)==value,'Pinned copy changed: '+name)
    require(b"BATCH_ID='autonomous-dual366'" in (root/'common.py').read_bytes() and b'autonomous-dual337' not in (root/'common.py').read_bytes(),'Derived common changed')
    require(b"'approved_model_slots':6" in (root/'worker.py').read_bytes() and b"'approved_model_slots':8" not in (root/'worker.py').read_bytes(),'Derived worker changed')
    require(sha(root/'approved_scope.md')==p['approved_scope_sha256'],'Proposal bytes changed')
    folder=PROJECT/'.runtime/snapshots'/p['runtime_build'];runtime=load(folder/'runtime-manifest.json')
    require(sha(folder/'runtime-manifest.json')==p['runtime_manifest_sha256'] and runtime.get('shared_data_copied') is False and len(runtime.get('files',{}))==p['runtime_file_count']==298,'Runtime manifest changed')
    require(all(sha(PROJECT/name)==value and sha(folder/name)==value for name,value in runtime['files'].items()),'Running source changed')
    require(sha(PROJECT/'runtime-process.ps1')==p['runtime_process_sha256'],'Runtime helper changed')
    ReadOnly,capture,_known_apps=_common()
    require(digest(ReadOnly(PROJECT/'data').get('provider',p['provider_id']))==p['provider_sha256'],'Provider/pricing changed')
    return True

def verify_history(p):
    ReadOnly,capture,_known_apps=_common()
    require(all(capture(ReadOnly(PROJECT/path))==p['protected_isolated'][label] for label,path in p['isolated_paths'].items()),'Old isolated data/fees changed')
    require(len(p['protected_files'])==758 and all((PROJECT/name).resolve().is_relative_to(PROJECT/'work') and sha(PROJECT/name)==value for name,value in p['protected_files'].items()),'Old sealed evidence changed')
    return True

def validate_authorization(a,plan,plan_sha,manifest_sha,prof):
    require(isinstance(a,dict) and APPROVAL_KEYS<=set(a),'Approval fields missing')
    require(a['authorization_source']=='direct_user_reply' and a['scope']==BATCH and a['decision']=='approve' and a['reply']==prof['approval_phrase'],'Direct new scope approval missing')
    ref=a['question_ref'];require(isinstance(ref,str) and bool(re.fullmatch(r'call_[A-Za-z0-9_-]{1,64}/q0',ref)) and ref!=OLD_REF,'New question_ref required')
    require(a['plan_sha256']==plan_sha and a['manifest_sha256']==manifest_sha,'Approval not bound to frozen package')
    _strict(a['limits'],LIMITS,'approval limits')
    require(_int(a['approved_model_slots'],'approved_model_slots')==6 and _int(a.get('effective_model_http',6),'effective_model_http')==6 and _int(a.get('json_repair_http',0),'json_repair_http')==0,'Approval limits/slots changed')
    require((_int(plan['approved_model_slots'],'plan approved_model_slots'),_int(plan['effective_model_http'],'plan effective_model_http'),_int(plan['json_repair_http'],'plan json_repair_http'))==(6,6,0),'Frozen package slot mismatch')

def approved(root,p):
    a=load(root/'approval.json');validate_authorization(a,p,sha(root/'plan.json'),sha(root/'manifest.json'),_profile(root))
    return True

def assert_unconsumed(root,include_approval=False):
    names=['attempt.json','worker-started.json']+(['approval.json'] if include_approval else [])
    for name in names:require(not (root/name).exists(),'Consumed package cannot replay: '+name)

def _runtime(p,prof):
    from runtime_reference import runtime_check
    value=runtime_check(p);require(type(value.get('verified_pid')) is int and value['verified_pid']>0,'Observed PID invalid');return value

def _production(p):
    ReadOnly,_capture,_known_apps=_common()
    require(_capture(ReadOnly(PROJECT/'data'))==p['protected_data'],'Production baseline changed')

def approve(root,authorization):
    root=_canonical(root);p=load(root/'plan.json');prof=_profile(root)
    verify_frozen(root,p);verify_history(p);_production(p);_runtime(p,prof);assert_unconsumed(root,include_approval=True)
    path=Path(authorization).resolve();require(path.is_file() and not path.is_symlink() and not path.is_relative_to(PROJECT),'Direct approval file must be outside project')
    a=load(path);validate_authorization(a,p,sha(root/'plan.json'),sha(root/'manifest.json'),prof)
    verify_frozen(root,p);verify_history(p);_production(p);_runtime(p,prof);assert_unconsumed(root,include_approval=True)
    value={key:a[key] for key in APPROVAL_KEYS}
    if 'effective_model_http' in a:value['effective_model_http']=a['effective_model_http']
    if 'json_repair_http' in a:value['json_repair_http']=a['json_repair_http']
    with (root/'approval.json').open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2)
    require(sha(root/'plan.json')==a['plan_sha256'] and sha(root/'manifest.json')==a['manifest_sha256'],'Approval write changed frozen bytes')
    print(json.dumps({'state':'approved_not_dispatched','plan_sha256':a['plan_sha256'],'manifest_sha256':a['manifest_sha256']},ensure_ascii=False))

def authorize_worker(root,p):
    root=_canonical(root);verify_frozen(root,p);approved(root,p);verify_history(p);_production(p)
    attempt=load(root/'attempt.json');require(attempt.get('state')=='admitted' and attempt.get('approval_sha256')==sha(root/'approval.json'),'Admission missing')
    with (root/'worker-started.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'plan_sha256':sha(root/'plan.json'),'single_worker':True},f)

def _preflight(root):
    p=load(root/'plan.json');prof=_profile(root);verify_frozen(root,p);approved(root,p);verify_history(p);assert_unconsumed(root);_production(p);return p,_runtime(p,prof)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['validate-pending','approve','validate','live']);parser.add_argument('--authorization');args=parser.parse_args()
    root=HERE
    if args.action=='validate-pending':
        p=load(root/'plan.json');prof=_profile(root);verify_frozen(root,p);verify_history(p);assert_unconsumed(root,include_approval=True);_production(p)
        print(json.dumps({'state':'pending_not_approved','limits':LIMITS,'runtime':_runtime(p,prof)},ensure_ascii=False));return
    if args.action=='approve':
        require(args.authorization,'Authorization file required');approve(root,args.authorization);return
    p,runtime=_preflight(root)
    if args.action=='validate':
        print(json.dumps({'state':'approved_not_dispatched','limits':LIMITS,'runtime':runtime},ensure_ascii=False));return
    value={'state':'admitted','approval_sha256':sha(root/'approval.json'),'plan_sha256':sha(root/'plan.json'),'runtime':runtime,'automatic_retry':False}
    with (root/'attempt.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    try:
        from worker import run
        result=run('live',root/'live-output',p);value.update(state=result['state'],counts=result.get('dispatch_counts'),physical_http=result['physical_http'])
    except BaseException as exc:value.update(state='stopped',failure_type=type(exc).__name__)
    finally:
        tmp=root/'attempt-writing.tmp';tmp.write_text(json.dumps(value,indent=2),'utf-8');os.replace(tmp,root/'attempt.json')
    require(value['state']=='passed','Batch consumed/stopped; no retry or stage continuation')
if __name__=='__main__':main()
