import copy
import json

import pytest

from test_api import client, approved, create_env, forbid_api_external_calls
from test_task_next_step import saved, READY
from app import main
from app.task_next_step import describe


def publication(task, *, status='success', mode=None, include_result=True):
    result = {'app_id': task['dify_app_id'], 'app_type': mode or task['app_type'], 'state': 'succeeded', 'workflow_id': 'saved-graph'}
    return {'id': 'publication', 'kind': 'publish', 'revision': task['revision'], 'environment_id': task['environment_id'],
        'app_id': task['dify_app_id'], 'status': status, 'result': result if include_result else {}}


def test_imported_task_without_publication_is_not_sent_directly_to_run():
    assert describe(saved(), READY)['state'] == 'publication'


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat'])
def test_import_publish_key_and_run_advice_is_ordered_and_readonly(mode):
    task = saved(); task['app_type'] = mode; original = copy.deepcopy(task)
    step = describe(task, READY, runtime_key_paired=False)
    assert step['state'] == 'publication' and step['target_page'] == '运行' and task == original
    assert all(step[key] is False for key in ['task_changed', 'network_requested', 'automatic_execution', 'business_verified'])
    task['runs'] = [publication(task)]
    assert describe(task, READY, runtime_key_paired=False)['state'] == 'runtime_key'
    assert describe(task, READY, runtime_key_paired=True)['state'] == 'run'


@pytest.mark.parametrize('status', ['unknown', 'pending'])
def test_unconfirmed_publish_without_result_never_recommends_republish_or_run(status):
    task = saved(); task['runs'] = [publication(task, status=status, include_result=False)]
    step = describe(task, READY, runtime_key_paired=True)
    assert step['state'] in {'publication_review', 'busy'}
    assert '重发' in json.dumps(step, ensure_ascii=False) or step['state'] == 'busy'


@pytest.mark.parametrize('field,value', [('revision', 2), ('environment_id', 'other'), ('app_id', 'other')])
def test_other_scope_publications_do_not_clear_current_publication_step(field, value):
    task = saved(); row = publication(task); row[field] = value; task['runs'] = [row]
    assert describe(task, READY, runtime_key_paired=True)['state'] == 'publication'


def test_chatflow_cannot_use_a_workflow_or_untyped_receipt_as_publication_success():
    task = saved(); task['app_type'] = 'advanced-chat'; task['runs'] = [publication(task, mode='workflow')]
    assert describe(task, READY, runtime_key_paired=True)['state'] == 'publication_review'
    task['runs'][0]['result'].pop('app_type')
    assert describe(task, READY, runtime_key_paired=True)['state'] == 'publication_review'


def test_existing_current_runs_go_to_review_without_rebinding_or_republishing():
    task = saved(); task['runs'] = [{'id': 'old-result', 'kind': 'run', 'revision': 3, 'environment_id': 'env',
        'app_id': 'app', 'app_type': 'workflow', 'status': 'success'}]
    assert describe(task, READY, runtime_key_paired=False)['state'] == 'review'
    task['runs'].append(publication(task, status='unknown', include_result=False))
    assert describe(task, READY, runtime_key_paired=True)['state'] == 'publication_review'


def test_new_advice_facts_change_token_without_task_revision_change():
    task = saved(); before = describe(task, READY, runtime_key_paired=False)
    task['runs'].append(publication(task)); published = describe(task, READY, runtime_key_paired=False)
    keyed = describe(task, READY, runtime_key_paired=True)
    assert len({before['snapshot_token'], published['snapshot_token'], keyed['snapshot_token']}) == 3
    assert task['revision'] == 3


def test_agent_path_is_not_promoted_to_workflow_publication():
    task = saved(); task['app_type'] = 'agent'
    assert describe(task, READY, runtime_key_paired=False)['state'] == 'run'


def test_actual_route_observes_key_pairing_without_decrypting_key_or_writing(client, monkeypatch):
    env = create_env(client)
    task = approved(client, env_id=env['id']); tid = task['id']
    task = client.post('/api/tasks/' + tid + '/build', json={'revision': task['revision']}).json()
    task.update(dify_app_id='current-app', status='imported'); task['runs'] = [publication(task)]
    main.store.put('task', tid, task)
    before = copy.deepcopy(main.store.get('task', tid)); budget = copy.deepcopy(main.store.get('task_budget', tid))
    response = client.get('/api/tasks/' + tid + '/next-step', params={'revision': task['revision']})
    assert response.status_code == 200 and response.json()['state'] == 'runtime_key'
    current = main.store.get('environment', env['id']); current['service_app_id'] = 'current-app'
    main.store.put_with_secrets('environment', env['id'], current, {'service_api_key': 'ISOLATED-NEVER-RETURN-KEY'})
    def forbid_decrypt(*args, **kwargs): pytest.fail('Navigation must not decrypt any credential')
    monkeypatch.setattr(main.store, 'secret', forbid_decrypt)
    response = client.get('/api/tasks/' + tid + '/next-step', params={'revision': task['revision']})
    assert response.status_code == 200 and response.json()['state'] == 'run'
    assert 'ISOLATED' not in response.text and 'service_api_key' not in response.text
    assert main.store.get('task', tid) == before and main.store.get('task_budget', tid) == budget
    current['service_app_id'] = 'other-app'; main.store.put('environment', env['id'], current)
    assert client.get('/api/tasks/' + tid + '/next-step', params={'revision': task['revision']}).json()['state'] == 'runtime_key'
