import copy
import hashlib
import io
import json
import zipfile

import pytest

from test_api import client, approved, create_env, forbid_api_external_calls
from app import main
from test_agent_plan import prepare as prepare_agent


def built(client, mode='workflow'):
    if mode == 'agent':
        task = prepare_agent(client)
        response = client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':'configuration'})
        assert response.status_code == 200, response.text
    else:
        task = approved(client, app_type=mode)
    result = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert result.status_code == 200, result.text
    return result.json()


def bundle(client, task, **params):
    return client.get(f"/api/tasks/{task['id']}/delivery-bundle", params={'revision': task['revision'], **params})


def unpack(response):
    assert response.status_code == 200, response.text if response.status_code != 200 else ''
    assert response.headers['content-type'] == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files['manifest.json'])
    assert set(files) == set(manifest['files']) | {'manifest.json'}
    for name, expected in manifest['files'].items():
        assert '/' not in name and '\\' not in name
        assert len(files[name]) == expected['bytes']
        assert hashlib.sha256(files[name]).hexdigest() == expected['sha256']
    return files, manifest


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat', 'agent'])
def test_same_saved_revision_and_original_artifact_bytes_for_all_types(client, mode, monkeypatch):
    task = built(client, mode); tid = task['id']
    before = copy.deepcopy(main.store.get('task', tid)); budget = main.store.get('task_budget', tid)
    def forbidden(*args, **kwargs): pytest.fail('Bundle must not decrypt or write any stored data')
    monkeypatch.setattr(main.store, 'secret', forbidden)
    monkeypatch.setattr(main.store, 'put', forbidden)
    monkeypatch.setattr(main.store, 'put_with_secrets', forbidden)
    response = bundle(client, task); files, manifest = unpack(response)
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-sierra-revision'] == str(task['revision'])
    assert manifest['revision'] == task['revision'] and manifest['app_type'] == mode
    assert manifest['task_id'] == tid and manifest['artifact_verification'] == 'static_only'
    assert manifest['artifact_integrity_basis'] == 'recorded_build_sha256'
    artifact_name = f"dify-{mode}-r{task['revision']}.yaml"
    assert files[artifact_name] == main.artifact_path(task).read_bytes()
    assert task['artifact']['sha256'] == hashlib.sha256(files[artifact_name]).hexdigest()
    report = files[f"report-r{task['revision']}.md"].decode()
    assert f"类型：{mode}；版本：r{task['revision']}" in report and '尚无匹配的真实导入记录' in report
    assert all(manifest[field] is False for field in ['platform_checked', 'business_verified', 'network_requested', 'task_changed'])
    assert main.store.get('task', tid) == before and main.store.get('task_budget', tid) == budget


def test_old_revision_and_missing_or_invalid_artifact_never_return_archive(client):
    task = approved(client)
    assert bundle(client, task).status_code == 422
    task = built(client)
    assert bundle(client, task, revision=task['revision'] + 1).status_code == 409
    main.artifact_path(task).unlink()
    assert bundle(client, task).status_code == 404


@pytest.mark.parametrize('change', ['unconfirmed', 'stale', 'invalid'])
def test_changed_saved_conditions_require_rebuild(client, change):
    task = built(client)
    if change == 'unconfirmed': task['configuration_confirmed'] = False
    if change == 'stale': task['plan_stale'] = True
    if change == 'invalid': task['artifact']['validation']['valid'] = False
    main.store.put('task', task['id'], task)
    assert bundle(client, task).status_code == 422


def test_changed_file_hash_rejected_without_rewriting_artifact(client):
    task = built(client); path = main.artifact_path(task)
    changed = path.read_bytes() + b'\n# changed after build\n'; path.write_bytes(changed)
    response = bundle(client, task)
    assert response.status_code == 409 and path.read_bytes() == changed


def test_legacy_artifact_exports_without_claiming_original_build_integrity(client):
    task = built(client); task['artifact'].pop('sha256'); main.store.put('task', task['id'], task)
    _, manifest = unpack(bundle(client, task))
    assert manifest['artifact_integrity_basis'] == 'legacy_export_bytes_only'
    assert 'sha256' not in main.store.get('task', task['id'])['artifact']


@pytest.mark.parametrize('location', ['artifact', 'requirements', 'manifest'])
def test_credentials_refused_without_partial_files_or_error_echo(client, location):
    task = built(client); secret = 'app-UNSAFE-SYNTHETIC-CREDENTIAL'
    if location == 'artifact':
        path = main.artifact_path(task); path.write_text(path.read_text('utf-8') + '\n# '+secret, 'utf-8')
    elif location == 'requirements': task['requirements']['goal'] = 'Bearer UNSAFESYNTHETICCREDENTIAL0123'
    else: task['configuration']['mock_dependencies'] = ['sk-UNSAFE-SYNTHETIC-CREDENTIAL']
    main.store.put('task', task['id'], task)
    response = bundle(client, task)
    assert response.status_code == 422 and 'UNSAFE' not in response.text
    assert response.headers['content-type'] == 'application/json'


def test_no_environment_credentials_or_raw_materials_enter_archive(client, monkeypatch):
    task = built(client); env = create_env(client)
    task['environment_id'] = env['id']; main.store.put('task', task['id'], task)
    main.store.put_with_secrets('environment', env['id'], main.store.get('environment', env['id']), {'service_api_key':'INTERNAL-RUNTIME-KEY-NEVER-EXPORTED'})
    def no_decrypt(*args, **kwargs): pytest.fail('Must only inspect metadata')
    monkeypatch.setattr(main.store, 'secret', no_decrypt)
    files, _ = unpack(bundle(client, task))
    assert len(files) == 4 and all(b'INTERNAL-RUNTIME-KEY' not in raw for raw in files.values())


