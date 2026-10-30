"""Public disposable protocol, zero external HTTP and no semantic claim."""
import json,subprocess,sys
from pathlib import Path
from common import PROJECT,require,sha
MODES=('success','user_prompt','unchanged','out_of_scope','invalid_json','clarification','provider_error','unknown_usage','truncated','review_reject','review_stale','wrong_context')
def run(output):
    output=Path(output).resolve();require(output.is_relative_to(PROJECT/'work') and not output.exists(),'New local output required');output.mkdir()
    root=Path(__file__).resolve().parent;before={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}};records={}
    for mode in MODES:
        result=subprocess.run([sys.executable,str(root/'worker.py'),mode,str(output/mode)],cwd=PROJECT,capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (output/(mode+'.log')).write_bytes(result.stdout+result.stderr);require(result.returncode==0,'Public worker crashed '+mode)
        r=json.loads((output/mode/'progress.json').read_text('utf-8'))
        passed=mode in {'success','user_prompt'};calls=0 if mode=='wrong_context' else 1
        require(r['state']==('passed' if passed else 'stopped') and r['physical_http']==0 and r['production_data_kept'] and r['semantic_reviewed'] is False and r['isolated_secrets_persisted'] is False,'Unexpected public outcome '+mode+' '+r.get('public_failure',''))
        require(r['model_http_started']==calls and (r.get('stage_counts',{'original':0})=={'original':calls}),'Extra stage/retry')
        require(r['budget_entry_count']==calls and r['planning_operation_count']==1,'Budget entries or planning operations differ from actual dispatch')
        if passed:require(r['normal_replanning_review'] and len(r['reviews'])==1 and len(r['deliveries'])==1 and r['existing_plan_sha256']=='1c7fd3e3d672f2d7b228453945f2379defcceaf265be72399fcea46e491fd5c4','Incomplete single candidate flow')
        else:require(not r.get('deliveries'),'Failed batch exported delivery')
        if calls:
            context=r['acceptance_case_context'];require(context['case_count']==6 and context['turn_count']==7 and context['content_sha256']=='261a6595f97a6f931284d65112af0ebd69eb3441ae194aaaf411e17eea6eee9a','Current saved cases missing')
        else:require(r.get('local_model_admission_stop') and not r.get('model_response_sources'),'Pre-dispatch stop failed')
        for item in r.get('model_response_sources',[]):
            archive=output/mode/item['file'];require(sha(archive)==item['sha256'] and len(archive.read_text('utf-8'))==item['characters'],'Response source changed')
        records[mode]={k:r.get(k) for k in ('state','model_http_started','physical_http','estimates','public_failure')}
    require(before=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}},'Sources changed')
    proof={'state':'passed','cases':records,'physical_http':0,'real_model_quality_verified':False,'source_sha256':before}
    (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n','utf-8');print(json.dumps({'state':'passed','cases':len(records),'physical_http':0}))
if __name__=='__main__':run(sys.argv[1])
