"""Freeze only; no decryption or live invocation without new direct regrant."""
import json,shutil,sys
from pathlib import Path
from common import PROJECT,ReadOnly,capture,digest,require,sha,LIMITS
from execute import FROZEN,POLICY,UPPER,REGRANT,SOURCE_PLAN,SOURCE_CASES,validated,current
from runtime_reference import runtime_check
def freeze():
    root=Path(__file__).resolve().parent;target=PROJECT/'work/reviewed-planning408'
    require(root==PROJECT/'tools/reviewed-planning408' and not target.exists(),'New canonical packet only')
    proof_path=PROJECT/'work/reviewed-planning408-local/rehearsal/proof.json';proof=json.loads(proof_path.read_text('utf-8'))
    require(proof['state']=='passed' and proof['physical_http']==0 and proof['source_sha256']=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}},'Source-bound public proof required')
    baseline=PROJECT/'work/planning-cases407';source=ReadOnly(PROJECT/'data');protected=json.loads((baseline/'consumed-sha256.json').read_text('utf-8'))
    require(len(source.list('task'))==25 and capture(source)==json.loads((baseline/'production-data-snapshot.json').read_text('utf-8')) and len(protected)==542,'Original data/source count changed')
    index=PROJECT/'work/reviewed-platform406/sealed-evidence-sha256.json'
    require(sha(index)=='7179493baf745669a8f67344adca00bd0f40b2ce0119115032ce01a4c5a936b5' and protected=={**json.loads(index.read_text('utf-8')),str(index.relative_to(PROJECT)).replace('\\','/'):sha(index)},'Latest consumed evidence index required')
    roots={'391':'work/chatflow-model391/live-output/data','394':'work/clarified-chatflow394/live-output/data','399':'work/bounded-chatflow399/live-output/data','401':'work/reviewed-chatflow401/live-output/data','405':'work/offline-candidate405/data'}
    isolated={key:capture(ReadOnly(PROJECT/path)) for key,path in roots.items()}
    require(all(value==json.loads((baseline/('isolated'+key+'-data-snapshot.json')).read_text('utf-8')) for key,value in isolated.items()),'Old isolated Task/fees changed')
    from guard import baseline as original_plan
    fixture=json.loads((root/'fixture.json').read_text('utf-8'));original_plan(fixture)
    provider=source.get('provider','9513f594-c256-46b7-882a-35d9871bf9d0')
    require(provider and provider['base_url'].rstrip('/')=='https://api.deepseek.com' and provider['model']=='deepseek-flash' and provider.get('protocol','openai-compatible')=='openai-compatible','Provider changed')
    sys.path.insert(0,str(PROJECT/'backend'))
    from app.provider_presets import runtime_profile
    from app.planning import validate_pricing
    require(runtime_profile(provider)=='deepseek' and validate_pricing(provider.get('pricing')) is not None,'Profile/price invalid')
    with source.connect() as db:require(db.execute('SELECT 1 FROM secrets WHERE id=?',(provider['id']+':api_key',)).fetchone(),'Encrypted Key absent')
    folder=PROJECT/'.runtime/snapshots/0.373.0-f8dc99952a3bf70b3b6d'
    plan={'schema_version':1,'batch_id':'reviewed-planning408','policy':POLICY,'limits':LIMITS,'new_conservative_upper':UPPER,'provider_id':provider['id'],'provider_sha256':digest(provider),'protected_data':capture(source),'protected_isolated':isolated,'protected_files':protected,'runtime_build':folder.name,'backend_path':str(folder/'backend'),'runtime_manifest_sha256':sha(folder/'runtime-manifest.json'),'runtime_process_sha256':sha(PROJECT/'runtime-process.ps1'),'rehearsal_proof_sha256':sha(proof_path),'all_old_reservations_kept':True,'billing_hard_cap':False,'regrant':REGRANT,'source_model_plan_sha256':SOURCE_PLAN,'source_cases_sha256':SOURCE_CASES,'source_task_id':fixture['source_task_id'],'source_revision':7}
    current(plan);runtime_check(plan)
    target.mkdir()
    for file in root.iterdir():
        if file.is_file() and file.suffix in {'.py','.json','.md'}:shutil.copyfile(file,target/file.name)
    (target/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n','utf-8');require({p.name for p in target.iterdir()}==FROZEN,'Unexpected packet file set')
    (target/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':plan['batch_id'],'files':{n:sha(target/n) for n in sorted(FROZEN)}},indent=2)+'\n','utf-8');validated(target)
    print(json.dumps({'state':'frozen_not_approved','files':len(FROZEN),'plan_sha256':sha(target/'plan.json'),'manifest_sha256':sha(target/'manifest.json'),'physical_http':0}))
if __name__=='__main__':freeze()
