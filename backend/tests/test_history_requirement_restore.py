"""Malformed saved requirements must not replace a usable current task."""
import copy
import json
import pytest
from test_api import client
from test_version_restore import seeded, read, forbid_external_calls
from app import main
from app.version_restore import token


FAULTS = [(key, 'missing', None) for key in main.REQ_KEYS]
FAULTS += [(key, 'value', ['PRIVATE-HISTORICAL-VALUE']) for key in main.REQ_KEYS]
FAULTS += [('goal', 'value', value) for value in [None, False, 42, 1.25, {}, []]]


@pytest.mark.parametrize('action', ['preview', 'restore'])
@pytest.mark.parametrize('key,change,value', FAULTS)
def test_invalid_requirements_rejected_before_exposing_or_restoring_history(client, action, key, change, value):
    task, _ = seeded(client)
    version = task['versions'][0]
    if change == 'missing':
        version['requirements'].pop(key)
    else:
        version['requirements'][key] = value
    main.store.put('task', task['id'], task)
    before = copy.deepcopy(main.get_task(task['id']))
    ledger = copy.deepcopy(main.store.get('task_budget', task['id']))
    if action == 'preview':
        response = read(client, task, version)
    else:
        response = client.post(f"/api/tasks/{task['id']}/restore", json={
            'revision': task['revision'], 'version_id': version['id'],
            'review_token': token(task, version), 'acknowledge_restore': True})
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text and 'review_token' not in response.text
    assert main.get_task(task['id']) == before
    assert main.store.get('task_budget', task['id']) == ledger


@pytest.mark.parametrize('empty', [False, True])
def test_text_requirements_keep_exact_saved_values_extra_fields_and_history(client, empty):
    task, _ = seeded(client)
    version = task['versions'][0]
    if empty:
        version['requirements'] = {key: '' for key in main.REQ_KEYS}
    version['requirements']['legacy_note'] = '  PRIVATE-LEGACY\n原样保留  '
    main.store.put('task', task['id'], task)
    before = copy.deepcopy(main.get_task(task['id']))
    response = read(client, task, version)
    assert response.status_code == 200, response.text
    assert 'PRIVATE' not in json.dumps(response.json())
    restored = client.post(f"/api/tasks/{task['id']}/restore", json={
        'revision': task['revision'], 'version_id': version['id'],
        'review_token': response.json()['review_token'], 'acknowledge_restore': True})
    assert restored.status_code == 200, restored.text
    saved = restored.json()
    assert saved['requirements'] == version['requirements']
    assert saved['versions'][0] == before['versions'][0]
    assert saved['versions'][-1]['requirements'] == before['requirements']
    assert saved['revision'] == before['revision'] + 1
    assert not saved['requirements_confirmed'] and not saved['configuration_confirmed']
    assert saved['runs'] == before['runs'] and saved['messages'] == before['messages']


BAD_CONFIG = [
    ('suggested_questions', 'PRIVATE-CONFIG'), ('suggested_questions', [None]),
    ('dataset_ids', {}), ('dataset_ids', [False]),
    ('mock_dependencies', 'PRIVATE-CONFIG'), ('mock_dependencies', [42]),
    ('mock_dependency_bindings', {}), ('mock_dependency_bindings', [None]),
    ('model_parameters', []), ('assistant_provider_id', 42),
    ('conversation_memory', 'false'), ('memory_turns', True),
    ('max_tokens', 1.5), ('retrieval_top_k', None), ('temperature', True),
    *[(key, []) for key in ('opening_statement', 'dify_model_provider', 'dify_model', 'resource_plan')],
]


@pytest.mark.parametrize('action', ['preview', 'restore'])
@pytest.mark.parametrize('key,value', BAD_CONFIG)
def test_invalid_configuration_cannot_restore_unusable_workbench(client, action, key, value):
    task, _ = seeded(client)
    version = task['versions'][0]
    version['configuration'][key] = value
    main.store.put('task', task['id'], task)
    before = copy.deepcopy(main.get_task(task['id']))
    if action == 'preview':
        response = read(client, task, version)
    else:
        response = client.post(f"/api/tasks/{task['id']}/restore", json={
            'revision': task['revision'], 'version_id': version['id'],
            'review_token': token(task, version), 'acknowledge_restore': True})
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text and 'review_token' not in response.text
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('configuration', [
    {}, {'legacy_metadata': {'unrecognized': ['PRIVATE-LEGACY']}},
    {'temperature': 2.5, 'max_tokens': -1, 'memory_turns': 75},
])
def test_configuration_restore_preserves_legacy_fields_and_is_not_business_validation(client, configuration):
    task, _ = seeded(client)
    version = task['versions'][0]
    version['configuration'] = configuration
    main.store.put('task', task['id'], task)
    response = read(client, task, version)
    assert response.status_code == 200, response.text
    assert 'PRIVATE' not in response.text
    restored = client.post(f"/api/tasks/{task['id']}/restore", json={
        'revision': task['revision'], 'version_id': version['id'],
        'review_token': response.json()['review_token'], 'acknowledge_restore': True})
    assert restored.status_code == 200, restored.text
    saved = restored.json()
    assert saved['configuration'] == configuration
    assert not saved['configuration_confirmed'] and not saved['requirements_confirmed']


@pytest.mark.parametrize('field', ['dsl_reference', 'dsl_overlay'])
@pytest.mark.parametrize('bad', ['PRIVATE-DSL-RECORD', [], True])
@pytest.mark.parametrize('action', ['preview', 'restore'])
def test_invalid_dsl_preservation_container_cannot_poison_later_baseline_read(client, field, bad, action):
    task, _ = seeded(client)
    version = task['versions'][0]
    version[field] = bad
    main.store.put('task', task['id'], task)
    before = copy.deepcopy(main.get_task(task['id']))
    if action == 'preview':
        response = read(client, task, version)
    else:
        response = client.post(f"/api/tasks/{task['id']}/restore", json={
            'revision': task['revision'], 'version_id': version['id'],
            'review_token': token(task, version), 'acknowledge_restore': True})
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text
    assert main.get_task(task['id']) == before
