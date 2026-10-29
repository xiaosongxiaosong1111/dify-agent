"""Freeze only after public scope/source protection proof; creates no approval."""
import json
from pathlib import Path
import shutil
from support import PROJECT,LIMITS,ReadOnly,capture,digest,load,require,sha

def freeze():
    source=Path(__file__).resolve().parent;target=PROJECT/'work/first-case-trace376';require(source==PROJECT/'tools/first-case-trace376' and not target.exists(),'Only new canonical freeze')
    proof=load(PROJECT/'work/first-case-trace376-local/rehearsal-proof.json');require(proof.get('state')=='passed' and proof.get('physical_http')==0 and proof.get('source_sha256')=={f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}},'Final rehearsed sources required')
    from execute import TARGET,UPPER,REGRANT,FROZEN,validated
    store=ReadOnly(PROJECT/'data');task=store.get('task',TARGET['task_id']);env=store.get('environment',TARGET['environment_id']);parent=load(PROJECT/'work/chatflow-order375/plan.json');progress=load(PROJECT/'work/chatflow-order375/live-output/progress.json')
    require(len(store.list('task'))==19 and progress['state']=='stopped' and progress['dispatch_counts']['reads']==13,'Parent source changed')
    old={}
    for name,value in parent['consumed_files'].items():require(sha(PROJECT/name)==value,'Old evidence changed');old[name]=value
    for name,value in load(PROJECT/'work/chatflow-order375/manifest.json')['files'].items():require(sha(PROJECT/'work/chatflow-order375'/name)==value,'Parent frozen source changed');old['work/chatflow-order375/'+name]=value
    for name in ('manifest.json','approval.json','attempt.json','worker-started.json','live-output/progress.json','post-live-data-snapshot.json'):old['work/chatflow-order375/'+name]=sha(PROJECT/'work/chatflow-order375'/name)
    plan={k:parent[k] for k in ('runtime_build','runtime_manifest_sha256','runtime_process_sha256','backend_path')}
    plan.update(schema_version=1,batch_id='first-case-trace376',limits=LIMITS,explicit_regrant=REGRANT,conservative_upper=UPPER,wall_seconds=600,model_estimate_book_upper_usd='0.755473652',old_reservations_preserved=True,protected_data=capture(store),environment_sha256=digest(env),old_evidence=old,case_source_sha256=digest(task),direct_new_approval_required=True)
    target.mkdir()
    for file in source.iterdir():
        if file.is_file() and file.suffix in {'.py','.json','.md'}:shutil.copyfile(file,target/file.name)
    (target/'target.json').write_text(json.dumps(TARGET,indent=2)+'\n','utf-8');(target/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n','utf-8')
    require({f.name for f in target.iterdir()}==FROZEN,'Unexpected frozen set')
    (target/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':plan['batch_id'],'files':{name:sha(target/name) for name in sorted(FROZEN)}},indent=2)+'\n','utf-8');require(validated(target)==plan,'Frozen validation failed')
    return {'state':'frozen_not_approved','files':len(FROZEN),'plan_sha256':sha(target/'plan.json'),'manifest_sha256':sha(target/'manifest.json'),'real_dify_http':0}

if __name__=='__main__':print(json.dumps(freeze()))
