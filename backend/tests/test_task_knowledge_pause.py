"""Task pause must fence subsequent provisioning writes, not discard their receipts."""
import asyncio
import copy
import pytest
from test_knowledge import (client, adapter, forbid_knowledge_external_calls,
                            task_with_env, approved_job, DATASET, DOCUMENT)
from app import main
from app.dify import DifyClient


@pytest.mark.parametrize('method,prefix',[
    ('create_dataset',['dataset']),
    ('create_scoped_dataset_key',['dataset','key']),
    ('create_text_document',['dataset','key','document']),
])
def test_task_pause_keeps_inflight_result_and_stops_following_writes(client,adapter,monkeypatch,method,prefix):
    task,_=task_with_env(client)
    task['materials']=[{'id':'extra','name':'第二份公开资料','status':'parsed','text':'第二份公开合成说明'}]
    main.store.put('task',task['id'],task)
    job=approved_job(client,task,material_ids=['extra'])
    original=getattr(DifyClient,method)
    async def paused(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        response=await asyncio.to_thread(client.post,f"/api/tasks/{task['id']}/pause")
        assert response.status_code==200 and response.json()['status']=='paused'
        assert (await asyncio.to_thread(client.patch,f"/api/tasks/{task['id']}",json={'name':'不应修改'})).status_code==409
        return result
    monkeypatch.setattr(DifyClient,method,paused)
    response=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert response.status_code==200,response.text
    saved=response.json()
    assert adapter['writes']==prefix
    assert saved['status']=='paused' and saved['dataset_id']==DATASET
    assert len(saved['operations'])==len(prefix) and all(o['status']=='success' for o in saved['operations'])
    assert main.get_task(task['id'])['status']=='paused'
    assert main.store.has_secret(job['id'],'dataset_api_key')==('key' in prefix)
    assert sum(bool(d.get('remote_id')) for d in saved['documents'])==prefix.count('document')


def test_task_pause_changes_only_owned_dispatchable_jobs_and_keeps_unknown(client,adapter):
    task,_=task_with_env(client);other,_=task_with_env(client)
    original=approved_job(client,task);untouched=approved_job(client,other)
    before={}
    for state in ('running','indexing','unknown','ready','applied','draft','canceled','needs_input'):
        row=copy.deepcopy(original);row.update(id='checkpoint-'+state,status=state)
        if state=='unknown':row['operations']=[{'id':'uncertain','kind':'create_dataset','status':'unknown'}]
        main.store.put('knowledge_job',row['id'],row);before[row['id']]=copy.deepcopy(row)
    paused=client.post(f"/api/tasks/{task['id']}/pause")
    assert paused.status_code==200
    assert main.knowledge.job(original['id'])['status']=='paused'
    for key,row in before.items():
        after=main.knowledge.job(key)
        if row['status'] in {'running','indexing'}:
            assert after['status']=='paused' and after['operations']==row['operations']
        else:assert after==row
    # Public has_dataset_key is a projection, not a stored field.
    assert main.knowledge.public(main.knowledge.job(untouched['id']))==untouched
    assert adapter['writes']==[]


def test_explicit_continue_reuses_completed_resource_without_recreating(client,adapter,monkeypatch):
    task,_=task_with_env(client);job=approved_job(client,task)
    original=DifyClient.create_dataset
    async def paused(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        await asyncio.to_thread(client.post,f"/api/tasks/{task['id']}/pause")
        return result
    monkeypatch.setattr(DifyClient,'create_dataset',paused)
    first=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={}).json()
    assert first['status']=='paused' and adapter['writes']==['dataset']
    assert client.get(f"/api/knowledge-jobs/{job['id']}").status_code==200
    main.knowledge.recover()
    assert adapter['writes']==['dataset']
    monkeypatch.setattr(DifyClient,'create_dataset',original)
    second=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert second.status_code==200,second.text
    assert second.json()['status']=='ready' and adapter['writes']==['dataset','key','document']
    assert second.json()['documents'][0]['remote_id']==DOCUMENT


@pytest.mark.parametrize('scope',['task','job'])
def test_pending_result_after_task_pause_stays_unknown_on_restart(client,adapter,scope):
    task,_=task_with_env(client);job=approved_job(client,task)
    row=main.knowledge.job(job['id']);row.update(status='running',operations=[{'id':'in-flight','kind':'create_dataset','status':'pending'}])
    main.store.put('knowledge_job',job['id'],row)
    url=f"/api/tasks/{task['id']}/pause" if scope=='task' else f"/api/knowledge-jobs/{job['id']}/pause"
    assert client.post(url).status_code==200
    assert main.knowledge.job(job['id'])['status']=='paused'
    main.knowledge.recover()
    saved=main.knowledge.job(job['id'])
    assert saved['status']=='unknown' and saved['operations'][0]['status']=='unknown'
    assert client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={}).status_code==409
    assert adapter['writes']==[]


def test_task_pause_during_prewrite_identity_read_prevents_first_write(client,adapter,monkeypatch):
    task,_=task_with_env(client);job=approved_job(client,task)
    original=DifyClient.workspace
    async def pause_before_write(self):
        result=await original(self)
        await asyncio.to_thread(client.post,f"/api/tasks/{task['id']}/pause")
        return result
    monkeypatch.setattr(DifyClient,'workspace',pause_before_write)
    result=client.post(f"/api/knowledge-jobs/{job['id']}/execute",json={})
    assert result.status_code==200 and result.json()['status']=='paused'
    assert result.json()['operations']==[] and adapter['writes']==[]
