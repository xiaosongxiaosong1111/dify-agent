"""Canonical one-shot admission. No old attempt or source-tree live entry is accepted."""
import argparse,json,os,sys
from pathlib import Path
from common import PROJECT,BATCH_ID,LIMITS,ReadOnly,capture,digest,require,sha

NAMES={'common.py','boundary.py','boundary_checks.py','storage_guard.py','reviews.py','reviews_checks.py','pagination.py','pagination_checks.py','candidate.py','journey.py','worker.py','synthetic.py','runtime_reference.py','execute.py','freeze.py','rehearse.py','README.md','fixture.json','approved_scope.md','plan.json'}
UPPER={'model':51,'reads':1597,'login':47,'import':28,'publish':28,'key':28,'run':134}
def load(path):
    def pairs(rows):
        result={}
        for k,v in rows:require(k not in result,'Duplicate JSON field');result[k]=v
        return result
    raw=Path(path).read_bytes();require(len(raw)<=12000000,'JSON too large')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Non-finite JSON'))

def verify_frozen(root,p):
    root=Path(root).resolve();require(PROJECT==Path(r'E:\workSpace\dify-agent'),'Original live project only');manifest=load(root/'manifest.json')
    require(root==PROJECT/'work'/BATCH_ID and not sys.flags.optimize and manifest['batch_id']==BATCH_ID and set(manifest['files'])==NAMES,'Canonical package required')
    require(all(not (root/n).is_symlink() and (root/n).resolve().parent==root and sha(root/n)==v for n,v in manifest['files'].items()),'Frozen source changed')
    require(load(root/'plan.json')==p and p['batch_id']==BATCH_ID and p['limits']==LIMITS and p['new_conservative_upper']==UPPER and p['approved_model_slots']==8 and p['effective_model_http']==6 and p['json_repair_http']==0 and p['model_estimate_book_upper_usd']=='2.755473652','Scope changed')
    require(p['approved_plan_commit']=='e09376a4a626a1d7c3b738f5383c220eb5302152' and p['runtime_build']=='0.410.0-88f593682f0b5eb52500','Wrong approved source/runtime')
    require(sha(root/'approved_scope.md')==p['approved_scope_sha256'],'Approved scope changed')
    folder=PROJECT/'.runtime/snapshots'/p['runtime_build'];manifest=load(folder/'runtime-manifest.json')
    require(sha(folder/'runtime-manifest.json')==p['runtime_manifest_sha256'] and manifest['shared_data_copied'] is False,'Wrong runtime manifest')
    require(all(sha(PROJECT/n)==v and sha(folder/n)==v for n,v in manifest['files'].items()),'Running source changed')
    require(digest(ReadOnly(PROJECT/'data').get('provider',p['provider_id']))==p['provider_sha256'],'Provider/pricing changed')
    return True

def verify_history(p):
    require(all(capture(ReadOnly(PROJECT/path))==p['protected_isolated'][label] for label,path in p['isolated_paths'].items()),'Old isolated data/fees changed')
    require(len(p['protected_files'])==733 and all((PROJECT/n).resolve().is_relative_to(PROJECT/'work') and sha(PROJECT/n)==v for n,v in p['protected_files'].items()),'Old sealed evidence changed')

def approved(root,p):
    a=load(root/'approval.json')
    require(a.get('authorization_source')=='direct_user_reply' and a.get('question_ref')=='call_b4c700f1b4d24950a303b16fbe157440/q0' and a.get('reply')=='恢复并批准本批范围' and a.get('decision')=='approve','Direct new scope approval missing')
    require(a.get('plan_sha256')==sha(root/'plan.json') and a.get('manifest_sha256')==sha(root/'manifest.json') and a.get('limits')==LIMITS and a.get('approved_model_slots')==8,'Approval not bound to frozen package')

def authorize_worker(root,p):
    root=Path(root).resolve();verify_frozen(root,p);approved(root,p);verify_history(p)
    require(capture(ReadOnly(PROJECT/'data'))==p['protected_data'],'Production changed before worker')
    attempt=load(root/'attempt.json');require(attempt.get('state')=='admitted' and attempt.get('approval_sha256')==sha(root/'approval.json'),'Admission missing')
    with (root/'worker-started.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'plan_sha256':sha(root/'plan.json'),'single_worker':True},f)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['validate','live']);args=parser.parse_args()
    root=Path(__file__).resolve().parent;p=load(root/'plan.json');verify_frozen(root,p);approved(root,p);verify_history(p)
    require(not (root/'attempt.json').exists() and not (root/'worker-started.json').exists(),'Consumed package cannot replay')
    require(capture(ReadOnly(PROJECT/'data'))==p['protected_data'],'Production baseline changed')
    from runtime_reference import runtime_check
    runtime=runtime_check(p)
    if args.action=='validate':
        print(json.dumps({'state':'approved_not_dispatched','limits':LIMITS,'runtime':runtime}));return
    value={'state':'admitted','approval_sha256':sha(root/'approval.json'),'plan_sha256':sha(root/'plan.json'),'runtime':runtime,'automatic_retry':False}
    with (root/'attempt.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    try:
        from worker import run
        r=run('live',root/'live-output',p);value.update(state=r['state'],counts=r.get('dispatch_counts'),physical_http=r['physical_http'])
    except BaseException as exc:value.update(state='stopped',failure_type=type(exc).__name__)
    finally:
        tmp=root/'attempt-writing.tmp';tmp.write_text(json.dumps(value,indent=2),'utf-8');os.replace(tmp,root/'attempt.json')
    require(value['state']=='passed','Batch consumed/stopped; no retry or stage continuation')
if __name__=='__main__':main()
