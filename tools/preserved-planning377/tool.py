"""Freeze/approval/once-only lifecycle for preserved-planning377.

No approval, attempt, worker marker or live output is created by import.  Live
is only reachable from the canonical original-machine directory after a new
direct user reply binds the exact plan and manifest.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from common import (APPROVAL_PHRASE, APPROVAL_SUFFIX, BATCH, CANONICAL,
                    EXPECTED_COUNTS, ISOLATED, LIMITS, MAX_MODEL_HTTP,
                    MODEL_BOOK_UPPER_USD, OLD_375_PLAN_SHA, OLD_ENTRY_COUNT,
                    OLD_REFS, ORIGINAL_PROJECT, OUTPUT_TOKENS, PACKAGE_FILES,
                    PER_CALL_USD, PER_MODEL_TOTAL_USD, PROJECT, PROVIDER_ID,
                    PROVIDER_MODEL, PROVIDER_PROTOCOL, ReadOnly, RUNTIME_BUILD,
                    RUNTIME_FILE_COUNT, RUNTIME_PID_OBSERVED, RUNTIME_VERSION,
                    SEAL_INDEX_SHA, SETTLED_TOTAL, SOURCE_PINS, TARGET_REVISION,
                    TARGET_TASK, TIMEOUT_SECONDS, TOTAL_SEALED_COUNT, UPPER,
                    WALL_SECONDS, capture, digest, history_prefix, is_hex, load,
                    load_sealed_map, money, require, sha, sha_bytes, uuid,
                    verified_sources, verify_sealed_map, verify_375_stop)
from common import ENVIRONMENT_ID

HERE = Path(__file__).resolve().parent
APPROVAL_KEYS = {'authorization_source', 'scope', 'decision', 'reply', 'question_ref',
                 'plan_sha256', 'manifest_sha256', 'limits', 'approved_model_slots',
                 'effective_model_http', 'json_repair_http'}
TARGET_SHAPE = {
    'revision': TARGET_REVISION, 'status': 'paused', 'app_type': 'advanced-chat',
    'requirements_confirmed': True, 'configuration_confirmed': False,
    'workflow_plan': None, 'agent_plan': None, 'artifact': None, 'dify_app_id': None,
    'materials': [], 'runs': [],
    'counts': {'messages': 6, 'versions': 5, 'planning_runs': 1,
               'intake_history': 1, 'runs': 0},
    'interview_attempts_present': False, 'execution_limits_present': False,
}
REGRANT = {'from_batch': 'autonomous-dual375', 'model_slot': 1, 'estimate_usd': '0.100',
           'remaining_kept': {'model': 2, 'estimate_usd': '0.200',
                              'dify_estimate_usd': '0.100', 'reads': 116,
                              'import': 2, 'publish': 2, 'key': 2, 'run': 14}}
PLAN_REQUIRED = {
    'schema_version', 'batch_id', 'approval_state', 'approval_phrase',
    'approval_question_suffix', 'source_batch', 'regrant', 'limits',
    'new_conservative_upper', 'per_call_reserve_usd', 'model_total_reserve_usd',
    'model_estimate_book_upper_usd', 'billing_hard_cap', 'wall_seconds',
    'max_model_http', 'output_tokens', 'timeout_seconds', 'target_task_id',
    'target_task_revision', 'target_task_sha256', 'target_budget_sha256',
    'target_task_shape', 'execution_limits_present', 'initial_no_graph',
    'initial_execution_policy_none', 'history_prefix', 'intake_review_sha256',
    'decision_report_sha256', 'cases_sha256', 'configuration_sha256',
    'requirements_sha256', 'provider_id', 'provider_sha256', 'provider_model',
    'provider_protocol', 'environment_id', 'environment_sha256',
    'environment_identity_sha256', 'expected_counts', 'runtime_build',
    'runtime_version', 'runtime_file_count', 'runtime_pid_observed',
    'runtime_manifest_sha256', 'runtime_process_sha256', 'backend_path',
    'runtime_process_observed', 'protected_data', 'protected_isolated',
    'protected_files', 'protected_files_sha256', 'protected_count',
    'old_375_plan_sha256', 'seal_index_sha256', 'old_375_stop', 'source_pins',
    'source_file_sha256', 'package_files', 'proposal_doc', 'proposal_sha256',
    'created_at',
}


def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _write_json(path, value):
    path = Path(path)
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
    os.replace(tmp, path)


def canonical(root):
    raw = Path(root)
    require(not raw.is_symlink() and raw.resolve() == CANONICAL,
            'Canonical original-machine root required')
    require(PROJECT == ORIGINAL_PROJECT, 'Original project only')
    require(not sys.flags.optimize, 'Unoptimized entry only')
    require(raw.is_dir(), 'Canonical root missing')
    return raw.resolve()


def package_files(root):
    root = Path(root)
    result = {}
    for name in PACKAGE_FILES:
        path = root / name
        require(path.is_file() and not path.is_symlink(), 'Package file missing: ' + name)
        result[name] = sha(path)
    return result


def validate_manifest(root, manifest):
    require(isinstance(manifest, dict) and manifest.get('schema_version') == 1
            and manifest.get('batch_id') == BATCH, 'Manifest identity changed')
    files = manifest.get('files')
    require(isinstance(files, dict) and set(files) == set(PACKAGE_FILES),
            'Manifest file set changed')
    actual = package_files(root)
    require(files == actual, 'Frozen package changed')
    return files


def validate_plan(p):
    require(isinstance(p, dict) and PLAN_REQUIRED <= set(p), 'Plan fields missing')
    require(p['schema_version'] == 1 and p['batch_id'] == BATCH
            and p['approval_state'] == 'pending', 'Plan identity changed')
    require(p['approval_phrase'] == APPROVAL_PHRASE
            and p['approval_question_suffix'] == APPROVAL_SUFFIX,
            'Approval phrase changed')
    require(p['source_batch'] == 'autonomous-dual375' and p['regrant'] == REGRANT,
            'Regrant scope changed')
    require(p['limits'] == LIMITS and p['new_conservative_upper'] == UPPER,
            'Limits changed')
    require(p['per_call_reserve_usd'] == PER_CALL_USD
            and p['model_total_reserve_usd'] == PER_MODEL_TOTAL_USD
            and p['model_estimate_book_upper_usd'] == MODEL_BOOK_UPPER_USD
            and p['billing_hard_cap'] is False, 'Cost bounds changed')
    require(p['wall_seconds'] == WALL_SECONDS and p['max_model_http'] == MAX_MODEL_HTTP
            and p['output_tokens'] == OUTPUT_TOKENS
            and p['timeout_seconds'] == TIMEOUT_SECONDS, 'Model bounds changed')
    require(p['target_task_id'] == TARGET_TASK and p['target_task_revision'] == TARGET_REVISION,
            'Target Task changed')
    require(p['provider_id'] == PROVIDER_ID and p['provider_model'] == PROVIDER_MODEL
            and p['provider_protocol'] == PROVIDER_PROTOCOL, 'Provider changed')
    require(p['environment_id'] == ENVIRONMENT_ID, 'Environment changed')
    require(uuid(p['environment_id']), 'Environment id invalid')
    require(p['target_task_shape'] == TARGET_SHAPE, 'Target Task shape changed')
    require(p['execution_limits_present'] is False
            and p['initial_no_graph'] is True
            and p['initial_execution_policy_none'] is True, 'Initial state changed')
    require(p['expected_counts'] == EXPECTED_COUNTS, 'Expected object counts changed')
    require(p['runtime_build'] == RUNTIME_BUILD and p['runtime_version'] == RUNTIME_VERSION
            and p['runtime_file_count'] == RUNTIME_FILE_COUNT
            and type(p['runtime_pid_observed']) is int and p['runtime_pid_observed'] > 0,
            'Runtime identity changed')
    require(p['backend_path'] == str(PROJECT / '.runtime' / 'snapshots'
                                     / RUNTIME_BUILD / 'backend'), 'Backend path changed')
    require(p['protected_count'] == TOTAL_SEALED_COUNT
            and p['old_375_plan_sha256'] == OLD_375_PLAN_SHA
            and p['seal_index_sha256'] == SEAL_INDEX_SHA, 'Seal identity changed')
    require(isinstance(p['protected_files'], dict)
            and len(p['protected_files']) == TOTAL_SEALED_COUNT
            and digest(p['protected_files']) == p['protected_files_sha256'],
            'Protected file map changed')
    require(all(is_hex(p[key]) for key in
                ('target_task_sha256', 'target_budget_sha256', 'intake_review_sha256',
                 'decision_report_sha256', 'cases_sha256', 'configuration_sha256',
                 'requirements_sha256', 'provider_sha256', 'environment_sha256',
                 'environment_identity_sha256', 'runtime_manifest_sha256',
                 'runtime_process_sha256', 'protected_files_sha256', 'proposal_sha256')),
            'Plan digest invalid')
    require(isinstance(p['protected_data'], dict)
            and isinstance(p['protected_isolated'], dict), 'Protection snapshots missing')
    require(isinstance(p['history_prefix'], dict)
            and set(p['history_prefix']) == {'messages', 'versions', 'planning_runs',
                                             'intake_history', 'runs', 'interview_attempts'},
            'History prefix fields changed')
    require(isinstance(p['source_pins'], dict) and set(p['source_pins']) == set(SOURCE_PINS),
            'Source pin set changed')
    require(isinstance(p['source_file_sha256'], dict)
            and set(p['source_file_sha256']) ==
            {directory + '/' + name for directory, spec in SOURCE_PINS.items()
             for name in spec['files']}, 'Source file digest set changed')
    require(isinstance(p['package_files'], dict) and set(p['package_files']) == set(PACKAGE_FILES),
            'Package file set changed')
    return True


def verify_package(root, plan=None):
    root = Path(root)
    manifest = load(root / 'manifest.json')
    files = validate_manifest(root, manifest)
    if plan is not None:
        require(plan['package_files'] == files, 'Plan package digests changed')
    for name in ('common.py', 'tool.py', 'worker.py', 'checks.py'):
        compile((root / name).read_bytes(), name, 'exec')
    blobs, commits = verified_sources(PROJECT, SOURCE_PINS)
    if plan is not None:
        require({path: sha_bytes(raw) for path, raw in blobs.items()}
                == plan['source_file_sha256'], 'Pinned source digests changed')
        require({directory: spec['commit'] for directory, spec in plan['source_pins'].items()}
                == {directory: commits[directory] for directory in commits},
                'Resolved source commits changed')
        require(all(set(plan['source_pins'][directory]['files'])
                    == set(spec['files']) for directory, spec in SOURCE_PINS.items()),
                'Source pin file list changed')
    return blobs


def validate_authorization(a, plan, plan_sha, manifest_sha):
    require(isinstance(a, dict) and APPROVAL_KEYS <= set(a), 'Approval fields missing')
    require(a['authorization_source'] == 'direct_user_reply'
            and a['scope'] == BATCH and a['decision'] == 'approve'
            and a['reply'] == APPROVAL_PHRASE, 'Direct new approval missing')
    ref = a['question_ref']
    require(isinstance(ref, str) and bool(re.fullmatch(r'call_[A-Za-z0-9_-]{1,64}/q0', ref))
            and ref not in OLD_REFS, 'New question_ref required')
    require(a['plan_sha256'] == plan_sha and a['manifest_sha256'] == manifest_sha,
            'Approval not bound to frozen package')
    require(a['limits'] == LIMITS and a['approved_model_slots'] == 1
            and a['effective_model_http'] == 1 and a['json_repair_http'] == 0,
            'Approval limits changed')
    require(plan['limits'] == LIMITS and plan['max_model_http'] == 1,
            'Frozen package limits changed')
    return True


def assert_unconsumed(root, include_approval=False):
    names = ['attempt.json', 'worker-started.json']
    if include_approval:
        names.append('approval.json')
    for name in names:
        require(not (Path(root) / name).exists(), 'Consumed package cannot replay: ' + name)


def approved(root, plan):
    path = Path(root) / 'approval.json'
    require(path.is_file() and not path.is_symlink(), 'Approval missing')
    a = load(path)
    validate_authorization(a, plan, sha(Path(root) / 'plan.json'),
                           sha(Path(root) / 'manifest.json'))
    return True


def _identity(env):
    keys = ('id', 'base_url', 'console_workspace_id', 'version')
    return digest({key: env.get(key) for key in keys})


def _strip_runtime_token(token):
    require(isinstance(token, str) and token, 'Runtime token invalid')
    text = token.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
    return text


def _runtime_flag_values(tokens, flag):
    values = []
    for index, token in enumerate(tokens):
        if token == flag:
            require(index + 1 < len(tokens), 'Runtime flag missing value: ' + flag)
            values.append(_strip_runtime_token(tokens[index + 1]))
        elif token.startswith(flag + '='):
            values.append(_strip_runtime_token(token[len(flag) + 1:]))
    return values


def _norm_runtime_path(value):
    require(isinstance(value, str) and value.strip(), 'Runtime path missing')
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
    require(os.path.isabs(text), 'Runtime --app-dir must be absolute')
    return os.path.normcase(os.path.normpath(os.path.abspath(text)))


def runtime_process_matches(pid, exe, argv, backend_path):
    """Pure identity gate shared by psutil/CIM; returns sanitized metadata."""
    require(type(pid) is int and pid > 0, 'Runtime PID invalid')
    venv = os.path.normcase(os.path.abspath(
        str(PROJECT / '.venv' / 'Scripts' / 'python.exe')))
    actual_exe = os.path.normcase(os.path.abspath(str(exe or '')))
    require(actual_exe == venv, 'Runtime exe is not the original venv')
    if isinstance(argv, str):
        tokens = shlex.split(argv, posix=False)
    else:
        require(isinstance(argv, (list, tuple))
                and all(isinstance(value, str) for value in argv),
                'Runtime command metadata invalid')
        tokens = [str(value) for value in argv]
    tokens = [_strip_runtime_token(token) for token in tokens]
    found = False
    for index, token in enumerate(tokens):
        if token == '-m' and index + 1 < len(tokens) and tokens[index + 1] == 'uvicorn':
            found = True
    require(found, 'Runtime -m uvicorn missing')
    app_tokens = [token for token in tokens if token.endswith(':app')]
    require(app_tokens == ['app.main:app'], 'Runtime module changed')
    require(_runtime_flag_values(tokens, '--host') == ['127.0.0.1'],
            'Runtime host changed')
    require(_runtime_flag_values(tokens, '--port') == ['8765'],
            'Runtime port changed')
    app_dirs = _runtime_flag_values(tokens, '--app-dir')
    require(len(app_dirs) == 1, 'Runtime --app-dir count changed')
    selected = _norm_runtime_path(app_dirs[0])
    expected = _norm_runtime_path(str(backend_path))
    require(selected == expected, 'Runtime --app-dir is not the fixed backend')
    raw = ' '.join(tokens)
    return {'pid': pid, 'exe': actual_exe, 'backend': selected,
            'backend_sha256': sha_bytes(selected.encode()),
            'command_sha256': sha_bytes(raw.encode())}


def runtime_process_facts(backend_path):
    result = []
    try:
        import psutil
    except ImportError:
        script = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } "
                  "| Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress")
        done = subprocess.run(['powershell', '-NoProfile', '-NonInteractive',
                               '-Command', script], capture_output=True, text=True)
        require(done.returncode == 0, 'CIM process query unavailable')
        try:
            data = json.loads(done.stdout) if done.stdout.strip() else []
        except Exception:
            raise RuntimeError('CIM process JSON invalid') from None
        if isinstance(data, dict):
            data = [data]
        for row in data:
            try:
                meta = runtime_process_matches(row.get('ProcessId'),
                                               row.get('ExecutablePath') or '',
                                               row.get('CommandLine') or '',
                                               backend_path)
            except RuntimeError:
                continue
            result.append(meta)
        return result
    for proc in psutil.process_iter(['pid', 'exe', 'cmdline']):
        try:
            info = proc.info or {}
        except Exception:
            continue
        try:
            meta = runtime_process_matches(info.get('pid'), info.get('exe') or '',
                                           info.get('cmdline') or [], backend_path)
        except RuntimeError:
            continue
        result.append(meta)
    return result


def runtime_snapshot():
    folder = PROJECT / '.runtime' / 'snapshots' / RUNTIME_BUILD
    manifest_path = folder / 'runtime-manifest.json'
    require(manifest_path.is_file() and not manifest_path.is_symlink(),
            'Runtime manifest missing')
    runtime = load(manifest_path)
    files = runtime.get('files')
    require(runtime.get('shared_data_copied') is False
            and isinstance(files, dict) and len(files) == RUNTIME_FILE_COUNT == 298,
            'Runtime manifest changed')
    require(all(sha(PROJECT / name) == value and sha(folder / name) == value
                for name, value in files.items()), 'Running source/snapshot changed')
    helper = PROJECT / 'runtime-process.ps1'
    require(helper.is_file() and not helper.is_symlink(), 'Runtime helper missing')
    backend = folder / 'backend'
    require(backend.is_dir() and not backend.is_symlink(), 'Runtime backend missing')
    facts = runtime_process_facts(str(backend))
    require(facts, 'Managed runtime process ownership not verified')
    require(len(facts) == 1, 'Managed runtime process must be unique')
    return {'runtime_build': RUNTIME_BUILD, 'runtime_version': RUNTIME_VERSION,
            'runtime_file_count': len(files),
            'runtime_manifest_sha256': sha(manifest_path),
            'runtime_process_sha256': sha(helper),
            'backend_path': str(backend), 'runtime_process_observed': facts}


def validate_runtime_binding(value, plan):
    for key in ('runtime_build', 'runtime_version', 'runtime_file_count',
                'runtime_manifest_sha256', 'runtime_process_sha256', 'backend_path'):
        require(value[key] == plan[key], 'Runtime binding changed: ' + key)
    return True


def verify_runtime(plan):
    value = runtime_snapshot()
    validate_runtime_binding(value, plan)
    return value['runtime_process_observed']


def verify_isolated(plan):
    require(set(plan['protected_isolated']) == set(ISOLATED), 'Isolated root set changed')
    for label, path in ISOLATED.items():
        actual = capture(ReadOnly(PROJECT / path))
        require(actual == plan['protected_isolated'][label],
                'Old isolated root changed: ' + label)
    return True


def validate_start(plan):
    validate_plan(plan)
    data = ReadOnly(PROJECT / 'data')
    require(capture(data) == plan['protected_data'], 'Production baseline changed')
    require(len(data.list('task')) == EXPECTED_COUNTS['task']
            and len(data.list('environment')) == EXPECTED_COUNTS['environment']
            and len(data.list('provider')) == EXPECTED_COUNTS['provider'],
            'Production object counts changed')
    task = data.get('task', TARGET_TASK)
    budget = data.get('task_budget', TARGET_TASK)
    limits = data.get('execution_limits', TARGET_TASK)
    require(isinstance(task, dict) and isinstance(budget, dict), 'Target Task/budget missing')
    require(digest(task) == plan['target_task_sha256']
            and digest(budget) == plan['target_budget_sha256'],
            'Target Task/budget digest changed')
    require(history_prefix(task) == plan['history_prefix'], 'Task history prefix changed')
    require(digest(task.get('intake_review')) == plan['intake_review_sha256'],
            'Intake review changed')
    planning = task.get('planning_runs') or []
    require(len(planning) == 1 and isinstance(planning[0], dict)
            and digest(planning[0].get('decision_report')) == plan['decision_report_sha256'],
            'Old decision report changed')
    require(digest(task.get('test_cases')) == plan['cases_sha256']
            and digest(task.get('configuration')) == plan['configuration_sha256']
            and digest(task.get('requirements')) == plan['requirements_sha256'],
            'Saved Task inputs changed')
    require(task.get('id') == TARGET_TASK and task.get('revision') == TARGET_REVISION
            and task.get('status') == 'paused' and task.get('app_type') == 'advanced-chat',
            'Target Task state changed')
    require(task.get('requirements_confirmed') is True
            and task.get('configuration_confirmed') is False
            and task.get('intake_required') is True
            and task.get('plan_review_required') is True, 'Task gates changed')
    require(not task.get('active_interview_id') and not task.get('active_image_operation_id'),
            'Task has an active operation')
    require(task.get('workflow_plan') is None and task.get('agent_plan') is None
            and task.get('artifact') is None and task.get('dify_app_id') is None,
            'Target Task already has graph/artifact/App')
    require(task.get('materials') == [] and task.get('runs') == [],
            'Target Task materials/runs changed')
    require(('interview_attempts' in task)
            == plan['history_prefix']['interview_attempts']['present'],
            'interview_attempts presence changed')
    old_run = planning[0]
    require(old_run.get('status') == 'paused'
            and old_run.get('stop_reason') == 'needs_decision'
            and old_run.get('last_candidate') is None, 'Old planning run changed')
    require(budget.get('id') == TARGET_TASK and budget.get('limit_usd') == '0.600'
            and budget.get('policy_revision') == 1, 'Budget policy changed')
    entries = budget.get('entries')
    require(isinstance(entries, list) and len(entries) == OLD_ENTRY_COUNT,
            'Original settled ledger count changed')
    total = 0
    for entry in entries:
        require(entry.get('status') == 'settled'
                and entry.get('call_status') == 'returned'
                and entry.get('cost_basis') == 'reported_usage'
                and entry.get('provider_id') == PROVIDER_ID
                and entry.get('charged_usd') is not None, 'Original ledger changed')
        total += money(entry['charged_usd'])
    require(str(total) == SETTLED_TOTAL, 'Original settled total changed')
    require(limits is None, 'execution_limits must stay absent')
    provider = data.get('provider', plan['provider_id'])
    environment = data.get('environment', plan['environment_id'])
    require(isinstance(provider, dict) and digest(provider) == plan['provider_sha256'],
            'Provider/pricing changed')
    require(provider.get('model') == PROVIDER_MODEL
            and provider.get('protocol') == PROVIDER_PROTOCOL
            and provider.get('id') == plan['provider_id'],
            'Provider identity changed')
    require(task.get('environment_id') == plan['environment_id'],
            'Task environment changed')
    require(isinstance(environment, dict)
            and digest(environment) == plan['environment_sha256']
            and _identity(environment) == plan['environment_identity_sha256'],
            'Environment metadata changed')
    require(verify_375_stop(PROJECT) == plan['old_375_stop'], '375 stop facts changed')
    verify_sealed_map(PROJECT, plan['protected_files'])
    verify_isolated(plan)
    verify_runtime(plan)
    return {'task': task, 'budget': budget, 'provider': provider,
            'environment': environment, 'limits': limits}


def pre_dispatch(root, plan, stop_path):
    require(not Path(stop_path).exists(), 'Explicit stop before dispatch')
    canonical(root)
    verify_package(root, plan)
    approved(root, plan)
    verify_runtime(plan)
    data = ReadOnly(PROJECT / 'data')
    require(data.get('execution_limits', plan['target_task_id']) is None,
            'execution_limits appeared')
    require(digest(data.get('provider', plan['provider_id'])) == plan['provider_sha256'],
            'Provider changed before dispatch')
    return True


def authorize_worker(root, plan):
    root = canonical(root)
    verify_package(root, plan)
    approved(root, plan)
    baseline = validate_start(plan)
    attempt = load(root / 'attempt.json')
    require(attempt.get('state') == 'admitted'
            and attempt.get('approval_sha256') == sha(root / 'approval.json'),
            'Admission missing')
    require(not (root / 'worker-started.json').exists(), 'Worker already started')
    with (root / 'worker-started.json').open('x', encoding='utf-8') as handle:
        json.dump({'pid': os.getpid(), 'plan_sha256': sha(root / 'plan.json'),
                   'single_worker': True}, handle)
    return baseline


def sources(output=None):
    blobs, commits = verified_sources(PROJECT, SOURCE_PINS)
    value = {'schema_version': 1, 'batch_id': BATCH, 'pins': SOURCE_PINS,
             'commits': commits,
             'files': {path: sha_bytes(raw) for path, raw in blobs.items()},
             'created_at': now()}
    if output:
        out = Path(output)
        require(out.is_relative_to(PROJECT / 'work') and not out.exists(),
                'New work source directory required')
        out.mkdir()
        _write_json(out / 'source-pins.json', value)
    return value


def pending(root):
    root = canonical(root)
    assert_unconsumed(root, include_approval=True)
    require(not (root / 'plan.json').exists() and not (root / 'manifest.json').exists(),
            'Plan/manifest already exist')
    validate_manifest(root, {'schema_version': 1, 'batch_id': BATCH,
                             'files': package_files(root)})
    blobs, commits = verified_sources(PROJECT, SOURCE_PINS)
    source_files = {path: sha_bytes(raw) for path, raw in blobs.items()}
    sealed = load_sealed_map(PROJECT)
    verify_sealed_map(PROJECT, sealed)
    stop_facts = verify_375_stop(PROJECT)
    data = ReadOnly(PROJECT / 'data')
    require(len(data.list('task')) == EXPECTED_COUNTS['task']
            and len(data.list('environment')) == EXPECTED_COUNTS['environment']
            and len(data.list('provider')) == EXPECTED_COUNTS['provider'],
            'Production object counts changed')
    task = data.get('task', TARGET_TASK)
    budget = data.get('task_budget', TARGET_TASK)
    limits = data.get('execution_limits', TARGET_TASK)
    require(isinstance(task, dict) and isinstance(budget, dict), 'Target Task/budget missing')
    require(task.get('id') == TARGET_TASK and task.get('revision') == TARGET_REVISION
            and task.get('status') == 'paused' and task.get('app_type') == 'advanced-chat',
            'Target Task state changed')
    require(task.get('requirements_confirmed') is True
            and task.get('configuration_confirmed') is False
            and task.get('intake_required') is True
            and task.get('plan_review_required') is True, 'Task gates changed')
    require(task.get('workflow_plan') is None and task.get('agent_plan') is None
            and task.get('artifact') is None and task.get('dify_app_id') is None
            and task.get('materials') == [] and task.get('runs') == [],
            'Target Task is not graph/artifact/App free')
    history = history_prefix(task)
    require({key: history[key]['count'] for key in
             ('messages', 'versions', 'planning_runs', 'intake_history', 'runs')}
            == TARGET_SHAPE['counts'], 'Target Task history shape changed')
    require(history['interview_attempts']['present'] is False,
            'interview_attempts must stay absent for r6')
    old_run = (task.get('planning_runs') or [None])[0]
    require(isinstance(old_run, dict) and old_run.get('status') == 'paused'
            and old_run.get('stop_reason') == 'needs_decision'
            and isinstance(old_run.get('decision_report'), dict)
            and old_run.get('last_candidate') is None, 'Old needs_decision changed')
    require(len(budget.get('entries') or []) == OLD_ENTRY_COUNT
            and budget.get('limit_usd') == '0.600'
            and budget.get('policy_revision') == 1, 'Original budget changed')
    total = sum((money(entry['charged_usd']) for entry in budget['entries']), 0)
    require(str(total) == SETTLED_TOTAL, 'Original settled total changed')
    require(limits is None, 'execution_limits must be absent')
    provider = data.get('provider', PROVIDER_ID)
    environment = data.get('environment', ENVIRONMENT_ID)
    require(isinstance(provider, dict) and isinstance(environment, dict),
            'Provider/environment missing')
    require(provider.get('model') == PROVIDER_MODEL
            and provider.get('protocol') == PROVIDER_PROTOCOL
            and provider.get('id') == PROVIDER_ID
            and environment.get('id') == ENVIRONMENT_ID,
            'Provider/environment identity changed')
    require(task.get('environment_id') == environment.get('id'), 'Task environment changed')
    shape = {'revision': task['revision'], 'status': task['status'],
             'app_type': task['app_type'],
             'requirements_confirmed': task['requirements_confirmed'],
             'configuration_confirmed': task['configuration_confirmed'],
             'workflow_plan': task.get('workflow_plan'),
             'agent_plan': task.get('agent_plan'),
             'artifact': task.get('artifact'), 'dify_app_id': task.get('dify_app_id'),
             'materials': task.get('materials'), 'runs': task.get('runs'),
             'counts': {key: history[key]['count'] for key in
                        ('messages', 'versions', 'planning_runs', 'intake_history', 'runs')},
             'interview_attempts_present': history['interview_attempts']['present'],
             'execution_limits_present': limits is not None}
    require(shape == TARGET_SHAPE, 'Target Task shape changed')
    runtime = runtime_snapshot()
    plan = {
        'schema_version': 1, 'batch_id': BATCH, 'approval_state': 'pending',
        'approval_phrase': APPROVAL_PHRASE, 'approval_question_suffix': APPROVAL_SUFFIX,
        'source_batch': 'autonomous-dual375', 'regrant': REGRANT,
        'limits': LIMITS, 'new_conservative_upper': UPPER,
        'per_call_reserve_usd': PER_CALL_USD,
        'model_total_reserve_usd': PER_MODEL_TOTAL_USD,
        'model_estimate_book_upper_usd': MODEL_BOOK_UPPER_USD,
        'billing_hard_cap': False, 'wall_seconds': WALL_SECONDS,
        'max_model_http': MAX_MODEL_HTTP, 'output_tokens': OUTPUT_TOKENS,
        'timeout_seconds': TIMEOUT_SECONDS,
        'target_task_id': TARGET_TASK, 'target_task_revision': TARGET_REVISION,
        'target_task_sha256': digest(task), 'target_budget_sha256': digest(budget),
        'target_task_shape': TARGET_SHAPE, 'execution_limits_present': False,
        'initial_no_graph': True, 'initial_execution_policy_none': True,
        'history_prefix': history,
        'intake_review_sha256': digest(task.get('intake_review')),
        'decision_report_sha256': digest(old_run.get('decision_report')),
        'cases_sha256': digest(task.get('test_cases')),
        'configuration_sha256': digest(task.get('configuration')),
        'requirements_sha256': digest(task.get('requirements')),
        'provider_id': provider.get('id'), 'provider_sha256': digest(provider),
        'provider_model': provider.get('model'),
        'provider_protocol': provider.get('protocol'),
        'environment_id': environment.get('id'),
        'environment_sha256': digest(environment),
        'environment_identity_sha256': _identity(environment),
        'expected_counts': EXPECTED_COUNTS,
        'runtime_build': runtime['runtime_build'],
        'runtime_version': runtime['runtime_version'],
        'runtime_file_count': runtime['runtime_file_count'],
        'runtime_pid_observed': RUNTIME_PID_OBSERVED,
        'runtime_manifest_sha256': runtime['runtime_manifest_sha256'],
        'runtime_process_sha256': runtime['runtime_process_sha256'],
        'backend_path': runtime['backend_path'],
        'runtime_process_observed': runtime['runtime_process_observed'],
        'protected_data': capture(data),
        'protected_isolated': {label: capture(ReadOnly(PROJECT / path))
                               for label, path in ISOLATED.items()},
        'protected_files': sealed,
        'protected_files_sha256': digest(sealed), 'protected_count': len(sealed),
        'old_375_plan_sha256': OLD_375_PLAN_SHA, 'seal_index_sha256': SEAL_INDEX_SHA,
        'old_375_stop': stop_facts,
        'source_pins': {directory: {'commit': commits[directory],
                                    'files': list(spec['files'])}
                        for directory, spec in SOURCE_PINS.items()},
        'source_file_sha256': source_files,
        'package_files': package_files(root),
        'proposal_doc': 'tools/preserved-planning377/README.md',
        'proposal_sha256': sha(PROJECT / 'tools' / 'preserved-planning377' / 'README.md'),
        'created_at': now(),
    }
    require(sha(PROJECT / 'tools' / 'preserved-planning377' / 'README.md')
            == sha(root / 'README.md'), 'Canonical README differs from committed source')
    validate_plan(plan)
    manifest = {'schema_version': 1, 'batch_id': BATCH,
                'files': package_files(root), 'created_at': now()}
    _write_json(root / 'plan.json', plan)
    _write_json(root / 'manifest.json', manifest)
    print(json.dumps({'state': 'pending_not_approved',
                      'plan_sha256': sha(root / 'plan.json'),
                      'manifest_sha256': sha(root / 'manifest.json'),
                      'protected_count': len(sealed)}, ensure_ascii=False))


def approve(root, authorization):
    root = canonical(root)
    plan = load(root / 'plan.json')
    validate_plan(plan)
    verify_package(root, plan)
    validate_start(plan)
    assert_unconsumed(root, include_approval=True)
    path = Path(authorization).resolve()
    require(path.is_file() and not path.is_symlink() and not path.is_relative_to(PROJECT),
            'Direct approval file must be outside the project')
    a = load(path)
    validate_authorization(a, plan, sha(root / 'plan.json'), sha(root / 'manifest.json'))
    verify_package(root, plan)
    validate_start(plan)
    assert_unconsumed(root, include_approval=True)
    value = {key: a[key] for key in APPROVAL_KEYS}
    with (root / 'approval.json').open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
    require(sha(root / 'plan.json') == a['plan_sha256']
            and sha(root / 'manifest.json') == a['manifest_sha256'],
            'Approval write changed frozen bytes')
    print(json.dumps({'state': 'approved_not_dispatched',
                      'plan_sha256': a['plan_sha256'],
                      'manifest_sha256': a['manifest_sha256']}, ensure_ascii=False))


def validate(root):
    root = canonical(root)
    plan = load(root / 'plan.json')
    validate_plan(plan)
    verify_package(root, plan)
    approved(root, plan)
    assert_unconsumed(root)
    baseline = validate_start(plan)
    print(json.dumps({'state': 'approved_not_dispatched', 'limits': LIMITS,
                      'target_task_id': baseline['task']['id'],
                      'revision': baseline['task']['revision'],
                      'runtime': plan['runtime_build']}, ensure_ascii=False))


def live(root):
    root = canonical(root)
    plan = load(root / 'plan.json')
    validate_plan(plan)
    verify_package(root, plan)
    approved(root, plan)
    assert_unconsumed(root)
    validate_start(plan)
    attempt = {'state': 'admitted', 'approval_sha256': sha(root / 'approval.json'),
               'plan_sha256': sha(root / 'plan.json'), 'automatic_retry': False,
               'created_at': now()}
    with (root / 'attempt.json').open('x', encoding='utf-8') as handle:
        json.dump(attempt, handle)
    try:
        from worker import run
        result = run('live', root / 'live-output', plan)
        attempt.update(state=result['state'], counts=result.get('stage_counts'),
                       stage_counts=result.get('stage_counts'),
                       model_http_started=result.get('model_http_started'),
                       physical_http=result.get('physical_http'),
                       candidate_sha256=result.get('candidate_sha256'),
                       failure_type=result.get('failure_type'),
                       failure_reason=result.get('failure_reason'),
                       stop_reason=result.get('stop_reason'))
    except BaseException as exc:
        attempt.update(state='stopped', failure_type=type(exc).__name__,
                       failure_reason=(str(exc).strip().replace('\n', ' ')[:500]
                                       or type(exc).__name__))
        raise
    finally:
        _write_json(root / 'attempt.json', attempt)
    require(attempt['state'] == 'passed',
            'Batch consumed/stopped; no retry or continuation')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['sources', 'pending', 'approve',
                                           'validate', 'live'])
    parser.add_argument('--authorization')
    parser.add_argument('--output')
    args = parser.parse_args()
    root = HERE
    if args.action == 'sources':
        print(json.dumps(sources(args.output), ensure_ascii=False))
        return
    if args.action == 'pending':
        pending(root)
        return
    if args.action == 'approve':
        require(args.authorization, 'Authorization file required')
        approve(root, args.authorization)
        return
    if args.action == 'validate':
        validate(root)
        return
    live(root)


if __name__ == '__main__':
    main()
