"""Generate a public rehearsal copy and the one-shot pending 371 freeze; never dispatch."""
import argparse,hashlib,importlib.util,json,os,re,sqlite3,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
WORK=(PROJECT/'work').resolve()
BATCH='autonomous-dual371'
PINS={'common.py','boundary.py','boundary_checks.py','storage_guard.py','reviews.py','reviews_checks.py','pagination.py','pagination_checks.py','candidate.py','journey.py','worker.py','synthetic.py','runtime_reference.py','rehearse.py','fixture.json'}
NAMES=PINS|{'execute.py','freeze.py','README.md','profile.json','approved_scope.md','plan.json'}
ISOLATED={'391':'work/chatflow-model391/live-output/data','394':'work/clarified-chatflow394/live-output/data','399':'work/bounded-chatflow399/live-output/data','401':'work/reviewed-chatflow401/live-output/data','405':'work/offline-candidate405/data','408':'work/reviewed-planning408/live-output/data','409':'work/offline-candidate409/data','414':'work/autonomous-chatflow414/live-output/data','416':'work/autonomous-chatflow416/live-output/data','418':'work/recovered-chatflow418/live-output/data','420':'work/reviewed-spec-planning420/live-output/data'}
PROFILE_KEYS={'schema_version','batch_id','approval_scope','approval_phrase','approval_question_suffix','limits','new_conservative_upper','approved_model_slots','effective_model_http','json_repair_http','per_model_reserve_usd','model_total_usd','model_estimate_book_upper_usd','dify_estimate_usd','combined_estimate_usd','billing_hard_cap','wall_seconds','task_start_cap','task_minutes','runtime_build','runtime_version','runtime_file_count','runtime_pid_observed','source_commit','source_dir','source_normalization','source_pins','expected_counts','workspace_id','environment_id','provider_id','provider_model','provider_protocol','console_version','proposal_doc','protected_old_count','protected_337_count','protected_total_count','sealed_index_sha256','protected_seals','isolated_paths'}
PLAN_KEYS={'schema_version','batch_id','approval_state','proposal_state','source_commit','source_commit_base','source_dir','source_normalization','source_pins','frozen_source_files','proposal_doc','proposal_sha256','approved_scope_sha256','limits','new_conservative_upper','approved_model_slots','effective_model_http','json_repair_http','per_model_reserve_usd','model_total_usd','model_estimate_book_upper_usd','dify_estimate_usd','combined_estimate_usd','billing_hard_cap','wall_seconds','task_start_cap','task_minutes','runtime_build','runtime_version','runtime_file_count','runtime_pid','runtime_manifest_sha256','runtime_process_sha256','backend_path','provider_id','provider_sha256','environment_id','protected_data','isolated_paths','protected_isolated','protected_files','protected_old_count','protected_337_count','protected_total_count','sealed_index_sha256','protected_seals','known_apps'}
LIMITS={'new_tasks':1,'model':6,'reads':128,'login':1,'import':2,'publish':2,'key':2,'run':14}
UPPER={'model':57,'reads':1730,'login':49,'import':30,'publish':30,'key':30,'run':148}
SEALS={'autonomous-dual366':{'path':'work/autonomous-dual366/seal-after-stop.json','sha256':'bb6ab4daf437039b71b844748d881752030db17ef9f07cf5602b24cfc6856803','entries':26},'console-http-probe369':{'path':'work/console-http-probe369/seal.json','sha256':'9bd03c377eeb064b667c0ab23086b76fc315c939ca2ebb49ed29d045f3f6a972','entries':2},'console-port-forward370':{'path':'work/console-port-forward370/seal.json','sha256':'2cbfb287f9cc38b9e65e6fb28c2f14127350ad5b66465c2b864f10b96c3fff85','entries':6}}

def require(value,message):
    if not value:raise RuntimeError(message)

def sha_bytes(value):return hashlib.sha256(value).hexdigest()
def sha(path):return sha_bytes(Path(path).read_bytes())
def _hex(value):return isinstance(value,str) and bool(re.fullmatch(r'[0-9a-f]{64}',value))
def _githex(value):return isinstance(value,str) and bool(re.fullmatch(r'[0-9a-f]{40}',value))
def _int(value,label):
    require(type(value) is int,label+' must be int');return value
