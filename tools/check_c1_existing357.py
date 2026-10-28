"""Verify exact stop phases/counts from the immutable C1 bundle; no live execution."""
import argparse,concurrent.futures,json,subprocess,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT/'work/c1-existing357'
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--playwright',required=True);args=p.parse_args();out=Path(args.output).resolve();assert out.is_relative_to(PROJECT/'work');out.mkdir(exist_ok=False,parents=True)
sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
from execute import validated
from support import ReadOnly,current
validated(ROOT);expected={'success':('passed','modified_miss',5,32,1,2,2,2,4),'fail_login':('stopped_needs_review','reconnect',0,0,1,0,0,0,0),'wrong_workspace':('stopped_needs_review','reconnect',0,2,1,0,0,0,0),'fail_model':('stopped_needs_review','complete_interview',2,2,1,0,0,0,0),'invalid_plan':('stopped_needs_review','first_plan',3,2,1,0,0,0,0),'fail_publish':('stopped_needs_review','original_publish',3,6,1,1,1,0,0),'fail_run':('stopped_needs_review','original_hit',3,11,1,1,1,1,1)}
plan=validated(ROOT);current(PROJECT,plan)
def run(mode):
 folder=out/mode;r=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),str(ROOT/'rehearse.py'),'--mode',mode,'--output',str(folder),'--playwright',args.playwright],cwd=PROJECT,capture_output=True,text=True,encoding='utf-8',errors='replace')
 (folder/'output.txt').write_text(r.stdout+'\n'+r.stderr,'utf-8');assert r.returncode==0,(mode,r.returncode)
 value=json.loads((folder/'progress.json').read_text('utf-8'));actual=(value['state'],value['phase'],*[value['dispatch_counts'][k] for k in ('model','reads','login','import','publish','key','run')]);assert actual==expected[mode],(mode,actual)
 assert value['physical_http']==0 and value['protection']['other_original_tasks_objects_and_ledgers_kept'] and all(v['semantic_reviewed'] is False for v in value.get('reviews',{}).values())
 if mode=='success':assert value['delivery']['file_hashes_verified'] and len(value['reviews'])==5
 return {'mode':mode,'state':value['state'],'phase':value['phase'],'counts':value['dispatch_counts'],'physical_http':0}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,expected))
current(PROJECT,plan);assert not (ROOT/'approval.json').exists() and not (ROOT/'attempt.json').exists()
assert (PROJECT/'tools/c1-existing357/gates_check.py').read_bytes()==(ROOT/'gates_check.py').read_bytes()
r=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),str(PROJECT/'tools/c1-existing357/gates_check.py')],cwd=PROJECT,capture_output=True,text=True,encoding='utf-8',errors='replace');assert r.returncode==0,r.stderr;(out/'gates.txt').write_text(r.stdout+'\n'+r.stderr,'utf-8');gates=json.loads(r.stdout)
reuse=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),str(ROOT/'reuse_checks.py')],cwd=PROJECT,capture_output=True,text=True,encoding='utf-8',errors='replace');assert reuse.returncode==0,reuse.stderr;reuse_result=json.loads(reuse.stdout);(out/'reuse-checks.json').write_text(reuse.stdout,'utf-8')
proof={'state':'passed','reuse_guard_checks':reuse_result['checks'],'gates':gates['gates'],'same_frozen_scenarios':results,'semantic_reviews_verified':False,'physical_model_dify_http':0,'production_unchanged':True,'approval_created':False,'attempt_created':False};(out/'proof.json').write_text(json.dumps(proof,indent=2),'utf-8');print(json.dumps({'state':'passed','gates':gates['gates'],'scenarios':len(results),'physical_http':0,'production_unchanged':True}))
