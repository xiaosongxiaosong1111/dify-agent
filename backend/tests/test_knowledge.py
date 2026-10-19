import asyncio
import copy
import json
import uuid
from datetime import datetime,timezone,timedelta
import pytest
from test_api import client,create,create_env
from app import main
from app.dify import DifyClient,DifyError

WORKSPACE=str(uuid.uuid4());DATASET=str(uuid.uuid4());DOCUMENT=str(uuid.uuid4())

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
