import asyncio
import copy
import hashlib
import json
import uuid
from datetime import datetime,timezone,timedelta
import pytest
import httpx
from test_api import client,create,create_env
from app import main
from app.dify import DifyClient,DifyError
from app.storage import Store

WORKSPACE=str(uuid.uuid4());DATASET=str(uuid.uuid4());DOCUMENT=str(uuid.uuid4())

@pytest.fixture(autouse=True)
def forbid_knowledge_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('知识资料隔离检查不得访问真实 HTTP 或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)

@pytest.fixture
def adapter(monkeypatch):
    state={'writes':[],'indexing_status':'completed','completed_segments':1,'total_segments':1,'workspace_id':WORKSPACE,'model_active':True}
    async def workspace(self):return {'id':state['workspace_id'],'name':'测试空间'}
    async def models(self,kind):return {'data':[{'provider':'langgenius/embed/embed','models':[{'model':'embedding-exact','status':'active' if state['model_active'] else 'disabled','model_properties':{}}]}]}
    async def create_dataset(self,name,description,strategy,**kwargs):state['writes'].append('dataset');return {'id':DATASET}
    async def create_key(self,dataset,**kwargs):
        assert dataset==DATASET;state['writes'].append('key');return {'token':'dataset-private-unit-key'}
    async def create_doc(self,dataset,doc,strategy,owner,**kwargs):
        assert self.store.secret(owner,'dataset_api_key')=='dataset-private-unit-key';assert dataset==DATASET
        state['writes'].append('document');state['last_text']=doc['text'];state['strategy']=strategy;state['embedding']=kwargs.get('embedding_model');return {'document':{'id':DOCUMENT},'batch':'batch'}
    async def status(self,dataset,document):return {'id':document,'indexing_status':state['indexing_status'],'completed_segments':state['completed_segments'],'total_segments':state['total_segments']}
    for name,fn in [('workspace',workspace),('models',models),('create_dataset',create_dataset),('create_scoped_dataset_key',create_key),('create_text_document',create_doc),('document_status',status)]:monkeypatch.setattr(DifyClient,name,fn)
    return state

def task_with_env(client):
    env=create_env(client);client.patch('/api/environments/'+env['id'],json={'service_app_id':'old-app','service_api_key':'old-runtime','dataset_api_key':'old-dataset'})
    return create(client,env_id=env['id']),env

def propose(client,task,**changes):
    body={'revision':task['revision'],'name':'测试资料库','purpose':'开发联调知识库准备，核对已授权资料范围。','description':'技术样例','indexing_technique':'economy','text':'  退货规则：7 天。\n完整原文  ','document_name':'政策说明',**changes}
    return client.post(f"/api/tasks/{task['id']}/knowledge-jobs",json=body)

def approved_job(client,task,**changes):
    response=propose(client,task,**changes);assert response.status_code==201,response.text
    job=response.json();r=client.post(f"/api/knowledge-jobs/{job['id']}/confirm",json={'task_revision':task['revision'],'accept_unknown_embedding_cost':changes.get('indexing_technique')=='high_quality'});assert r.status_code==200,r.text
    return r.json()


def test_no_writes_before_explicit_confirmation_and_start(client,adapter):
    task,env=task_with_env(client);r=propose(client,task);assert r.status_code==201,r.text
    job=r.json();assert job['status']=='draft' and job['workspace']['id']==WORKSPACE and adapter['writes']==[]
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={}).status_code==409
    assert adapter['writes']==[] and main.get_task(task['id'])['revision']==task['revision']
    assert client.post(f"/api/knowledge-jobs/{job['id']}/confirm",json={'task_revision':True}).status_code==409


def test_ready_is_real_index_completion_and_apply_advances_revision(client,adapter):
    task,env=task_with_env(client);job=approved_job(client,task)
    r=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={});assert r.status_code==200,r.text
    ready=r.json();assert ready['status']=='ready' and ready['dataset_id']==DATASET and ready['has_dataset_key']
    assert adapter['writes']==['dataset','key','document'] and adapter['last_text']=='  退货规则：7 天。\n完整原文  '
    assert main.store.secret(env['id'],'dataset_api_key')=='old-dataset' and main.store.secret(env['id'],'service_api_key')=='old-runtime'
    assert 'dataset-private-unit-key' not in r.text and b'dataset-private-unit-key' not in main.store.path.read_bytes()
    assert main.get_task(task['id'])['configuration']['dataset_ids']==[]
    applied=client.post(f"/api/knowledge-jobs/{job['id']}/apply",json={'revision':task['revision']})
    assert applied.status_code==200,applied.text
    assert applied.json()['revision']==task['revision']+1 and applied.json()['configuration']['dataset_ids']==[DATASET]
    assert not applied.json()['configuration_confirmed']
    assert main.store.get('knowledge_job',job['id'])['applied_revision']==applied.json()['revision']
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={}).status_code==409


