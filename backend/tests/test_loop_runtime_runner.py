"""Exercise the fixed live runner against an isolated in-memory remote, no networking."""
import asyncio,sys,copy,hashlib,importlib.util,json,shutil,uuid
from pathlib import Path
import pytest,yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.storage import Store
from app.dify import DifyError


@pytest.fixture
def runner(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[2];spec=importlib.util.spec_from_file_location('isolated_loop_runtime_runner',root/'work/loop-runtime-live.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    pack=tmp_path/'work/loop-validation-pack';shutil.copytree(root/'work/loop-validation-pack',pack);monkeypatch.setattr(mod,'ROOT',tmp_path);monkeypatch.setattr(mod,'PACK',pack);monkeypatch.setattr(mod,'FILE',tmp_path/'work/result.json')
    store=Store(tmp_path/'data');store.put('environment',mod.ENV,{'id':mod.ENV,'base_url':'http://127.0.0.1:8080','version':'1.17.1','name':'isolated fixture'});store.set_secret(mod.ENV,'console_token','private-admin-key-for-test');store.set_secret(mod.ENV,'csrf_token','private-csrf-for-test')
    env={'apps':{},'calls':[],'auth_failure':False,'unknown_import':False,'failed_import':False,'wrong_output':False}
    manifest=json.loads((pack/'manifest.json').read_text(encoding='utf-8'));case_by_name={c['app_name']:c for c in manifest['cases']}
    class Fake:
        def __init__(self,environment,storage):self.env=environment;self.store=storage
        async def test(self):
            env['calls'].append(('GET','preflight',None))
            if env['auth_failure']:raise DifyError('HTTP401',http_status=401)
            return {'data':[]}
        async def import_new(self,content,name):
            env['calls'].append(('POST','import',name))
            if env['unknown_import']:raise DifyError('超时，结果可能未知')
            if env['failed_import']:return {'status':'failed'}
            app=str(uuid.uuid4());doc=json.loads(json.dumps(yaml.safe_load(content)));env['apps'][app]={'id':app,'name':name,'document':doc,'published':False,'key':None};return {'app_id':app,'status':'completed'}
        async def export_dsl(self,app):return yaml.safe_dump(env['apps'][app]['document'])
        async def request(self,method,path,**kwargs):
            env['calls'].append((method,path,kwargs.get('json')))
            if path=='/console/api/apps':return {'data':[{'id':a['id'],'name':a['name']} for a in env['apps'].values()],'has_more':False}
            if path=='/v1/workflows/run':
                app=self.env['service_app_id'];a=env['apps'][app];case=case_by_name[a['name']];a['run_id']=str(uuid.uuid4());out=copy.deepcopy(case['expected_output']) or {};a['case']=case['case'];a['status']=case['expected_status']
                if env['wrong_output']:out={'count':99}
                return {'workflow_run_id':a['run_id'],'data':{'id':a['run_id'],'status':a['status'],'outputs':out,'error':'known technical error' if a['status']=='failed' else ''}}
            app=path.split('/apps/')[1].split('/')[0];a=env['apps'][app]
            if path.endswith('/workflows/publish'):
                if method=='POST':a['published']=True;return {'result':'success'}
                return {'id':str(uuid.UUID(app)),'graph':a['document']['workflow']['graph']} if a['published'] else None
            if path.endswith('/api-keys'):
                if method=='POST':a['key']='private-service-'+app;return {'token':a['key']}
                return {'data':[{'token':a['key']}] if a['key'] else []}
            if path.endswith('/node-executions'):
                cid=a['case'];rows=[{'id':str(uuid.uuid4()),'node_id':'increment','node_type':'code','status':'failed' if cid=='invalid-update-type' else 'succeeded','error':'type failure' if cid=='invalid-update-type' else None,'inputs':{'count':v}} for v in mod.BODY_INPUTS[cid]]
                if cid in {'limit-unmet','no-progress'}:rows.append({'id':str(uuid.uuid4()),'node_id':'repeat__loop_limit' if cid=='limit-unmet' else 'repeat__loop_progress','node_type':'code','status':'failed','error':'known protection failure'})
                return {'data':rows}
            if '/workflow-runs/' in path:return {'id':a['run_id'],'status':a['status'],'graph':a['document']['workflow']['graph']}
            raise AssertionError('unapproved fake path '+path)
    monkeypatch.setattr(mod,'DifyClient',Fake)
    return mod,store,env,manifest


def test_six_cases_complete_against_controlled_remote_without_modifying_user_store(runner):
    mod,store,remote,manifest=runner;before=store.list('environment');asyncio.run(mod.execute());r=json.loads(mod.FILE.read_text(encoding='utf-8'))
    assert r['status']=='passed' and len(r['cases'])==6 and all(c['verified'] and c['run_attempts']==1 for c in r['cases'].values())
    assert len([c for c in remote['calls'] if c[1]=='import'])==6 and len([c for c in remote['calls'] if c[1]=='/v1/workflows/run'])==6
    assert store.list('environment')==before and not store.list('task')
    assert 'private-service-' not in mod.FILE.read_text(encoding='utf-8') and 'private-admin-key' not in mod.FILE.read_text(encoding='utf-8')
    writes=len([c for c in remote['calls'] if c[0]=='POST']);asyncio.run(mod.execute());assert len([c for c in remote['calls'] if c[0]=='POST'])==writes


def test_supplemental_console_source_same_instance_never_copies_or_changes_credentials(runner):
    mod,store,remote,manifest=runner
    source={'id':mod.ALTERNATE_CONSOLE,'name':'same instance source','base_url':'http://127.0.0.1:8080','version':'1.17.1'}
    store.put('environment',mod.ALTERNATE_CONSOLE,source);store.set_secret(mod.ALTERNATE_CONSOLE,'console_token','alternate-private-admin')
    before=store.list('environment');old_key=store.secret(mod.ENV,'console_token')
    asyncio.run(mod.execute(mod.ALTERNATE_CONSOLE));record=json.loads(mod.FILE.read_text(encoding='utf-8'))
    assert record['status']=='passed' and record['environment_id']==mod.ENV and record['console_source_id']==mod.ALTERNATE_CONSOLE
    assert store.list('environment')==before and store.secret(mod.ENV,'console_token')==old_key
    with pytest.raises(ValueError,match='不能切换'):asyncio.run(mod.execute())


def test_supplemental_source_cannot_point_to_other_instance_or_arbitrary_owner(runner):
    mod,store,remote,manifest=runner
    store.put('environment',mod.ALTERNATE_CONSOLE,{'id':mod.ALTERNATE_CONSOLE,'base_url':'http://different.test','version':'1.17.1'})
    with pytest.raises(ValueError,match='不一致'):asyncio.run(mod.execute(mod.ALTERNATE_CONSOLE))
    with pytest.raises(ValueError,match='未批准'):asyncio.run(mod.execute(str(uuid.uuid4())))
    assert not remote['calls']


def test_all_publish_labels_fit_native_limit_without_changing_approved_app_names(runner):
    mod,store,remote,manifest=runner
    assert all(1<=len(mod.publish_metadata(i)['marked_name'])<=20 for i in range(6))
    asyncio.run(mod.execute())
    assert {app['name'] for app in remote['apps'].values()}=={c['app_name'] for c in manifest['cases']}


def test_known_rejected_publish_is_skipped_not_retried_and_other_approved_cases_continue(runner):
    mod,store,remote,manifest=runner;mod.save({'authorization':'user_approved_six_case_resource_plan_2026_10_12','environment_id':mod.ENV,'cases':{'initial-goal':{'sha256':next(c['sha256'] for c in manifest['cases'] if c['case']=='initial-goal'),'app_name':'Sierra Loop Validation initial-goal','run_attempts':0,'publish_attempts':1,'blocked_known_publish_rejection':True}},'pending':None})
    asyncio.run(mod.execute());record=json.loads(mod.FILE.read_text(encoding='utf-8'))
    assert record['status']=='partial_not_verified' and record['cases']['initial-goal']['run_attempts']==0
    assert len([c for c in remote['calls'] if c[1]=='import'])==5 and len([c for c in remote['calls'] if c[1]=='/v1/workflows/run'])==5


def test_explicit_additional_publish_bound_to_one_existing_app_never_reimports_or_reruns(runner,monkeypatch):
    mod,store,remote,manifest=runner
    asyncio.run(mod.execute());record=json.loads(mod.FILE.read_text(encoding='utf-8'));entry=record['cases']['initial-goal'];app=entry['app_id']
    monkeypatch.setattr(mod,'INITIAL_GOAL_RETRY_APP',app)
    entry.update(blocked_known_publish_rejection=True,published=False,publish_attempts=1,run_attempts=0,publish_rejection_proof={'http_status':422})
    entry.pop('verified');entry.pop('publication_response_received');mod.save(record)
    imports=len([c for c in remote['calls'] if c[1]=='import']);runs=len([c for c in remote['calls'] if c[1]=='/v1/workflows/run'])
    asyncio.run(mod.execute(retry_initial_goal_publish=True));record=json.loads(mod.FILE.read_text(encoding='utf-8'))
    assert record['status']=='passed' and record['cases']['initial-goal']['publish_attempts']==2
    assert len([c for c in remote['calls'] if c[1]=='import'])==imports and len([c for c in remote['calls'] if c[1]=='/v1/workflows/run'])==runs+1
    calls=len(remote['calls']);asyncio.run(mod.execute(retry_initial_goal_publish=True));assert len([c for c in remote['calls'][calls:] if c[0]=='POST'])==0


def test_auth_failure_keeps_valid_zero_write_ledger_for_explicit_resume(runner):
    mod,store,remote,manifest=runner;remote['auth_failure']=True
    with pytest.raises(DifyError):asyncio.run(mod.execute())
    r=json.loads(mod.FILE.read_text(encoding='utf-8'));assert r['environment_id']==mod.ENV and not r['cases'] and not r['pending']
    assert not any(method=='POST' for method,_,_ in remote['calls']);remote['auth_failure']=False;asyncio.run(mod.execute())
    assert json.loads(mod.FILE.read_text(encoding='utf-8'))['status']=='passed'


def test_unknown_import_never_automatically_recreated(runner):
    mod,store,remote,manifest=runner;remote['unknown_import']=True
    with pytest.raises(DifyError):asyncio.run(mod.execute())
    r=json.loads(mod.FILE.read_text(encoding='utf-8'));assert r['pending']['kind']=='import'
    remote['unknown_import']=False
    with pytest.raises(ValueError,match='未知'):asyncio.run(mod.execute())
    assert len([c for c in remote['calls'] if c[1]=='import'])==1


def test_known_failed_import_not_automatically_retried(runner):
    mod,store,remote,manifest=runner;remote['failed_import']=True
    with pytest.raises(ValueError):asyncio.run(mod.execute())
    remote['failed_import']=False
    with pytest.raises(ValueError,match='已有导入派发'):asyncio.run(mod.execute())
    assert len([c for c in remote['calls'] if c[1]=='import'])==1


def test_wrong_output_is_recorded_not_expected_result_relaxed_or_rerun(runner):
    mod,store,remote,manifest=runner;remote['wrong_output']=True
    with pytest.raises(ValueError):asyncio.run(mod.execute())
    r=json.loads(mod.FILE.read_text(encoding='utf-8'));assert not r['cases']['normal']['verified'] and r['cases']['normal']['outputs']=={'count':99}
    remote['wrong_output']=False
    with pytest.raises(ValueError,match='一次派发'):asyncio.run(mod.execute())
    assert len([c for c in remote['calls'] if c[1]=='/v1/workflows/run'])==1


def test_changed_manifest_even_with_new_matching_file_hash_is_not_new_authorization(runner):
    mod,store,remote,manifest=runner;case=manifest['cases'][0];path=mod.PACK/case['file'];path.write_text(path.read_text(encoding='utf-8')+'\n# new content',encoding='utf-8');case['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();(mod.PACK/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='整份manifest'):asyncio.run(mod.execute())
    assert not remote['calls']


def test_preexisting_approved_name_does_not_become_app_reuse_permission(runner):
    mod,store,remote,manifest=runner;app=str(uuid.uuid4());remote['apps'][app]={'id':app,'name':manifest['cases'][0]['app_name']}
    with pytest.raises(ValueError,match='既有'):asyncio.run(mod.execute())
    assert not any(method=='POST' for method,_,_ in remote['calls'])
