"""Canonical two-plan scope requiring an explicit regrant; no automatic replay."""
import argparse,json,os,sys
from pathlib import Path
from common import PROJECT,ReadOnly,capture,digest,require,sha
from runtime_reference import runtime_check
ROOT=Path(__file__).resolve().parent
FROZEN={'common.py','guard.py','worker.py','runtime_reference.py','execute.py','freeze.py','rehearse.py','fixture.json','README.md','plan.json'}
LIMITS={'model':2,'reads':0,'login':0,'new_tasks':0,'import':0,'publish':0,'key':0,'run':0}
UPPER={'model':43,'reads':1469,'login':46,'import':26,'publish':26,'key':26,'run':120}
POLICY={'max_model_http':2,'per_stage':1,'output_tokens':6000,'timeout_seconds':120,'wall_seconds':3600,'review_seconds':300,'root_review_required':True,'production_writes':False,'dify_http':0,'no_retry':True,'normal_max_retries':0,'max_archived_response_characters':100000,'json_repair_http':0,'per_call_reserve_usd':'0.100','total_estimate_usd':'0.200','model_book_upper_usd':'1.955473652','isolated_new_tasks':1,'manual_intake':'agent_delegated','root_reviews':3,'interviews':0,'plans':2,'static_deliveries':2}
REGRANT={'source_batch':'recovered-chatflow418','unstarted_model_slots':2,'estimate_usd':'0.200','new_slots':0,'source_attempt_sha256':'c5b2ec9fcc4190562b2447a34a6b317e8a2dbb484c0b2862e41cb6aea9b6990d'}
ISOLATED={'391':'work/chatflow-model391/live-output/data','394':'work/clarified-chatflow394/live-output/data','399':'work/bounded-chatflow399/live-output/data','401':'work/reviewed-chatflow401/live-output/data','405':'work/offline-candidate405/data','408':'work/reviewed-planning408/live-output/data','409':'work/offline-candidate409/data','414':'work/autonomous-chatflow414/live-output/data','416':'work/autonomous-chatflow416/live-output/data','418':'work/recovered-chatflow418/live-output/data'}

def load(path):
 def pairs(rows):
  value={}
  for k,v in rows:require(k not in value,'Duplicate JSON field');value[k]=v
  return value
 raw=Path(path).read_bytes();require(len(raw)<=10_000_000,'Oversize JSON');return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Non-finite JSON'))

def validated(root):
 manifest=load(root/'manifest.json');require(manifest.get('batch_id')=='reviewed-spec-planning420' and set(manifest.get('files',{}))==FROZEN,'Wrong manifest')
 require(all(not (root/n).is_symlink() and (root/n).resolve().parent==root.resolve() and sha(root/n)==v for n,v in manifest['files'].items()),'Frozen sources changed')
 p=load(root/'plan.json');require(p.get('batch_id')=='reviewed-spec-planning420' and digest(p.get('policy'))==digest(POLICY) and digest(p.get('limits'))==digest(LIMITS) and p.get('new_conservative_upper')==UPPER,'Frozen scope changed')
 require(p.get('runtime_build')=='0.379.0-8a7d82953ed4021341dc' and p.get('backend_path')==str(PROJECT/'.runtime/snapshots'/p['runtime_build']/'backend') and p.get('provider_id')=='9513f594-c256-46b7-882a-35d9871bf9d0','Wrong provider/runtime')
 require(type(p.get('new_model_slots')) is int and p['new_model_slots']==0 and digest(p.get('regrant'))==digest(REGRANT) and set(p.get('protected_isolated',{}))==set(ISOLATED) and p.get('all_old_reservations_kept') is True and p.get('billing_hard_cap') is False,'Exact two unused planning slots required')
 require(p.get('original_model_has_no_saved_graph') is True and p.get('full_business_accepted') is False,'Original model must start from a blank graph; not full acceptance')
 return p

