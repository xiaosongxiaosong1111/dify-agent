"""Run only public rehearsals in separate processes; physical HTTP must remain zero."""
import argparse,json,subprocess,sys
from pathlib import Path
from common import PROJECT,require

MODES=('success','fail_login','wrong_workspace','wrong_faq','invalid_model_json','unknown_model_usage','fail_import','fail_publish','fail_key','fail_service','wrong_message_source','changed_draft_state','second_turn_business_failure','failure_diagnostic_error')
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--mode',choices=MODES);p.add_argument('--all',action='store_true');p.add_argument('--child',action='store_true');a=p.parse_args()
    output=Path(a.output).resolve();require(output.is_relative_to(PROJECT/'work') and not output.exists(),'New public work directory required')
    if a.child:
        require(a.mode is not None,'Public mode required')
        from worker import run
        r=run(a.mode,output)
        expected='passed' if a.mode=='success' else 'stopped'
        require(r['state']==expected and r['physical_http']==0 and not r.get('protection_failure'),'Public rehearsal mismatch: '+str(r.get('local_public_error')))
        c=r['dispatch_counts']
        if a.mode in {'fail_login','wrong_workspace','wrong_faq'}:require(c['model']==0 and c['import']==0 and c['run']==0,'Setup failure dispatched later stages')
        if a.mode in {'invalid_model_json','unknown_model_usage'}:require(c['model']==1 and c['import']==0 and c['run']==0,'Model failure retried or created resources')
        if a.mode=='fail_import':require(c['model']==3 and c['import']==1 and c['publish']==0 and c['key']==0 and c['run']==0,'Import failure did not stop')
        if a.mode=='fail_publish':require(c['import']==1 and c['publish']==1 and c['key']==0 and c['run']==0,'Publish failure did not stop')
        if a.mode=='fail_key':require(c['publish']==1 and c['key']==1 and c['run']==0,'Key failure did not stop')
        if a.mode=='fail_service':require(c['model']==3 and c['run']==1,'Service failure retried or continued to modification')
        if a.mode in {'wrong_message_source','failure_diagnostic_error'}:require(c['model']==3 and c['run']==1,'Diagnostic source/error dispatched another case')
        if a.mode=='changed_draft_state':require(c['import']==1 and c['publish']==0 and c['key']==0 and c['run']==0,'Changed draft published')
        if a.mode=='second_turn_business_failure':
            f=r.get('failure_capture') or {}
            require(c['model']==3 and c['run']==7 and c['import']==1 and f.get('management_reads')==4 and f.get('state')=='captured','Unique failed second turn did not stop after four reads')
        print(json.dumps({'mode':a.mode,'state':r['state'],'counts':r.get('dispatch_counts'),'physical_http':0}))
        return
    output.mkdir();rows=[]
    for mode in MODES if a.all else (a.mode or 'success',):
        child=output/mode
        result=subprocess.run([sys.executable,__file__,'--child','--mode',mode,'--output',str(child)],capture_output=True,text=True,timeout=180)
        (output/(mode+'.log')).write_text(result.stdout+result.stderr,'utf-8')
        require(result.returncode==0,'Rehearsal failed: '+mode+'; see '+str(output/(mode+'.log')))
        value=json.loads((child/'progress.json').read_text('utf-8'));rows.append({'mode':mode,'state':value['state'],'counts':value['dispatch_counts'],'physical_http':value['physical_http'],'protection':value['protection']})
    (output/'summary.json').write_text(json.dumps({'state':'passed','modes':rows,'physical_http':0},indent=2),'utf-8')
    print(json.dumps({'state':'passed','modes':len(rows),'physical_http':0}))
if __name__=='__main__':main()
