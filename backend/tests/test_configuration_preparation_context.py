"""Regression for real provisioning facts reaching configuration suggestions."""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from test_configuration_proposals import (
    client, prepared, candidate, provider,
    forbid_configuration_external_calls,
)
from app import main


def bound_preparation(client, monkeypatch):
    task = prepared(client, monkeypatch)
    task = main.get_task(task['id'])
    task['configuration']['dataset_ids'] = ['kb_readable']
    text = 'PUBLIC_FAQ_BODY_MUST_NOT_APPEAR_IN_PREPARATION_METADATA'
    digest = hashlib.sha256(text.encode()).hexdigest()
    task['materials'] = [{'id': 'source-1', 'name': 'faq.txt', 'status': 'parsed',
                          'text': text, 'sha256': digest, 'reference_mode': 'borrow'}]
    main.save_task(task)
    env = main.store.get('environment', task['environment_id'])
    job = {'id': 'ready-job', 'task_id': task['id'], 'environment_id': env['id'],
           'status': 'applied', 'operations': [], 'dataset_id': 'kb_readable', 'indexing_technique': 'economy',
           'connection': {key: env.get(key) for key in ('base_url', 'version', 'connection_revision')},
           'observed_at': datetime.now(timezone.utc).isoformat(),
           'documents': [{'id': 'document-1', 'material_id': 'source-1', 'name': 'faq.txt',
                          'text': text, 'sha256': digest,
                          'indexing': {'indexing_status': 'completed', 'completed_segments': 1,
                                       'total_segments': 1}}],
           'dataset_api_key': 'SECRET_TEST_MARKER_NOT_A_REAL_KEY'}
    main.store.put('knowledge_job', job['id'], job)
    return task, job


def test_current_applied_preparation_has_only_bound_metadata(client, monkeypatch):
    task, job = bound_preparation(client, monkeypatch)
    evidence = main.configuration_proposals.knowledge_preparations(task)
    assert len(evidence) == 1
    assert evidence[0]['dataset_id'] == job['dataset_id']
    assert evidence[0]['documents'] == [{'name': 'faq.txt', 'sha256': job['documents'][0]['sha256'],
                                       'indexing': job['documents'][0]['indexing']}]
    encoded = json.dumps(evidence)
    assert task['materials'][0]['text'] not in encoded
    assert job['dataset_api_key'] not in encoded
    assert 'material_id' not in encoded and 'text' not in evidence[0]['documents'][0]


@pytest.mark.parametrize('change', [
    'connection_revision', 'foreign_environment', 'foreign_task', 'not_applied', 'unselected',
    'expired', 'future', 'material_text', 'material_sha', 'material_name', 'unparsed',
    'index_pending', 'index_empty', 'missing_material', 'bad_observed',
])
def test_stale_or_foreign_preparation_is_excluded(client, monkeypatch, change):
    task, job = bound_preparation(client, monkeypatch)
    if change == 'connection_revision':
        env = main.store.get('environment', task['environment_id'])
        env['connection_revision'] = 'changed'
        main.store.put('environment', env['id'], env)
    elif change == 'foreign_environment': job['environment_id'] = 'foreign'
    elif change == 'foreign_task': job['task_id'] = 'foreign'
    elif change == 'not_applied': job['status'] = 'ready'
    elif change == 'unselected': task['configuration']['dataset_ids'] = []
    elif change == 'expired': job['observed_at'] = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()
    elif change == 'future': job['observed_at'] = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    elif change == 'material_text': task['materials'][0]['text'] += 'changed'
    elif change == 'material_sha': task['materials'][0]['sha256'] = '0' * 64
    elif change == 'material_name': task['materials'][0]['name'] = 'other.txt'
    elif change == 'unparsed': task['materials'][0]['status'] = 'failed'
    elif change == 'index_pending': job['documents'][0]['indexing']['indexing_status'] = 'indexing'
    elif change == 'index_empty': job['documents'][0]['indexing']['completed_segments'] = 0
    elif change == 'missing_material': task['materials'] = []
    else: job['observed_at'] = 'unknown'
    main.store.put('knowledge_job', job['id'], job)
    assert main.configuration_proposals.knowledge_preparations(task) == []


def test_generate_receives_verified_preparation_without_applying_proposal(client, monkeypatch):
    task, job = bound_preparation(client, monkeypatch)
    model_provider = provider(client)
    task = client.patch(f"/api/tasks/{task['id']}", json={
        'configuration': {'assistant_provider_id': model_provider['id']},
    }).json()
    before = copy.deepcopy(task['configuration'])
    captured = []

    async def model(*args, **kwargs):
        messages = args[2]
        context = json.loads(messages[1]['content'])
        captured.append(context['knowledge_preparations'])
        return json.dumps(candidate()), {'prompt_tokens': 10, 'completion_tokens': 20}

    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f"/api/tasks/{task['id']}/configuration-proposal/generate",
                           json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert len(captured) == 1 and captured[0][0]['dataset_id'] == job['dataset_id']
    assert response.json()['configuration'] == before
    assert not response.json()['configuration_confirmed']