"""Public disposable protocol, zero external HTTP and no semantic claim."""
import json,subprocess,sys
from pathlib import Path
from common import PROJECT,require,sha
MODES=('success','clarification','invalid_original','provider_error','unknown_usage','truncated','review_reject','review_stale')
def run(output):
    output=Path(output).resolve();require(output.is_relative_to(PROJECT/'work') and not output.exists(),'New local output required');output.mkdir()
    root=Path(__file__).resolve().parent;before={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}};records={}
    for mode in MODES:
        result=subprocess.run([sys.executable,str(root/'worker.py'),mode,str(output/mode)],cwd=PROJECT,capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (output/(mode+'.log')).write_bytes(result.stdout+result.stderr);require(result.returncode==0,'Public worker crashed '+mode)
        r=json.loads((output/mode/'progress.json').read_text('utf-8'))
        require(r['state']==('passed' if mode=='success' else 'stopped') and r['physical_http']==0 and r['production_data_kept'] and r['semantic_reviewed'] is False and r['isolated_secrets_persisted'] is False,'Unexpected public outcome '+mode)
        require(r['model_http_started']==1 and r['stage_counts']=={'original':1},'Extra stage/retry')
        if mode=='success':require(len(r['reviews'])==1 and len(r['deliveries'])==1,'Incomplete single candidate flow')
        else:require(not r.get('deliveries'),'Failed batch exported delivery')
        records[mode]={k:r.get(k) for k in ('state','model_http_started','physical_http','estimates','public_failure')}
    require(before=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}},'Sources changed')
    proof={'state':'passed','cases':records,'physical_http':0,'real_model_quality_verified':False,'source_sha256':before}
    (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n','utf-8');print(json.dumps({'state':'passed','cases':len(records),'physical_http':0}))
if __name__=='__main__':run(sys.argv[1])
