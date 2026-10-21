import copy
import json
import sqlite3

import pytest
from test_api import client, forbid_api_external_calls
from test_workflow_publication import setup
from app import main

NEW_KEY = 'app-ISOLATED-RUNTIME-KEY-ONLY'


def prepare(client, monkeypatch):
    task, env, state = setup(client, monkeypatch)
    # The publication fixture transport is not needed: prohibit even adapter calls.
    def forbidden(*a, **kw): pytest.fail('Runtime-key registration must not access Dify')
    monkeypatch.setattr(main.DifyClient, 'request', forbidden)
    return task, env


def read(client, task): return client.get(f"/api/tasks/{task['id']}/runtime-key", params={'revision': task['revision']})


def save(client, task, token, **changes):
    body = {'revision': task['revision'], 'review_token': token, 'confirm_bind': True, 'service_api_key': NEW_KEY} | changes
    return client.post(f"/api/tasks/{task['id']}/runtime-key", json=body)


def cipher_rows():
    with main.store.connect() as db: return dict(db.execute('SELECT id,value FROM secrets'))


def test_local_state_then_explicit_binding_preserves_task_and_other_credentials(client, monkeypatch):
    task, env = prepare(client, monkeypatch)
    main.store.put_with_secrets('environment', env['id'], main.store.get('environment', env['id']), {'dataset_api_key': 'isolated-dataset-key', 'service_api_key': 'app-old-isolated-key'})
    before_task = main.store.get('task', task['id']); before_env = main.store.get('environment', env['id']); before_keys = cipher_rows()
    r = read(client, task); assert r.status_code == 200, r.text
    state = r.json(); assert state['has_runtime_key'] and not state['matches_current_app'] and not state['network_requested']
    assert state['shared_environment_tasks'] == 1 and 'fingerprint' not in r.text and 'app-old-isolated-key' not in r.text
    assert cipher_rows() == before_keys and main.store.get('task', task['id']) == before_task
    r = save(client, task, state['review_token']); assert r.status_code == 200, r.text
    assert r.json()['matches_current_app'] and r.json()['saved'] and not r.json()['unchanged'] and NEW_KEY not in r.text
    assert main.store.get('task', task['id']) == before_task
    after = main.store.get('environment', env['id']); assert after['service_app_id'] == task['dify_app_id']
    assert after['connection_revision'] != before_env['connection_revision'] and after['capabilities']['runtime'] == 'registered_unverified'
    assert after['capabilities']['console'] == before_env['capabilities']['console']
    assert main.store.secret(env['id'], 'service_api_key') == NEW_KEY
    for k, v in before_keys.items():
        if k != env['id'] + ':service_api_key': assert cipher_rows()[k] == v
    assert NEW_KEY.encode() not in Path(main.store.path).read_bytes()


from pathlib import Path


def test_identical_key_is_noop_no_cipher_or_connection_churn(client, monkeypatch):
    task, env = prepare(client, monkeypatch); p = read(client, task).json(); assert save(client, task, p['review_token']).status_code == 200
    before_env = main.store.get('environment', env['id']); before_keys = cipher_rows(); p = read(client, task).json()
    r = save(client, task, p['review_token']); assert r.status_code == 200 and r.json()['unchanged']
    assert main.store.get('environment', env['id']) == before_env and cipher_rows() == before_keys


@pytest.mark.parametrize('change', ['revision', 'app', 'artifact', 'environment_url', 'connection_revision', 'workspace', 'active_key', 'pause', 'missing_import', 'old_import'])
def test_stale_or_unknown_source_never_replaces_key(client, monkeypatch, change):
    task, env = prepare(client, monkeypatch); p = read(client, task).json(); current = main.store.get('task', task['id']); e = main.store.get('environment', env['id'])
    if change == 'revision': current['revision'] += 1
    elif change == 'app': current['dify_app_id'] = 'other-app'
    elif change == 'artifact': main.artifact_path(current).write_bytes(main.artifact_path(current).read_bytes() + b'\n#changed')
    elif change == 'environment_url': e['base_url'] = 'http://127.0.0.1:9999'
    elif change == 'connection_revision': e['connection_revision'] = 'changed'
    elif change == 'workspace': e['console_workspace_id'] = 'other-space'
    elif change == 'active_key': main.store.put_with_secrets('environment', env['id'], e, {'service_api_key': 'app-OTHER-USER-UPDATE'})
    elif change == 'pause': current['status'] = 'paused'; current['pause_generation'] = 1
    elif change == 'missing_import': current['runs'] = []
    else: current['runs'][0]['revision'] -= 1
    main.store.put('task', task['id'], current); main.store.put('environment', env['id'], e); before = cipher_rows()
    r = save(client, task, p['review_token']); assert r.status_code in {404, 409}, r.text
    assert cipher_rows() == before


