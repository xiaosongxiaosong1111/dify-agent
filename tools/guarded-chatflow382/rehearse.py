"""Independent public stores, full protocol shape and prefix-only stopping."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
from common import PROJECT,LIMITS,require,sha

MODES=('success','nonempty_no_answer','blank_order','bypass_order_value','fail_login','wrong_workspace','fail_import','fail_publish','changed_published','fail_key','fail_service','business_failure','changed_session','wrong_message_source','stop_after_first')

def rehearse(output):
    output=Path(output).resolve();require(output.is_relative_to(PROJECT/'work'),'Only local work output');output.mkdir(exist_ok=False)
    source=Path(__file__).resolve().parent
    source_hashes={f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}}
    def one(mode):
        folder=output/mode
        result=subprocess.run([sys.executable,str(source/'worker.py'),mode,str(folder)],cwd=PROJECT,capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (output/(mode+'.log')).write_bytes(result.stdout+result.stderr);require(result.returncode==0,'Public worker crashed: '+mode)
        record=json.loads((folder/'progress.json').read_text('utf-8'));require(record['state']==('passed' if mode in {'success','nonempty_no_answer','blank_order'} else 'stopped') and record['physical_http']==0 and all(record['protection'].values()),'Unexpected rehearsal outcome: '+mode)
        require(all(type(v) is int and 0<=v<=LIMITS[k] for k,v in record['dispatch_counts'].items()),'Counter overflow')
        return mode,record
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:records=dict(pool.map(one,MODES))
    normal=records['success'];require(normal['dispatch_counts']=={'model':0,'reads':80,'login':1,'import':2,'publish':2,'key':2,'run':14} and len(normal['traces'])==14 and len(normal['deliveries'])==2,'Complete public flow missing')
    def shape(r):return [(d['method'],d['kind'],d['version'],d.get('case_index'),d.get('second_turn')) for d in r['dispatches']]
    for mode,record in records.items():
        require(shape(record)==shape(normal)[:len(record['dispatches'])],'Failure did not stop on same sequence: '+mode)
        require(all(d.get('response_body_read') is True for d in record['dispatches'] if d['status'] is not None),'Unread response body')
    require(source_hashes=={f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}},'Sources changed during rehearsal')
    proof={'state':'passed','full_success_counts':normal['dispatch_counts'],'cases':{m:{'state':r['state'],'counts':r['dispatch_counts'],'original_state_kept':True} for m,r in records.items()},'physical_http':0,'prefix_stop_verified':True,'real_business_verified':False,'source_sha256':{f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}}}
    (output/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8')
    return proof

if __name__=='__main__':
    require(len(sys.argv)==2,'Supply new local work output');value=rehearse(Path(sys.argv[1]));print(json.dumps({'state':value['state'],'cases':len(value['cases']),'physical_http':0}))