def test_chatflow_report_exports_only_safe_saved_replies_from_current_attempt(client):
    task = built(client, 'advanced-chat')
    task['dify_app_id'] = 'current-synthetic-app'
    cases = []
    runs = []
    markers = {
        'safe': '来自当前试跑的回答',
        'secret': 'Bearer SYNTHETICPRETENDKEY01234567890',
        'oversized': '超限正文' * 1500,
    }
    for key, answer in markers.items():
        case = {'id': key, 'name': key, 'input': {'query': key},
                'expectation': {'mode': 'manual', 'description': '核对公开合成回答'}}
        cases.append(case)
        runs.append({
            'id': f'run-{key}', 'kind': 'run', 'revision': task['revision'],
            'environment_id': task['environment_id'], 'app_id': task['dify_app_id'],
            'status': 'success', 'input': case['input'], 'test_case': case,
            'result': {'answer': answer, 'metadata': {'wire': '不导出原响应附加字段'}},
        })
    cases.append({'id': 'continuation', 'name': '同会话补号', 'input': {'query': '查订单'},
                  'expectation': {'mode': 'manual', 'description': '首轮需追问'},
                  'followups': [{'input': {'query': 'DEMO-42'},
                                 'expectation': {'mode': 'manual', 'description': '核对合成订单'}}]})
    continuation = cases[-1]
    runs.append({
        **runs[0], 'id': 'run-continuation', 'status': 'unknown',
        'input': continuation['input'], 'test_case': continuation,
        'result': {'conversation_case': True, 'complete': False, 'conversation_id': 'local-conversation',
                   'turns': [{'index': 1, 'status': 'success', 'input': continuation['input'],
                              'expectation': continuation['expectation'], 'source_conversation_id': None,
                              'result': {'answer': '请提供订单号。', 'conversation_id': 'local-conversation'}}],
                   'pending_turn': {'index': 2, 'result': {'answer': '未核对的补号正文'}}},
    })
    runs.append({**runs[0], 'id': 'foreign-app', 'app_id': 'different-synthetic-app',
                 'result': {'answer': '旧应用的回复'}})
    task.update(test_cases=cases, runs=runs)
    main.store.put('task', task['id'], task)
    before = main.get_task(task['id'])

    files, _ = unpack(bundle(client, task))
    report = files[f"report-r{task['revision']}.md"].decode()
    encoded = report.split('## 当前 Chatflow 样例实际回复', 1)[1].split('```json\n', 1)[1].split('\n```', 1)[0]
    evidence = json.loads(encoded)
    assert [row['run_id'] for row in evidence] == ['run-safe', 'run-secret', 'run-oversized', 'run-continuation']
    assert [row['turns'] for row in evidence] == [
        [{'index': 1, 'state': 'saved', 'answer': markers['safe']}],
        [{'index': 1, 'state': 'withheld'}],
        [{'index': 1, 'state': 'over_limit'}],
        [{'index': 1, 'state': 'saved', 'answer': '请提供订单号。'}],
    ]
    assert evidence[-1]['status'] == 'unknown'
    assert all(marker not in report for marker in (markers['secret'], '超限正文', '旧应用的回复',
                                                   '未核对的补号正文', '不导出原响应附加字段'))
    assert main.get_task(task['id']) == before


def test_path_outside_task_is_refused_before_read(client, tmp_path):
    task = built(client); external = tmp_path / 'outside.yaml'; external.write_text('DO-NOT-READ', 'utf-8')
    task['artifact']['filename'] = str(external); main.store.put('task', task['id'], task)
    response = bundle(client, task)
    assert response.status_code == 422 and 'DO-NOT-READ' not in response.text


def test_same_revision_fact_change_during_report_does_not_return_mixed_snapshot(client, monkeypatch):
    task = built(client); original = main.report
    def changing_report(item_id):
        response = original(item_id)
        current = main.get_task(item_id); current['status'] = 'paused'; main.store.put('task', item_id, current)
        return response
    monkeypatch.setattr(main, 'report', changing_report)
    assert bundle(client, task).status_code == 409


def test_unknown_publication_mock_todos_and_budget_reserve_remain_in_report(client):
    task = built(client); task['configuration']['mock_dependencies'] = ['合成订单接口']
    task['dify_app_id'] = 'saved-current-app'
    task['runs'] = [{'id':'unknown-publish','kind':'publish','status':'unknown','revision':task['revision'],
        'environment_id':None,'app_id':task['dify_app_id'],'result':{}}]
    main.store.put('task', task['id'], task)
    ledger = main.budgets.get(task['id']); ledger['entries'] = [{'id':'unknown-cost','status':'unknown','reserved_usd':'0.0188541','charged_usd':None}]
    # Minimal historical ledger fields used by the existing report grouping.
    ledger['entries'][0].update(kind='planning',created_at=main.now(),cost_basis='reserved_unknown_usage',usage={})
    main.store.put('task_budget', task['id'], ledger)
    before = copy.deepcopy(ledger)
    files, manifest = unpack(bundle(client, task))
    report = files[f"report-r{task['revision']}.md"].decode()
    assert '禁止直接重发' in report and '合成订单接口' in report and '0.0188541' in report
    assert manifest['mock_dependencies'] == ['合成订单接口']
    assert main.store.get('task_budget', task['id']) == before
