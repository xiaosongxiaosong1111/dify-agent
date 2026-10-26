import copy
import json
from uuid import uuid4

import pytest
import httpx
from test_api import client, approved, code_only_plan, restore_payload
from app import main
from app.storage import Store
from app.version_restore import preview, node_changes


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('AT-24 隔离检查不得访问真实 HTTP 或调用模型')

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


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


def test_restore_reconfirm_rebuild_keeps_history_but_never_revives_old_pass(client, monkeypatch):
    task = approved(client)
    tid = task['id']
    task['workflow_plan'] = code_only_plan()
    task['dify_app_id'] = 'fixture-only-original-app'
    case = {'id': 'fixed-case', 'name': '固定回归样例', 'required': True,
            'input': {'query': 'hello'}, 'expectation': {'mode': 'equals', 'expected': 'hello'}}
    task['test_cases'] = [case]
    task['runs'] = [{'id': str(uuid4()), 'kind': 'run', 'status': 'success',
                     'revision': task['revision'], 'environment_id': None,
                     'app_id': 'fixture-only-original-app',
                     'test_case': copy.deepcopy(case), 'input': copy.deepcopy(case['input']),
                     'evaluation': {'status': 'passed', 'mode': 'equals'}}]
    main.store.put('task', tid, task)
    response = client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    version = copy.deepcopy(task['versions'][-1])
    old_artifact = main.DATA_ROOT / tid / task['artifact']['filename']
    old_bytes = old_artifact.read_bytes()
    assert client.get(f'/api/tasks/{tid}/acceptance').json()['all_required_passed']

    response = client.patch(f'/api/tasks/{tid}', json={'requirements': {'goal': '恢复前的新目标'}})
    assert response.status_code == 200, response.text
    task = response.json()
    changed_plan = code_only_plan()
    changed_plan['nodes'][1]['config']['code'] += '\n# 恢复前的修改'
    response = client.post(f'/api/tasks/{tid}/plan', json={'revision': task['revision'], 'plan': changed_plan})
    assert response.status_code == 200, response.text
    task = response.json()
    for kind in ('requirements', 'configuration'):
        response = client.post(f'/api/tasks/{tid}/confirm', json={'kind': kind, 'revision': task['revision']})
        assert response.status_code == 200, response.text
        task = response.json()
    task['dify_app_id'] = 'fixture-only-bound-app'
    main.store.put('task', tid, task)
    before = copy.deepcopy(task)
    ledger = copy.deepcopy(main.store.get('task_budget', tid))
    payload = restore_payload(client, tid, version['id'])
    response = client.post(f'/api/tasks/{tid}/restore', json=payload)
    assert response.status_code == 200, response.text
    restored = response.json()
    revision = restored['revision']
    assert revision == before['revision'] + 1
    assert restored['app_type'] == before['app_type'] == 'workflow'
    assert restored['requirements'] == version['requirements']
    assert restored['workflow_plan'] == version['workflow_plan']
    assert restored['test_cases'] == [case]
    assert not restored['requirements_confirmed'] and not restored['configuration_confirmed']
    assert restored['artifact'] is None and restored['dify_app_id'] is None
    assert restored['confirmations'] == before['confirmations']
    assert restored['runs'] == before['runs']
    assert restored['versions'][:-1] == before['versions']
    saved_current = restored['versions'][-1]
    assert saved_current['label'] == '恢复前保存' and saved_current['revision'] == before['revision']
    assert saved_current['requirements'] == before['requirements']
    assert saved_current['workflow_plan'] == changed_plan

    # Reopen only the fixture database: persistence must not depend on response objects.
    monkeypatch.setattr(main, 'store', Store(main.store.root))
    assert client.get(f'/api/tasks/{tid}').json() == restored
    for kind in ('requirements', 'configuration'):
        assert client.post(f'/api/tasks/{tid}/confirm', json={'kind': kind, 'revision': before['revision']}).status_code == 409
    assert client.post(f'/api/tasks/{tid}/build', json={'revision': revision}).status_code == 422
    assert client.get(f'/api/tasks/{tid}/artifact').status_code == 404
    assert client.post(f'/api/tasks/{tid}/confirm', json={'kind': 'configuration', 'revision': revision}).status_code == 422
    assert client.get(f'/api/tasks/{tid}').json() == restored

    for kind in ('requirements', 'configuration'):
        response = client.post(f'/api/tasks/{tid}/confirm', json={'kind': kind, 'revision': revision})
        assert response.status_code == 200, response.text
    response = client.post(f'/api/tasks/{tid}/build', json={'revision': revision})
    assert response.status_code == 200, response.text
    rebuilt = response.json()
    assert rebuilt['artifact']['revision'] == revision
    assert rebuilt['artifact']['verification'] == 'static_only'
    assert rebuilt['dify_app_id'] is None and rebuilt['runs'] == before['runs']
    assert rebuilt['confirmations'][-2:][0]['revision'] == revision
    assert [row['kind'] for row in rebuilt['confirmations'][-2:]] == ['requirements', 'configuration']
    assert all(row['revision'] == revision for row in rebuilt['confirmations'][-2:])
    assert rebuilt['versions'][:len(restored['versions'])] == restored['versions']
    summary = client.get(f'/api/tasks/{tid}/acceptance').json()
    assert summary['revision'] == revision and not summary['all_required_passed']
    assert summary['required']['passed'] == 0 and summary['required']['not_run'] == 1
    assert summary['cases'][0]['run_id'] is None
    assert old_artifact.read_bytes() == old_bytes
    assert main.store.get('task_budget', tid) == ledger
    # The original preview remains consumed even after confirmation and build.
    persisted = copy.deepcopy(main.store.get('task', tid))
    assert client.post(f'/api/tasks/{tid}/restore', json=payload).status_code == 409
    assert main.store.get('task', tid) == persisted


