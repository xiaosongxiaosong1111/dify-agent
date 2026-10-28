"""Bounded SDK-fixture checks of the exact frozen zero-model package, never live."""
import argparse,concurrent.futures,json,subprocess,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT/'work/c1-model-free368'
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--playwright',required=True);args=p.parse_args();out=Path(args.output).resolve();assert out.is_relative_to(PROJECT/'work');out.mkdir(exist_ok=False,parents=True)
sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
from execute import validated
from support import current,sha
plan=validated(ROOT);current(PROJECT,plan)
for name,value in json.loads((ROOT/'manifest.json').read_text('utf-8'))['files'].items():
 if name!='plan.json':assert sha(PROJECT/'tools/c1-model-free368'/name)==value
expected={
 'success':('passed','modified_miss',0,17,1,1,1,1,2),
 'fail_login':('stopped_needs_review','reconnect',0,0,1,0,0,0,0),
 'expired_session':('stopped_needs_review','reconnect',0,2,1,0,0,0,0),
 'wrong_workspace':('stopped_needs_review','reconnect',0,2,1,0,0,0,0),
 'fail_import':('stopped_needs_review','modified_import',0,2,1,1,0,0,0),
 'old_app_import':('stopped_needs_review','modified_import',0,2,1,1,0,0,0),
 'fail_publish':('stopped_needs_review','modified_publish',0,6,1,1,1,0,0),
 'fail_key':('stopped_needs_review','modified_key',0,10,1,1,1,1,0),
 'fail_run':('stopped_needs_review','modified_hit',0,11,1,1,1,1,1),
 'wrong_trace':('stopped_needs_review','modified_hit',0,14,1,1,1,1,1),
}

def check(mode):
 folder=out/mode;r=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),str(ROOT/'rehearse.py'),'--mode',mode,'--output',str(folder),'--playwright',args.playwright],cwd=PROJECT,capture_output=True,text=True,encoding='utf-8',errors='replace')
 (folder/'output.txt').write_text(r.stdout+'\n'+r.stderr,'utf-8');assert r.returncode==0,(mode,r.returncode)
 value=json.loads((folder/'progress.json').read_text('utf-8'));actual=(value['state'],value['phase'],*[value['dispatch_counts'][k] for k in ('model','reads','login','import','publish','key','run')]);assert actual==expected[mode],(mode,actual)
 assert value['physical_http']==0 and value['protection']['other_original_tasks_objects_and_ledgers_kept'] and value['protection']['existing_failed_history_and_ledger_kept']
 assert value['model_requests']==[] and all(v['semantic_reviewed'] is False and v['model_generated'] is False and v['human_signoff'] is False for v in value.get('reviews',{}).values())
 if mode=='success':assert value['delivery']['file_hashes_verified'] and value['delivery']['graph_matches_reviewed_imported_version'] and len(value['reviews'])==1
 return {'mode':mode,'state':value['state'],'phase':value['phase'],'counts':value['dispatch_counts'],'physical_http':0}

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(check,expected))
proof={'state':'passed','same_frozen_scenarios':results,'new_model_http_in_all_cases':0,'physical_model_dify_http':0,'production_unchanged':True,'approval_created':False,'attempt_created':False,'existing_original_history_copied_not_replayed':True}
for filename,key in [('gates_check.py','gates'),('reuse_checks.py','store_checks')]:
 # This byte-identical source entry tests that a source directory cannot execute live.
 r=subprocess.run([str(PROJECT/'.venv/Scripts/python.exe'),str(PROJECT/'tools/c1-model-free368'/filename)],cwd=PROJECT,capture_output=True,text=True,encoding='utf-8',errors='replace')
 assert r.returncode==0,r.stderr;value=json.loads(r.stdout);proof[key]=value.get('gates',value.get('checks'));(out/(key+'.json')).write_text(r.stdout,'utf-8')
current(PROJECT,plan);assert not (ROOT/'approval.json').exists() and not (ROOT/'attempt.json').exists()
(out/'proof.json').write_text(json.dumps(proof,indent=2),'utf-8');print(json.dumps({'state':'passed','gates':proof['gates'],'store_checks':proof['store_checks'],'scenarios':len(results),'new_model_http':0,'production_unchanged':True}))