def approved(root,p):
 a=load(root/'approval.json');require(a.get('authorization_source')=='direct_human_reply' and a.get('decision')=='approve' and a.get('batch_id')==p['batch_id'] and a.get('plan_sha256')==sha(root/'plan.json') and a.get('manifest_sha256')==sha(root/'manifest.json') and digest(a.get('policy'))==digest(POLICY) and a.get('new_conservative_upper')==UPPER and type(a.get('new_model_slots')) is int and a['new_model_slots']==0 and digest(a.get('regrant'))==digest(REGRANT) and all(isinstance(a.get(k),str) and a[k].strip() for k in ('question_ref','reply')),'Direct two-slot regrant approval required')

def source_scope():
 root=PROJECT/'work/recovered-chatflow418'
 require(sha(root/'attempt.json')==REGRANT['source_attempt_sha256'],'Source consumed attempt changed')
 a=load(root/'attempt.json');r=load(root/'live-output/progress.json')
 require(a.get('state')==r.get('state')=='stopped' and type(a.get('physical_http')) is int and a['physical_http']==1 and type(a.get('model_http_started')) is int and a['model_http_started']==1 and digest(r.get('stage_counts'))==digest({'complete_interview':1,'original':0,'modified':0}),'Only two unstarted planning slots from stopped418')

def current(p):
 source_scope();source=ReadOnly(PROJECT/'data');require(capture(source)==p['protected_data'] and len(source.list('task'))==26,'Original production data changed')
 require(all(capture(ReadOnly(PROJECT/path))==p['protected_isolated'][k] for k,path in ISOLATED.items()),'Old isolated data/fees changed')
 require(digest(source.get('provider',p['provider_id']))==p['provider_sha256'],'Provider/pricing changed')
 require(all((PROJECT/n).resolve().is_relative_to(PROJECT/'work') and sha(PROJECT/n)==v for n,v in p['protected_files'].items()),'Old consumed evidence changed')
 folder=PROJECT/'.runtime/snapshots'/p['runtime_build'];require(sha(folder/'runtime-manifest.json')==p['runtime_manifest_sha256'],'Runtime manifest changed')
 require(all(sha(PROJECT/n)==v and sha(folder/n)==v for n,v in load(folder/'runtime-manifest.json')['files'].items()),'Runtime/source changed')

def claim(root,value):
 with (root/'attempt.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)

def authorize_worker(root,p):
 require(root==PROJECT/'work/reviewed-spec-planning420' and not sys.flags.optimize,'Canonical nonoptimized worker only');require(validated(root)==p,'Plan changed');approved(root,p);current(p)
 a=load(root/'attempt.json');require(a.get('state')=='admitted' and a.get('approval_sha256')==sha(root/'approval.json'),'Missing current admission')
 with (root/'worker-started.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'single_worker':True,'plan_sha256':sha(root/'plan.json')},f)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['validate','live']);args=parser.parse_args();require(ROOT==PROJECT/'work/reviewed-spec-planning420' and not sys.flags.optimize,'Canonical nonoptimized entry only');p=validated(ROOT)
 if args.action=='validate':print(json.dumps({'state':'validated_not_approved','plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json')}));return
 approved(ROOT,p);require(not (ROOT/'attempt.json').exists() and not (ROOT/'worker-started.json').exists(),'Consumed batch, never replay');current(p);runtime=runtime_check(p);a={'state':'admitted','runtime':runtime,'approval_sha256':sha(ROOT/'approval.json'),'plan_sha256':sha(ROOT/'plan.json'),'automatic_retry':False};claim(ROOT,a)
 try:
  from worker import run
  result=run('live',ROOT/'live-output',p);a.update(state=result['state'],model_http_started=result['model_http_started'],physical_http=result['physical_http'])
 except BaseException as exc:a.update(state='stopped',failure_type=type(exc).__name__)
 finally:
  tmp=ROOT/'attempt-writing.tmp';tmp.write_text(json.dumps(a,indent=2),'utf-8');os.replace(tmp,ROOT/'attempt.json')
 require(a['state']=='passed','Independent batch consumed/stopped; no retry or stage continuation')
if __name__=='__main__':main()