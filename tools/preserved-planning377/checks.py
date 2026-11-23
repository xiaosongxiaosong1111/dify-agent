"""Public, real-behaviour checks for preserved-planning377.  No real data/HTTP."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT / 'backend'))

import common
import worker
import tool

PASS = []


def ok(name):
    PASS.append(name)
    print('PASS ' + name)


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _run_public(root, mode):
    out = Path(root) / mode
    done = subprocess.run([sys.executable, str(HERE / 'worker.py'), mode, str(out)],
                          cwd=str(PROJECT), capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise AssertionError(mode + ' worker failed:\n' + done.stdout + '\n' + done.stderr)
    result = json.loads((out / 'result.json').read_text('utf-8'))
    return result, out


def _reader(out):
    return common.ReadOnly(out / 'data')


def _synthetic_plan(merged):
    return {
        'schema_version': 1, 'batch_id': common.BATCH, 'approval_state': 'pending',
        'approval_phrase': common.APPROVAL_PHRASE,
        'approval_question_suffix': common.APPROVAL_SUFFIX,
        'source_batch': 'autonomous-dual375', 'regrant': copy.deepcopy(tool.REGRANT),
        'limits': copy.deepcopy(common.LIMITS),
        'new_conservative_upper': copy.deepcopy(common.UPPER),
        'per_call_reserve_usd': common.PER_CALL_USD,
        'model_total_reserve_usd': common.PER_MODEL_TOTAL_USD,
        'model_estimate_book_upper_usd': common.MODEL_BOOK_UPPER_USD,
        'billing_hard_cap': False, 'wall_seconds': common.WALL_SECONDS,
        'max_model_http': common.MAX_MODEL_HTTP,
        'output_tokens': common.OUTPUT_TOKENS,
        'timeout_seconds': common.TIMEOUT_SECONDS,
        'target_task_id': common.TARGET_TASK,
        'target_task_revision': common.TARGET_REVISION,
        'target_task_sha256': 'a' * 64, 'target_budget_sha256': 'b' * 64,
        'target_task_shape': copy.deepcopy(tool.TARGET_SHAPE),
        'execution_limits_present': False, 'initial_no_graph': True,
        'initial_execution_policy_none': True,
        'history_prefix': {
            'messages': {'count': 0, 'sha256': 'c' * 64},
            'versions': {'count': 0, 'sha256': 'c' * 64},
            'planning_runs': {'count': 0, 'sha256': 'c' * 64},
            'intake_history': {'count': 0, 'sha256': 'c' * 64},
            'runs': {'count': 0, 'sha256': 'c' * 64},
            'interview_attempts': {'present': False, 'count': 0, 'sha256': 'd' * 64},
        },
        'intake_review_sha256': 'e' * 64, 'decision_report_sha256': 'f' * 64,
        'cases_sha256': '0' * 64, 'configuration_sha256': '1' * 64,
        'requirements_sha256': '2' * 64,
        'provider_id': common.PROVIDER_ID, 'provider_sha256': '3' * 64,
        'provider_model': common.PROVIDER_MODEL,
        'provider_protocol': common.PROVIDER_PROTOCOL,
        'environment_id': common.ENVIRONMENT_ID,
        'environment_sha256': '4' * 64,
        'environment_identity_sha256': '5' * 64,
        'expected_counts': copy.deepcopy(common.EXPECTED_COUNTS),
        'runtime_build': common.RUNTIME_BUILD,
        'runtime_version': common.RUNTIME_VERSION,
        'runtime_file_count': common.RUNTIME_FILE_COUNT,
        'runtime_pid_observed': common.RUNTIME_PID_OBSERVED,
        'runtime_manifest_sha256': '6' * 64,
        'runtime_process_sha256': '7' * 64,
        'backend_path': str(PROJECT / '.runtime' / 'snapshots'
                            / common.RUNTIME_BUILD / 'backend'),
        'runtime_process_observed': [],
        'protected_data': {}, 'protected_isolated': {},
        'protected_files': merged,
        'protected_files_sha256': common.digest(merged),
        'protected_count': common.TOTAL_SEALED_COUNT,
        'old_375_plan_sha256': common.OLD_375_PLAN_SHA,
        'seal_index_sha256': common.SEAL_INDEX_SHA, 'old_375_stop': {},
        'source_pins': {directory: {'commit': 'a' * 40,
                                    'files': list(spec['files'])}
                        for directory, spec in common.SOURCE_PINS.items()},
        'source_file_sha256': {directory + '/' + name: 'b' * 64
                               for directory, spec in common.SOURCE_PINS.items()
                               for name in spec['files']},
        'package_files': {name: 'c' * 64 for name in common.PACKAGE_FILES},
        'proposal_doc': 'tools/preserved-planning377/README.md',
        'proposal_sha256': 'd' * 64, 'created_at': tool.now(),
    }


def test_success(root):
    result, out = _run_public(root, 'success')
    assert result['state'] == 'passed', result
    assert result['model_http_started'] == 1 and result['physical_http'] == 0, result
    assert result['stage_counts'] == {'original': 1}
    assert result['failure_reason'] is None
    assert result['workflow_plan_saved'] is True
    assert result['revision_before'] == 6 and result['revision_after'] == 7
    assert result['ledger']['before_entries'] == 3 and result['ledger']['after_entries'] == 4
    entry = result['ledger']['new_entry']
    assert entry['status'] == 'settled' and entry['cost_basis'] == 'reported_usage'
    assert entry['charged_usd'] is not None
    assert result['usage']['completion_tokens'] == 300
    assert result['execution_limits_absent'] is True
    response = result['model_response']
    assert response and common.sha_bytes((out / response['file']).read_bytes()) == response['sha256']
    reader = _reader(out)
    task = reader.get('task', result['target_task_id'])
    assert common.digest(task['workflow_plan']) == result['candidate_sha256']
    assert task['plan_source'] == 'model' and task['revision'] == 7
    assert task['status'] == 'configuration' and task['configuration_confirmed'] is False
    assert len(task['messages']) == 8 and len(task['versions']) == 6
    assert len(task['planning_runs']) == 2
    stored_budget = reader.get('task_budget', task['id'])
    assert common.digest(stored_budget['entries'][:3]) == result['ledger']['before_sha256']
    assert reader.get('execution_limits', task['id']) is None
    assert (out / 'review-source-original.json').is_file()
    assert not (out / 'stop.json').exists()
    # Root may arrive later: the saved graph and full text remain readable.
    again = _reader(out).get('task', task['id'])
    assert common.digest(again['workflow_plan']) == result['candidate_sha256']
    assert (out / response['file']).is_file()
    assert result['root_review'] == 'public_synthetic_not_reviewed'
    assert result['semantic_reviewed'] is False and result['human_signoff'] is False
    ok('success saves complete candidate, usage, source and exits')


def test_invalid_json(root):
    result, out = _run_public(root, 'invalid_json')
    assert result['state'] == 'stopped', result
    assert result['model_http_started'] == 1 and result['physical_http'] == 0
    assert result['stage_counts'] == {'original': 1}
    assert result['workflow_plan_saved'] is False
    assert result['revision_after'] == 6
    assert result['ledger']['after_entries'] == 4
    assert result['model_response'] and (out / result['model_response']['file']).is_file()
    assert result['stop_reason'] and result['failure_reason']
    assert _reader(out).get('task', result['target_task_id'])['workflow_plan'] is None
    ok('bad JSON stops after one HTTP and keeps the original graph')


def test_needs_decision(root):
    result, out = _run_public(root, 'needs_decision')
    assert result['state'] == 'stopped' and result['model_http_started'] == 1
    assert result['stage_counts'] == {'original': 1}
    assert result['workflow_plan_saved'] is False
    assert result['planning_run'] and result['planning_run']['decision_report']
    assert result['planning_run']['stop_reason'] == 'needs_decision'
    assert result['failure_reason']
    assert _reader(out).get('task', result['target_task_id'])['workflow_plan'] is None
    ok('real needs_decision is preserved, not swallowed as success')


def test_unknown_usage(root):
    result, out = _run_public(root, 'unknown_usage')
    assert result['state'] == 'stopped' and result['model_http_started'] == 1
    assert result['stage_counts'] == {'original': 1}
    assert result['workflow_plan_saved'] is False
    entry = result['ledger']['new_entry']
    assert entry['status'] == 'unknown' and entry['charged_usd'] is None
    assert result['failure_reason']
    assert _reader(out).get('task', result['target_task_id'])['workflow_plan'] is None
    ok('unknown usage is persisted as unknown with no retry')


def test_boundary_rejections():
    provider = copy.deepcopy(worker.PUBLIC_PROVIDER_OBJECT)
    key = common.PUBLIC_KEY
    record = {'responses': {}, 'quotes': {}}
    stop_path = Path(tempfile.mkdtemp()) / 'stop.json'
    messages = [{'role': 'user', 'content': '公开替身协议'}]
    kwargs = {'max_tokens': 6000, 'timeout': 120, 'json_mode': True,
              'stream': False, 'allow_images': False}

    def request(url, body_messages):
        body = {'model': provider['model'], 'messages': body_messages,
                'max_tokens': 6000, 'stream': False,
                'thinking': {'type': 'disabled'},
                'response_format': {'type': 'json_object'}}
        class Req:
            method = 'POST'
            headers = {'authorization': 'Bearer ' + key}
            content = json.dumps(body).encode()
        Req.url = url
        return Req()

    boundary = worker.Boundary(provider, key, record, lambda: None, stop_path, False)
    boundary.begin()
    boundary.prepare(provider, key, messages, kwargs)
    boundary.admit(request('https://api.deepseek.com/chat/completions', messages))
    assert boundary.calls['original'] == 1
    try:
        boundary.prepare(provider, key, messages, kwargs)
        raise AssertionError('second model call was accepted')
    except RuntimeError:
        pass
    second = worker.Boundary(provider, key, record, lambda: None, stop_path, False)
    second.begin()
    second.prepare(provider, key, messages, kwargs)
    try:
        second.admit(request('https://api.deepseek.com/v1/chat/completions', messages))
        raise AssertionError('other endpoint was accepted')
    except RuntimeError:
        pass
    sync = worker.Boundary(provider, key, record, lambda: None, stop_path, False)
    sync.begin()
    sync.prepare(provider, key, messages, kwargs)
    wrong = request('https://api.deepseek.com/chat/completions', messages)
    wrong.headers = {'authorization': 'Bearer WRONG'}
    try:
        sync.admit(wrong)
        raise AssertionError('wrong credential was accepted')
    except RuntimeError:
        pass
    dify = worker.Boundary(provider, key, record, lambda: None, stop_path, False)
    dify.begin()
    dify.prepare(provider, key, messages, kwargs)
    try:
        dify.admit(request('https://public-dify.invalid/v1/chat-messages', messages))
        raise AssertionError('Dify endpoint was accepted')
    except RuntimeError:
        pass
    try:
        worker.forbidden_sync()
        raise AssertionError('synchronous HTTP was accepted')
    except RuntimeError:
        pass
    wrong_provider = worker.Boundary(provider, key, record, lambda: None, stop_path, False)
    wrong_provider.begin()
    try:
        wrong_provider.prepare({**provider, 'model': 'other-model'}, key, messages, kwargs)
        raise AssertionError('wrong provider was accepted')
    except RuntimeError:
        pass
    ok('second call, other endpoint, Dify, sync HTTP and wrong provider/credential are rejected')


def test_guard_tamper():
    old_task = worker._public_task()
    old_budget = worker._public_budget()
    candidates = {common.digest({'nodes': [], 'edges': []})}
    base_old = copy.deepcopy(old_task)
    base_old['state_sequence'] = 5
    valid = copy.deepcopy(base_old)
    worker._check_task_value(common.PUBLIC_TASK, base_old, valid, candidates)
    valid_budget = copy.deepcopy(old_budget)
    worker._check_budget_value(common.PUBLIC_TASK, old_budget, valid_budget, common.PUBLIC_PROVIDER)
    bad_values = []
    value = copy.deepcopy(valid); value['messages'][0]['content'] = 'tampered'; bad_values.append(value)
    value = copy.deepcopy(valid); value['id'] = 'other'; bad_values.append(value)
    value = copy.deepcopy(valid); value['revision'] = 8; bad_values.append(value)
    value = copy.deepcopy(valid); value['workflow_plan'] = {'nodes': []}; bad_values.append(value)
    value = copy.deepcopy(valid); value['interview_attempts'] = []; bad_values.append(value)
    value = copy.deepcopy(valid); value['requirements']['goal'] = 'changed'; bad_values.append(value)
    value = copy.deepcopy(valid); value['state_sequence'] = 4; bad_values.append(value)
    for value in bad_values:
        try:
            worker._check_task_value(common.PUBLIC_TASK, base_old, value, candidates)
            raise AssertionError('tampered Task was accepted')
        except RuntimeError:
            pass
    bad_budgets = []
    value = copy.deepcopy(valid_budget); value['limit_usd'] = '0.700'; bad_budgets.append(value)
    value = copy.deepcopy(valid_budget); value['entries'][0]['charged_usd'] = '0.1'; bad_budgets.append(value)
    value = copy.deepcopy(valid_budget)
    value['entries'].append({'id': 'x', 'operation_id': 'y', 'revision': 6, 'kind': 'plan',
                             'provider_id': common.PUBLIC_PROVIDER,
                             'reserved_usd': '0.200', 'status': 'reserved'})
    bad_budgets.append(value)
    for value in bad_budgets:
        try:
            worker._check_budget_value(common.PUBLIC_TASK, old_budget, value,
                                       common.PUBLIC_PROVIDER)
            raise AssertionError('tampered budget was accepted')
        except RuntimeError:
            pass

    from app.storage import Store
    folder = Path(tempfile.mkdtemp())
    try:
        store = Store(folder)
        store.put('provider', common.PUBLIC_PROVIDER, copy.deepcopy(worker.PUBLIC_PROVIDER_OBJECT))
        store.put('environment', common.PUBLIC_ENV, copy.deepcopy(worker.PUBLIC_ENV_OBJECT))
        store.put('task', common.PUBLIC_TASK, old_task)
        store.put('task_budget', common.PUBLIC_TASK, old_budget)
        old = store.get('task', common.PUBLIC_TASK)
        budget = store.get('task_budget', common.PUBLIC_TASK)
        Guarded = worker._guarded(Store, folder, common.PUBLIC_TASK, old, budget,
                                  set(), common.PUBLIC_PROVIDER, common.PUBLIC_KEY)
        guarded = Guarded(folder)
        assert guarded.secret(common.PUBLIC_PROVIDER, 'api_key') == common.PUBLIC_KEY
        assert guarded.has_secret(common.PUBLIC_PROVIDER, 'api_key') is True
        for kind, item, value in (
                ('execution_limits', common.PUBLIC_TASK,
                 {'id': common.PUBLIC_TASK, 'max_started_runs': 12}),
                ('environment', common.PUBLIC_ENV, {})):
            try:
                guarded.put(kind, item, value)
                raise AssertionError('unapproved object write was accepted')
            except RuntimeError:
                pass
        for item, name in ((common.PUBLIC_ENV, 'console_token'),
                           (common.PUBLIC_ENV, 'service_api_key')):
            try:
                guarded.secret(item, name)
                raise AssertionError('other credential read was accepted')
            except RuntimeError:
                pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    ok('wrong Task/revision/plan/prefix/budget and unapproved writes are blocked')


def test_sealed_map():
    old_map = {'work/old/%04d' % i: _sha('old%d' % i) for i in range(831)}
    seal = {'work/autonomous-dual375/seal/%02d' % i: _sha('seal%d' % i)
            for i in range(27)}
    index = {'work/autonomous-dual375/index.json': common.SEAL_INDEX_SHA}
    merged = common.merge_sealed(old_map, seal, index)
    assert len(merged) == 859 == common.TOTAL_SEALED_COUNT
    assert common.OLD_MAP_COUNT + common.SEAL_ENTRY_COUNT + 1 == 859
    bad_cases = [
        (dict(list(old_map.items())[:830]), seal, index),
        (old_map, dict(list(seal.items())[:26]), index),
        (old_map, seal, {**index, 'work/autonomous-dual375/other.json':
                         common.SEAL_INDEX_SHA}),
    ]
    for bad in bad_cases:
        try:
            common.merge_sealed(*bad)
            raise AssertionError('bad sealed map was accepted')
        except RuntimeError:
            pass
    conflict = dict(seal)
    conflict.pop(next(iter(conflict)))
    conflict[next(iter(old_map))] = _sha('conflict')
    try:
        common.merge_sealed(old_map, conflict, index)
        raise AssertionError('conflicting sealed path was accepted')
    except RuntimeError:
        pass
    plan = _synthetic_plan(merged)
    tool.validate_plan(plan)
    bad_plans = []
    value = copy.deepcopy(plan); value['protected_count'] = 858; bad_plans.append(value)
    value = copy.deepcopy(plan); value['protected_files_sha256'] = '0' * 64; bad_plans.append(value)
    value = copy.deepcopy(plan); value['protected_files'].pop(next(iter(value['protected_files']))); bad_plans.append(value)
    value = copy.deepcopy(plan); value['regrant'] = dict(value['regrant'], model_slot=2); bad_plans.append(value)
    value = copy.deepcopy(plan); value['target_task_shape'] = dict(value['target_task_shape'], revision=7); bad_plans.append(value)
    for value in bad_plans:
        try:
            tool.validate_plan(value)
            raise AssertionError('bad plan/sealed binding was accepted')
        except RuntimeError:
            pass
    ok('859 sealed map and real plan gate accept 859 and reject tampering')


def test_runtime_gate():
    value = {'runtime_build': common.RUNTIME_BUILD,
             'runtime_version': common.RUNTIME_VERSION,
             'runtime_file_count': common.RUNTIME_FILE_COUNT,
             'runtime_manifest_sha256': 'a' * 64,
             'runtime_process_sha256': 'b' * 64,
             'backend_path': 'snapshot/backend'}
    plan = dict(value)
    tool.validate_runtime_binding(value, plan)
    for key, bad_value in (('runtime_build', 'other-build'),
                           ('runtime_version', '0.410.0'),
                           ('runtime_file_count', 297),
                           ('runtime_manifest_sha256', '0' * 64),
                           ('runtime_process_sha256', '1' * 64),
                           ('backend_path', 'other/backend')):
        bad = dict(value)
        bad[key] = bad_value
        try:
            tool.validate_runtime_binding(bad, plan)
            raise AssertionError('bad runtime binding was accepted')
        except RuntimeError:
            pass
    ok('runtime binding gate rejects build/version/count/hash/path tampering')


def _runtime_argv(app_dir, module='app.main:app', host='127.0.0.1', port='8765'):
    return ['-m', 'uvicorn', module, '--host', host, '--port', port,
            '--app-dir', app_dir]


def test_runtime_process_identity():
    venv = str(PROJECT / '.venv' / 'Scripts' / 'python.exe')
    backend = str(PROJECT / '.runtime' / 'snapshots'
                  / common.RUNTIME_BUILD / 'backend')
    legal = _runtime_argv(backend)
    meta = tool.runtime_process_matches(12020, venv, legal, backend)
    assert meta['pid'] == 12020
    assert meta['backend'] == tool._norm_runtime_path(backend)
    assert meta['backend_sha256'] and meta['command_sha256']
    assert 'command' not in meta
    tool.runtime_process_matches(12020, venv,
                                 _runtime_argv('"%s"' % backend), backend)
    tool.runtime_process_matches(12020, venv,
                                 legal[:-2] + ['--app-dir=' + backend], backend)
    spaced = backend + ' dir'
    tool.runtime_process_matches(12020, venv,
                                 _runtime_argv('"%s"' % spaced), spaced)
    old = str(PROJECT / '.runtime' / 'snapshots' / '0.410.0-old' / 'backend')
    project_backend = str(PROJECT / 'backend')
    bad = [
        (venv, _runtime_argv(old)),
        (venv, _runtime_argv(project_backend)),
        (venv, _runtime_argv(backend + '-evil')),
        (str(PROJECT / 'backend' / 'python.exe'), legal),
        (venv, _runtime_argv(backend, module='app.other:app')),
        (venv, _runtime_argv(backend, port='8000')),
        (venv, _runtime_argv(backend, host='0.0.0.0')),
        (venv, ['uvicorn', 'app.main:app', '--host', '127.0.0.1',
                '--port', '8765', '--app-dir', backend]),
        (venv, legal + ['--app-dir', backend]),
        (venv, _runtime_argv('.runtime/snapshots/'
                             + common.RUNTIME_BUILD + '/backend')),
    ]
    for exe, argv in bad:
        try:
            tool.runtime_process_matches(12020, exe, argv, backend)
            raise AssertionError('bad runtime process metadata was accepted')
        except RuntimeError:
            pass
    ok('runtime process identity requires venv, uvicorn module/host/port and exact --app-dir')


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, 'utf-8')


def _stop_fixture(folder):
    package = Path(folder) / 'work' / 'autonomous-dual375'
    live = package / 'live-output'
    live.mkdir(parents=True, exist_ok=True)
    progress = {'state': 'stopped',
                'dispatch_counts': {'model': 0, 'reads': 6, 'login': 1,
                                    'import': 0, 'publish': 0, 'key': 0, 'run': 0},
                'physical_http': 7}
    _write(live / 'progress.json', json.dumps(progress))
    _write(package / 'attempt.json', json.dumps({'state': 'stopped'}))
    _write(live / 'review-source-faq_read.json', '{}')
    return package, live


def test_sealed_loader():
    folder = Path(tempfile.mkdtemp())
    try:
        package, live = _stop_fixture(folder)
        old = {}
        for i in range(831):
            rel = 'work/old/%04d.txt' % i
            data = ('old%d' % i).encode()
            path = folder / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            old[rel] = _sha_bytes(data)
        plan_path = package / 'plan.json'
        plan_path.write_text(json.dumps({'protected_files': old}), 'utf-8')
        old_plan_sha = common.sha(plan_path)
        names = ['README.md', 'approval.json', 'attempt.json', 'profile.json',
                 'worker.py', 'execute.py', 'prepare.py', 'checks.py',
                 'derivation.py', 'live-output/progress.json',
                 'live-output/review-source-faq_read.json']
        names += ['member-%02d.txt' % i for i in range(16)]
        seal = {}
        for name in names:
            path = package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text('member ' + name, 'utf-8')
            seal[name] = common.sha(path)
        seal_path = package / 'seal-after-stop.json'
        seal_path.write_text(json.dumps(seal), 'utf-8')
        seal_sha = common.sha(seal_path)
        merged = common.load_sealed_map(folder, old_plan_sha=old_plan_sha,
                                        seal_index_sha=seal_sha)
        assert len(merged) == 859 == common.TOTAL_SEALED_COUNT
        assert merged['work/autonomous-dual375/live-output/progress.json'] == \
            seal['live-output/progress.json']
        assert merged['work/autonomous-dual375/seal-after-stop.json'] == seal_sha
        common.verify_sealed_map(folder, merged, old_plan_sha=old_plan_sha,
                                 seal_index_sha=seal_sha)
        (package / 'member-00.txt').write_bytes(b'tampered')
        try:
            common.verify_sealed_map(folder, merged, old_plan_sha=old_plan_sha,
                                     seal_index_sha=seal_sha)
            raise AssertionError('tampered sealed member was accepted')
        except RuntimeError:
            pass
        bad = dict(seal)
        bad.pop(next(iter(bad)))
        bad['../escape'] = 'a' * 64
        seal_path.write_text(json.dumps(bad), 'utf-8')
        try:
            common.load_sealed_map(folder, old_plan_sha=old_plan_sha,
                                   seal_index_sha=common.sha(seal_path))
            raise AssertionError('escaping 375 seal key was accepted')
        except RuntimeError:
            pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    ok('actual 375 relative-map loader builds 859, verifies every SHA and rejects escape')


def test_receipts():
    folder = Path(tempfile.mkdtemp())
    try:
        package, live = _stop_fixture(folder)
        common.verify_375_stop(folder)
        _write(live / 'review-faq_read.json', '{}')
        try:
            common.verify_375_stop(folder)
            raise AssertionError('live-output receipt was accepted')
        except RuntimeError:
            pass
        (live / 'review-faq_read.json').unlink()
        _write(package / 'review-faq_read.json', '{}')
        try:
            common.verify_375_stop(folder)
            raise AssertionError('root receipt was accepted')
        except RuntimeError:
            pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    ok('only review-source-* is allowed; live-output and root receipts are rejected')


def test_source_pins():
    blobs, commits = common.verified_sources(PROJECT, common.SOURCE_PINS)
    assert set(blobs) == {'tools/autonomous-dual375/derivation.py',
                          'tools/autonomous-dual374/reuse_policy.py',
                          'tools/autonomous-dual374/storage_guard.py'}
    assert all(len(value) == 40 for value in commits.values())
    for name, raw in blobs.items():
        compile(raw, name, 'exec')
    value = tool.sources()
    assert value['batch_id'] == common.BATCH and value['files']
    bad = copy.deepcopy(common.SOURCE_PINS)
    bad['tools/autonomous-dual375']['commit'] = '0' * 40
    try:
        common.verified_sources(PROJECT, bad)
        raise AssertionError('bad source commit was accepted')
    except RuntimeError:
        pass
    bad = copy.deepcopy(common.SOURCE_PINS)
    bad['tools/autonomous-dual375']['files'] = ['no-such-377.py']
    try:
        common.verified_sources(PROJECT, bad)
        raise AssertionError('bad source file was accepted')
    except RuntimeError:
        pass
    ok('pinned sources equal the worktree and compile; tampering is rejected')


def _valid_approval():
    return {'authorization_source': 'direct_user_reply', 'scope': common.BATCH,
            'decision': 'approve', 'reply': common.APPROVAL_PHRASE,
            'question_ref': 'call_newvalid377/q0', 'plan_sha256': 'a' * 64,
            'manifest_sha256': 'b' * 64, 'limits': common.LIMITS,
            'approved_model_slots': 1, 'effective_model_http': 1,
            'json_repair_http': 0}


def test_approval_rejections():
    plan = {'limits': common.LIMITS, 'max_model_http': 1}
    approval = _valid_approval()
    tool.validate_authorization(approval, plan, 'a' * 64, 'b' * 64)
    bad = []
    value = copy.deepcopy(approval); value['question_ref'] = 'call_f5b63df1752f441284ac9ee97f031930/q0'; bad.append(value)
    value = copy.deepcopy(approval); value['authorization_source'] = 'agent_delegated'; bad.append(value)
    value = copy.deepcopy(approval); value['reply'] = '同意'; bad.append(value)
    value = copy.deepcopy(approval); value['plan_sha256'] = 'c' * 64; bad.append(value)
    value = copy.deepcopy(approval); value['limits'] = dict(common.LIMITS, model=2); bad.append(value)
    for value in bad:
        try:
            tool.validate_authorization(value, plan, 'a' * 64, 'b' * 64)
            raise AssertionError('bad approval was accepted')
        except RuntimeError:
            pass

    folder = Path(tempfile.mkdtemp())
    try:
        tool.assert_unconsumed(folder)
        (folder / 'attempt.json').write_text('{}', 'utf-8')
        try:
            tool.assert_unconsumed(folder)
            raise AssertionError('consumed attempt was accepted')
        except RuntimeError:
            pass
        (folder / 'approval.json').write_text('{}', 'utf-8')
        try:
            tool.assert_unconsumed(folder, include_approval=True)
            raise AssertionError('existing approval was accepted')
        except RuntimeError:
            pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    ok('old ref, non-direct approval, wrong literal/hash/limits and replay are rejected')


def test_manifest_tamper():
    folder = Path(tempfile.mkdtemp())
    try:
        for name in common.PACKAGE_FILES:
            shutil.copy2(HERE / name, folder / name)
        manifest = {'schema_version': 1, 'batch_id': common.BATCH,
                    'files': tool.package_files(folder)}
        tool.validate_manifest(folder, manifest)
        (folder / 'README.md').write_text('changed', 'utf-8')
        try:
            tool.validate_manifest(folder, manifest)
            raise AssertionError('tampered package was accepted')
        except RuntimeError:
            pass
        (folder / 'README.md').write_text((HERE / 'README.md').read_text('utf-8'), 'utf-8')
        broken = copy.deepcopy(manifest)
        broken['files'].pop('README.md')
        try:
            tool.validate_manifest(folder, broken)
            raise AssertionError('manifest missing a file was accepted')
        except RuntimeError:
            pass
        real = folder / 'real_common.py'
        shutil.copy2(HERE / 'common.py', real)
        link = folder / 'common.py'
        try:
            link.unlink()
            os.symlink(real, link)
        except (OSError, NotImplementedError):
            print('SKIP symlink package check (platform refused symlink)')
        else:
            try:
                tool.package_files(folder)
                raise AssertionError('symlink package file was accepted')
            except RuntimeError:
                pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    ok('manifest/package tamper and symlink are rejected')


def main():
    root = Path(tempfile.mkdtemp(dir=PROJECT / 'work',
                                 prefix='preserved-planning377-check-'))
    try:
        test_success(root)
        test_invalid_json(root)
        test_needs_decision(root)
        test_unknown_usage(root)
        test_boundary_rejections()
        test_guard_tamper()
        test_sealed_map()
        test_runtime_gate()
        test_runtime_process_identity()
        test_source_pins()
        test_sealed_loader()
        test_receipts()
        test_approval_rejections()
        test_manifest_tamper()
    except BaseException:
        traceback.print_exc()
        print('FAIL after %d checks' % len(PASS))
        raise SystemExit(1)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print('PASS %d checks; public synthetic only, not business/platform acceptance' % len(PASS))


if __name__ == '__main__':
    main()
