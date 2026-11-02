"""Independent public stores, full protocol shape and prefix-only stopping."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
from common import PROJECT,LIMITS,require,sha

MODES=('success','nonempty_no_answer','blank_order','bypass_order_value','followup_classifier_bypass','fail_login','wrong_workspace','fail_import','changed_draft_state','fail_publish','changed_published','changed_published_state','fail_key','fail_service','business_failure','second_turn_business_failure','failure_diagnostic_error','changed_session','wrong_message_source','stop_after_first')

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
    normal=records['success'];require(normal['dispatch_counts']=={'model':0,'reads':41,'login':1,'import':1,'publish':1,'key':1,'run':7} and len(normal['traces'])==7 and len(normal['deliveries'])==1,'Complete public flow missing')
    def shape(r):return [(d['method'],d['kind'],d['version'],d.get('case_index'),d.get('second_turn')) for d in r['dispatches']]
    for mode,record in records.items():
        require(shape(record)==shape(normal)[:len(record['dispatches'])],'Failure did not stop on same sequence: '+mode)
        require(all(d.get('response_body_read') is True for d in record['dispatches'] if d['status'] is not None),'Unread response body')
        capture=record.get('failure_capture')
        if capture:
            reads=[d for d in record['dispatches'] if d.get('failure_capture')]
            require(capture['reports_attempted']==1 and capture['management_reads']==len(reads)<=4,'Failure capture limit')
            first=next(i for i,d in enumerate(record['dispatches']) if d.get('failure_capture'))
            require(all(d.get('failure_capture') and d['method']=='GET' and d['kind']=='reads' for d in record['dispatches'][first:]),'Service/write after failure capture')
        if mode in {'business_failure','second_turn_business_failure'}:require(capture and capture['state']=='captured','Business failure evidence missing')
        if mode=='second_turn_business_failure':require(capture['turn']==2 and 'out_of_scope' in capture['node_ids'],'Captured wrong turn/branch')
        if mode=='failure_diagnostic_error':require(capture and capture['state']!='captured','Diagnostic failure falsely passed')
    require(source_hashes=={f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}},'Sources changed during rehearsal')
    proof={'state':'passed','full_success_counts':normal['dispatch_counts'],'cases':{m:{'state':r['state'],'counts':r['dispatch_counts'],'original_state_kept':True} for m,r in records.items()},'physical_http':0,'prefix_stop_verified':True,'real_business_verified':False,'source_sha256':{f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}}}
    (output/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8')
    return proof

if __name__=='__main__':
    require(len(sys.argv)==2,'Supply new local work output');value=rehearse(Path(sys.argv[1]));print(json.dumps({'state':value['state'],'cases':len(value['cases']),'physical_http':0}))
