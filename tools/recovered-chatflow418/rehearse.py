"""Public protocol shapes, no actual semantics or external HTTP."""
import json,subprocess,sys
from pathlib import Path
from common import PROJECT,require,sha,SEED
COUNTS={'success':3,'complete_paraphrase':3,'missing_interview_cases':0,'second_incomplete':1,'invalid_original':2,'original_clarification':2,'changed_scope':3,'unchanged_modified':3,'provider_error':1,'invalid_json':1,'unknown_usage':1,'unknown_modified':3,'truncated':1,'review_reject':2,'review_stale':2,'seed_review_reject':0,'seed_review_stale':0,'complete_review_stale':1,'wrong_original_context':1}
MODES=tuple(COUNTS)

def run(output):
 output=Path(output).resolve();require(output.is_relative_to(PROJECT/'work') and not output.exists(),'New local proof output');output.mkdir();root=Path(__file__).resolve().parent;before={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.md','.json'}};records={}
 for mode in MODES:
  process=subprocess.run([sys.executable,str(root/'worker.py'),mode,str(output/mode)],cwd=PROJECT,capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));(output/(mode+'.log')).write_bytes(process.stdout+process.stderr);require(process.returncode==0,'Public process crashed '+mode)
  r=json.loads((output/mode/'progress.json').read_text('utf-8'));require(r['state']==('passed' if mode in {'success','complete_paraphrase'} else 'stopped') and r['physical_http']==0 and r['production_data_kept'] and r['isolated_secrets_persisted'] is False and r['semantic_reviewed'] is False,'Unexpected public outcome '+mode+': '+r.get('public_failure',''))
  require(r['model_http_started']==COUNTS[mode] and r['budget_entry_count']==COUNTS[mode],'Unexpected calls, budget entries or retry '+mode)
  stage_values=list(r.get('stage_counts',{}).values());require(stage_values==sorted(stage_values,reverse=True) and all(x in (0,1) for x in stage_values),'Not a single-call prefix '+mode)
  if mode in {'success','complete_paraphrase'}:
   require(r['saved_initial_source']==SEED and sha(output/mode/'saved-initial-response.txt')==SEED['response_sha256'] and r['saved_initial_adopted_revision']==3,'Fixed original candidate was not independently adopted')
   require(r['interview_context']['complete_interview']['case_count']==6 and r['interview_context']['complete_interview']['turn_count']==7,'Complete interview lacks actual saved cases')
   require(len(r['reviews'])==4 and len(r['deliveries'])==2 and r['planning_context']['original']['existing_plan_sha256'] is None and r['planning_context']['modified']['existing_plan_sha256']==r['original_plan_sha256'],'Incomplete blank-to-modified full chain')
   require(all(v['case_count']==6 and v['turn_count']==7 for v in r['planning_context'].values()),'Current cases missing')
  elif COUNTS[mode]<3:require(not r.get('deliveries'),'Exported before all original gates')
  elif mode in {'changed_scope','unchanged_modified','unknown_modified'}:require(len(r.get('deliveries',[]))==1,'Failed modified phase should retain only original delivery')
  for value in r.get('responses',{}).values():
   file=output/mode/value['file'];require(sha(file)==value['sha256'] and len(file.read_text('utf-8'))==value['characters'],'Model archive changed')
  records[mode]={k:r.get(k) for k in ('state','model_http_started','physical_http','budget_entry_count','estimates','public_failure')}
 require(before=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.md','.json'}},'Sources changed during proof')
 proof={'state':'passed','cases':records,'source_sha256':before,'physical_http':0,'real_model_quality_verified':False,'semantic_reviewed':False};(output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n','utf-8');print(json.dumps({'state':'passed','cases':len(records),'physical_http':0}))
if __name__=='__main__':run(sys.argv[1])
