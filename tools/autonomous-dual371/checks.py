"""Local negative checks for 371 admission and packaging; no HTTP, secret or canonical marker."""
import copy,json,sys,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import prepare,execute

H='a'*64;PLAN_SHA='b'*64;MANIFEST_SHA='c'*64
OLD366_COUNTS={'model':0,'reads':0,'login':1,'import':0,'publish':0,'key':0,'run':0}

def require(value,message):
    if not value:raise RuntimeError(message)

def rejected(fn,text):
    try:fn()
    except RuntimeError as exc:
        require(text in str(exc),'Wrong rejection: '+str(exc));return
    raise AssertionError('Expected rejection: '+text)

def plan(profile):
    source={name:H for name in execute.NAMES-{'plan.json'}}
    return {'schema_version':1,'batch_id':execute.BATCH,'approval_state':'pending','proposal_state':'proposed_not_approved','source_commit':'d'*40,'source_commit_base':profile['source_commit'],'source_dir':profile['source_dir'],'source_normalization':profile['source_normalization'],'source_pins':profile['source_pins'],'frozen_source_files':source,'proposal_doc':profile['proposal_doc'],'proposal_sha256':H,'approved_scope_sha256':H,'limits':execute.LIMITS,'new_conservative_upper':execute.UPPER,'approved_model_slots':6,'effective_model_http':6,'json_repair_http':0,'per_model_reserve_usd':'0.100','model_total_usd':'0.600','model_estimate_book_upper_usd':'3.355473652','dify_estimate_usd':'0.100','combined_estimate_usd':'0.700','billing_hard_cap':False,'wall_seconds':3600,'task_start_cap':12,'task_minutes':45,'runtime_build':profile['runtime_build'],'runtime_version':profile['runtime_version'],'runtime_file_count':298,'runtime_pid':28732,'runtime_manifest_sha256':H,'runtime_process_sha256':H,'backend_path':str(execute.PROJECT/'.runtime/snapshots'/profile['runtime_build']/'backend'),'provider_id':profile['provider_id'],'provider_sha256':H,'environment_id':profile['environment_id'],'protected_data':{'objects':{},'secrets':{},'files':{}},'isolated_paths':profile['isolated_paths'],'protected_isolated':{k:{} for k in profile['isolated_paths']},'protected_files':{'work/sealed-'+str(i)+'.json':H for i in range(795)},'protected_old_count':733,'protected_337_count':24,'protected_total_count':795,'sealed_index_sha256':profile['sealed_index_sha256'],'protected_seals':profile['protected_seals'],'known_apps':[]}

def authorization(profile):
    return {'authorization_source':'direct_user_reply','scope':execute.BATCH,'decision':'approve','reply':profile['approval_phrase'],'question_ref':'call_'+'0'*32+'/q0','plan_sha256':PLAN_SHA,'manifest_sha256':MANIFEST_SHA,'limits':execute.LIMITS,'approved_model_slots':6,'effective_model_http':6,'json_repair_http':0}