@pytest.mark.parametrize('remote_status,segments,total,expected',[('waiting',0,0,'indexing'),('splitting',0,0,'indexing'),('completed',0,0,'needs_input'),('completed',True,1,'needs_input'),('completed',1,None,'needs_input'),('error',0,0,'needs_input'),('future-state',0,0,'needs_input')])
def test_submission_or_invalid_counts_never_ready(client,adapter,remote_status,segments,total,expected):
    task,_=task_with_env(client);job=approved_job(client,task);adapter.update(indexing_status=remote_status,completed_segments=segments,total_segments=total)
    result=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert result.status_code==200,result.text
    assert result.json()['status']==expected
    assert client.post(f"/api/knowledge-jobs/{job['id']}/apply",json={'revision':task['revision']}).status_code==409


def test_revision_change_invalidates_proposal(client,adapter):
    task,_=task_with_env(client);job=propose(client,task).json();client.patch('/api/tasks/'+task['id'],json={'name':'改名'})
    assert client.post(f"/api/knowledge-jobs/{job['id']}/confirm",json={'task_revision':task['revision']}).status_code==409
    assert adapter['writes']==[]


def test_workspace_change_pauses_before_first_write(client,adapter):
    task,_=task_with_env(client);job=approved_job(client,task);adapter['workspace_id']=str(uuid.uuid4())
    result=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert result.json()['status']=='paused' and '工作空间' in result.json()['message'] and adapter['writes']==[]


def test_high_quality_requires_actual_model_and_explicit_unknown_cost_acceptance(client,adapter):
    task,_=task_with_env(client)
    assert propose(client,task,indexing_technique='high_quality').status_code==422
    response=propose(client,task,indexing_technique='high_quality',embedding_provider='langgenius/embed/embed',embedding_model='embedding-exact');assert response.status_code==201,response.text
    job=response.json()
    assert client.post(f"/api/knowledge-jobs/{job['id']}/confirm",json={'task_revision':task['revision']}).status_code==422
    assert client.post(f"/api/knowledge-jobs/{job['id']}/confirm",json={'task_revision':task['revision'],'accept_unknown_embedding_cost':True}).status_code==200
    result=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={});assert result.json()['status']=='ready'
    assert adapter['strategy']=='high_quality' and adapter['embedding']=='embedding-exact'


def test_no_silent_economy_embedding_ignore(client,adapter):
    task,_=task_with_env(client)
    result=propose(client,task,embedding_model='unwanted')
    assert result.status_code==422 and '不自动忽略' in result.text and adapter['writes']==[]


def test_unreadable_or_oversized_documents_not_truncated(client,adapter):
    task,_=task_with_env(client)
    assert propose(client,task,text='x'*100001).status_code==422
    assert propose(client,task,text='',material_ids=['missing']).status_code==422
    assert propose(client,task,text='',material_ids=[{}]).status_code==422
    assert adapter['writes']==[]


def test_source_material_is_snapshotted_whole(client,adapter):
    task,_=task_with_env(client);current=main.get_task(task['id']);current['materials']=[{'id':'material','name':'文档.txt','status':'parsed','text':'完整资料\n'*4000}];main.save_task(current)
    result=propose(client,task,text='',material_ids=['material'])
    assert result.status_code==201,result.text
    doc=result.json()['documents'][0];assert doc['text']=='完整资料\n'*4000 and doc['characters']==20000


@pytest.mark.parametrize('http_status',[None,400,500])
def test_unknown_write_is_durable_and_not_blindly_repeated(client,adapter,monkeypatch,http_status):
    task,_=task_with_env(client);job=approved_job(client,task)
    async def fail(*args,**kwargs):raise DifyError('外部结果未确认。',http_status=http_status)
    monkeypatch.setattr(DifyClient,'create_dataset',fail)
    result=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={});assert result.json()['status']=='unknown'
    assert main.store.get('knowledge_job',job['id'])['operations'][0]['status']=='unknown'
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={}).status_code==409
    assert propose(client,task).status_code==409


