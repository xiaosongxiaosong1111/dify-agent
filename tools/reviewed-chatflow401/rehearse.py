"""Normal planning and bounded repair protocol; public substitutions only."""
import json,subprocess,sys
from pathlib import Path
from common import PROJECT,ReadOnly,require,sha
MODES=('success','json_repair','json_repair_failed','repair_truncated_source','duplicate_fields','deep_structure','python_header','clarification','invalid_original','provider_error','unknown_usage','truncated','review_reject','review_stale')
def run(output):
    output=Path(output).resolve();require(output.is_relative_to(PROJECT/'work') and not output.exists(),'New local output required');output.mkdir()
    root=Path(__file__).resolve().parent;before={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}};records={}
    for mode in MODES:
        result=subprocess.run([sys.executable,str(root/'worker.py'),mode,str(output/mode)],cwd=PROJECT,capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (output/(mode+'.log')).write_bytes(result.stdout+result.stderr);require(result.returncode==0,'Public worker crashed '+mode)
        r=json.loads((output/mode/'progress.json').read_text('utf-8'));expected='passed' if mode in {'success','json_repair','python_header'} else 'stopped'
        require(r['state']==expected and r['physical_http']==0 and r['production_data_kept'] and r['semantic_reviewed'] is False and r['isolated_secrets_persisted'] is False,'Unexpected public outcome '+mode)
        calls=2 if mode in {'json_repair','json_repair_failed'} else 1
        require(r['model_http_started']==calls and r['stage_counts']=={'original':calls},'Extra model request or unexpected repair '+mode)
        store=ReadOnly(output/mode/'data');budgets=store.list('task_budget')
        require(len(budgets)==1 and len(budgets[0]['entries'])==calls,'Public ledger count differs from simulated model requests')
        with store.connect() as db:require(db.execute('SELECT COUNT(*) FROM secrets').fetchone()[0]==0,'Credential copy persisted')
        require(all(sha(output/mode/item['file'])==item['sha256'] and len((output/mode/item['file']).read_text('utf-8'))==item['characters'] for item in r.get('model_response_sources',[])),'Archived response source changed')
        require(r.get('node_guidance',{}).get('app_type')=='advanced-chat' and len(r['node_guidance']['items'])==7,'Missing new seven-type guidance provenance')
        if expected=='passed':require(len(r['reviews'])==len(r['deliveries'])==1,'Missing root-source review or static ZIP')
        else:require(not r.get('deliveries'),'Failed batch returned delivery')
        if mode=='json_repair':require(r['json_repair_admission']['known_usage'] and r['json_repair_admission']['normal_json_syntax_only'],'Missing normal JSON repair admission')
        if mode=='python_header':require(r['normal_deterministic_fixes'],'Missing deterministic correction audit')
        records[mode]={k:r.get(k) for k in ('state','model_http_started','physical_http','estimates','public_failure','normal_deterministic_fixes')}
    require(before=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}},'Sources changed during proof')
    proof={'state':'passed','cases':records,'physical_http':0,'real_model_quality_verified':False,'source_sha256':before}
    (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n','utf-8');print(json.dumps({'state':'passed','cases':len(records),'physical_http':0}))
if __name__=='__main__':run(sys.argv[1])