def _strict(value,expected,label):
    require(isinstance(value,dict) and set(value)==set(expected),label+' fields changed')
    require(all(type(value[key]) is int and value[key]==expected[key] for key in expected),label+' must be exact ints')

def load(path):
    def pairs(rows):
        result={}
        for k,v in rows:require(k not in result,'Duplicate JSON field');result[k]=v
        return result
    raw=Path(path).read_bytes();require(len(raw)<=12000000,'JSON too large')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Non-finite JSON'))

def validate_profile(p):
    require(isinstance(p,dict) and set(p)==PROFILE_KEYS,'Profile fields changed')
    require(_int(p['schema_version'],'schema_version')==1 and p['batch_id']==BATCH and p['approval_scope']==BATCH,'Profile identity changed')
    require(p['approval_phrase']=='允许改授366未派发范围并新增1次登录，执行独立371批' and p['approval_question_suffix']=='/q0','Approval phrase changed')
    _strict(p['limits'],LIMITS,'limits');_strict(p['new_conservative_upper'],UPPER,'new_conservative_upper')
    require(_int(p['approved_model_slots'],'approved_model_slots')==6 and _int(p['effective_model_http'],'effective_model_http')==6 and _int(p['json_repair_http'],'json_repair_http')==0,'Model slots changed')
    require((p['per_model_reserve_usd'],p['model_total_usd'],p['model_estimate_book_upper_usd'],p['dify_estimate_usd'],p['combined_estimate_usd'])==('0.100','0.600','3.355473652','0.100','0.700'),'Cost bounds changed')
    require(p['billing_hard_cap'] is False and _int(p['wall_seconds'],'wall_seconds')==3600 and _int(p['task_start_cap'],'task_start_cap')==12 and _int(p['task_minutes'],'task_minutes')==45,'Time bounds changed')
    require(p['runtime_build']=='0.410.0-23c94dbe89553f265c3b' and p['runtime_version']=='0.410.0' and _int(p['runtime_file_count'],'runtime_file_count')==298 and _int(p['runtime_pid_observed'],'runtime_pid_observed')>0,'Runtime identity changed')
    require(_githex(p['source_commit']) and p['source_dir']=='tools/autonomous-dual337' and p['source_normalization']=='crlf_to_lf','Source identity changed')
    require(set(p['source_pins'])==PINS and len(p['source_pins'])==15 and all(_hex(v) for v in p['source_pins'].values()),'Source pins changed')
    _strict(p['expected_counts'],{'task':26,'environment':10,'provider':2},'expected_counts')
    require(p['workspace_id']=='c3306c18-ceb2-4bee-b2d1-796ce2048f17' and p['environment_id']=='202bfb35-2f92-47c1-bc1b-eac32082181d' and p['provider_id']=='9513f594-c256-46b7-882a-35d9871bf9d0','Public identity changed')
    require(p['provider_model']=='deepseek-flash' and p['provider_protocol']=='openai-compatible' and p['console_version']=='1.17.1','Provider identity changed')
    require(p['proposal_doc']=='docs/autonomous-dual371-plan-20261122.md','Proposal path changed')
    require((_int(p['protected_old_count'],'protected_old_count'),_int(p['protected_337_count'],'protected_337_count'),_int(p['protected_total_count'],'protected_total_count'))==(733,24,795),'Protection counts changed')
    require(p['sealed_index_sha256']=='c9d9ef645118610e0fce61f5aed8deeb3e30f7e56b17d2c58511a25e5eef04e0' and p['protected_seals']==SEALS,'Protection seals changed')
    require(p['isolated_paths']==ISOLATED,'Isolated roots changed')

def load_profile():
    p=load(HERE/'profile.json');validate_profile(p);return p

def _replace_once(raw,old,new,label):
    require(isinstance(raw,bytes),label+' is not bytes')
    count=raw.count(old);require(count==1,label+' replacement count '+str(count))
    return raw.replace(old,new)

