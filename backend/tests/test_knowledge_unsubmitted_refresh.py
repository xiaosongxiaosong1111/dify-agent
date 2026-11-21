"""Unsubmitted documents are an explicit continue state, never remote index failures."""
import asyncio
import copy
import uuid
import pytest
from test_knowledge import (client, adapter, forbid_knowledge_external_calls,
                            task_with_env, approved_job, DATASET)
from app import main
from app.dify import DifyClient


def pause_after(method, task, client):
    original = getattr(DifyClient, method)
    once = []
    async def paused(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        if not once:
            once.append(1)
            response = await asyncio.to_thread(client.post, f"/api/tasks/{task['id']}/pause")
            assert response.status_code == 200 and response.json()['status'] == 'paused'
        return result
    return original, paused


def test_pause_after_dataset_refresh_reports_unsubmitted_without_reads(client, adapter, monkeypatch):
    task, _ = task_with_env(client)
    job = approved_job(client, task)
    original, paused = pause_after('create_dataset', task, client)
    monkeypatch.setattr(DifyClient, 'create_dataset', paused)
    first = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={}).json()
    assert first['status'] == 'paused' and first['dataset_id'] == DATASET
    assert adapter['writes'] == ['dataset'] and not first['documents'][0].get('remote_id')
    reads = []
    status = DifyClient.document_status
    async def counted(self, *args, **kwargs):
        reads.append(args)
        return await status(self, *args, **kwargs)
    monkeypatch.setattr(DifyClient, 'document_status', counted)
    before_task = copy.deepcopy(main.get_task(task['id']))
    before_ops = copy.deepcopy(main.knowledge.job(job['id'])['operations'])
    response = client.post(f"/api/knowledge-jobs/{job['id']}/refresh")
    assert response.status_code == 200, response.text
    refreshed = response.json()
    assert refreshed['status'] == 'paused' and '尚未提交' in refreshed['message']
    assert reads == [] and adapter['writes'] == ['dataset']
    assert main.get_task(task['id']) == before_task
    assert main.knowledge.job(job['id'])['operations'] == before_ops
    assert main.get_task(task['id'])['configuration']['dataset_ids'] == []
    monkeypatch.setattr(DifyClient, 'create_dataset', original)
    resumed = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'ready'
    assert adapter['writes'] == ['dataset', 'key', 'document'] and adapter['writes'].count('dataset') == 1


def test_pause_after_key_refresh_keeps_resume_without_second_key(client, adapter, monkeypatch):
    task, _ = task_with_env(client)
    job = approved_job(client, task)
    original, paused = pause_after('create_scoped_dataset_key', task, client)
    monkeypatch.setattr(DifyClient, 'create_scoped_dataset_key', paused)
    first = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={}).json()
    assert first['status'] == 'paused' and first['has_dataset_key'] is True
    assert adapter['writes'] == ['dataset', 'key']
    refreshed = client.post(f"/api/knowledge-jobs/{job['id']}/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()['status'] == 'paused' and '尚未提交' in refreshed.json()['message']
    assert adapter['writes'] == ['dataset', 'key']
    monkeypatch.setattr(DifyClient, 'create_scoped_dataset_key', original)
    resumed = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'ready'
    assert adapter['writes'] == ['dataset', 'key', 'document'] and adapter['writes'].count('key') == 1


def test_multiple_documents_pause_after_first_keeps_remainder_unsubmitted(client, adapter, monkeypatch):
    task, _ = task_with_env(client)
    uploaded = client.post(f"/api/tasks/{task['id']}/materials", files={'file': ('原始资料.txt', '独立资料全文'.encode())})
    assert uploaded.status_code == 200, uploaded.text
    task = uploaded.json()
    job = approved_job(client, task, material_ids=[task['materials'][0]['id']])
    assert len(job['documents']) == 2
    document_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    _, paused = pause_after('create_text_document', task, client)
    async def upload(self, *args, **kwargs):
        result = await paused(self, *args, **kwargs)
        result['document']['id'] = document_ids[len(adapter['writes']) - 3]
        return result
    monkeypatch.setattr(DifyClient, 'create_text_document', upload)
    first = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={}).json()
    assert first['status'] == 'paused' and adapter['writes'] == ['dataset', 'key', 'document']
    assert first['documents'][0]['remote_id'] == document_ids[0] and not first['documents'][1].get('remote_id')
    reads = []
    status = DifyClient.document_status
    async def counted(self, *args, **kwargs):
        reads.append(args)
        return await status(self, *args, **kwargs)
    monkeypatch.setattr(DifyClient, 'document_status', counted)
    response = client.post(f"/api/knowledge-jobs/{job['id']}/refresh")
    assert response.status_code == 200, response.text
    refreshed = response.json()
    assert refreshed['status'] == 'paused' and '尚未提交' in refreshed['message']
    assert [row[1] for row in reads] == [document_ids[0]]
    assert refreshed['documents'][0]['indexing']['indexing_status'] == 'completed'
    assert not refreshed['documents'][1].get('remote_id')
    resumed = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body['status'] == 'ready' and adapter['writes'] == ['dataset', 'key', 'document', 'document']
    assert [d['remote_id'] for d in body['documents']] == document_ids


@pytest.mark.parametrize('remote_status,segments,total',[('future-state',0,0),('error',0,0),('completed',0,0)])
def test_submitted_failure_beside_unsubmitted_stays_needs_input(client, adapter, monkeypatch, remote_status, segments, total):
    task, _ = task_with_env(client)
    uploaded = client.post(f"/api/tasks/{task['id']}/materials", files={'file': ('原始资料.txt', '独立资料全文'.encode())})
    assert uploaded.status_code == 200, uploaded.text
    task = uploaded.json()
    job = approved_job(client, task, material_ids=[task['materials'][0]['id']])
    _, paused = pause_after('create_text_document', task, client)
    monkeypatch.setattr(DifyClient, 'create_text_document', paused)
    first = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={}).json()
    assert first['status'] == 'paused' and first['documents'][0].get('remote_id')
    assert not first['documents'][1].get('remote_id')
    adapter.update(indexing_status=remote_status, completed_segments=segments, total_segments=total)
    response = client.post(f"/api/knowledge-jobs/{job['id']}/refresh")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'needs_input' and not body['documents'][1].get('remote_id')
    before = copy.deepcopy(main.get_task(task['id']))
    assert client.post(f"/api/knowledge-jobs/{job['id']}/apply", json={'revision': task['revision']}).status_code == 409
    assert main.get_task(task['id']) == before and main.get_task(task['id'])['configuration']['dataset_ids'] == []


def test_old_needs_input_with_only_unsubmitted_docs_refresh_restores_paused(client, adapter, monkeypatch):
    task, _ = task_with_env(client)
    job = approved_job(client, task)
    original, paused = pause_after('create_dataset', task, client)
    monkeypatch.setattr(DifyClient, 'create_dataset', paused)
    first = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={}).json()
    assert first['status'] == 'paused' and first['dataset_id'] == DATASET and adapter['writes'] == ['dataset']
    monkeypatch.setattr(DifyClient, 'create_dataset', original)
    stored = main.knowledge.job(job['id'])
    stored.update(status='needs_input', message='Dify 返回未识别的索引状态，不确认可用，请核对实例。')
    main.store.put('knowledge_job', job['id'], stored)
    response = client.post(f"/api/knowledge-jobs/{job['id']}/refresh")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'paused' and '尚未提交' in body['message']
    assert adapter['writes'] == ['dataset']
    resumed = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'ready' and adapter['writes'] == ['dataset', 'key', 'document']
