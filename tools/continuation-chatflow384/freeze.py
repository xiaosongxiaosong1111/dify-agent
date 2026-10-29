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
    from execute import FAILURE_POLICY
    source=Path(__file__).resolve().parent;target=PROJECT/'work/continuation-chatflow384'
    require(source==PROJECT/'tools/continuation-chatflow384' and not target.exists(),'Freeze only new canonical package')
    proof=json.loads((PROJECT/'work/continuation-chatflow384-local/rehearsal-proof.json').read_text('utf-8'));require(proof.get('state')=='passed' and proof.get('physical_http')==0,'Isolated full-chain proof required')
    require(proof.get('source_sha256')=={f.name:sha(f) for f in source.iterdir() if f.is_file() and f.suffix in {'.py','.json','.md'}},'Rehearsed sources changed')
    fixture=json.loads((source/'fixture.json').read_text('utf-8'));store=ReadOnly(PROJECT/'data');env=store.get('environment',fixture['environment_id'])
    require(len(store.list('task'))==22 and env and env.get('console_workspace_id')==fixture['workspace_id'],'Original source changed')
    with tempfile.TemporaryDirectory(dir=PROJECT/'work/continuation-chatflow384-local') as folder:
        os.environ['FLOWCRAFT_DATA_DIR']=folder;sys.path.insert(0,str(PROJECT/'backend'))
        from app import main as h
        from contract import build
        contract=build(h,fixture)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8765/api/runtime',timeout=10) as r:runtime=json.load(r)
    require(runtime.get('version')=='0.360.0' and runtime.get('mode')=='snapshot','Wrong runtime')
    runtime_root=PROJECT/'.runtime/snapshots'/runtime['build_id'];manifest=json.loads((runtime_root/'runtime-manifest.json').read_text('utf-8'))
    for name,value in manifest['files'].items():require(sha(PROJECT/name)==value and sha(runtime_root/name)==value,'Runtime/source mismatch')
    require(capture(store)==json.loads((PROJECT/'work/order-continuation383/post-deploy-data-snapshot.json').read_text('utf-8')),'Authorized19/post-deployment baseline changed')
    consumed=json.loads((PROJECT/'work/order-continuation383/consumed-sha256.json').read_text('utf-8'))
    require(len(consumed)==367 and all((PROJECT/name).resolve().is_relative_to(PROJECT/'work') and sha(PROJECT/name)==value for name,value in consumed.items()),'375/376/378/380/382/older consumed evidence changed')
    plan={'schema_version':1,'batch_id':'continuation-chatflow384','new_independent_scope':True,'old_reservations_preserved':True,'limits':LIMITS,'wall_seconds':3600,'execution_policy':{'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None},'model_estimate_book_upper_usd':'0.755473652','estimated_new_dify_usd':'0.10','estimate_is_bill_hard_cap':False,'host_cost_unknown':True,'new_conservative_upper':{'model':30,'reads':1213,'login':43,'import':22,'publish':22,'key':22,'run':92},'environment_id':env['id'],'environment_sha256':digest(env),'workspace_id':env['console_workspace_id'],'protected_data':capture(store),'consumed_files':consumed,'runtime_build':runtime['build_id'],'runtime_manifest_sha256':sha(runtime_root/'runtime-manifest.json'),'runtime_process_sha256':sha(PROJECT/'runtime-process.ps1'),'backend_path':str(runtime_root/'backend'),'model_autonomous_planning_verified':False,'original_section11_complete':False,'rehearsal_proof_sha256':sha(PROJECT/'work/continuation-chatflow384-local/rehearsal-proof.json')}
    plan['failure_diagnostic_policy']=FAILURE_POLICY
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
