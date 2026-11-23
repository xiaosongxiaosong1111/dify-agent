"""Independent 375 freeze, direct-approval and once-only live admission.

No approval, attempt or live marker is created by import.  Secret values and real
task text are never printed or copied into logs here.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import derivation

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
BATCH = derivation.BATCH
NAMES = set(derivation.NAMES)
PACKAGE_FILES = set(derivation.PACKAGE_FILES)
FROZEN_SOURCE_FILES = set(derivation.FROZEN_SOURCE_FILES)
PINNED = set(derivation.PINNED_337) | set(derivation.PINNED_374)
LIMITS = derivation.LIMITS
UPPER = derivation.UPPER
SEALS = derivation.SEALS
ISOLATED = derivation.ISOLATED
OLD_REFS = {
    'call_b4c700f1b4d24950a303b16fbe157440/q0',
    'call_ae6b67f5efb74c0c92f2dff733484166/q0',
    'call_19a54287e07f4214acf3a0235a269efc/q0',
    'call_2198e5ab4b42451d988d3bda9e350cb3/q0',
    'call_f946936e3fa747669cd271019cf87e75/q0',
}
APPROVAL_KEYS = {'authorization_source', 'scope', 'decision', 'reply', 'question_ref',
                 'plan_sha256', 'manifest_sha256', 'limits', 'approved_model_slots',
                 'effective_model_http', 'json_repair_http'}
PROFILE_KEYS = {
    'schema_version', 'batch_id', 'approval_scope', 'approval_phrase',
    'approval_question_suffix', 'limits', 'new_conservative_upper',
    'approved_model_slots', 'effective_model_http', 'json_repair_http',
    'per_model_reserve_usd', 'model_total_usd', 'model_estimate_book_upper_usd',
    'dify_estimate_usd', 'combined_estimate_usd', 'billing_hard_cap', 'wall_seconds',
    'task_start_cap', 'task_minutes', 'runtime_build', 'runtime_version',
    'runtime_file_count', 'runtime_pid_observed', 'source_commit', 'source_dir',
    'source_commit_base', 'source_dir_base', 'source_normalization', 'source_pins',
    'expected_counts', 'workspace_id', 'environment_id', 'provider_id', 'provider_model',
    'provider_protocol', 'console_version', 'proposal_doc', 'target_task_id',
    'target_task_revision', 'protected_old_count', 'protected_337_count',
    'protected_base_count', 'protected_371_entries', 'protected_total_count',
    'sealed_index_sha256', 'protected_seals', 'isolated_paths',
}
PLAN_KEYS = {
    'schema_version', 'batch_id', 'approval_state', 'proposal_state', 'source_commit',
    'source_commit_shared', 'source_commit_base', 'source_dir', 'source_dir_base',
    'source_normalization', 'source_pins', 'source_file_sha256', 'frozen_source_files',
    'proposal_doc', 'proposal_sha256', 'approved_scope_sha256', 'limits',
    'new_conservative_upper', 'approved_model_slots', 'effective_model_http',
    'json_repair_http', 'per_model_reserve_usd', 'model_total_usd',
    'model_estimate_book_upper_usd', 'dify_estimate_usd', 'combined_estimate_usd',
    'billing_hard_cap', 'wall_seconds', 'task_start_cap', 'task_minutes',
    'runtime_build', 'runtime_version', 'runtime_file_count', 'runtime_pid',
    'runtime_manifest_sha256', 'runtime_process_sha256', 'backend_path', 'provider_id',
    'provider_sha256', 'environment_id', 'environment_sha256',
    'environment_identity_sha256', 'target_task_id',
    'target_task_revision', 'target_task_sha256', 'target_budget_sha256',
    'execution_limits_present', 'history_prefix', 'intake_review_sha256',
    'decision_report_sha256', 'cases_sha256', 'configuration_sha256',
    'requirements_sha256', 'interview_reviews', 'expected_counts', 'protected_data',
    'isolated_paths', 'protected_isolated', 'protected_files', 'protected_old_count',
    'protected_337_count', 'protected_base_count', 'protected_371_entries',
    'protected_total_count', 'sealed_index_sha256', 'protected_seals', 'known_apps',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def digest(value):
    return derivation.digest(value)


def _hex(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{64}', value))


def _githex(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{40}', value))


def _uuid(value):
    from uuid import UUID
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _int(value, label):
    require(type(value) is int, label + ' must be int')
    return value


def _bool(value, label):
    require(type(value) is bool, label + ' must be bool')
    return value


def _strict(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected), label + ' fields changed')
    require(all(type(value[key]) is int and value[key] == expected[key] for key in expected),
            label + ' must be exact ints')


IDENTITY_KEYS = ('id', 'base_url', 'console_workspace_id', 'version')


def environment_identity_sha256(env):
    require(isinstance(env, dict), 'Environment must be a mapping')
    return derivation.digest({key: env.get(key) for key in IDENTITY_KEYS})


def check_environment_identity(p, env):
    """Continuous gate: only URL/workspace/version identity must stay frozen."""
    require(isinstance(p, dict) and environment_identity_sha256(env)
            == p['environment_identity_sha256'], 'Environment identity changed')


def check_environment_profile(p, env):
    """Startup gate: the complete environment profile stays frozen."""
    require(isinstance(p, dict) and isinstance(env, dict)
            and derivation.digest(env) == p['environment_sha256'],
            'Environment profile changed')


def _money(value, label='amount'):
    require(isinstance(value, str) and value, label + ' must be decimal text')
    try:
        amount = Decimal(value)
    except InvalidOperation:
        require(False, label + ' is not decimal')
    require(amount.is_finite() and amount >= 0, label + ' must be finite and non-negative')
    return amount


def load(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result

    raw = Path(path).read_bytes()
    require(len(raw) <= 12000000, 'JSON too large')
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'Non-finite JSON'))


def _common():
    from common import ReadOnly, capture, known_apps
    return ReadOnly, capture, known_apps


def _head(project):
    return subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'],
                                   text=True).strip()


def _canonical(root):
    raw = Path(root)
    require(not raw.is_symlink() and raw.resolve() == PROJECT / 'work' / BATCH
            and not sys.flags.optimize, 'Canonical nonoptimized root required')
    require(PROJECT == Path(r'E:\workSpace\dify-agent'), 'Original project only')
    return raw.resolve()


def _source_pin_value(directory):
    if directory == derivation.SOURCE_DIR_337:
        return derivation.SOURCE_COMMIT_337, derivation.PINNED_337
    if directory == derivation.SOURCE_DIR_374:
        return derivation.SOURCE_COMMIT_374, derivation.PINNED_374
    raise RuntimeError('Source directory changed')


def validate_profile(p):
    require(isinstance(p, dict) and set(p) == PROFILE_KEYS, 'Profile fields changed')
    require(_int(p['schema_version'], 'schema_version') == 1 and p['batch_id'] == BATCH
            and p['approval_scope'] == BATCH, 'Profile identity changed')
    require(p['approval_phrase'] == '允许将371剩余范围明确改授375并新增1次登录，执行独立批'
            and p['approval_question_suffix'] == '/q0', 'Approval phrase changed')
    _strict(p['limits'], LIMITS, 'limits')
    _strict(p['new_conservative_upper'], UPPER, 'new_conservative_upper')
    require(_int(p['approved_model_slots'], 'approved_model_slots') == 3
            and _int(p['effective_model_http'], 'effective_model_http') == 3
            and _int(p['json_repair_http'], 'json_repair_http') == 0, 'Model slots changed')
    require((p['per_model_reserve_usd'], p['model_total_usd'],
             p['model_estimate_book_upper_usd'], p['dify_estimate_usd'],
             p['combined_estimate_usd']) ==
            ('0.100', '0.300', '3.355473652', '0.100', '0.400'), 'Cost bounds changed')
    require(_bool(p['billing_hard_cap'], 'billing_hard_cap') is False
            and _int(p['wall_seconds'], 'wall_seconds') == 3600
            and _int(p['task_start_cap'], 'task_start_cap') == 12
            and _int(p['task_minutes'], 'task_minutes') == 45, 'Time bounds changed')
    require(p['runtime_build'] == '0.411.0-90c28f738d4306fbff75'
            and p['runtime_version'] == '0.411.0'
            and _int(p['runtime_file_count'], 'runtime_file_count') == 298
            and _int(p['runtime_pid_observed'], 'runtime_pid_observed') > 0,
            'Runtime identity changed')
    require(p['source_commit'] == derivation.SOURCE_COMMIT_337
            and p['source_commit_base'] == derivation.SOURCE_COMMIT_374
            and p['source_dir'] == derivation.SOURCE_DIR_337
            and p['source_dir_base'] == derivation.SOURCE_DIR_374
            and p['source_normalization'] == derivation.SOURCE_NORMALIZATION,
            'Source identity changed')
    require(isinstance(p['source_pins'], dict)
            and set(p['source_pins']) == {derivation.SOURCE_DIR_337,
                                          derivation.SOURCE_DIR_374},
            'Source pin set changed')
    for directory in (derivation.SOURCE_DIR_337, derivation.SOURCE_DIR_374):
        expected_commit, expected_files = _source_pin_value(directory)
        spec = p['source_pins'][directory]
        require(isinstance(spec, dict) and set(spec) == {'commit', 'files'},
                'Source pin fields changed')
        require(spec['commit'] == expected_commit, 'Source pin commit changed')
        require(isinstance(spec['files'], list) and set(spec['files']) == set(expected_files)
                and len(spec['files']) == len(expected_files), 'Source pin files changed')
    _strict(p['expected_counts'], {'task': 27, 'environment': 10, 'provider': 2},
            'expected_counts')
    require(p['workspace_id'] == 'c3306c18-ceb2-4bee-b2d1-796ce2048f17'
            and p['environment_id'] == '202bfb35-2f92-47c1-bc1b-eac32082181d'
            and p['provider_id'] == '9513f594-c256-46b7-882a-35d9871bf9d0',
            'Public identity changed')
    require(p['provider_model'] == 'deepseek-flash'
            and p['provider_protocol'] == 'openai-compatible'
            and p['console_version'] == '1.17.1', 'Provider identity changed')
    require(p['proposal_doc'] == 'docs/reviewed-mainline375-plan-20261123.md',
            'Proposal path changed')
    require(_uuid(p['target_task_id'])
            and p['target_task_id'] == '1154f0c0-5e01-4492-b5c7-97bfbbbc2a61'
            and _int(p['target_task_revision'], 'target_task_revision') == 6,
            'Target Task changed')
    require((_int(p['protected_old_count'], 'protected_old_count'),
             _int(p['protected_337_count'], 'protected_337_count'),
             _int(p['protected_base_count'], 'protected_base_count'),
             _int(p['protected_371_entries'], 'protected_371_entries'),
             _int(p['protected_total_count'], 'protected_total_count')) ==
            (733, 24, 795, 35, 831), 'Protection counts changed')
    require(p['sealed_index_sha256'] ==
            'c9d9ef645118610e0fce61f5aed8deeb3e30f7e56b17d2c58511a25e5eef04e0'
            and p['protected_seals'] == SEALS, 'Protection seals changed')
    require(p['isolated_paths'] == ISOLATED, 'Isolated roots changed')


def load_profile(path):
    p = load(path)
    validate_profile(p)
    return p


def _profile(root):
    return load_profile(Path(root) / 'profile.json')


def _history_rows(value):
    require(isinstance(value, dict) and set(value) ==
            {'messages', 'versions', 'planning_runs', 'intake_history', 'runs',
             'interview_attempts'}, 'History prefix fields changed')
    counts = {'messages': 6, 'versions': 5, 'planning_runs': 1,
              'intake_history': 1, 'runs': 0}
    for key, count in counts.items():
        row = value[key]
        require(isinstance(row, dict) and set(row) == {'count', 'sha256'},
                'History prefix fields changed: ' + key)
        require(_int(row['count'], key + ' count') == count and _hex(row['sha256']),
                'History prefix changed: ' + key)
    row = value['interview_attempts']
    require(isinstance(row, dict) and set(row) == {'present', 'count', 'sha256'},
            'interview_attempts prefix fields changed')
    _bool(row['present'], 'interview_attempts present')
    require(_int(row['count'], 'interview_attempts count') == 0
            and row['sha256'] == digest([]), 'interview_attempts prefix changed')


def _interview_rows(value, target):
    require(isinstance(value, dict) and set(value) ==
            {'first_interview', 'complete_interview'}, 'Interview review set changed')
    for stage, row in value.items():
        fact = derivation.INTERVIEW_FACTS[stage]
        require(isinstance(row, dict) and set(row) ==
                {'source_sha256', 'receipt_sha256', 'task_id', 'revision', 'decision',
                 'actor'}, 'Interview review fields changed')
        require(_hex(row['source_sha256'])
                and row['source_sha256'] == fact['source_sha256']
                and _hex(row['receipt_sha256'])
                and row['task_id'] == target
                and _int(row['revision'], 'interview revision') == fact['revision']
                and row['decision'] == 'proceed'
                and row['actor'] == 'agent_delegated',
                'Interview review binding changed: ' + stage)


def validate_plan(p, prof, project=PROJECT):
    require(isinstance(p, dict) and set(p) == PLAN_KEYS, 'Plan fields changed')
    require(_int(p['schema_version'], 'schema_version') == 1 and p['batch_id'] == BATCH
            and p['approval_state'] == 'pending'
            and p['proposal_state'] == 'proposed_not_approved',
            'Plan is not a pending proposal')
    require(_githex(p['source_commit'])
            and p['source_commit_shared'] == prof['source_commit']
            and p['source_commit_base'] == prof['source_commit_base']
            and p['source_dir'] == prof['source_dir']
            and p['source_dir_base'] == prof['source_dir_base']
            and p['source_normalization'] == prof['source_normalization'],
            'Plan source commit changed')
    require(p['source_pins'] == prof['source_pins'], 'Plan source pins changed')
    require(isinstance(p['source_file_sha256'], dict)
            and set(p['source_file_sha256']) == PINNED
            and all(_hex(v) for v in p['source_file_sha256'].values()),
            'Plan source hashes changed')
    require(isinstance(p['frozen_source_files'], dict)
            and set(p['frozen_source_files']) == FROZEN_SOURCE_FILES
            and all(_hex(v) for v in p['frozen_source_files'].values()),
            'Plan frozen files changed')
    require(p['proposal_doc'] == prof['proposal_doc']
            and _hex(p['proposal_sha256'])
            and p['approved_scope_sha256'] == p['proposal_sha256'],
            'Plan proposal binding changed')
    _strict(p['limits'], LIMITS, 'limits')
    _strict(p['new_conservative_upper'], UPPER, 'new_conservative_upper')
    require(_int(p['approved_model_slots'], 'approved_model_slots') == 3
            and _int(p['effective_model_http'], 'effective_model_http') == 3
            and _int(p['json_repair_http'], 'json_repair_http') == 0,
            'Plan limits changed')
    require((p['per_model_reserve_usd'], p['model_total_usd'],
             p['model_estimate_book_upper_usd'], p['dify_estimate_usd'],
             p['combined_estimate_usd']) ==
            ('0.100', '0.300', '3.355473652', '0.100', '0.400')
            and _bool(p['billing_hard_cap'], 'billing_hard_cap') is False,
            'Plan cost changed')
    require(_int(p['wall_seconds'], 'wall_seconds') == 3600
            and _int(p['task_start_cap'], 'task_start_cap') == 12
            and _int(p['task_minutes'], 'task_minutes') == 45, 'Plan time changed')
    require((p['runtime_build'], p['runtime_version'],
             _int(p['runtime_file_count'], 'runtime_file_count')) ==
            (prof['runtime_build'], prof['runtime_version'], prof['runtime_file_count'])
            and _int(p['runtime_pid'], 'runtime_pid') > 0
            and _hex(p['runtime_manifest_sha256']) and _hex(p['runtime_process_sha256']),
            'Plan runtime changed')
    require(p['backend_path'] == str(Path(project) / '.runtime' / 'snapshots' /
                                     prof['runtime_build'] / 'backend'),
            'Plan backend path changed')
    require(p['provider_id'] == prof['provider_id']
            and p['environment_id'] == prof['environment_id']
            and _hex(p['provider_sha256']) and _hex(p['environment_sha256'])
            and _hex(p['environment_identity_sha256']),
            'Plan public identity changed')
    require(p['target_task_id'] == prof['target_task_id']
            and _int(p['target_task_revision'], 'target_task_revision') == 6
            and _hex(p['target_task_sha256']) and _hex(p['target_budget_sha256'])
            and _bool(p['execution_limits_present'], 'execution_limits_present') is False,
            'Plan target Task changed')
    _history_rows(p['history_prefix'])
    require(_hex(p['intake_review_sha256']) and _hex(p['decision_report_sha256'])
            and _hex(p['cases_sha256']) and _hex(p['configuration_sha256'])
            and _hex(p['requirements_sha256']), 'Plan target digests changed')
    _interview_rows(p['interview_reviews'], prof['target_task_id'])
    _strict(p['expected_counts'], {'task': 27, 'environment': 10, 'provider': 2},
            'expected_counts')
    require(isinstance(p['protected_data'], dict), 'Plan protected data missing')
    require(p['isolated_paths'] == prof['isolated_paths']
            and isinstance(p['protected_isolated'], dict)
            and set(p['protected_isolated']) == set(prof['isolated_paths'])
            and all(isinstance(v, dict) for v in p['protected_isolated'].values()),
            'Plan protected roots changed')
    require(isinstance(p['protected_files'], dict)
            and len(p['protected_files']) == prof['protected_total_count'] == 831
            and all(isinstance(k, str) and k and _hex(v)
                    for k, v in p['protected_files'].items()),
            'Plan protected files changed')
    require((_int(p['protected_old_count'], 'protected_old_count'),
             _int(p['protected_337_count'], 'protected_337_count'),
             _int(p['protected_base_count'], 'protected_base_count'),
             _int(p['protected_371_entries'], 'protected_371_entries'),
             _int(p['protected_total_count'], 'protected_total_count')) ==
            (733, 24, 795, 35, 831)
            and p['sealed_index_sha256'] == prof['sealed_index_sha256']
            and p['protected_seals'] == prof['protected_seals'],
            'Plan protection counts changed')
    require(isinstance(p['known_apps'], list)
            and all(_uuid(v) for v in p['known_apps']), 'Plan known apps changed')


def verify_frozen_files(root, p, prof, source_project=PROJECT, project=PROJECT,
                        check_head=False, check_runtime=True):
    root = Path(root).resolve()
    manifest = load(root / 'manifest.json')
    require(_int(manifest.get('schema_version'), 'manifest schema_version') == 1
            and manifest.get('batch_id') == BATCH
            and set(manifest.get('files', {})) == NAMES, 'Manifest identity changed')
    for name, value in manifest['files'].items():
        path = root / name
        require(not path.is_symlink() and path.resolve().parent == root
                and path.is_file() and sha(path) == value,
                'Frozen source changed: ' + name)
    require(load(root / 'plan.json') == p, 'Plan bytes changed')
    require(all(sha(root / name) == value
                for name, value in p['frozen_source_files'].items()),
            'Plan source digest changed')
    verified = derivation.verified_sources(source_project, prof['source_pins'])
    require({name: sha_bytes(raw) for name, raw in verified.items()} ==
            p['source_file_sha256'], 'Plan source hashes changed')
    for name, raw in verified.items():
        require((root / name).read_bytes() == derivation.derive(name, raw),
                'Pinned/derived copy changed: ' + name)
    require(b"BATCH_ID='autonomous-dual375'" in (root / 'common.py').read_bytes()
            and b'autonomous-dual337' not in (root / 'common.py').read_bytes(),
            'Derived common changed')
    require(b"if mode=='live'" in (root / 'journey.py').read_bytes()
            and b"'reused_interviews': 'synthetic_prior_shape'" not in
            (root / 'journey.py').read_bytes(), 'Derived journey changed')
    require(sha(root / 'approved_scope.md') == p['approved_scope_sha256'],
            'Proposal bytes changed')
    proposal = Path(project) / p['proposal_doc']
    require(proposal.is_file() and not proposal.is_symlink()
            and sha_bytes(proposal.read_bytes()) == p['proposal_sha256'],
            'Proposal document changed')
    if check_head:
        require(_head(source_project) == p['source_commit'], 'Source commit changed')
    if check_runtime:
        folder = Path(project) / '.runtime' / 'snapshots' / p['runtime_build']
        runtime = load(folder / 'runtime-manifest.json')
        require(sha(folder / 'runtime-manifest.json') == p['runtime_manifest_sha256']
                and runtime.get('shared_data_copied') is False
                and len(runtime.get('files', {})) == p['runtime_file_count'] == 298,
                'Runtime manifest changed')
        require(all(sha(Path(project) / name) == value and sha(folder / name) == value
                    for name, value in runtime['files'].items()), 'Running source changed')
        require(sha(Path(project) / 'runtime-process.ps1') == p['runtime_process_sha256'],
                'Runtime helper changed')
    return True


def verify_frozen(root, p):
    root = _canonical(root)
    prof = _profile(root)
    validate_plan(p, prof)
    verify_frozen_files(root, p, prof)
    ReadOnly, _capture, _known_apps = _common()
    data = ReadOnly(PROJECT / 'data')
    require(digest(data.get('provider', p['provider_id'])) == p['provider_sha256'],
            'Provider/pricing changed')
    env = data.get('environment', p['environment_id'])
    check_environment_identity(p, env)
    return True


def _old371_admission(p):
    """Re-read the sealed old 371 stop evidence at admission, not just its hash."""
    base = (PROJECT / 'work/autonomous-dual371').resolve()
    require(base.is_relative_to((PROJECT / 'work').resolve()) and base.is_dir(),
            'Old 371 sealed directory changed')
    expected = {'model': 3, 'reads': 6, 'login': 1, 'import': 0,
                'publish': 0, 'key': 0, 'run': 0}
    for name, count_key, check_task in (
            ('live-output/progress.json', 'dispatch_counts', True),
            ('attempt.json', 'counts', False)):
        path = base / name
        require(path.is_file() and not path.is_symlink(), 'Old 371 record missing')
        key = path.relative_to(PROJECT).as_posix()
        require(key in p['protected_files'] and sha(path) == p['protected_files'][key],
                'Old 371 record not sealed')
        value = load(path)
        require(isinstance(value, dict) and value.get('state') == 'stopped',
                'Old 371 is not stopped')
        counts = value.get(count_key)
        require(isinstance(counts, dict) and set(counts) == set(expected)
                and all(type(counts[k]) is int and counts[k] == expected[k]
                        for k in expected), 'Old 371 dispatch changed')
        require(_int(value.get('physical_http'), 'physical_http') == 10,
                'Old 371 physical count changed')
        require(not value.get('deliveries') and not value.get('apps')
                and not value.get('bundles'), 'Old 371 resources changed')
        require(value.get('workflow_plan') is None and value.get('dify_app_id') is None
                and value.get('artifact') is None, 'Old 371 graph/App/artifact changed')
        if check_task:
            require(value.get('task_id') == p['target_task_id'], 'Old 371 task changed')
    return True


def verify_history(p):
    ReadOnly, capture, _known_apps = _common()
    require(all(capture(ReadOnly(PROJECT / path)) == p['protected_isolated'][label]
                for label, path in p['isolated_paths'].items()),
            'Old isolated data/fees changed')
    require(len(p['protected_files']) == 831
            and all((PROJECT / name).resolve().is_relative_to(PROJECT / 'work')
                    and sha(PROJECT / name) == value
                    for name, value in p['protected_files'].items()),
            'Old sealed evidence changed')
    _old371_admission(p)
    return True


def validate_authorization(a, plan, plan_sha, manifest_sha, prof):
    require(isinstance(a, dict) and APPROVAL_KEYS <= set(a), 'Approval fields missing')
    require(a['authorization_source'] == 'direct_user_reply'
            and a['scope'] == BATCH and a['decision'] == 'approve'
            and a['reply'] == prof['approval_phrase'],
            'Direct new scope approval missing')
    ref = a['question_ref']
    require(isinstance(ref, str)
            and bool(re.fullmatch(r'call_[A-Za-z0-9_-]{1,64}/q0', ref))
            and ref not in OLD_REFS, 'New question_ref required')
    require(a['plan_sha256'] == plan_sha and a['manifest_sha256'] == manifest_sha,
            'Approval not bound to frozen package')
    _strict(a['limits'], LIMITS, 'approval limits')
    require(_int(a['approved_model_slots'], 'approved_model_slots') == 3
            and _int(a['effective_model_http'], 'effective_model_http') == 3
            and _int(a['json_repair_http'], 'json_repair_http') == 0,
            'Approval limits/slots changed')
    require((_int(plan['approved_model_slots'], 'plan approved_model_slots'),
             _int(plan['effective_model_http'], 'plan effective_model_http'),
             _int(plan['json_repair_http'], 'plan json_repair_http')) == (3, 3, 0),
            'Frozen package slot mismatch')


def approved(root, p):
    path = Path(root) / 'approval.json'
    require(path.is_file() and not path.is_symlink(), 'Approval missing')
    a = load(path)
    validate_authorization(a, p, sha(Path(root) / 'plan.json'),
                           sha(Path(root) / 'manifest.json'), _profile(root))
    return True


def assert_unconsumed(root, include_approval=False):
    names = ['attempt.json', 'worker-started.json']
    if include_approval:
        names.append('approval.json')
    for name in names:
        require(not (Path(root) / name).exists(), 'Consumed package cannot replay: ' + name)


def _runtime(p, prof):
    from runtime_reference import runtime_check
    value = runtime_check(p)
    require(type(value.get('verified_pid')) is int and value['verified_pid'] > 0,
            'Observed PID invalid')
    return value


def _production(p):
    ReadOnly, capture, _known_apps = _common()
    data = ReadOnly(PROJECT / 'data')
    require(capture(data) == p['protected_data'], 'Production baseline changed')
    task = data.get('task', p['target_task_id'])
    budget = data.get('task_budget', p['target_task_id'])
    limits = data.get('execution_limits', p['target_task_id'])
    require(digest(task) == p['target_task_sha256']
            and digest(budget) == p['target_budget_sha256']
            and limits is None, 'Target Task/budget changed')


def approve(root, authorization):
    root = _canonical(root)
    p = load(root / 'plan.json')
    prof = _profile(root)
    verify_frozen(root, p)
    verify_history(p)
    _production(p)
    _runtime(p, prof)
    assert_unconsumed(root, include_approval=True)
    path = Path(authorization).resolve()
    require(path.is_file() and not path.is_symlink()
            and not path.is_relative_to(PROJECT),
            'Direct approval file must be outside project')
    a = load(path)
    validate_authorization(a, p, sha(root / 'plan.json'), sha(root / 'manifest.json'), prof)
    verify_frozen(root, p)
    verify_history(p)
    _production(p)
    _runtime(p, prof)
    assert_unconsumed(root, include_approval=True)
    value = {key: a[key] for key in APPROVAL_KEYS}
    with (root / 'approval.json').open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2)
    require(sha(root / 'plan.json') == a['plan_sha256']
            and sha(root / 'manifest.json') == a['manifest_sha256'],
            'Approval write changed frozen bytes')
    print(json.dumps({'state': 'approved_not_dispatched',
                      'plan_sha256': a['plan_sha256'],
                      'manifest_sha256': a['manifest_sha256']}, ensure_ascii=False))


def authenticate_worker(root, p):
    """Authenticate package and approval before any DB or secret read."""
    root = _canonical(root)
    prof = _profile(root)
    validate_plan(p, prof)
    verify_frozen_files(root, p, prof)
    approved(root, p)
    attempt_path = root / 'attempt.json'
    require(attempt_path.is_file() and not attempt_path.is_symlink(), 'Admission missing')
    attempt = load(attempt_path)
    require(attempt.get('state') == 'admitted'
            and attempt.get('approval_sha256') == sha(root / 'approval.json'),
            'Admission missing')
    require(not (root / 'worker-started.json').exists(), 'Worker already started')
    return True


def authorize_worker(root, p):
    """Exclusive one-worker gate: frozen approval first, protection/runtime, then marker."""
    root = _canonical(root)
    marker = root / 'worker-started.json'
    require(not marker.exists(), 'Worker already started')
    authenticate_worker(root, p)
    prof = _profile(root)
    require(not marker.exists(), 'Worker already started')
    verify_history(p)
    _production(p)
    _runtime(p, prof)
    attempt = load(root / 'attempt.json')
    require(attempt.get('state') == 'admitted'
            and attempt.get('approval_sha256') == sha(root / 'approval.json'),
            'Admission missing')
    require(not marker.exists(), 'Worker already started')
    try:
        with marker.open('x', encoding='utf-8') as f:
            json.dump({'pid': os.getpid(), 'plan_sha256': sha(root / 'plan.json'),
                       'single_worker': True}, f)
    except FileExistsError:
        raise RuntimeError('Worker already started') from None


def validate_pending(root):
    root = _canonical(root)
    p = load(root / 'plan.json')
    prof = _profile(root)
    verify_frozen(root, p)
    verify_history(p)
    assert_unconsumed(root, include_approval=True)
    _production(p)
    return {'state': 'pending_not_approved', 'limits': LIMITS,
            'runtime': _runtime(p, prof)}


def _preflight(root):
    p = load(root / 'plan.json')
    prof = _profile(root)
    verify_frozen(root, p)
    approved(root, p)
    verify_history(p)
    assert_unconsumed(root)
    _production(p)
    return p, _runtime(p, prof)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['validate-pending', 'approve', 'validate', 'live'])
    parser.add_argument('--authorization')
    args = parser.parse_args()
    root = HERE
    if args.action == 'validate-pending':
        print(json.dumps(validate_pending(root), ensure_ascii=False))
        return
    if args.action == 'approve':
        require(args.authorization, 'Authorization file required')
        approve(root, args.authorization)
        return
    p, runtime = _preflight(root)
    if args.action == 'validate':
        print(json.dumps({'state': 'approved_not_dispatched', 'limits': LIMITS,
                          'runtime': runtime}, ensure_ascii=False))
        return
    value = {'state': 'admitted', 'approval_sha256': sha(root / 'approval.json'),
             'plan_sha256': sha(root / 'plan.json'), 'runtime': runtime,
             'automatic_retry': False}
    with (root / 'attempt.json').open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2)
    try:
        from worker import run
        result = run('live', root / 'live-output', p)
        value.update(state=result['state'], counts=result.get('dispatch_counts'),
                     physical_http=result['physical_http'])
    except BaseException as exc:
        value.update(state='stopped', failure_type=type(exc).__name__)
    finally:
        tmp = root / 'attempt-writing.tmp'
        tmp.write_text(json.dumps(value, indent=2), 'utf-8')
        os.replace(tmp, root / 'attempt.json')
    require(value['state'] == 'passed',
            'Batch consumed/stopped; no retry or stage continuation')


if __name__ == '__main__':
    main()