def test_restore_keeps_credentials_and_policy_and_clears_historical_conflict_confirmation(client):
    task, version = seeded(client)
    task['plan_review_required'] = True
    task['intake_required'] = True
    task['environment_id'] = 'fixture-current-environment'
    historical = task['versions'][0]
    historical['environment_id'] = 'fixture-historical-environment'
    historical['conflict_review'] = {'confirmation': {'revision': version['revision'], 'accepted': True}}
    historical['plan_review_required'] = False
    historical['requirements_confirmed'] = True
    historical['configuration_confirmed'] = True
    historical['dify_app_id'] = 'fixture-historical-app'
    for kind, identity, key in [('environment', 'fixture-historical-environment', 'console_token'),
                                ('provider', 'fixture-provider', 'api_key')]:
        main.store.put(kind, identity, {'id': identity, 'name': '隔离连接'})
        main.store.set_secret(identity, key, 'fixture-current-secret')
    records = {kind: copy.deepcopy(main.store.list(kind)) for kind in ('environment', 'provider')}
    with main.store.connect() as connection:
        secrets = connection.execute('SELECT id, value FROM secrets ORDER BY id').fetchall()
    original_history = copy.deepcopy(task['versions'])
    main.store.put('task', task['id'], task)
    response = client.post(f"/api/tasks/{task['id']}/restore", json=restore_payload(client, task['id'], version['id']))
    assert response.status_code == 200, response.text
    restored = response.json()
    assert restored['environment_id'] == 'fixture-historical-environment'
    assert restored['plan_review_required'] is True and restored['intake_required'] is True
    assert restored['conflict_enabled'] is True
    assert restored['conflict_review']['confirmation'] == {}
    assert restored['versions'][:-1] == original_history
    assert not restored['requirements_confirmed'] and not restored['configuration_confirmed']
    assert restored['artifact'] is None and restored['dify_app_id'] is None
    assert 'fixture-current-secret' not in response.text
    assert all(main.store.list(kind) == rows for kind, rows in records.items())
    with main.store.connect() as connection:
        assert connection.execute('SELECT id, value FROM secrets ORDER BY id').fetchall() == secrets


@pytest.mark.parametrize('pending', ['run', 'budget'])
def test_restore_blocks_pending_work_without_mutating_task_or_ledger(client, pending):
    task, version = seeded(client)
    payload = restore_payload(client, task['id'], version['id'])
    if pending == 'run':
        task['runs'] = [{'id': str(uuid4()), 'kind': 'run', 'status': 'pending', 'revision': task['revision']}]
        main.store.put('task', task['id'], task)
    else:
        ledger = main.store.get('task_budget', task['id']) or {}
        ledger['entries'] = [{'id': 'fixture-reservation', 'status': 'reserved'}]
        main.store.put('task_budget', task['id'], ledger)
    before = copy.deepcopy(main.store.get('task', task['id']))
    ledger = copy.deepcopy(main.store.get('task_budget', task['id']))
    assert read(client, task, version).status_code == 200
    response = client.post(f"/api/tasks/{task['id']}/restore", json=payload)
    assert response.status_code == 409 and '任务正在执行' in response.json()['detail']
    assert main.store.get('task', task['id']) == before
    assert main.store.get('task_budget', task['id']) == ledger