def test_known_auth_rejection_can_resume_after_user_start(client,adapter,monkeypatch):
    task,_=task_with_env(client);job=approved_job(client,task);original=DifyClient.create_dataset
    async def denied(*args,**kwargs):raise DifyError('HTTP 401',http_status=401)
    monkeypatch.setattr(DifyClient,'create_dataset',denied)
    result=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={});assert result.json()['status']=='paused' and result.json()['operations'][-1]['status']=='rejected'
    monkeypatch.setattr(DifyClient,'create_dataset',original)
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={}).json()['status']=='ready'


def test_pause_in_flight_retains_result_blocks_next_write_and_mutations(client,adapter,monkeypatch):
    task,env=task_with_env(client);job=approved_job(client,task)
    async def paused(self,*args,**kwargs):
        assert (await asyncio.to_thread(client.post,f"/api/knowledge-jobs/{job['id']}/pause")).status_code==200
        assert (await asyncio.to_thread(client.patch,'/api/tasks/'+task['id'],json={'name':'不应修改'})).status_code==409
        assert (await asyncio.to_thread(client.patch,'/api/environments/'+env['id'],json={'name':'不应修改'})).status_code==409
        return {'id':DATASET}
    monkeypatch.setattr(DifyClient,'create_dataset',paused)
    response=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert response.status_code==200,response.text
    assert response.json()['status']=='paused' and response.json()['dataset_id']==DATASET and response.json()['operations'][0]['status']=='success'
    assert adapter['writes']==[] and not main.store.has_secret(job['id'],'dataset_api_key')


def test_restart_marks_pending_unknown_without_remote_retry(client,adapter):
    task,_=task_with_env(client);job=approved_job(client,task);stored=main.knowledge.job(job['id']);stored.update(status='running',operations=[{'id':'op','kind':'create_dataset','status':'pending'}]);main.store.put('knowledge_job',job['id'],stored)
    main.knowledge.recover();result=main.knowledge.job(job['id'])
    assert result['status']=='unknown' and result['operations'][0]['status']=='unknown' and adapter['writes']==[]


def test_unknown_created_dataset_requires_manual_verification_and_exact_identity(client,adapter,monkeypatch):
    task,_=task_with_env(client);job=approved_job(client,task)
    async def fail(*args,**kwargs):raise DifyError('结果可能未知。')
    monkeypatch.setattr(DifyClient,'create_dataset',fail);client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert client.post(f"/api/knowledge-jobs/{job['id']}/reconcile",json={'resource_id':DATASET}).status_code==409
    async def read(self,method,path,**kwargs):return {'id':DATASET,'name':'测试资料库','indexing_technique':'economy'}
    monkeypatch.setattr(DifyClient,'request',read)
    response=client.post(f"/api/knowledge-jobs/{job['id']}/reconcile",json={'resource_id':DATASET,'verified_in_dify':True})
    assert response.status_code==200,response.text
    assert response.json()['dataset_id']==DATASET and response.json()['operations'][0]['reconciled_by']=='user_confirmed_console'


def test_unknown_key_can_only_be_replaced_with_explicit_choice_once(client,adapter,monkeypatch):
    task,_=task_with_env(client);job=approved_job(client,task);calls=[]
    async def key(*args,**kwargs):calls.append(1);raise DifyError('Key 响应未知。')
    monkeypatch.setattr(DifyClient,'create_scoped_dataset_key',key)
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={}).json()['status']=='unknown'
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={}).status_code==409
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={'replace_unknown_key':True}).json()['status']=='unknown'
    assert len(calls)==2
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={'replace_unknown_key':True}).status_code==409


def test_time_limit_stops_before_dispatch(client,adapter,monkeypatch):
    task,_=task_with_env(client);job=approved_job(client,task);original=DifyClient.workspace
    async def expired(self):
        current=main.knowledge.job(job['id']);current['started_at']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat();main.store.put('knowledge_job',job['id'],current)
        return await original(self)
    monkeypatch.setattr(DifyClient,'workspace',expired)
    response=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert response.json()['status']=='paused' and '时间上限' in response.json()['message'] and adapter['writes']==[]


def test_space_switch_during_write_is_unknown_and_stops_next_dispatch(client,adapter,monkeypatch):
    task,_=task_with_env(client);job=approved_job(client,task)
    async def moved(self,*args,**kwargs):
        adapter['workspace_id']=str(uuid.uuid4());return {'id':DATASET}
    monkeypatch.setattr(DifyClient,'create_dataset',moved)
    response=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert response.json()['status']=='unknown' and response.json()['dataset_id'] is None
    assert response.json()['operations'][0]['status']=='unknown' and adapter['writes']==[]