@pytest.mark.parametrize('changes', [{'confirm_bind': False}, {'confirm_bind': 1}, {'revision': True}, {'service_api_key': ''}, {'service_api_key': 'LEAK-ME\nBAD'}, {'service_api_key': ['LEAK-ME']}, {'service_api_key': 'LEAK-ME' * 600}, {'unknown': 'LEAK-ME'}, {'review_token': 'LEAK-ME'}])
def test_invalid_secret_body_not_echoed_and_no_partial_save(client, monkeypatch, changes):
    task, env = prepare(client, monkeypatch); p = read(client, task).json(); before = cipher_rows(); e = main.store.get('environment', env['id'])
    r = save(client, task, p['review_token'], **changes)
    assert r.status_code == 422 and 'LEAK-ME' not in r.text and NEW_KEY not in r.text
    assert cipher_rows() == before and main.store.get('environment', env['id']) == e


@pytest.mark.parametrize('content,kind', [('not-json-LEAK-ME', 'application/json'), ('{"service_api_key":"LEAK-ME"}', 'text/plain')])
def test_invalid_json_or_type_not_echoed(client, monkeypatch, content, kind):
    task, env = prepare(client, monkeypatch); before = cipher_rows()
    r = client.post(f"/api/tasks/{task['id']}/runtime-key", content=content, headers={'Content-Type': kind})
    assert r.status_code == 422 and 'LEAK-ME' not in r.text and cipher_rows() == before


def test_shared_environment_inflight_task_blocks_but_other_environment_does_not(client, monkeypatch):
    task, env = prepare(client, monkeypatch); related = copy.deepcopy(task); related['id'] = 'other-related-task'; related['status'] = 'running'; related['runs'] = []
    main.store.put('task', related['id'], related); p = read(client, task).json(); assert p['shared_environment_tasks'] == 2
    before = cipher_rows(); assert save(client, task, p['review_token']).status_code == 409 and cipher_rows() == before
    related['environment_id'] = 'different-env'; main.store.put('task', related['id'], related)
    assert save(client, task, p['review_token']).status_code == 409
    p = read(client, task).json(); assert save(client, task, p['review_token']).status_code == 200


def test_cannot_reuse_another_task_token_or_change_task_ownership(client, monkeypatch):
    task, env = prepare(client, monkeypatch); p = read(client, task).json(); other = copy.deepcopy(task); other['id'] = 'other-task'; main.store.put('task', other['id'], other)
    target = main.store.root / other['id']; target.mkdir(); (target / other['artifact']['filename']).write_bytes(main.artifact_path(task).read_bytes())
    before = cipher_rows(); assert save(client, other, p['review_token']).status_code == 409 and cipher_rows() == before


def test_duplicate_secret_field_is_rejected_without_echo(client, monkeypatch):
    task, env = prepare(client, monkeypatch); state = read(client, task).json(); before = cipher_rows()
    body = json.dumps({'revision': task['revision'], 'review_token': state['review_token'], 'confirm_bind': True, 'service_api_key': NEW_KEY})[:-1] + ',"service_api_key":"LEAK-ME-DUPLICATE"}'
    r = client.post(f"/api/tasks/{task['id']}/runtime-key", content=body, headers={'Content-Type': 'application/json'})
    assert r.status_code == 422 and 'LEAK-ME' not in r.text and NEW_KEY not in r.text and cipher_rows() == before
