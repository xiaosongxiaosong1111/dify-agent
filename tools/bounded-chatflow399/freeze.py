"""New explicit two-request scope; no old reservations reused or decrypted."""
import json,shutil,sys
from pathlib import Path
from common import PROJECT,ReadOnly,capture,digest,require,sha,LIMITS
from execute import FROZEN,POLICY,UPPER,validated,current
from runtime_reference import runtime_check
def freeze():
    root=Path(__file__).resolve().parent;target=PROJECT/'work/bounded-chatflow399';require(root==PROJECT/'tools/bounded-chatflow399' and not target.exists(),'New canonical packet only')
    proof_path=PROJECT/'work/bounded-chatflow399-local/rehearsal/proof.json';proof=json.loads(proof_path.read_text('utf-8'))
    require(proof['state']=='passed' and proof['physical_http']==0 and proof['source_sha256']=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}},'Source-bound public proof required')
    baseline=PROJECT/'work/planning-attempt398';source=ReadOnly(PROJECT/'data');protected=json.loads((baseline/'consumed-sha256.json').read_text('utf-8'))
    require(len(source.list('task'))==24 and len(protected)==457 and capture(source)==json.loads((baseline/'production-data-snapshot.json').read_text('utf-8')),'Original production source changed')
    isolated={}
    for batch,key in [('chatflow-model391','isolated391'),('clarified-chatflow394','isolated394')]:
        isolated[key]=capture(ReadOnly(PROJECT/'work'/batch/'live-output/data'))
        require(isolated[key]==json.loads((baseline/(key+'-data-snapshot.json')).read_text('utf-8')),'Old isolated Task/fee changed')
    provider=source.get('provider','9513f594-c256-46b7-882a-35d9871bf9d0')
    require(provider and provider['base_url'].rstrip('/')=='https://api.deepseek.com' and provider['model']=='deepseek-flash' and provider.get('protocol','openai-compatible')=='openai-compatible','Provider differs')
    sys.path.insert(0,str(PROJECT/'backend'))
    from app.provider_presets import runtime_profile
    from app.planning import validate_pricing
    require(runtime_profile(provider)=='deepseek' and validate_pricing(provider.get('pricing')) is not None,'Profile/prices invalid')
    with source.connect() as db:require(db.execute('SELECT 1 FROM secrets WHERE id=?',(provider['id']+':api_key',)).fetchone(),'Encrypted Key absent')
    folder=PROJECT/'.runtime/snapshots/0.369.0-ff46c4bbe293269c1a14'
    plan={'schema_version':1,'batch_id':'bounded-chatflow399','policy':POLICY,'limits':LIMITS,'new_conservative_upper':UPPER,'provider_id':provider['id'],'provider_sha256':digest(provider),'protected_data':capture(source),'protected_isolated_391':isolated['isolated391'],'protected_isolated_394':isolated['isolated394'],'protected_files':protected,'runtime_build':folder.name,'backend_path':str(folder/'backend'),'runtime_manifest_sha256':sha(folder/'runtime-manifest.json'),'runtime_process_sha256':sha(PROJECT/'runtime-process.ps1'),'rehearsal_proof_sha256':sha(proof_path),'all_old_reservations_kept':True,'billing_hard_cap':False,'new_scope':{'new_model_slots':2,'new_estimate_usd':'0.160','old_slots_reused':0}}
    current(plan);runtime_check(plan);target.mkdir()
    for file in root.iterdir():
        if file.is_file() and file.suffix in {'.py','.json','.md'}:shutil.copyfile(file,target/file.name)
    (target/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n','utf-8');require({p.name for p in target.iterdir()}==FROZEN,'Unexpected frozen files')
    (target/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':plan['batch_id'],'files':{n:sha(target/n) for n in sorted(FROZEN)}},indent=2)+'\n','utf-8');validated(target)
    print(json.dumps({'state':'frozen_not_approved','files':len(FROZEN),'plan_sha256':sha(target/'plan.json'),'manifest_sha256':sha(target/'manifest.json'),'physical_http':0}))
if __name__=='__main__':freeze()
