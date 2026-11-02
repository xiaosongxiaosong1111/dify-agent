"""Freeze new scope only after source-bound zero-HTTP verification."""
import json,shutil,sys
from pathlib import Path
from common import PROJECT,ReadOnly,capture,digest,require,sha,SEED,saved_seed
from execute import POLICY,UPPER,LIMITS,ISOLATED,FROZEN,validated,current,REGRANT
from runtime_reference import runtime_check

def freeze():
 root=Path(__file__).resolve().parent;target=PROJECT/'work/recovered-chatflow418';require(root==PROJECT/'tools/recovered-chatflow418' and not target.exists(),'New canonical packet only')
 proof_path=PROJECT/'work/recovered-chatflow418-local/rehearsal-verified/proof.json';proof=json.loads(proof_path.read_text('utf-8'));require(proof['state']=='passed' and proof['physical_http']==0 and proof['source_sha256']=={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'}},'Final source-bound public proof required')
 baseline=PROJECT/'work/autonomous-chatflow416';source=ReadOnly(PROJECT/'data');require(len(source.list('task'))==26 and capture(source)==json.loads((baseline/'post-production-data-snapshot.json').read_text('utf-8')),'Production baseline changed')
 index=baseline/'sealed-evidence-sha256.json';require(sha(index)=='fd7b73c80d6b7a2c99d893576b2c4c506979e25c4d71125422fe6f2beff62b9d','Old consumed index changed');files=json.loads(index.read_text('utf-8'));require(len(files)==666,'Wrong protected count');files[index.relative_to(PROJECT).as_posix()]=sha(index)
 isolated={k:capture(ReadOnly(PROJECT/path)) for k,path in ISOLATED.items()};require(all(value==json.loads((baseline/('post-'+k+'-data-snapshot.json')).read_text('utf-8')) for k,value in isolated.items()),'Old isolated data changed')
 provider=source.get('provider','9513f594-c256-46b7-882a-35d9871bf9d0');require(provider and provider['base_url'].rstrip('/')=='https://api.deepseek.com' and provider['model']=='deepseek-flash' and provider.get('protocol','openai-compatible')=='openai-compatible','Selected provider changed')
 sys.path.insert(0,str(PROJECT/'backend'));from app.provider_presets import runtime_profile;from app.planning import validate_pricing
 require(runtime_profile(provider)=='deepseek' and validate_pricing(provider.get('pricing')) is not None,'Profile/price invalid')
 with source.connect() as db:require(db.execute('SELECT 1 FROM secrets WHERE id=?',(provider['id']+':api_key',)).fetchone(),'Encrypted selected Key absent')
 folder=PROJECT/'.runtime/snapshots/0.378.0-3f71a320b40afcec120e'
 p={'schema_version':1,'batch_id':'recovered-chatflow418','policy':POLICY,'limits':LIMITS,'new_conservative_upper':UPPER,'new_model_slots':0,'regrant':REGRANT,'seed':SEED,'provider_id':provider['id'],'provider_sha256':digest(provider),'protected_data':capture(source),'protected_isolated':isolated,'protected_files':files,'runtime_build':folder.name,'backend_path':str(folder/'backend'),'runtime_manifest_sha256':sha(folder/'runtime-manifest.json'),'runtime_process_sha256':sha(PROJECT/'runtime-process.ps1'),'rehearsal_proof_sha256':sha(proof_path),'all_old_reservations_kept':True,'billing_hard_cap':False,'original_model_has_no_saved_graph':True,'full_business_accepted':False}
 saved_seed();current(p);runtime_check(p);target.mkdir()
 for file in root.iterdir():
  if file.is_file() and file.suffix in {'.py','.json','.md'}:shutil.copyfile(file,target/file.name)
 (target/'plan.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n','utf-8');require({x.name for x in target.iterdir()}==FROZEN,'Unexpected packet file set')
 (target/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':p['batch_id'],'files':{n:sha(target/n) for n in sorted(FROZEN)}},indent=2)+'\n','utf-8');validated(target)
 print(json.dumps({'state':'frozen_not_approved','files':len(FROZEN),'plan_sha256':sha(target/'plan.json'),'manifest_sha256':sha(target/'manifest.json'),'physical_http':0}))
if __name__=='__main__':freeze()