def checks():
    passed=0;trace=[]
    profile=prepare.load_profile();prepare.validate_profile(profile);passed+=1;trace.append('profile_exact')
    bad=copy.deepcopy(profile);bad['limits']['model']=True;rejected(lambda:prepare.validate_profile(bad),'limits must be exact ints');passed+=1
    bad=copy.deepcopy(profile);bad['approved_model_slots']=6.0;rejected(lambda:prepare.validate_profile(bad),'approved_model_slots must be int');passed+=1;trace.append('strict_profile_ints')
    require(len(execute.NAMES)==21 and len(profile['source_pins'])==15,'Frozen file counts changed');passed+=1;trace.append('counts_21_15')
    require(set(execute.NAMES)==prepare.NAMES and set(profile['source_pins'])==prepare.PINS,'Prepared file sets changed');passed+=1;trace.append('names_match')
    base=prepare.PROJECT/profile['source_dir'];verified=prepare._verified_sources(prepare.PROJECT,profile);require(set(verified)==prepare.PINS and len(verified)==15,'Verified source helper mismatch');passed+=1
    require(prepare._normalize_source(b'a\r\nb')==b'a\nb','CRLF normalization changed');passed+=1
    for name,value in profile['source_pins'].items():
        raw=(base/name).read_bytes();norm=prepare._normalize_source(raw);require(prepare.sha_bytes(norm)==value,'Pinned source changed: '+name);passed+=1
        derived=prepare.derive(name,norm)
        if name=='common.py':require(b'autonomous-dual337' not in derived and b"BATCH_ID='autonomous-dual371'" in derived,'Common replacement wrong')
        elif name=='worker.py':require(b"'approved_model_slots':8" not in derived and b"'approved_model_slots':6" in derived,'Worker replacement wrong')
        else:require(derived==norm,'Unapproved source rewrite: '+name)
    old=b"BATCH_ID='autonomous-dual337'"
    rejected(lambda:prepare._replace_once(b'nothing',old,b"BATCH_ID='autonomous-dual371'",'test'),'replacement count 0')
    rejected(lambda:prepare._replace_once(old+old,old,b"BATCH_ID='autonomous-dual371'",'test'),'replacement count 2')
    passed+=1;trace.append('derive_exact_once')
    p=plan(profile);execute.validate_plan(p,profile);passed+=1;trace.append('plan_valid')
    for key,value,text in (('limits',{'new_tasks':2},'limits fields changed'),('new_conservative_upper',{'reads':1725},'new_conservative_upper fields changed'),('approved_model_slots',8,'Plan limits changed'),('approved_model_slots',True,'approved_model_slots must be int'),('effective_model_http',5,'Plan limits changed'),('json_repair_http',1,'Plan limits changed'),('model_estimate_book_upper_usd','0.600','Plan cost changed'),('billing_hard_cap',True,'Plan cost changed'),('runtime_build','0.410.0-other','Plan runtime changed'),('runtime_pid',28732.0,'runtime_pid must be int'),('runtime_file_count',298.0,'runtime_file_count must be int'),('source_commit_base','e'*40,'Plan source commit changed'),('source_normalization','other','Plan source commit changed'),('protected_total_count',794,'Plan protection counts changed'),('protected_old_count',733.0,'protected_old_count must be int'),('schema_version',True,'schema_version must be int'),('protected_seals',{},'Plan protected captures changed')):
        bad=copy.deepcopy(p);bad[key]=value;rejected(lambda bad=bad:execute.validate_plan(bad,profile),text);passed+=1
    trace.append('plan_tamper_rejected')
    a=authorization(profile);execute.validate_authorization(a,p,PLAN_SHA,MANIFEST_SHA,profile);passed+=1;trace.append('authorization_valid')
    mixed=copy.deepcopy(a);mixed['question_ref']='call_New_ID-1/q0';execute.validate_authorization(mixed,p,PLAN_SHA,MANIFEST_SHA,profile);passed+=1
    for oldref in execute.OLD_REFS:
        bad=copy.deepcopy(a);bad['question_ref']=oldref;rejected(lambda bad=bad:execute.validate_authorization(bad,p,PLAN_SHA,MANIFEST_SHA,profile),'New question_ref required');passed+=1
    for key,value,text in (('reply','允许独立366完整新范围','Direct new scope approval missing'),('scope','autonomous-dual366','Direct new scope approval missing'),('approved_model_slots',8,'Approval limits/slots changed'),('approved_model_slots',True,'approved_model_slots must be int'),('effective_model_http',5,'Approval limits/slots changed'),('json_repair_http',1,'Approval limits/slots changed'),('limits',{'model':True},'approval limits fields changed'),('limits',dict(execute.LIMITS,model=6.0),'approval limits must be exact ints'),('plan_sha256','f'*64,'Approval not bound to frozen package'),('manifest_sha256','f'*64,'Approval not bound to frozen package')):
        bad=copy.deepcopy(a);bad[key]=value;rejected(lambda bad=bad:execute.validate_authorization(bad,p,PLAN_SHA,MANIFEST_SHA,profile),text);passed+=1
    bad=copy.deepcopy(a);del bad['question_ref'];rejected(lambda:execute.validate_authorization(bad,p,PLAN_SHA,MANIFEST_SHA,profile),'Approval fields missing');passed+=1
    trace.append('authorization_tamper_rejected')
    rejected(lambda:execute._canonical(HERE),'Canonical nonoptimized root required');passed+=1
    rejected(lambda:execute._canonical(execute.PROJECT/'work'/'autonomous-dual337'),'Canonical nonoptimized root required');passed+=1;trace.append('wrong_paths_rejected')
    if execute.PROJECT!=Path(r'E:\workSpace\dify-agent'):
        rejected(lambda:execute._canonical(execute.PROJECT/'work'/execute.BATCH),'Original project only');passed+=1;trace.append('clone_project_rejected')
    with tempfile.TemporaryDirectory(dir=execute.PROJECT/'work',prefix='autonomous-dual371-seal-') as tmp:
        root=Path(tmp);batch=root/'batch';batch.mkdir();(root/'README.md').write_bytes(b'project-readme');(batch/'README.md').write_bytes(b'batch-readme')
        resolved=prepare._batch_sealed(batch.resolve(),'README.md',prepare.sha_bytes(b'batch-readme'));require(resolved==(batch/'README.md').resolve(),'Batch seal resolved outside batch');passed+=1
        rejected(lambda:prepare._batch_sealed(batch.resolve(),'README.md',prepare.sha_bytes(b'project-readme')),'Sealed evidence changed');passed+=1
        rejected(lambda:prepare._batch_sealed(batch.resolve(),'../outside',prepare.sha_bytes(b'batch-readme')),'Sealed path escaped');passed+=1
        rejected(lambda:prepare._batch_sealed(batch.resolve(),str(batch/'README.md'),prepare.sha_bytes(b'batch-readme')),'Sealed path absolute');passed+=1
    trace.append('sealed_batch_relative')
    with tempfile.TemporaryDirectory(dir=execute.PROJECT/'work',prefix='autonomous-dual371-group-') as tmp:
        root=Path(tmp).resolve();batch=root/'work'/'batch';batch.mkdir(parents=True);(root/'README.md').write_bytes(b'project');(batch/'README.md').write_bytes(b'batch')
        index={'README.md':prepare.sha_bytes(b'batch')};(batch/'seal.json').write_text(json.dumps(index),'utf-8')
        spec={'path':'work/batch/seal.json','sha256':prepare.sha(batch/'seal.json'),'entries':1};group=prepare._seal_group(root,spec)
        require(len(group)==2 and 'work/batch/README.md' in group and 'work/batch/seal.json' in group,'Seal group index binding changed');passed+=1
    trace.append('seal_group_index')
    base_count=profile['protected_old_count']+profile['protected_337_count']+1;added=sum(spec['entries']+1 for spec in profile['protected_seals'].values());require(base_count==758 and added==37 and base_count+added==profile['protected_total_count']==795,'Protected total arithmetic changed');passed+=1;trace.append('protected_795_counts')
    good={'state':'stopped','dispatch_counts':dict(OLD366_COUNTS),'physical_http':1};prepare._old366_not_dispatched(good,'dispatch_counts');passed+=1
    bad=copy.deepcopy(good);bad['dispatch_counts']['model']=1;rejected(lambda:prepare._old366_not_dispatched(bad,'dispatch_counts'),'Old 366 was dispatched');passed+=1
    bad=copy.deepcopy(good);bad['task_id']='task';rejected(lambda:prepare._old366_not_dispatched(bad,'dispatch_counts'),'Old 366 scope changed');passed+=1
    with tempfile.TemporaryDirectory(dir=execute.PROJECT/'work',prefix='autonomous-dual371-old366-') as tmp:
        root=Path(tmp).resolve();batch=root/'work'/'batch';(batch/'live-output').mkdir(parents=True)
        progress=batch/'live-output'/'progress.json';attempt=batch/'attempt.json'
        progress.write_text(json.dumps({'state':'stopped','dispatch_counts':dict(OLD366_COUNTS),'physical_http':1}),'utf-8')
        attempt.write_text(json.dumps({'state':'stopped','counts':dict(OLD366_COUNTS),'physical_http':1}),'utf-8')
        files={'work/batch/live-output/progress.json':prepare.sha(progress),'work/batch/attempt.json':prepare.sha(attempt)}
        prepare._old366_gate(root,batch,files);passed+=1
        progress.write_text(json.dumps({'state':'stopped','dispatch_counts':dict(OLD366_COUNTS,model=1),'physical_http':1}),'utf-8');files['work/batch/live-output/progress.json']=prepare.sha(progress)
        rejected(lambda:prepare._old366_gate(root,batch,files),'Old 366 was dispatched');passed+=1
        progress.write_text(json.dumps({'state':'stopped','dispatch_counts':dict(OLD366_COUNTS),'physical_http':1}),'utf-8');files['work/batch/live-output/progress.json']=prepare.sha(progress)
        attempt.write_text(json.dumps({'state':'stopped','counts':dict(OLD366_COUNTS,reads=1),'physical_http':1}),'utf-8');files['work/batch/attempt.json']=prepare.sha(attempt)
        rejected(lambda:prepare._old366_gate(root,batch,files),'Old 366 was dispatched');passed+=1
    trace.append('old366_gate')
    with tempfile.TemporaryDirectory(dir=execute.PROJECT/'work',prefix='autonomous-dual371-checks-') as tmp:
        root=Path(tmp);execute.assert_unconsumed(root,include_approval=True);passed+=1
        (root/'attempt.json').write_text('{}','utf-8');rejected(lambda:execute.assert_unconsumed(root),'Consumed package cannot replay');passed+=1
        (root/'attempt.json').unlink();(root/'worker-started.json').write_text('{}','utf-8');rejected(lambda:execute.assert_unconsumed(root),'Consumed package cannot replay');passed+=1
        (root/'worker-started.json').unlink();(root/'approval.json').write_text('{}','utf-8');rejected(lambda:execute.assert_unconsumed(root,include_approval=True),'Consumed package cannot replay');passed+=1
    trace.append('replay_markers_rejected')
    for name in ('approval.json','attempt.json','worker-started.json'):
        require(not (HERE/name).exists(),'Canonical marker in source directory: '+name)
    passed+=1;trace.append('no_canonical_markers')
    print(json.dumps({'state':'passed','checks':passed,'cases':trace,'physical_http':0,'secret_reads':0,'canonical_markers':0},ensure_ascii=False))
if __name__=='__main__':checks()
