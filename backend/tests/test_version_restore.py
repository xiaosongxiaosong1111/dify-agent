import copy
import json
from uuid import uuid4

import pytest
from test_api import client, approved, code_only_plan, restore_payload
from app import main
from app.version_restore import preview, node_changes


def seeded(client):
    task = approved(client)
    task['workflow_plan'] = code_only_plan()
    task['test_cases'] = [{'id': 'old', 'name': '旧样例'}]
    task['materials'] = [{'id': 'old', 'name': 'private-filename', 'text': 'PRIVATE-MATERIAL'}]
    task['dsl_reference'] = {'id': 'private-reference', 'source_app_id': 'PRIVATE-APP'}
    main.snapshot(task, 'PRIVATE-LABEL')
    version = copy.deepcopy(task['versions'][-1])
    task['versions'] = [version]
    task['requirements']['goal'] = 'PRIVATE-CURRENT-RULE'
    task['configuration']['temperature'] = 0.8
    task['configuration']['dataset_ids'] = ['PRIVATE-DATASET']
    task['workflow_plan']['nodes'][1]['config']['code'] += '\n# PRIVATE-CODE'
    task['test_cases'] = []
    task['materials'] = []
    task['artifact'] = {'revision': task['revision'], 'path': 'PRIVATE-PATH'}
    task['dify_app_id'] = 'PRIVATE-BOUND-APP'
    main.store.put('task', task['id'], task)
    return task, version


def read(client, task, version):
    return client.get(f"/api/tasks/{task['id']}/versions/{version['id']}/restore-preview", params={'revision': task['revision']})


def test_preview_is_read_only_precise_and_contains_no_customer_values(client):
    task, version = seeded(client)
    before = copy.deepcopy(main.store.get('task', task['id']))
    ledger = copy.deepcopy(main.store.get('task_budget', task['id']))
    response = read(client, task, version)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['verification'] == 'local_history_restore_preview_only'
    assert not value['task_changed'] and not value['network_requested'] and not value['business_verified']
    rows = {v['key']: v for v in value['sections']}
    assert rows['requirements']['fields'] == ['目标']
    assert rows['configuration']['fields'] == ['温度', '知识库选择']
    assert rows['workflow_plan']['nodes']['changed'] == 1
    assert rows['test_cases']['current_count'] == 0 and rows['test_cases']['historical_count'] == 1
    assert rows['materials']['current_count'] == 0 and rows['materials']['historical_count'] == 1
    assert len(value['impacts']) == 5
    assert 'PRIVATE' not in response.text and 'private-' not in response.text
    assert main.store.get('task', task['id']) == before
    assert main.store.get('task_budget', task['id']) == ledger


def test_restore_creates_new_revision_and_preserves_pre_restore_and_ledger(client):
    task, version = seeded(client)
    task['messages'].append({'role': 'user', 'content': '保留讨论', 'purpose': 'discussion'})
    task['runs'] = [{'id': str(uuid4()), 'kind': 'run', 'status': 'success', 'revision': task['revision']}]
    main.store.put('task', task['id'], task)
    ledger = copy.deepcopy(main.store.get('task_budget', task['id']))
    payload = restore_payload(client, task['id'], version['id'])
    response = client.post(f"/api/tasks/{task['id']}/restore", json=payload)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['revision'] == task['revision'] + 1
    assert value['requirements'] == version['requirements'] and value['configuration'] == version['configuration']
    assert value['workflow_plan'] == version['workflow_plan']
    assert value['test_cases'] == version['test_cases'] and value['materials'] == version['materials']
    assert not value['requirements_confirmed'] and not value['configuration_confirmed']
    assert value['artifact'] is None and value['dify_app_id'] is None
    assert value['versions'][0] == version
    assert value['versions'][-1]['label'] == '恢复前保存'
    assert value['versions'][-1]['requirements'] == task['requirements']
    assert value['messages'] == task['messages'] and value['runs'] == task['runs']
    assert main.store.get('task_budget', task['id']) == ledger
    assert client.post(f"/api/tasks/{task['id']}/restore", json=payload).status_code == 409


@pytest.mark.parametrize('change', ['revision', 'same_revision_current', 'same_revision_confirm', 'same_revision_artifact', 'historical', 'different_version', 'different_task'])
def test_review_cannot_be_replayed_for_changed_or_different_content(client, change):
    task, version = seeded(client)
    payload = restore_payload(client, task['id'], version['id'])
    if change == 'revision': task['revision'] += 1
    elif change == 'same_revision_current': task['requirements']['rules'] += '新规则'
    elif change == 'same_revision_confirm': task['configuration_confirmed'] = not task['configuration_confirmed']
    elif change == 'same_revision_artifact': task['artifact']['path'] += '-changed'
    elif change == 'historical': task['versions'][0]['configuration']['temperature'] = 0.99
    elif change == 'different_version':
        other = copy.deepcopy(version);other['id'] = str(uuid4());task['versions'].append(other);payload['version_id'] = other['id']
    else:
        other = approved(client);other['versions'] = [copy.deepcopy(version)];main.store.put('task', other['id'], other);task = other;payload['revision'] = other['revision']
    main.store.put('task', task['id'], task)
    before = copy.deepcopy(main.store.get('task', task['id']))
    assert client.post(f"/api/tasks/{task['id']}/restore", json=payload).status_code == 409
    assert main.store.get('task', task['id']) == before


