import asyncio,importlib.util,json,shutil,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,yaml
from app.storage import Store
from app.dify import DifyError


@pytest.fixture
def runner(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[2];spec=importlib.util.spec_from_file_location('isolated_loop_branch_runner',root/'work/loop-branch-runtime-live.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    (tmp_path/'work').mkdir();shutil.copy(root/'work/loop-branch-runtime.yaml',tmp_path/'work/loop-branch-runtime.yaml');monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'FILE',tmp_path/'work/result.json')
    store=Store(tmp_path/'data');store.put('environment',m.SOURCE,{'id':m.SOURCE,'base_url':'http://127.0.0.1:8080','version':'1.17.1'});store.set_secret(m.SOURCE,'console_token','private-test-admin')
    remote={'calls':[],'app':None,'document':None,'run':None,'query':None,'key':None,'unknown_import':False,'wrong_output':False}
    class Fake:
        def __init__(self,env,store):self.env=env
        async def test(self):return {}
        async def import_new(self,text,name):
            remote['calls'].append(('POST','import'))
            if remote['unknown_import']:raise DifyError('timeout unknown')
            remote['app']=str(uuid.uuid4());remote['document']=text;return {'app_id':remote['app'],'status':'completed'}
        async def export_dsl(self,app):assert app==remote['app'];return remote['document']
        async def request(self,method,path,**kw):
            remote['calls'].append((method,path))
            if path=='/console/api/apps':return {'data':[{'id':remote['app'],'name':m.NAME}] if remote['app'] else [],'has_more':False}
            if path.endswith('/workflows/publish'):return {'id':str(uuid.uuid4()),'graph':yaml.safe_load(remote['document'])['workflow']['graph']}
            if path.endswith('/api-keys'):
                if method=='POST':remote['key']='private-test-service';return {'token':remote['key']}
                return {'data':[{'token':remote['key']}] if remote['key'] else []}
            if path=='/v1/workflows/run':
                remote['run']=str(uuid.uuid4());remote['query']=kw['json']['inputs']['query'];return {'workflow_run_id':remote['run'],'data':{'id':remote['run'],'status':'succeeded','outputs':{'count':4 if remote['wrong_output'] else 3}}}
            if path.endswith('/node-executions'):
                rows=[{'id':str(uuid.uuid4()),'node_id':'large','node_type':'code','status':'succeeded','inputs':{'count':1}}]
                if remote['query']=='0':rows.insert(0,{'id':str(uuid.uuid4()),'node_id':'small','node_type':'code','status':'succeeded','inputs':{'count':0}})
                return {'data':rows}
            if '/workflow-runs/' in path:return {'id':remote['run'],'status':'succeeded','graph':yaml.safe_load(remote['document'])['workflow']['graph']}
            raise AssertionError('unapproved path')
    monkeypatch.setattr(m,'DifyClient',Fake);return m,store,remote


def test_fixed_branch_app_two_inputs_complete_without_reimport_or_rerun(runner):
    m,store,remote=runner;before=store.list('environment');asyncio.run(m.execute());r=json.loads(m.FILE.read_text(encoding='utf-8'))
    assert r['status']=='passed' and len(r['runs'])==2 and all(v['attempts']==1 and v['verified'] for v in r['runs'].values())
    assert len([call for call in remote['calls'] if call==('POST','import')])==1
    assert len([call for call in remote['calls'] if call==('POST','/v1/workflows/run')])==2
    assert store.list('environment')==before and 'private-test' not in m.FILE.read_text(encoding='utf-8')
    count=len(remote['calls']);asyncio.run(m.execute());assert not any(method=='POST' for method,_ in remote['calls'][count:])


def test_unknown_import_cannot_automatically_recreate(runner):
    m,store,remote=runner;remote['unknown_import']=True
    with pytest.raises(DifyError):asyncio.run(m.execute())
    assert json.loads(m.FILE.read_text(encoding='utf-8'))['pending']=='import'
    count=len(remote['calls'])
    with pytest.raises(ValueError,match='未知'):asyncio.run(m.execute())
    assert len(remote['calls'])==count


def test_wrong_result_stops_before_second_case_and_never_relaxes_or_retries(runner):
    m,store,remote=runner;remote['wrong_output']=True
    with pytest.raises(ValueError,match='不放宽'):asyncio.run(m.execute())
    r=json.loads(m.FILE.read_text(encoding='utf-8'));assert r['runs']['0']['attempts']==1 and not r['runs']['0']['verified'] and '1' not in r['runs']
    with pytest.raises(ValueError,match='不能重跑'):asyncio.run(m.execute())
    assert len([call for call in remote['calls'] if call==('POST','/v1/workflows/run')])==1
