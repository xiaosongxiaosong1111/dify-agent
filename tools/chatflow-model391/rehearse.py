"""Disposable public protocol only; never infer real model quality from it."""
import json,subprocess,sys
from pathlib import Path
from common import PROJECT,require,sha

MODES=('success','invalid_original','changed_scope','provider_error','unknown_usage','truncated','review_reject','review_stale','stop_after_original')

def run(output):
    output=Path(output).resolve();require(output.is_relative_to(PROJECT/'work') and not output.exists(),'New local output required');output.mkdir()
    root=Path(__file__).resolve().parent;before={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}};records={}
    for mode in MODES:
        result=subprocess.run([sys.executable,str(root/'worker.py'),mode,str(output/mode)],cwd=PROJECT,capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (output/(mode+'.log')).write_bytes(result.stdout+result.stderr);require(result.returncode==0,'Public worker crashed '+mode)
        r=json.loads((output/mode/'progress.json').read_text('utf-8'));require(r['state']==('passed' if mode=='success' else 'stopped') and r['physical_http']==0 and r['production_data_kept'] and r['semantic_reviewed'] is False and r['isolated_secrets_persisted'] is False,'Unexpected public outcome '+mode)
        require(0<=r['model_http_started']<=2 and all(v<=1 for v in r.get('stage_counts',{}).values()),'Dispatch/retry overflow')
        if mode=='success':require(r['model_http_started']==2 and len(r['reviews'])==2 and len(r['deliveries'])==2,'Incomplete two-candidate flow')
        elif mode=='changed_scope':require(r['model_http_started']==2 and len(r['reviews'])==1 and len(r['deliveries'])==1,'Changed candidate was adopted or earlier work lost')
        else:require(r['model_http_started']==1 and r.get('stage_counts',{}).get('modified',0)==0,'Failure continued into another model stage')
        records[mode]={k:r.get(k) for k in ('state','model_http_started','physical_http','estimates','public_failure')}
    require(before=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}},'Sources changed during rehearsal')
    proof={'state':'passed','cases':records,'physical_http':0,'real_model_quality_verified':False,'source_sha256':before};(output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n','utf-8');print(json.dumps({'state':'passed','cases':len(records),'physical_http':0}))

if __name__=='__main__':run(sys.argv[1])