def test_index_error_does_not_expose_job_key(client,adapter,monkeypatch):
    task,_=task_with_env(client);job=approved_job(client,task)
    async def error(self,dataset,document):
        return {'id':document,'indexing_status':'error','completed_segments':0,'total_segments':0,'error':'returned dataset-private-unit-key must be redacted'}
    monkeypatch.setattr(DifyClient,'document_status',error)
    response=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert response.json()['status']=='needs_input' and 'dataset-private-unit-key' not in response.text
    assert '[已脱敏]' in response.json()['documents'][0]['indexing']['error']


@pytest.mark.parametrize('app_type', ['workflow', 'advanced-chat', 'agent'])
def test_raw_upload_plan_confirm_restart_index_and_apply(client, adapter, monkeypatch, app_type):
    env = create_env(client)
    response = client.post('/api/tasks', json={'name': '只有原始知识资料', 'app_type': app_type, 'environment_id': env['id']})
    assert response.status_code == 201, response.text
    task = response.json()  # 保留新任务真实准入门禁，不使用旧版 create fixture。
    raw = '  退货政策：七天内可退。\n来源：公开合成资料。  '
    response = client.post(f"/api/tasks/{task['id']}/materials", files={'file': ('原始政策.txt', raw.encode(), 'text/plain')})
    assert response.status_code == 200, response.text
    task = response.json()
    material = task['materials'][0]
    assert material['status'] == 'parsed' and material['text'] == raw
    before = copy.deepcopy(main.get_task(task['id']))
    response = propose(client, task, text='', material_ids=[material['id']])
    assert response.status_code == 201, response.text
    job = response.json()
    doc = job['documents'][0]
    assert job['status'] == 'draft' and job['task_revision'] == task['revision']
    assert job['purpose'] == '开发联调知识库准备，核对已授权资料范围。'
    assert job['indexing_technique'] == 'economy' and '不调用 Embedding' in job['cost_note']
    assert doc['source'] == 'material' and doc['material_id'] == material['id']
    assert doc['text'] == raw and doc['sha256'] == hashlib.sha256(raw.encode()).hexdigest()
    assert adapter['writes'] == [] and main.get_task(task['id']) == before
    response = client.post(f"/api/knowledge-jobs/{job['id']}/confirm", json={'task_revision': task['revision']})
    assert response.status_code == 200, response.text
    approved = response.json()
    assert approved['status'] == 'approved' and adapter['writes'] == []
    assert main.get_task(task['id']) == before
    monkeypatch.setattr(main, 'store', Store(main.store.root))
    assert client.get(f"/api/knowledge-jobs/{job['id']}").json() == approved
    assert client.get(f"/api/tasks/{task['id']}/knowledge-jobs").json() == [approved]
    assert main.get_task(task['id']) == before and adapter['writes'] == []
    adapter.update(indexing_status='waiting', completed_segments=0, total_segments=0)
    response = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'indexing'
    assert adapter['writes'] == ['dataset', 'key', 'document'] and adapter['last_text'] == raw
    assert client.post(f"/api/knowledge-jobs/{job['id']}/apply", json={'revision': task['revision']}).status_code == 409
    assert main.get_task(task['id']) == before
    adapter.update(indexing_status='completed', completed_segments=1, total_segments=1)
    response = client.post(f"/api/knowledge-jobs/{job['id']}/refresh")
    assert response.status_code == 200 and response.json()['status'] == 'ready'
    assert '不等于检索效果已验收' in response.json()['message']
    response = client.post(f"/api/knowledge-jobs/{job['id']}/apply", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied['app_type'] == app_type and applied['revision'] == task['revision'] + 1
    assert applied['configuration']['dataset_ids'] == [DATASET]
    assert not applied['configuration_confirmed'] and not applied['requirements_confirmed']
    assert not applied['artifact'] and not applied['dify_app_id'] and not applied['runs']
    assert applied['materials'] == before['materials']
    persisted = Store(main.store.root)
    assert persisted.get('task', task['id']) == main.get_task(task['id'])
    assert persisted.get('knowledge_job', job['id'])['applied_revision'] == applied['revision']
    assert adapter['writes'] == ['dataset', 'key', 'document']


@pytest.mark.parametrize('filename,raw', [('图片.png', b'not-an-image'), ('空文档.txt', b'   '), ('超限.txt', b'x' * 100001)], ids=['unsupported-image', 'empty-text', 'oversized-text'])
def test_unreadable_raw_upload_cannot_propose_or_write(client, adapter, filename, raw):
    task, _ = task_with_env(client)
    response = client.post(f"/api/tasks/{task['id']}/materials", files={'file': (filename, raw)})
    assert response.status_code == 200, response.text
    task = response.json()
    material = task['materials'][0]
    assert material['status'] == 'needs_input' and material['error'] and material['text'] == ''
    before = copy.deepcopy(main.get_task(task['id']))
    response = propose(client, task, text='', material_ids=[material['id']])
    assert response.status_code == 422 and '完整文本' in response.text
    assert adapter['writes'] == [] and main.get_task(task['id']) == before
    assert client.get(f"/api/tasks/{task['id']}/knowledge-jobs").json() == []


def test_foreign_material_cannot_be_used_for_current_task(client, adapter):
    task, _ = task_with_env(client)
    other, _ = task_with_env(client)
    response = client.post(f"/api/tasks/{other['id']}/materials", files={'file': ('其他任务.txt', '其他任务资料'.encode())})
    assert response.status_code == 200, response.text
    material = response.json()['materials'][0]
    before = copy.deepcopy(main.get_task(task['id']))
    response = propose(client, task, text='', material_ids=[material['id']])
    assert response.status_code == 422 and '完整文本' in response.text
    assert adapter['writes'] == [] and main.get_task(task['id']) == before
    assert main.store.list('knowledge_job') == []


def test_disabled_embedding_after_approval_never_downgrades_or_writes(client, adapter):
    task, _ = task_with_env(client)
    job = approved_job(client, task, indexing_technique='high_quality', embedding_provider='langgenius/embed/embed', embedding_model='embedding-exact')
    adapter['model_active'] = False
    response = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert response.status_code == 200, response.text
    paused = response.json()
    assert paused['status'] == 'paused' and '未自动替换索引方式' in paused['message']
    assert paused['indexing_technique'] == 'high_quality' and paused['embedding_model'] == 'embedding-exact'
    assert adapter['writes'] == [] and paused['operations'] == []
    assert main.get_task(task['id'])['configuration']['dataset_ids'] == []


@pytest.mark.parametrize('change', ['task', 'connection'])
def test_approved_plan_cannot_execute_after_bound_revision_changes(client, adapter, change):
    task, env = task_with_env(client)
    job = approved_job(client, task)
    path, body = (f"/api/tasks/{task['id']}", {'name': '新任务修订'}) if change == 'task' else (f"/api/environments/{env['id']}", {'console_token': 'new-unit-token'})
    response = client.patch(path, json=body)
    assert response.status_code == 200, response.text
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert response.status_code == 409 and '变化' in response.text
    assert adapter['writes'] == [] and main.get_task(task['id']) == before


def test_ready_job_is_rechecked_before_apply(client, adapter):
    task, _ = task_with_env(client)
    job = approved_job(client, task)
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={}).json()['status'] == 'ready'
    before = copy.deepcopy(main.get_task(task['id']))
    adapter.update(indexing_status='error', completed_segments=0)
    response = client.post(f"/api/knowledge-jobs/{job['id']}/apply", json={'revision': task['revision']})
    assert response.status_code == 409 and '索引不是可用状态' in response.text
    assert main.get_task(task['id']) == before
    assert main.knowledge.job(job['id'])['status'] == 'needs_input'
    assert adapter['writes'] == ['dataset', 'key', 'document']