def derive(name,raw):
    if name=='common.py':
        value=_replace_once(raw,b"BATCH_ID='autonomous-dual337'",b"BATCH_ID='autonomous-dual371'",name)
        require(b'autonomous-dual337' not in value,'Derived common still names 337');return value
    if name=='worker.py':
        value=_replace_once(raw,b"'approved_model_slots':8",b"'approved_model_slots':6",name)
        require(b"'approved_model_slots':8" not in value,'Derived worker still records 8');return value
    return raw

def _normalize_source(raw):
    require(isinstance(raw,bytes),'Source is not bytes');return raw.replace(b'\r\n',b'\n')

def _verified_sources(project,p):
    source=(project/p['source_dir']).resolve();require((project/p['source_dir']).is_dir() and not (project/p['source_dir']).is_symlink() and source==(project/p['source_dir']).resolve(),'Source directory changed')
    result={}
    for name,value in p['source_pins'].items():
        path=(source/name).resolve();require(path.is_file() and not (source/name).is_symlink() and path.parent==source,'Pinned source missing: '+name)
        raw=_normalize_source(path.read_bytes());require(sha_bytes(raw)==value,'Pinned source changed: '+name)
        result[name]=raw
    require(set(result)==PINS and len(result)==15,'Pinned source set changed')
    return result

def _source_common(project,p,verified):
    source=(project/p['source_dir']).resolve();expected=(source/'common.py').resolve()
    require('common.py' in verified and (source/'common.py').is_file(),'Verified common missing')
    if 'common' in sys.modules:
        cached=Path(getattr(sys.modules['common'],'__file__','')).resolve()
        require(cached==expected,'Cached common came from a different path')
        return sys.modules['common']
    sys.path.insert(0,str(source))
    try:
        import common
        require(Path(common.__file__).resolve()==expected,'Imported common came from a different path');return common
    finally:
        sys.path.remove(str(source))

