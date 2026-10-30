"""Canonical new-scope admission only; never replay a consumed batch."""
import argparse,json,os,sys
from pathlib import Path
from common import PROJECT,ReadOnly,capture,digest,require,sha,LIMITS
from runtime_reference import runtime_check

ROOT=Path(__file__).resolve().parent
REGRANT={'source_batch':'reviewed-chatflow401','unstarted_model_slots':1,'estimate_usd':'0.080','new_slots':0}
SOURCE_PLAN='1c7fd3e3d672f2d7b228453945f2379defcceaf265be72399fcea46e491fd5c4'
SOURCE_CASES='261a6595f97a6f931284d65112af0ebd69eb3441ae194aaaf411e17eea6eee9a'
FROZEN={'common.py','guard.py','worker.py','runtime_reference.py','execute.py','freeze.py','rehearse.py','fixture.json','README.md','plan.json'}
UPPER={'model':35,'reads':1405,'login':45,'import':25,'publish':25,'key':25,'run':113}
POLICY={'max_model_http':1,'per_stage':1,'output_tokens':6000,'timeout_seconds':120,'wall_seconds':1800,'review_seconds':300,'root_review_required':True,'production_writes':False,'dify_http':0,'no_retry':True,'normal_max_retries':0,'max_archived_response_characters':100000,'json_repair_http':0,'per_call_reserve_usd':'0.080','total_estimate_usd':'0.080','model_book_upper_usd':'1.155473652'}

def load(path):
    def pairs(rows):
        value={}
        for k,v in rows:require(k not in value,'Duplicate JSON field');value[k]=v
        return value
    raw=Path(path).read_bytes();require(len(raw)<=10_000_000,'Oversize JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Non-finite JSON'))

def validated(root):
    manifest=load(root/'manifest.json');require(manifest.get('batch_id')=='reviewed-planning408' and set(manifest.get('files',{}))==FROZEN,'Wrong manifest')
    require(all(not (root/n).is_symlink() and (root/n).resolve().parent==root.resolve() and sha(root/n)==v for n,v in manifest['files'].items()),'Frozen source changed')
    plan=load(root/'plan.json')
    require(plan.get('batch_id')=='reviewed-planning408' and digest(plan.get('policy'))==digest(POLICY) and digest(plan.get('limits'))==digest(LIMITS) and plan.get('new_conservative_upper')==UPPER,'Frozen scope changed')
    require(plan.get('runtime_build')=='0.373.0-f8dc99952a3bf70b3b6d' and plan.get('backend_path')==str(PROJECT/'.runtime/snapshots'/plan['runtime_build']/'backend') and plan.get('provider_id')=='9513f594-c256-46b7-882a-35d9871bf9d0','Wrong runtime/provider source')
    require(plan.get('regrant')==REGRANT and set(plan.get('protected_isolated',{}))=={'391','394','399','401','405'} and plan.get('source_model_plan_sha256')==SOURCE_PLAN and plan.get('source_cases_sha256')==SOURCE_CASES,'Explicit remaining-slot regrant required')
    require(plan.get('all_old_reservations_kept') is True and plan.get('billing_hard_cap') is False,'Old reservations/billing boundary changed')
    return plan

def approved(root,plan):
    a=load(root/'approval.json')
    require(a.get('authorization_source')=='direct_human_reply' and a.get('decision')=='approve' and a.get('batch_id')==plan['batch_id'] and a.get('plan_sha256')==sha(root/'plan.json') and a.get('manifest_sha256')==sha(root/'manifest.json') and digest(a.get('policy'))==digest(POLICY) and a.get('new_conservative_upper')==UPPER and all(isinstance(a.get(k),str) and a[k].strip() for k in ('question_ref','reply')),'New direct scope approval required')

def current(plan):
    source=ReadOnly(PROJECT/'data');require(capture(source)==plan['protected_data'] and len(source.list('task'))==25,'Production data changed')
    roots={'391':'work/chatflow-model391/live-output/data','394':'work/clarified-chatflow394/live-output/data','399':'work/bounded-chatflow399/live-output/data','401':'work/reviewed-chatflow401/live-output/data','405':'work/offline-candidate405/data'}
    require(all(capture(ReadOnly(PROJECT/path))==plan['protected_isolated'][key] for key,path in roots.items()),'Old isolated Task/fees changed')
    prior=load(PROJECT/'work/reviewed-chatflow401/attempt.json')
    require(prior['state']=='stopped' and prior['model_http_started']==1 and sha(PROJECT/'work/reviewed-chatflow401/attempt.json')=='b1f4dbc407dfebe018563ccb56bb0409174f89a6a507f873101f9cf414a34892','401 remaining-slot source changed')
    p=source.get('provider',plan['provider_id']);require(digest(p)==plan['provider_sha256'],'Provider/price changed')
    require(all((PROJECT/n).resolve().is_relative_to(PROJECT/'work') and sha(PROJECT/n)==v for n,v in plan['protected_files'].items()),'Consumed evidence/deliveries changed')
    folder=PROJECT/'.runtime/snapshots'/plan['runtime_build'];require(sha(folder/'runtime-manifest.json')==plan['runtime_manifest_sha256'],'Runtime manifest changed')
    require(all(sha(PROJECT/n)==v and sha(folder/n)==v for n,v in load(folder/'runtime-manifest.json')['files'].items()),'Current runtime/source changed')

def claim(root,value):
    with (root/'attempt.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)

def authorize_worker(root,plan):
    require(root==PROJECT/'work/reviewed-planning408' and not sys.flags.optimize,'Canonical unoptimized worker only')
    require(validated(root)==plan,'Changed plan');approved(root,plan);current(plan)
    admission=load(root/'attempt.json');require(admission.get('state')=='admitted' and admission.get('approval_sha256')==sha(root/'approval.json'),'Missing current admission')
    with (root/'worker-started.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'single_worker':True,'plan_sha256':sha(root/'plan.json')},f)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['validate','live']);args=parser.parse_args()
    require(ROOT==PROJECT/'work/reviewed-planning408' and not sys.flags.optimize,'Canonical nonoptimized entry only');plan=validated(ROOT)
    if args.action=='validate':print(json.dumps({'state':'validated_not_approved','plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json')}));return
    approved(ROOT,plan);require(not (ROOT/'attempt.json').exists() and not (ROOT/'worker-started.json').exists(),'Consumed batch; no retry')
    current(plan);runtime=runtime_check(plan);record={'state':'admitted','runtime':runtime,'approval_sha256':sha(ROOT/'approval.json'),'plan_sha256':sha(ROOT/'plan.json'),'automatic_retry':False};claim(ROOT,record)
    try:
        from worker import run
        result=run('live',ROOT/'live-output',plan);record.update(state=result['state'],model_http_started=result['model_http_started'],physical_http=result['physical_http'])
    except BaseException as exc:record.update(state='stopped',failure_type=type(exc).__name__)
    finally:
        tmp=ROOT/'attempt-writing.tmp';tmp.write_text(json.dumps(record,indent=2),'utf-8');os.replace(tmp,ROOT/'attempt.json')
    require(record['state']=='passed','Independent batch stopped and consumed; no retry or borrowing')

if __name__=='__main__':main()