def test_every_document_must_finish_before_ready(client, adapter, monkeypatch):
    task, _ = task_with_env(client)
    response = client.post(f"/api/tasks/{task['id']}/materials", files={'file': ('原始资料.txt', '独立资料全文'.encode())})
    assert response.status_code == 200, response.text
    task = response.json()
    job = approved_job(client, task, material_ids=[task['materials'][0]['id']])
    document_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    original = DifyClient.create_text_document
    async def upload(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        result['document']['id'] = document_ids[len(adapter['writes']) - 3]
        return result
    async def status(self, dataset, document):
        finished = document == document_ids[0] or adapter.get('all_finished', False)
        return {'id': document, 'indexing_status': 'completed' if finished else 'waiting', 'completed_segments': int(finished), 'total_segments': 1}
    monkeypatch.setattr(DifyClient, 'create_text_document', upload)
    monkeypatch.setattr(DifyClient, 'document_status', status)
    response = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'indexing' and len(response.json()['documents']) == 2
    assert client.post(f"/api/knowledge-jobs/{job['id']}/apply", json={'revision': task['revision']}).status_code == 409
    assert main.get_task(task['id'])['configuration']['dataset_ids'] == []
    adapter['all_finished'] = True
    response = client.post(f"/api/knowledge-jobs/{job['id']}/refresh")
    assert response.status_code == 200 and response.json()['status'] == 'ready'
    assert adapter['writes'] == ['dataset', 'key', 'document', 'document']
