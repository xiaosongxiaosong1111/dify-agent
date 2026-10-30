"""Freeze a new model-only scope after source-bound public verification."""
import json,sys,urllib.request
from pathlib import Path
import shutil
from common import PROJECT,ReadOnly,capture,digest,require,sha,LIMITS
from execute import FROZEN,POLICY,UPPER,validated

def freeze():
    root=Path(__file__).resolve().parent;target=PROJECT/'work/chatflow-model391';require(root==PROJECT/'tools/chatflow-model391' and not target.exists(),'New canonical packet only')
    proof=json.loads((PROJECT/'work/chatflow-model391-local/rehearsal-proof.json').read_text('utf-8'))
    require(proof.get('state')=='passed' and proof.get('physical_http')==0 and proof['source_sha256']=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}},'Final source-bound public proof required')
    source=ReadOnly(PROJECT/'data');baseline=json.loads((PROJECT/'work/llm-context390/post-deploy-data-snapshot.json').read_text('utf-8'));protected=json.loads((PROJECT/'work/llm-context390/consumed-sha256.json').read_text('utf-8'))
    require(capture(source)==baseline and len(source.list('task'))==24 and len(protected)==415 and all(sha(PROJECT/n)==v for n,v in protected.items()),'Original data/evidence changed')
    fixture=json.loads((root/'fixture.json').read_text('utf-8'));provider=source.get('provider',fixture['provider_id']);require(provider and provider['base_url'].rstrip('/')=='https://api.deepseek.com' and provider['model']=='deepseek-flash' and provider.get('protocol','openai-compatible')=='openai-compatible','Selected source provider differs')
    sys.path.insert(0,str(PROJECT/'backend'));from app.provider_presets import runtime_profile
    from app.planning import validate_pricing
    require(runtime_profile(provider)=='deepseek' and validate_pricing(provider.get('pricing')) is not None,'Thinking/price source invalid')
    with source.connect() as db:require(db.execute('SELECT 1 FROM secrets WHERE id=?',(provider['id']+':api_key',)).fetchone(),'Encrypted provider key absent')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8765/api/runtime',timeout=10) as r:runtime=json.load(r)
    require(runtime['build_id']=='0.363.0-337d1119bd845a02a18b','Runtime changed')
    folder=PROJECT/'.runtime/snapshots'/runtime['build_id'];manifest=json.loads((folder/'runtime-manifest.json').read_text('utf-8'));require(all(sha(PROJECT/n)==v and sha(folder/n)==v for n,v in manifest['files'].items()),'Source/snapshot mismatch')
    plan={'schema_version':1,'batch_id':'chatflow-model391','policy':POLICY,'limits':LIMITS,'new_conservative_upper':UPPER,'provider_id':provider['id'],'provider_sha256':digest(provider),'protected_data':capture(source),'protected_files':protected,'runtime_build':runtime['build_id'],'backend_path':str(folder/'backend'),'runtime_manifest_sha256':sha(folder/'runtime-manifest.json'),'runtime_process_sha256':sha(PROJECT/'runtime-process.ps1'),'rehearsal_proof_sha256':sha(PROJECT/'work/chatflow-model391-local/rehearsal-proof.json'),'all_old_reservations_kept':True,'billing_hard_cap':False}
    target.mkdir()
    for file in root.iterdir():
        if file.is_file() and file.suffix in {'.py','.json','.md'}:shutil.copyfile(file,target/file.name)
    (target/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n','utf-8');require({p.name for p in target.iterdir()}==FROZEN,'Unexpected packet file set')
    (target/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':plan['batch_id'],'files':{n:sha(target/n) for n in sorted(FROZEN)}},indent=2)+'\n','utf-8');require(validated(target)==plan,'Final validation failed')
    print(json.dumps({'state':'frozen_not_approved','files':len(FROZEN),'plan_sha256':sha(target/'plan.json'),'manifest_sha256':sha(target/'manifest.json'),'physical_http':0}))

if __name__=='__main__':freeze()