def _runtime_check(project,p,verified,probe):
    require('runtime_reference.py' in verified,'Verified runtime helper missing')
    source=(project/p['source_dir']).resolve()
    if 'common' in sys.modules:require(Path(sys.modules['common'].__file__).resolve()==(source/'common.py').resolve(),'Cached common came from a different path')
    sys.path.insert(0,str(source))
    try:
        spec=importlib.util.spec_from_file_location('_dual337_runtime_reference',source/'runtime_reference.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        require(Path(module.__file__).resolve()==(source/'runtime_reference.py').resolve(),'Runtime helper came from a different path')
        return module.runtime_check(probe)
    finally:
        sys.path.remove(str(source))

def _hash_map(value):
    if isinstance(value,dict) and isinstance(value.get('files'),dict):value=value['files']
    if isinstance(value,dict) and isinstance(value.get('files'),list):value=value['files']
    if isinstance(value,list):
        rows=value;value={}
        for row in rows:
            require(isinstance(row,dict) and isinstance(row.get('path'),str) and _hex(row.get('sha256')),'Malformed sealed list')
            value[row['path']]=row['sha256']
    require(isinstance(value,dict) and value,'Sealed file map missing')
    result={}
    for name,item in value.items():
        require(isinstance(name,str) and name and _hex(item),'Malformed sealed entry')
        result[name.replace('\\','/')]=item
    return result

def _batch_file(base,name):
    require(isinstance(name,str) and name,'Sealed path missing')
    raw=Path(name);require(not raw.is_absolute() and not raw.drive and not raw.root,'Sealed path absolute')
    path=(base/name).resolve();require(path.is_relative_to(base) and path!=base and path.is_file(),'Sealed path escaped')
    return path

def _batch_sealed(base,name,value):
    require(_hex(value),'Sealed hash invalid');path=_batch_file(base,name)
    require(sha(path)==value,'Sealed evidence changed');return path

def _seal_group(project,spec):
    seal=project/spec['path'];base=seal.parent.resolve()
    require(not seal.is_symlink() and seal.is_file() and sha(seal)==spec['sha256'],'Seal index changed')
    require(base.is_relative_to((project/'work').resolve()) and base.is_dir(),'Seal directory escaped')
    entries=_hash_map(load(seal));require(len(entries)==spec['entries'],'Seal count changed')
    result={}
    for name,value in entries.items():
        path=_batch_sealed(base,name,value);key=path.relative_to(project).as_posix()
        require(key not in result,'Seal path collision: '+key);result[key]=value
    key=seal.relative_to(project).as_posix();require(key not in result,'Seal index collision');result[key]=sha(seal)
    require(len(result)==spec['entries']+1,'Seal total changed');return result

def _old366_not_dispatched(value,count_key):
    require(isinstance(value,dict) and value.get('state')=='stopped','Old 366 is not stopped')
    counts=value.get(count_key);expected={'model':0,'reads':0,'login':1,'import':0,'publish':0,'key':0,'run':0}
    require(isinstance(counts,dict) and set(counts)==set(expected) and all(type(counts[key]) is int and counts[key]==expected[key] for key in expected),'Old 366 was dispatched')
    require(_int(value.get('physical_http'),'physical_http')==1 and not value.get('task_id'),'Old 366 scope changed')

def _sealed_record(project,base,name,files):
    path=_batch_file(base,name);key=path.relative_to(project).as_posix()
    require(key in files and sha(path)==files[key],'Old 366 record not sealed: '+name)
    value=load(path);require(isinstance(value,dict),'Old 366 record malformed');return value

def _old366_gate(project,base,files):
    progress=_sealed_record(project,base,'live-output/progress.json',files)
    attempt=_sealed_record(project,base,'attempt.json',files)
    _old366_not_dispatched(progress,'dispatch_counts');_old366_not_dispatched(attempt,'counts')

def _history(project,p):
    sealed=project/'work/reviewed-spec-planning420/sealed-evidence-sha256.json'
    require(sha(sealed)==p['sealed_index_sha256'],'Old sealed index changed')
    old=_hash_map(load(sealed));old[sealed.relative_to(project).as_posix()]=sha(sealed)
    require(len(old)==p['protected_old_count']==733,'Old sealed count changed')
    for name,value in old.items():
        path=(project/name).resolve()
        require(path.is_relative_to(project/'work') and path.is_file() and sha(path)==value,'Old sealed evidence changed')
    seal=project/'work/autonomous-dual337/seal-after-stop.json';base=seal.parent.resolve()
    require(base.is_relative_to((project/'work').resolve()) and base.is_dir() and not seal.is_symlink(),'337 seal directory changed')
    recent=_hash_map(load(seal));require(len(recent)==p['protected_337_count']==24,'337 seal count changed')
    files=dict(old)
    for name,value in recent.items():
        candidate=_batch_sealed(base,name,value);key=candidate.relative_to(project).as_posix()
        require(key not in files,'337 seal path collision');files[key]=value
    key=seal.relative_to(project).as_posix();require(key not in files,'337 seal index collision');files[key]=sha(seal)
    require(len(files)==758,'Base protected count changed')
    for label,spec in p['protected_seals'].items():
        group=_seal_group(project,spec)
        for key,value in group.items():
            require(key not in files,'New seal path collision: '+key);files[key]=value
    require(len(files)==p['protected_total_count']==795,'Total protected count changed')
    old_base=(project/SEALS['autonomous-dual366']['path']).parent.resolve();_old366_gate(project,old_base,files)
    return files

def _roots(project,p,common):
    data=common.ReadOnly(project/'data')
    protected_data=common.capture(data)
    isolated={label:common.capture(common.ReadOnly(project/path)) for label,path in p['isolated_paths'].items()}
    require(len(isolated)+1==12,'Twelve protected roots required')
    return data,protected_data,isolated

def _write_package(stage,p,proposal,verified):
    for name,data in verified.items():(stage/name).write_bytes(derive(name,data))
    for name in ('execute.py','profile.json'):
        (stage/name).write_bytes((HERE/name).read_bytes())
    (stage/'freeze.py').write_bytes((HERE/'prepare.py').read_bytes())
    readme=HERE/'README.md';require(readme.is_file() and not readme.is_symlink(),'Local README not ready')
    (stage/'README.md').write_bytes(readme.read_bytes())
    (stage/'approved_scope.md').write_bytes(proposal)

def _make_plan(stage,p,proposal,project,common,data,runtime):
    folder=project/'.runtime/snapshots'/p['runtime_build']
    source_files={name:sha(stage/name) for name in sorted(NAMES-{'plan.json'})}
    plan={'schema_version':1,'batch_id':BATCH,'approval_state':'pending','proposal_state':'proposed_not_approved','source_commit':_head(project),'source_commit_base':p['source_commit'],'source_dir':p['source_dir'],'source_normalization':p['source_normalization'],'source_pins':p['source_pins'],'frozen_source_files':source_files,'proposal_doc':p['proposal_doc'],'proposal_sha256':sha_bytes(proposal),'approved_scope_sha256':sha_bytes(proposal),'limits':p['limits'],'new_conservative_upper':p['new_conservative_upper'],'approved_model_slots':6,'effective_model_http':6,'json_repair_http':0,'per_model_reserve_usd':p['per_model_reserve_usd'],'model_total_usd':p['model_total_usd'],'model_estimate_book_upper_usd':p['model_estimate_book_upper_usd'],'dify_estimate_usd':p['dify_estimate_usd'],'combined_estimate_usd':p['combined_estimate_usd'],'billing_hard_cap':False,'wall_seconds':p['wall_seconds'],'task_start_cap':p['task_start_cap'],'task_minutes':p['task_minutes'],'runtime_build':p['runtime_build'],'runtime_version':p['runtime_version'],'runtime_file_count':p['runtime_file_count'],'runtime_pid':_int(runtime['verified_pid'],'verified_pid'),'runtime_manifest_sha256':sha(folder/'runtime-manifest.json'),'runtime_process_sha256':sha(project/'runtime-process.ps1'),'backend_path':str(folder/'backend'),'provider_id':p['provider_id'],'provider_sha256':common.digest(data.get('provider',p['provider_id'])),'environment_id':p['environment_id'],'protected_data':None,'isolated_paths':p['isolated_paths'],'protected_isolated':None,'protected_files':None,'protected_old_count':p['protected_old_count'],'protected_337_count':p['protected_337_count'],'protected_total_count':p['protected_total_count'],'sealed_index_sha256':p['sealed_index_sha256'],'protected_seals':p['protected_seals'],'known_apps':sorted(common.known_apps(data))}
    require(set(plan)==PLAN_KEYS,'Plan fields changed');return plan

def _head(project):
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True).strip()