@pytest.mark.parametrize('changes', [
    {'acknowledge_restore': False}, {'acknowledge_restore': 'true'}, {'revision': True},
    {'review_token': 'PRIVATE-INVALID'}, {'version_id': 'PRIVATE-INVALID'},
    {'extra': 'PRIVATE-EXTRA'}, {'revision': '1'},
])
def test_restore_request_is_strict_and_errors_do_not_echo(client, changes):
    task, version = seeded(client)
    payload = {**restore_payload(client, task['id'], version['id']), **changes}
    before = copy.deepcopy(main.store.get('task', task['id']))
    response = client.post(f"/api/tasks/{task['id']}/restore", json=payload)
    assert response.status_code == 422
    assert 'PRIVATE' not in response.text
    assert main.store.get('task', task['id']) == before


def test_legacy_direct_restore_without_preview_is_rejected(client):
    task, version = seeded(client)
    assert client.post(f"/api/tasks/{task['id']}/restore", json={'version_id': version['id']}).status_code == 422


def test_busy_blocks_restore_but_not_read_only_comparison(client):
    task, version = seeded(client)
    payload = restore_payload(client, task['id'], version['id'])
    task['status'] = 'running';main.store.put('task', task['id'], task)
    assert read(client, task, version).status_code == 200
    assert client.post(f"/api/tasks/{task['id']}/restore", json=payload).status_code == 409
    assert main.store.get('task', task['id'])['revision'] == task['revision']


def test_legacy_missing_materials_is_preserved_and_intake_not_weakened(client):
    task, version = seeded(client)
    task['materials'] = [{'id': 'current'}]
    task['intake_required'] = True
    task['versions'][0].pop('materials')
    task['versions'][0]['intake_required'] = False
    main.store.put('task', task['id'], task)
    value = read(client, task, version).json()
    rows = {v['key']: v for v in value['sections']}
    assert not rows['materials']['changed'] and rows['materials']['historical_count'] == 1
    assert not rows['intake_required']['changed']
    result = client.post(f"/api/tasks/{task['id']}/restore", json=restore_payload(client, task['id'], version['id'])).json()
    assert result['materials'] == task['materials'] and result['intake_required'] is True


@pytest.mark.parametrize('bad', ['missing', 'duplicate', 'malformed', 'oversize', 'nan'])
def test_bad_snapshots_do_not_return_partial_or_usable_preview(client, bad):
    task, version = seeded(client)
    if bad == 'missing': task['versions'] = []
    elif bad == 'duplicate': task['versions'].append(copy.deepcopy(version))
    elif bad == 'malformed': task['versions'][0]['configuration'] = []
    elif bad == 'oversize': task['versions'][0]['requirements']['goal'] = 'x' * 8_000_001
    else: task['versions'][0]['configuration']['temperature'] = float('nan')
    # Store can encode historical legacy NaN; the comparison must not accept it.
    main.store.put('task', task['id'], task)
    response = read(client, task, version)
    assert response.status_code in {404, 422}
    assert 'review_token' not in response.text


def test_changes_are_type_strict_and_unknown_field_names_are_not_exposed(client):
    task, version = seeded(client)
    task['configuration']['max_tokens'] = True
    version['configuration']['max_tokens'] = 1
    version['configuration']['PRIVATE-UNKNOWN-KEY'] = 'PRIVATE-VALUE'
    result = preview(task, version)
    fields = next(s['fields'] for s in result['sections'] if s['key'] == 'configuration')
    assert '输出Token上限' in fields and '其他保存字段' in fields
    assert 'PRIVATE' not in json.dumps(result)


def test_nested_nodes_identity_order_edges_and_whole_plan_change_are_distinct():
    a = {'nodes': [{'id': 'outer', 'type': 'iteration', 'config': {'nodes': [{'id': 'child', 'type': 'code', 'config': {'code': 'a'}}], 'edges': []}}], 'edges': []}
    b = copy.deepcopy(a);b['nodes'][0]['config']['nodes'][0]['config']['code'] = 'b'
    value = node_changes(a, b)
    assert value['changed'] == 1 and value['added'] == value['removed'] == 0
    b['nodes'][0]['config']['nodes'][0]['id'] = 'renamed'
    value = node_changes(a, b)
    assert value['added'] == value['removed'] == 1 and value['changed'] == 1
    assert not node_changes({'nodes': [None]}, b)['available']


def test_stale_revision_and_unknown_target_fail_without_values(client):
    task, version = seeded(client)
    assert client.get(f"/api/tasks/{task['id']}/versions/{version['id']}/restore-preview", params={'revision': task['revision'] + 1}).status_code == 409
    assert client.get(f"/api/tasks/{task['id']}/versions/{uuid4()}/restore-preview", params={'revision': task['revision']}).status_code == 404
