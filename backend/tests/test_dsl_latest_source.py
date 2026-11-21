"""Online source reads must use the latest trustworthy import receipt, bound to its baseline."""
import copy

import httpx
import pytest
import yaml

from test_api import client  # noqa: F401  正常API替身夹具
from test_dsl_roundtrip import prepared, changed, apply, confirm_and_build, APP
from app import main
from app.dify import DifyClient
from app.dsl_roundtrip import digest
from app.run_diagnostics import binding

APP2 = '22222222-2222-4222-8222-222222222222'
APP3 = '33333333-3333-4333-8333-333333333333'
MARKER = 'APP2-GENERATION-MARKER'


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('来源谱系检查不得访问真实 HTTP、Dify 请求或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)
    monkeypatch.setattr(DifyClient, 'request', forbidden)


def second_import(client, monkeypatch):
    """APP1 在线读取/合并/构建 → 导入 APP2 成功；APP2 生成基线加独立标记。"""
    task, root = prepared(client)
    current = changed(root)
    async def exported(*args):
        return yaml.safe_dump(current, allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()['task']
    result, _ = apply(client, task)
    assert result.status_code == 200, result.text
    task = confirm_and_build(client, result.json())
    async def imported(*args):
        return {'app_id': APP2, 'status': 'completed'}
    monkeypatch.setattr(DifyClient, 'import_new', imported)
    response = client.post(f"/api/tasks/{task['id']}/import", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = main.get_task(task['id'])
    receipt = task['runs'][-1]
    assert receipt['kind'] == 'import' and (receipt.get('result') or {}).get('app_id') == APP2
    receipt['dsl_baseline']['app']['description'] = MARKER
    receipt['baseline_kind'] = 'generation_proposal'
    main.save_task(task)
    return task, current, root


def post_edit(client, task):
    return client.patch(f"/api/tasks/{task['id']}", json={'requirements': {'rules': '新增要求：保留处理结果'}}).json()


def test_latest_successful_app_is_read_after_local_revision_edit(client, monkeypatch):
    task, current, root = second_import(client, monkeypatch)
    old_reference = main.store.get('dsl_reference', task['dsl_reference']['id'])
    task = post_edit(client, task)
    assert task['dify_app_id'] is None and task['dsl_reference']['source_app_id'] == APP
    seen = []
    async def exported(self, appid):
        seen.append(appid)
        return yaml.safe_dump(current, allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert seen == [APP2]
    task = response.json()['task']
    reference = main.store.get('dsl_reference', task['dsl_reference']['id'])
    assert reference['source_app_id'] == APP2 and reference['source'] == 'dify_draft'
    assert reference['base']['app']['description'] == MARKER
    assert digest(reference['base']) == digest(main.get_task(task['id'])['runs'][-1]['dsl_baseline'])
    assert '较新的应用来源' in reference['baseline_note']
    code = next(node for node in reference['current']['workflow']['graph']['nodes'] if node['id'] == 'code')
    source = next(node for node in current['workflow']['graph']['nodes'] if node['id'] == 'code')
    assert 'upper()' in code['data']['code'] and code['position'] == source['position']
    assert main.store.get('dsl_reference', old_reference['id']) == old_reference
    assert main.get_task(task['id'])['runs'][-1]['dsl_baseline']['app']['description'] == MARKER


def test_recent_trusted_import_is_read_without_prior_reference(client, monkeypatch):
    task, root = prepared(client)
    task['dify_app_id'] = None
    main.save_task(task)
    async def imported(*args):
        return {'app_id': APP2, 'status': 'completed'}
    monkeypatch.setattr(DifyClient, 'import_new', imported)
    response = client.post(f"/api/tasks/{task['id']}/import", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = post_edit(client, response.json())
    assert task.get('dsl_reference') is None and task['dify_app_id'] is None
    seen = []
    async def exported(self, appid):
        seen.append(appid)
        return yaml.safe_dump(changed(root), allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert seen == [APP2]
    reference = main.store.get('dsl_reference', response.json()['task']['dsl_reference']['id'])
    assert reference['source_app_id'] == APP2


def test_known_zero_dispatch_failure_keeps_latest_success(client, monkeypatch):
    task, current, root = second_import(client, monkeypatch)
    task = main.get_task(post_edit(client, task)['id'])
    env = main.store.get('environment', task['environment_id'])
    task['runs'].append({'id': 'failed-355', 'kind': 'import', 'status': 'failed', 'outcome_unknown': False, 'revision': task['revision'], 'environment_id': env['id'], 'environment_binding': binding(env), 'app_type': task['app_type'], 'error': '本次未创建应用'})
    main.save_task(task)
    seen = []
    async def exported(self, appid):
        seen.append(appid)
        return yaml.safe_dump(current, allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert seen == [APP2]


@pytest.mark.parametrize('mutation', ['unknown', 'pending', 'running', 'foreign_env', 'foreign_binding', 'foreign_type', 'malformed_success', 'malformed_baseline', 'missing_baseline'])
def test_unsafe_latest_source_is_rejected_before_export(client, monkeypatch, mutation):
    task, current, root = second_import(client, monkeypatch)
    task = main.get_task(post_edit(client, task)['id'])
    env = main.store.get('environment', task['environment_id'])
    receipt = task['runs'][-1]
    base = {'kind': 'import', 'revision': task['revision'], 'environment_id': env['id'], 'environment_binding': binding(env), 'app_type': task['app_type']}
    if mutation == 'unknown':
        task['runs'].append({**base, 'id': 'new-unknown', 'status': 'unknown', 'outcome_unknown': True, 'result': None})
    elif mutation == 'pending':
        task['runs'].append({**base, 'id': 'new-pending', 'status': 'pending'})
    elif mutation == 'running':
        task['runs'].append({**base, 'id': 'new-running', 'status': 'running'})
    elif mutation == 'foreign_env':
        task['runs'].append({**base, 'id': 'foreign-env', 'status': 'success', 'environment_id': 'other-environment', 'result': {'app_id': APP3}})
    elif mutation == 'foreign_binding':
        task['runs'].append({**base, 'id': 'foreign-binding', 'status': 'success', 'environment_binding': 'other-binding', 'result': {'app_id': APP3}})
    elif mutation == 'foreign_type':
        task['runs'].append({**base, 'id': 'foreign-type', 'status': 'success', 'app_type': 'agent', 'result': {'app_id': APP3}})
    elif mutation == 'malformed_success':
        task['runs'].append({**base, 'id': 'malformed-success', 'status': 'success', 'result': {'app_id': ''}})
    elif mutation == 'malformed_baseline':
        receipt['dsl_baseline'] = {'kind': 'not-an-app'}
    else:
        receipt.pop('dsl_baseline')
        receipt.pop('baseline_kind', None)
        receipt['revision'] = 999
    main.save_task(task)
    before = copy.deepcopy(main.get_task(task['id']))
    references = copy.deepcopy(main.store.list('dsl_reference'))
    seen = []
    async def exported(self, appid):
        seen.append(appid)
        return yaml.safe_dump(current, allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == (409 if mutation == 'pending' else 422), response.text
    assert seen == []
    assert main.get_task(task['id']) == before
    assert main.store.list('dsl_reference') == references


def test_source_change_during_export_is_rejected_without_reference(client, monkeypatch):
    task, current, root = second_import(client, monkeypatch)
    task = main.get_task(post_edit(client, task)['id'])
    env = main.store.get('environment', task['environment_id'])
    references = copy.deepcopy(main.store.list('dsl_reference'))
    calls = []
    async def exported(self, appid):
        calls.append(appid)
        live = main.get_task(task['id'])
        live['runs'].append({'id': 'late-app3', 'kind': 'import', 'status': 'success', 'revision': live['revision'], 'environment_id': env['id'], 'environment_binding': binding(env), 'app_type': live['app_type'], 'result': {'app_id': APP3}, 'dsl_baseline': {'kind': 'app'}})
        main.save_task(live)
        return yaml.safe_dump(current, allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 409, response.text
    assert calls == [APP2]
    assert main.store.list('dsl_reference') == references


def test_explicit_current_app_and_matching_baseline_still_work(client, monkeypatch):
    task, root = prepared(client)
    seen = []
    async def exported(self, appid):
        seen.append(appid)
        return yaml.safe_dump(changed(root), allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert seen == [APP]
    reference = main.store.get('dsl_reference', response.json()['task']['dsl_reference']['id'])
    assert reference['source_app_id'] == APP and digest(reference['base']) == digest(root)


def legacy_capture(client, monkeypatch):
    task, root = prepared(client)
    calls = []
    async def exported(self, appid):
        calls.append(appid)
        return yaml.safe_dump(changed(root), allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    return response.json()['task'], calls


def test_legacy_reference_origin_change_blocks_before_export(client, monkeypatch):
    task, calls = legacy_capture(client, monkeypatch)
    env = main.store.get('environment', task['environment_id'])
    env['base_url'] = 'https://different-origin.invalid'
    main.store.put('environment', env['id'], env)
    before = copy.deepcopy(main.get_task(task['id']))
    references = copy.deepcopy(main.store.list('dsl_reference'))
    count = len(calls)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 422, response.text
    assert len(calls) == count
    assert main.get_task(task['id']) == before
    assert main.store.list('dsl_reference') == references


@pytest.mark.parametrize('result', [[], ['not-a-map']])
def test_malformed_legacy_import_result_is_rejected_without_export(client, monkeypatch, result):
    task, calls = legacy_capture(client, monkeypatch)
    task = post_edit(client, task)
    live = main.get_task(task['id'])
    env = main.store.get('environment', live['environment_id'])
    live['runs'].append({'id': 'malformed-newer', 'kind': 'import', 'status': 'success', 'revision': live['revision'], 'environment_id': env['id'], 'environment_binding': binding(env), 'app_type': live['app_type'], 'result': result})
    main.save_task(live)
    before = copy.deepcopy(main.get_task(task['id']))
    references = copy.deepcopy(main.store.list('dsl_reference'))
    count = len(calls)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 422, response.text
    assert len(calls) == count
    assert main.get_task(task['id']) == before
    assert main.store.list('dsl_reference') == references


@pytest.mark.parametrize('contradiction', ['binding', 'type'])
def test_contradicting_legacy_receipt_is_not_trusted(client, monkeypatch, contradiction):
    task, calls = legacy_capture(client, monkeypatch)
    task = post_edit(client, task)
    live = main.get_task(task['id'])
    run = live['runs'][-1]
    if contradiction == 'binding':
        run['environment_binding'] = 'other-binding'
    else:
        run['app_type'] = 'agent'
    main.save_task(live)
    before = copy.deepcopy(main.get_task(task['id']))
    references = copy.deepcopy(main.store.list('dsl_reference'))
    count = len(calls)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 422, response.text
    assert len(calls) == count
    assert main.get_task(task['id']) == before
    assert main.store.list('dsl_reference') == references


def test_unchanged_legacy_reference_still_reads_without_binding(client, monkeypatch):
    task, calls = legacy_capture(client, monkeypatch)
    task = post_edit(client, task)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert calls == [APP, APP]
    reference = main.store.get('dsl_reference', response.json()['task']['dsl_reference']['id'])
    assert reference['source_app_id'] == APP


def test_flagged_success_candidate_is_not_trusted(client, monkeypatch):
    task, current, root = second_import(client, monkeypatch)
    live = main.get_task(task['id'])
    live['runs'][-1]['outcome_unknown'] = True
    main.save_task(live)
    task = post_edit(client, task)
    before = copy.deepcopy(main.get_task(task['id']))
    references = copy.deepcopy(main.store.list('dsl_reference'))
    calls = []
    async def exported(self, appid):
        calls.append(appid)
        return yaml.safe_dump(current, allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 422, response.text
    assert calls == []
    assert main.get_task(task['id']) == before
    assert main.store.list('dsl_reference') == references


def test_flagged_legacy_reference_receipt_is_rejected(client, monkeypatch):
    task, calls = legacy_capture(client, monkeypatch)
    task = post_edit(client, task)
    live = main.get_task(task['id'])
    env = main.store.get('environment', live['environment_id'])
    run = live['runs'][-1]
    run.update(outcome_unknown=True, environment_binding=binding(env), app_type=live['app_type'])
    main.save_task(live)
    before = copy.deepcopy(main.get_task(task['id']))
    references = copy.deepcopy(main.store.list('dsl_reference'))
    count = len(calls)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 422, response.text
    assert len(calls) == count
    assert main.get_task(task['id']) == before
    assert main.store.list('dsl_reference') == references


def test_explicit_current_app_with_malformed_history_is_rejected(client, monkeypatch):
    task, root = prepared(client)
    task['runs'][0]['result'] = ['broken-map']
    main.save_task(task)
    calls = []
    async def exported(self, appid):
        calls.append(appid)
        return yaml.safe_dump(changed(root), allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    before = copy.deepcopy(main.get_task(task['id']))
    references = copy.deepcopy(main.store.list('dsl_reference'))
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 422, response.text
    assert calls == []
    assert main.get_task(task['id']) == before
    assert main.store.list('dsl_reference') == references