def cmd_sources(output):
    out=Path(output).resolve();p=load_profile();verified=_verified_sources(PROJECT,p)
    require(out.parent==WORK and not out.exists() and not out.is_symlink(),'New direct work output required')
    out.mkdir()
    for name,data in verified.items():(out/name).write_bytes(derive(name,data))
    (out/'execute.py').write_bytes((HERE/'execute.py').read_bytes())
    (out/'freeze.py').write_bytes((HERE/'prepare.py').read_bytes())
    (out/'profile.json').write_bytes((HERE/'profile.json').read_bytes())
    readme=HERE/'README.md';require(readme.is_file(),'Local README not ready');(out/'README.md').write_bytes(readme.read_bytes())
    print(json.dumps({'state':'public_sources_ready','output':str(out),'files':len(p['source_pins'])+4,'physical_http':0},ensure_ascii=False))

def cmd_pending(project_root):
    project=Path(project_root).resolve();p=load_profile()
    require(project==Path(r'E:\workSpace\dify-agent'),'Original project only')
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=project,text=True).strip(),'Clean original checkout required')
    head=_head(project);require(_githex(head),'Source commit invalid')
    work=(project/'work').resolve();require(work==project.resolve()/'work' and not (project/'work').is_symlink() and work.parent==project,'Work path changed')
    root=work/BATCH;require(not root.exists() and not root.is_symlink() and root.parent.resolve()==work,'Canonical package already exists')
    verified=_verified_sources(project,p)
    with sqlite3.connect((project/'data/flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        counts={k:n for k,n in db.execute("select kind,count(*) from objects where kind in ('task','environment','provider') group by kind")}
        secret_ids={row[0] for row in db.execute('select id from secrets')}
    require(counts==p['expected_counts'] and all(type(value) is int for value in counts.values()),'Protected counts changed')
    common=_source_common(project,p,verified);data=common.ReadOnly(project/'data')
    provider=data.get('provider',p['provider_id']);env=data.get('environment',p['environment_id'])
    require(provider and env,'Provider or environment missing')
    require(provider.get('id')==p['provider_id'] and provider.get('model')==p['provider_model'] and provider.get('protocol')==p['provider_protocol'] and isinstance(provider.get('pricing'),dict),'Provider profile changed')
    require(env.get('id')==p['environment_id'] and env.get('console_workspace_id')==p['workspace_id'] and env.get('version')==p['console_version'],'Workspace/environment changed')
    require({p['environment_id']+':'+k for k in ('console_login_email','console_login_password')}|{p['provider_id']+':api_key'}<=secret_ids,'Encrypted credentials missing')
    folder=project/'.runtime/snapshots'/p['runtime_build'];manifest=load(folder/'runtime-manifest.json')
    require(len(manifest['files'])==p['runtime_file_count'] and manifest.get('shared_data_copied') is False,'Runtime manifest changed')
    require(all(sha(project/name)==value and sha(folder/name)==value for name,value in manifest['files'].items()),'Runtime source/snapshot mismatch')
    probe={'runtime_build':p['runtime_build'],'runtime_manifest_sha256':sha(folder/'runtime-manifest.json'),'runtime_process_sha256':sha(project/'runtime-process.ps1')}
    runtime=_runtime_check(project,p,verified,probe)
    files=_history(project,p);data,protected_data,isolated=_roots(project,p,common)
    proposal=project/p['proposal_doc'];require(proposal.is_file() and not proposal.is_symlink(),'371 proposal document missing');proposal_bytes=proposal.read_bytes()
    stage=work/('.autonomous-dual371-staging-'+str(os.getpid()));require(not stage.exists() and not stage.is_symlink() and stage.parent.resolve()==work,'Staging path invalid')
    stage.mkdir()
    _write_package(stage,p,proposal_bytes,verified)
    plan=_make_plan(stage,p,proposal_bytes,project,common,data,runtime)
    plan.update(protected_data=protected_data,protected_isolated=isolated,protected_files=files)
    require(set(plan)==PLAN_KEYS,'Plan fields changed')
    (stage/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,sort_keys=True,indent=2),'utf-8')
    manifest={'schema_version':1,'batch_id':BATCH,'files':{name:sha(stage/name) for name in sorted(NAMES)}}
    (stage/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2),'utf-8')
    require(stage.resolve().parent==work and not stage.is_symlink(),'Staging escaped work')
    require(root.parent.resolve()==work and not root.exists() and not root.is_symlink(),'Canonical target changed')
    require(set(x.name for x in stage.iterdir())==NAMES|{'manifest.json'},'Frozen file set changed')
    require(set(manifest['files'])==NAMES and len(manifest['files'])==21,'Manifest file set changed')
    require(all((stage/name).is_file() and not (stage/name).is_symlink() and sha(stage/name)==value for name,value in manifest['files'].items()),'Frozen package hash mismatch')
    require(not (stage/'approval.json').exists() and not (stage/'attempt.json').exists() and not (stage/'worker-started.json').exists(),'Pending package contains live marker')
    os.rename(stage,root)
    print(json.dumps({'state':'pending_frozen_not_approved','root':str(root),'plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json'),'physical_http':0},ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    source=sub.add_parser('sources');source.add_argument('--output',required=True)
    pending=sub.add_parser('pending');pending.add_argument('--project-root',required=True)
    args=parser.parse_args()
    if args.command=='sources':cmd_sources(args.output)
    else:cmd_pending(args.project_root)
if __name__=='__main__':main()
