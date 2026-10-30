"""Canonical new-scope admission only; never replay a consumed batch."""
import argparse,json,os,sys
from pathlib import Path
from common import PROJECT,ReadOnly,capture,digest,require,sha,LIMITS
from runtime_reference import runtime_check

ROOT=Path(__file__).resolve().parent
FROZEN={'common.py','guard.py','worker.py','runtime_reference.py','execute.py','freeze.py','rehearse.py','fixture.json','README.md','plan.json'}
UPPER={'model':34,'reads':1341,'login':44,'import':24,'publish':24,'key':24,'run':106}
POLICY={'max_model_http':2,'per_stage':1,'output_tokens':6000,'timeout_seconds':120,'wall_seconds':1800,'review_seconds':300,'root_review_required':True,'production_writes':False,'dify_http':0,'no_batch_retry':True,'normal_max_retries':1,'max_json_repair_http':1,'max_archived_response_characters':100000,'per_call_reserve_usd':'0.080','total_estimate_usd':'0.160','model_book_upper_usd':'1.075473652'}

def load(path):
    def pairs(rows):
        value={}
        for k,v in rows:require(k not in value,'Duplicate JSON field');value[k]=v
        return value
    raw=Path(path).read_bytes();require(len(raw)<=10_000_000,'Oversize JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Non-finite JSON'))

def validated(root):
    manifest=load(root/'manifest.json');require(manifest.get('batch_id')=='bounded-chatflow399' and set(manifest.get('files',{}))==FROZEN,'Wrong manifest')
    require(all(not (root/n).is_symlink() and (root/n).resolve().parent==root.resolve() and sha(root/n)==v for n,v in manifest['files'].items()),'Frozen source changed')
    plan=load(root/'plan.json')
    require(plan.get('batch_id')=='bounded-chatflow399' and digest(plan.get('policy'))==digest(POLICY) and digest(plan.get('limits'))==digest(LIMITS) and plan.get('new_conservative_upper')==UPPER,'Frozen scope changed')
    require(plan.get('runtime_build')=='0.369.0-ff46c4bbe293269c1a14' and plan.get('backend_path')==str(PROJECT/'.runtime/snapshots'/plan['runtime_build']/'backend') and plan.get('provider_id')=='9513f594-c256-46b7-882a-35d9871bf9d0','Wrong runtime/provider source')
    require(plan.get('new_scope')=={'new_model_slots':2,'new_estimate_usd':'0.160','old_slots_reused':0} and isinstance(plan.get('protected_isolated_391'),dict) and isinstance(plan.get('protected_isolated_394'),dict),'Explicit full new bounded scope required')
    require(plan.get('all_old_reservations_kept') is True and plan.get('billing_hard_cap') is False,'Old reservations/billing boundary changed')
    return plan

def approved(root,plan):
    a=load(root/'approval.json')
    require(a.get('authorization_source')=='direct_human_reply' and a.get('decision')=='approve' and a.get('batch_id')==plan['batch_id'] and a.get('plan_sha256')==sha(root/'plan.json') and a.get('manifest_sha256')==sha(root/'manifest.json') and digest(a.get('policy'))==digest(POLICY) and a.get('new_conservative_upper')==UPPER and all(isinstance(a.get(k),str) and a[k].strip() for k in ('question_ref','reply')),'New direct scope approval required')

def current(plan):
    source=ReadOnly(PROJECT/'data');require(capture(source)==plan['protected_data'] and len(source.list('task'))==24,'Production data changed')
    require(capture(ReadOnly(PROJECT/'work/chatflow-model391/live-output/data'))==plan['protected_isolated_391'],'391 isolated Task/settled changed')
    require(capture(ReadOnly(PROJECT/'work/clarified-chatflow394/live-output/data'))==plan['protected_isolated_394'],'394 isolated Task/settled changed')
    p=source.get('provider',plan['provider_id']);require(digest(p)==plan['provider_sha256'],'Provider/price changed')
    require(all((PROJECT/n).resolve().is_relative_to(PROJECT/'work') and sha(PROJECT/n)==v for n,v in plan['protected_files'].items()),'Consumed evidence/deliveries changed')
    folder=PROJECT/'.runtime/snapshots'/plan['runtime_build'];require(sha(folder/'runtime-manifest.json')==plan['runtime_manifest_sha256'],'Runtime manifest changed')
    require(all(sha(PROJECT/n)==v and sha(folder/n)==v for n,v in load(folder/'runtime-manifest.json')['files'].items()),'Current runtime/source changed')

def claim(root,value):
    with (root/'attempt.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)

def authorize_worker(root,plan):
    require(root==PROJECT/'work/bounded-chatflow399' and not sys.flags.optimize,'Canonical unoptimized worker only')
    require(validated(root)==plan,'Changed plan');approved(root,plan);current(plan)
    admission=load(root/'attempt.json');require(admission.get('state')=='admitted' and admission.get('approval_sha256')==sha(root/'approval.json'),'Missing current admission')
    with (root/'worker-started.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'single_worker':True,'plan_sha256':sha(root/'plan.json')},f)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['validate','live']);args=parser.parse_args()
    require(ROOT==PROJECT/'work/bounded-chatflow399' and not sys.flags.optimize,'Canonical nonoptimized entry only');plan=validated(ROOT)
    if args.action=='validate':print(json.dumps({'state':'validated_not_approved','plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json')}));return
    approved(ROOT,plan);require(not (ROOT/'attempt.json').exists() and not (ROOT/'worker-started.json').exists(),'Consumed batch; no retry')
    current(plan);runtime=runtime_check(plan);record={'state':'admitted','runtime':runtime,'approval_sha256':sha(ROOT/'approval.json'),'plan_sha256':sha(ROOT/'plan.json'),'automatic_batch_retry':False,'normal_json_repair_allowed':True};claim(ROOT,record)
    try:
        from worker import run
        result=run('live',ROOT/'live-output',plan);record.update(state=result['state'],model_http_started=result['model_http_started'],physical_http=result['physical_http'])
    except BaseException as exc:record.update(state='stopped',failure_type=type(exc).__name__)
    finally:
        tmp=ROOT/'attempt-writing.tmp';tmp.write_text(json.dumps(record,indent=2),'utf-8');os.replace(tmp,ROOT/'attempt.json')
    require(record['state']=='passed','Independent batch stopped and consumed; no retry or borrowing')

if __name__=='__main__':main()
