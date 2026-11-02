"""Create once after isolated verification. No approval or live execution is produced."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
from common import PROJECT,LIMITS,ReadOnly,capture,digest,require,sha

def freeze():
    from execute import FAILURE_POLICY,STATE_POLICY
    source=Path(__file__).resolve().parent;target=PROJECT/'work/complete-answer410'
    require(source==PROJECT/'tools/complete-answer410' and not target.exists(),'Freeze only new canonical package')
    proof=json.loads((PROJECT/'work/complete-answer410-local/rehearsal-proof.json').read_text('utf-8'));require(proof.get('state')=='passed' and proof.get('physical_http')==0,'Isolated full-chain proof required')
    require(proof.get('source_sha256')=={f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}},'Rehearsed sources changed')
    fixture=json.loads((source/'fixture.json').read_text('utf-8'));store=ReadOnly(PROJECT/'data');env=store.get('environment',fixture['environment_id'])
    require(len(store.list('task'))==25 and env and env.get('console_workspace_id')==fixture['workspace_id'],'Original source changed')
    with tempfile.TemporaryDirectory(dir=PROJECT/'work/complete-answer410-local') as folder:
        os.environ['FLOWCRAFT_DATA_DIR']=folder;sys.path.insert(0,str(PROJECT/'backend'))
        from app import main as h
        from contract import build
        contract=build(h,fixture)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8765/api/runtime',timeout=10) as r:runtime=json.load(r)
    require(runtime.get('version')=='0.374.0' and runtime.get('mode')=='snapshot','Wrong runtime')
    runtime_root=PROJECT/'.runtime/snapshots'/runtime['build_id'];manifest=json.loads((runtime_root/'runtime-manifest.json').read_text('utf-8'))
    for name,value in manifest['files'].items():require(sha(PROJECT/name)==value and sha(runtime_root/name)==value,'Runtime/source mismatch')
    baseline=PROJECT/'work/reviewed-planning408';require(capture(store)==json.loads((baseline/'post-production-data-snapshot.json').read_text('utf-8')),'Production baseline changed')
    sealed=PROJECT/'work/offline-candidate409/sealed-evidence-sha256.json';require(sha(sealed)=='256b911af5f063dbd09f7e30e1a9d41bd8ff36e999e148eaaf5d1e677eedbb63','270 sealed index changed')
    consumed=json.loads(sealed.read_text('utf-8'));require(len(consumed)==574,'Wrong protected count');consumed[sealed.relative_to(PROJECT).as_posix()]=sha(sealed)
    require(all((PROJECT/name).resolve().is_relative_to(PROJECT/'work') and sha(PROJECT/name)==value for name,value in consumed.items()),'Old evidence/ZIP/source changed')
    isolated={};roots={'391':'work/chatflow-model391/live-output/data','394':'work/clarified-chatflow394/live-output/data','399':'work/bounded-chatflow399/live-output/data','401':'work/reviewed-chatflow401/live-output/data','405':'work/offline-candidate405/data','408':'work/reviewed-planning408/live-output/data','409':'work/offline-candidate409/data'}
    for key,path in roots.items():
        isolated[key]=capture(ReadOnly(PROJECT/path));saved=PROJECT/'work/offline-candidate409/local-data-snapshot.json' if key=='409' else baseline/('post-isolated'+key+'-data-snapshot.json')
        require(isolated[key]==json.loads(saved.read_text('utf-8')),'Old isolated data changed')
    plan={'schema_version':1,'batch_id':'complete-answer410','new_independent_scope':True,'old_reservations_preserved':True,'limits':LIMITS,'wall_seconds':2700,'execution_policy':{'max_started_runs':6,'max_total_minutes':30,'max_reported_cost_usd':None},'model_estimate_book_upper_usd':'1.155473652','estimated_new_dify_usd':'0.05','estimate_is_bill_hard_cap':False,'host_cost_unknown':True,'new_conservative_upper':{'model':35,'reads':1469,'login':46,'import':26,'publish':26,'key':26,'run':120},'environment_id':env['id'],'environment_sha256':digest(env),'workspace_id':env['console_workspace_id'],'protected_data':capture(store),'consumed_files':consumed,'runtime_build':runtime['build_id'],'runtime_manifest_sha256':sha(runtime_root/'runtime-manifest.json'),'runtime_process_sha256':sha(PROJECT/'runtime-process.ps1'),'backend_path':str(runtime_root/'backend'),'model_autonomous_planning_verified':False,'original_section11_complete':False,'rehearsal_proof_sha256':sha(PROJECT/'work/complete-answer410-local/rehearsal-proof.json')}
    plan.update(source_model_plan_sha256=contract['source_model_plan_sha256'],manual_configuration_review=True,protected_isolated=isolated)
    plan['failure_diagnostic_policy']=FAILURE_POLICY
    plan['state_policy']=STATE_POLICY
    target.mkdir()
    for file in source.iterdir():
        if file.is_file() and file.suffix in {'.py','.json','.md'}:shutil.copyfile(file,target/file.name)
    (target/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n','utf-8');(target/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n','utf-8')
    from execute import FROZEN,validated
    require({x.name for x in target.iterdir()}==FROZEN,'Unexpected frozen file set')
    (target/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':plan['batch_id'],'files':{name:sha(target/name) for name in sorted(FROZEN)}},ensure_ascii=False,indent=2)+'\n','utf-8')
    require(validated(target)==plan,'Final frozen scope validation failed')
    return {'state':'frozen_not_approved','files':len(FROZEN),'plan_sha256':sha(target/'plan.json'),'manifest_sha256':sha(target/'manifest.json'),'physical_model_dify_http':0}

if __name__=='__main__':print(json.dumps(freeze(),ensure_ascii=False))
