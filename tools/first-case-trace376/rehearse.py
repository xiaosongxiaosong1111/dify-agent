"""Public complete/negative cases with exact counters and no production access."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
from support import PROJECT,require,sha

MODES=('success','more_documents','index_error','fail_login','wrong_workspace','wrong_message','fail_nodes','changed_published','duplicate_document','fail_index_status','late_source')

def rehearse(output):
    output=Path(output).resolve();require(output.is_relative_to(PROJECT/'work'),'Only work output');output.mkdir(exist_ok=False);source=Path(__file__).resolve().parent
    hashes={f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}}
    def one(mode):
        r=subprocess.run([sys.executable,str(source/'worker.py'),mode,str(output/mode)],cwd=PROJECT,capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));(output/(mode+'.log')).write_bytes(r.stdout+r.stderr);require(r.returncode==0,'Worker crashed '+mode)
        record=json.loads((output/mode/'progress.json').read_text('utf-8'));complete=mode in {'success','more_documents','index_error'}
        require(record['state']==('diagnostic_complete_no_retest' if complete else 'stopped') and record['physical_http']==0 and record['new_tasks']==record['new_models']==record['new_resources']==record['service_requests']==0,'Outcome wrong '+mode)
        require(record['original_state_kept'] or mode=='late_source' and record.get('source_changed_externally') and record['saved_diagnostic_count']==0,'Source protection wrong '+mode)
        require('PRIVATE_NAME' not in json.dumps(record) and 'PRIVATE_CONTENT' not in json.dumps(record) and 'PRIVATE_KEY' not in json.dumps(record),'Private raw metadata leaked')
        require(record['dispatch_counts']['reads']<=10 and record['dispatch_counts']['login']<=1,'Count overflow')
        if complete:
            require(record['dispatch_counts']=={'reads':10,'login':1} and record['saved_diagnostic_count']==1 and record['diagnostic']['saved_status']=='success' and record['original_rule_failed_kept'],'Incomplete normal read')
            require(record['dataset']['indexing_technique']=='economy','Indexing state omitted')
            if mode=='more_documents':require(record['document_page']['has_more'] is True and len(record['documents'])==2,'Pagination ignored')
            if mode=='index_error':require(record['documents'][0]['indexing']['indexing_status']=='error' and record['documents'][0]['indexing']['error_present'],'Index failure erased')
        return mode,record
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:records=dict(pool.map(one,MODES))
    normal=records['success']
    def shape(record):return [(d['method'],d['kind'],d['phase']) for d in record['dispatches']]
    for mode,r in records.items():require(shape(r)==shape(normal)[:len(r['dispatches'])],'Not normal prefix '+mode)
    require(hashes=={f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}},'Source changed while testing')
    proof={'state':'passed','physical_http':0,'source_sha256':hashes,'normal_counts':normal['dispatch_counts'],'cases':{m:{'state':r['state'],'counts':r['dispatch_counts'],'saved_diagnostics':r['saved_diagnostic_count'],'external_source_change':bool(r.get('source_changed_externally'))} for m,r in records.items()},'no_service_models_or_resources':True,'original_failed_rule_kept':True,'metadata_names_content_credentials_omitted':True,'business_retested':False}
    (output/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8');return proof

if __name__=='__main__':
    require(len(sys.argv)==2,'Supply new work directory');p=rehearse(Path(sys.argv[1]));print(json.dumps({'state':'passed','cases':len(p['cases']),'physical_http':0}))
