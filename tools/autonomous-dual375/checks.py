"""Public negative and wiring checks for 375; no DB, secret, HTTP or real work receipt."""
import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import uuid
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
WORK = (PROJECT / 'work').resolve()
sys.path.insert(0, str(HERE))
import derivation
import execute
import prepare

H = 'a' * 64
PLAN_SHA = 'b' * 64
MANIFEST_SHA = 'c' * 64


def require(value, message):
    if not value:
        raise RuntimeError(message)


def rejected(fn, label):
    try:
        fn()
    except RuntimeError:
        return label
    raise AssertionError('Accepted ' + label)


def fake_task(profile):
    return {
        'id': profile['target_task_id'], 'revision': 6,
        'messages': [{} for _ in range(6)],
        'versions': [{} for _ in range(5)],
        'planning_runs': [{'decision_report': {'needs_decision': [
            {'question': '公开合成旧规划问题'}]}}],
        'intake_history': [{}], 'runs': [],
        'intake_review': {'source': 'model'},
        'test_cases': [{'id': 'public-case'}],
        'configuration': {'temperature': 0.2},
        'requirements': {'goal': '公开合成需求，不代表真实原文'},
    }


def fake_interviews(profile):
    result = {}
    for stage in ('first_interview', 'complete_interview'):
        fact = derivation.INTERVIEW_FACTS[stage]
        result[stage] = {'source_sha256': fact['source_sha256'], 'receipt_sha256': H,
                         'task_id': profile['target_task_id'], 'revision': fact['revision'],
                         'decision': 'proceed', 'actor': 'agent_delegated'}
    return result


def fake_files():
    return {'work/sealed-' + str(index) + '.json': H for index in range(831)}


def build_plan(profile, project=PROJECT):
    return {
        'schema_version': 1, 'batch_id': execute.BATCH, 'approval_state': 'pending',
        'proposal_state': 'proposed_not_approved', 'source_commit': 'd' * 40,
        'source_commit_shared': profile['source_commit'],
        'source_commit_base': profile['source_commit_base'],
        'source_dir': profile['source_dir'], 'source_dir_base': profile['source_dir_base'],
        'source_normalization': profile['source_normalization'],
        'source_pins': profile['source_pins'],
        'source_file_sha256': {name: H for name in
                               derivation.PINNED_337 + derivation.PINNED_374},
        'frozen_source_files': {name: H for name in derivation.FROZEN_SOURCE_FILES},
        'proposal_doc': profile['proposal_doc'], 'proposal_sha256': H,
        'approved_scope_sha256': H, 'limits': profile['limits'],
        'new_conservative_upper': profile['new_conservative_upper'],
        'approved_model_slots': profile['approved_model_slots'],
        'effective_model_http': profile['effective_model_http'],
        'json_repair_http': profile['json_repair_http'],
        'per_model_reserve_usd': profile['per_model_reserve_usd'],
        'model_total_usd': profile['model_total_usd'],
        'model_estimate_book_upper_usd': profile['model_estimate_book_upper_usd'],
        'dify_estimate_usd': profile['dify_estimate_usd'],
        'combined_estimate_usd': profile['combined_estimate_usd'],
        'billing_hard_cap': profile['billing_hard_cap'],
        'wall_seconds': profile['wall_seconds'],
        'task_start_cap': profile['task_start_cap'],
        'task_minutes': profile['task_minutes'],
        'runtime_build': profile['runtime_build'],
        'runtime_version': profile['runtime_version'],
        'runtime_file_count': profile['runtime_file_count'], 'runtime_pid': 12020,
        'runtime_manifest_sha256': H, 'runtime_process_sha256': H,
        'backend_path': str(Path(project) / '.runtime' / 'snapshots' /
                            profile['runtime_build'] / 'backend'),
        'provider_id': profile['provider_id'], 'provider_sha256': H,
        'environment_id': profile['environment_id'], 'environment_sha256': H,
        'environment_identity_sha256': H,
        'target_task_id': profile['target_task_id'], 'target_task_revision': 6,
        'target_task_sha256': H, 'target_budget_sha256': H,
        'execution_limits_present': False,
        'history_prefix': derivation.history_prefix(fake_task(profile)),
        'intake_review_sha256': H, 'decision_report_sha256': H,
        'cases_sha256': H, 'configuration_sha256': H, 'requirements_sha256': H,
        'interview_reviews': fake_interviews(profile),
        'expected_counts': profile['expected_counts'],
        'protected_data': {'objects': {}, 'secrets': {}, 'files': {}},
        'isolated_paths': profile['isolated_paths'],
        'protected_isolated': {key: {} for key in profile['isolated_paths']},
        'protected_files': fake_files(),
        'protected_old_count': profile['protected_old_count'],
        'protected_337_count': profile['protected_337_count'],
        'protected_base_count': profile['protected_base_count'],
        'protected_371_entries': profile['protected_371_entries'],
        'protected_total_count': profile['protected_total_count'],
        'sealed_index_sha256': profile['sealed_index_sha256'],
        'protected_seals': profile['protected_seals'], 'known_apps': [],
    }


def authorization(profile):
    return {'authorization_source': 'direct_user_reply', 'scope': execute.BATCH,
            'decision': 'approve', 'reply': profile['approval_phrase'],
            'question_ref': 'call_' + '0' * 32 + '/q0',
            'plan_sha256': PLAN_SHA, 'manifest_sha256': MANIFEST_SHA,
            'limits': execute.LIMITS, 'approved_model_slots': 3,
            'effective_model_http': 3, 'json_repair_http': 0}


def profile_checks(profile):
    passed = 0
    execute.validate_profile(profile)
    passed += 1
    bad = copy.deepcopy(profile)
    bad['limits']['model'] = True
    rejected(lambda: execute.validate_profile(bad), 'limits bool')
    passed += 1
    bad = copy.deepcopy(profile)
    bad['new_conservative_upper']['login'] = 49
    rejected(lambda: execute.validate_profile(bad), 'upper login')
    passed += 1
    bad = copy.deepcopy(profile)
    bad['approved_model_slots'] = 3.0
    rejected(lambda: execute.validate_profile(bad), 'slot float')
    passed += 1
    for key, value in (('combined_estimate_usd', '0.401'),
                       ('model_total_usd', '0.301'),
                       ('model_estimate_book_upper_usd', '3.355473653'),
                       ('dify_estimate_usd', '0.101'),
                       ('billing_hard_cap', True), ('wall_seconds', 3599),
                       ('task_start_cap', 13), ('task_minutes', 44),
                       ('runtime_build', '0.410.0-other'),
                       ('runtime_version', '0.410.0'),
                       ('runtime_file_count', 297),
                       ('runtime_pid_observed', 0),
                       ('source_commit', 'e' * 40),
                       ('source_commit_base', 'e' * 40),
                       ('source_dir', 'tools/other'),
                       ('source_dir_base', 'tools/other'),
                       ('source_normalization', 'other'),
                       ('expected_counts', {'task': 26, 'environment': 10,
                                            'provider': 2}),
                       ('target_task_id', str(uuid.uuid4())),
                       ('target_task_revision', 5),
                       ('protected_old_count', 732),
                       ('protected_337_count', 23),
                       ('protected_base_count', 794),
                       ('protected_371_entries', 34),
                       ('protected_total_count', 830),
                       ('sealed_index_sha256', 'f' * 64),
                       ('protected_seals', {}),
                       ('isolated_paths', {}),
                       ('proposal_doc', 'docs/other.md')):
        bad = copy.deepcopy(profile)
        bad[key] = value
        rejected(lambda bad=bad: execute.validate_profile(bad), 'profile ' + key)
        passed += 1
    bad = copy.deepcopy(profile)
    bad['source_pins']['tools/autonomous-dual337']['commit'] = 'e' * 40
    rejected(lambda: execute.validate_profile(bad), 'source pin commit')
    passed += 1
    bad = copy.deepcopy(profile)
    bad['source_pins']['tools/autonomous-dual374']['files'] = []
    rejected(lambda: execute.validate_profile(bad), 'source pin files')
    passed += 1
    return passed


def source_checks(profile):
    passed = 0
    verified = derivation.verified_sources(PROJECT, profile['source_pins'])
    require(set(verified) == set(derivation.PINNED_337) | set(derivation.PINNED_374),
            'Verified source set changed')
    passed += 1
    common = derivation.derive('common.py', verified['common.py'])
    require(b"BATCH_ID='autonomous-dual375'" in common
            and b'autonomous-dual337' not in common
            and b"MODEL_STAGES=('original_plan','modified_interview','modified_plan')" in common
            and b"MODEL_TOTAL_USD='0.300'" in common
            and b"'new_tasks':0,'model':3,'reads':122,'login':1" in common
            and b"'first_interview'" not in common, 'Derived common changed')
    module = types.ModuleType('_dual375_derived_common')
    module.__file__ = str(PROJECT / 'tools/autonomous-dual337/common.py')
    exec(compile(common, 'common.py', 'exec'), module.__dict__)
    require(module.BATCH_ID == derivation.BATCH and module.LIMITS == derivation.LIMITS
            and module.MODEL_STAGES == ('original_plan', 'modified_interview', 'modified_plan')
            and module.MODEL_TOTAL_USD == '0.300' and module.MODEL_CAP_USD == '0.100',
            'Derived common behavior changed')
    passed += 1
    journey = derivation.derive('journey.py', verified['journey.py'])
    require(b"if mode=='live'" in journey
            and b"'console_api' if mode=='live'" in journey
            and b"'actual_preserved_371_interviews'" in journey
            and b"synthetic_protocol=(mode!='live')" in journey
            and b"'reused_interviews': 'synthetic_prior_shape'" not in journey
            and b"'verification': 'synthetic_protocol_only'" not in journey,
            'Derived journey changed')
    tree = ast.parse(journey, filename='journey.py')
    intake = [node for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == 'post' and node.args
              and isinstance(node.args[0], ast.Constant)
              and node.args[0].value == '/intake/manual']
    require(len(intake) == 1, 'Derived journey intake call changed')
    note = {kw.arg: kw.value for kw in intake[0].keywords}.get('actor_note')
    require(isinstance(note, ast.IfExp), 'Derived actor note is not a live switch')
    passed += 1
    for name, raw in verified.items():
        if name.endswith('.py'):
            compile(derivation.derive(name, raw), name, 'exec')
        if name in {'common.py', 'journey.py'}:
            continue
        require(derivation.derive(name, raw) == raw, 'Unapproved source rewrite: ' + name)
        passed += 1
    local = derivation.local_bytes(PROJECT)
    require(set(local) == set(derivation.LOCAL_FILES) | {derivation.FREEZE_SOURCE},
            'Local source set changed')
    for name, raw in local.items():
        if name.endswith('.py'):
            compile(raw, name, 'exec')
    passed += 1
    old = b"BATCH_ID='autonomous-dual337'"
    rejected(lambda: derivation.replace_once(b'nothing', old,
                                              b"BATCH_ID='autonomous-dual375'", 'test'),
             'replacement count 0')
    rejected(lambda: derivation.replace_once(old + old, old,
                                              b"BATCH_ID='autonomous-dual375'", 'test'),
             'replacement count 2')
    passed += 1
    bad = copy.deepcopy(profile['source_pins'])
    bad['tools/autonomous-dual337']['commit'] = 'e' * 40
    rejected(lambda: derivation.verified_sources(PROJECT, bad), 'trusted commit changed')
    passed += 1
    with tempfile.TemporaryDirectory(dir=WORK, prefix='autonomous-dual375-inside-') as tmp:
        inside = Path(tmp).resolve()
        target = inside / 'file.py'
        target.write_text('public', 'utf-8')
        require(derivation._inside(inside, target, 'test') == target,
                'Inside file rejected')
        passed += 1
        with patch.object(Path, 'is_symlink', return_value=True):
            rejected(lambda: derivation._inside(inside, target, 'test'), 'source symlink')
        passed += 1
        outside = inside.parent / ('autonomous-dual375-outside-' + uuid.uuid4().hex)
        outside.mkdir()
        try:
            other = outside / 'file.py'
            other.write_text('public', 'utf-8')
            rejected(lambda: derivation._inside(inside, other, 'test'), 'source escaped')
            passed += 1
        finally:
            shutil.rmtree(outside, ignore_errors=True)
    return passed


def plan_checks(profile):
    passed = 0
    base = build_plan(profile)
    execute.validate_plan(base, profile)
    passed += 1
    alternate = copy.deepcopy(base)
    alternate['source_commit'] = 'a1' * 20
    execute.validate_plan(alternate, profile)
    passed += 1
    simple = [
        ('schema_version', 2), ('schema_version', True), ('batch_id', 'other'),
        ('approval_state', 'approved'), ('proposal_state', 'approved'),
        ('source_commit', 'x'), ('source_commit_shared', 'e' * 40),
        ('source_commit_base', 'e' * 40), ('source_dir', 'tools/other'),
        ('source_dir_base', 'tools/other'), ('source_normalization', 'other'),
        ('source_pins', {}), ('source_file_sha256', {}),
        ('frozen_source_files', {}), ('proposal_doc', 'docs/other.md'),
        ('proposal_sha256', 'x'), ('approved_scope_sha256', 'e' * 64),
        ('limits', {'new_tasks': 1}), ('limits', dict(execute.LIMITS, model=True)),
        ('new_conservative_upper', {'model': 58}),
        ('new_conservative_upper', dict(execute.UPPER, login=51)),
        ('approved_model_slots', 4), ('approved_model_slots', True),
        ('effective_model_http', 2), ('json_repair_http', 1),
        ('per_model_reserve_usd', '0.101'), ('model_total_usd', '0.301'),
        ('model_estimate_book_upper_usd', '3.355473653'),
        ('dify_estimate_usd', '0.101'), ('combined_estimate_usd', '0.401'),
        ('billing_hard_cap', True), ('wall_seconds', 3599),
        ('task_start_cap', 13), ('task_minutes', 44),
        ('runtime_build', '0.410.0-other'), ('runtime_version', '0.410.0'),
        ('runtime_file_count', 297), ('runtime_file_count', True),
        ('runtime_pid', 0), ('runtime_pid', 12020.0),
        ('runtime_manifest_sha256', 'x'), ('runtime_process_sha256', 'x'),
        ('backend_path', 'other'), ('provider_id', str(uuid.uuid4())),
        ('environment_id', str(uuid.uuid4())), ('provider_sha256', 'x'),
        ('environment_sha256', 'x'), ('environment_identity_sha256', 'x'),
        ('target_task_id', str(uuid.uuid4())),
        ('target_task_revision', 5), ('target_task_revision', True),
        ('target_task_sha256', 'x'), ('target_budget_sha256', 'x'),
        ('execution_limits_present', True), ('execution_limits_present', 0),
        ('intake_review_sha256', 'x'), ('decision_report_sha256', 'x'),
        ('cases_sha256', 'x'), ('configuration_sha256', 'x'),
        ('requirements_sha256', 'x'), ('expected_counts', {'task': 26}),
        ('expected_counts', {'task': True, 'environment': 10, 'provider': 2}),
        ('protected_data', []), ('isolated_paths', {}),
        ('protected_isolated', {}), ('protected_files', {}),
        ('protected_old_count', 732), ('protected_337_count', 23),
        ('protected_base_count', 794), ('protected_371_entries', 34),
        ('protected_total_count', 830), ('sealed_index_sha256', 'f' * 64),
        ('sealed_index_sha256', 'f' * 64), ('protected_seals', {}),
        ('known_apps', 'x'), ('known_apps', ['not-a-uuid']),
    ]
    for key, value in simple:
        bad = copy.deepcopy(base)
        bad[key] = value
        rejected(lambda bad=bad: execute.validate_plan(bad, profile), 'plan ' + key)
        passed += 1
    bad = copy.deepcopy(base)
    bad['history_prefix']['messages']['count'] = 5
    rejected(lambda: execute.validate_plan(bad, profile), 'history count')
    passed += 1
    bad = copy.deepcopy(base)
    bad['history_prefix']['interview_attempts']['present'] = 1
    rejected(lambda: execute.validate_plan(bad, profile), 'history present')
    passed += 1
    bad = copy.deepcopy(base)
    del bad['history_prefix']['runs']
    rejected(lambda: execute.validate_plan(bad, profile), 'history missing')
    passed += 1
    bad = copy.deepcopy(base)
    bad['interview_reviews']['first_interview']['actor'] = 'synthetic_protocol'
    rejected(lambda: execute.validate_plan(bad, profile), 'review actor')
    passed += 1
    bad = copy.deepcopy(base)
    bad['interview_reviews']['complete_interview']['decision'] = 'reject'
    rejected(lambda: execute.validate_plan(bad, profile), 'review decision')
    passed += 1
    bad = copy.deepcopy(base)
    bad['interview_reviews']['first_interview']['revision'] = 6
    rejected(lambda: execute.validate_plan(bad, profile), 'review first revision')
    passed += 1
    bad = copy.deepcopy(base)
    bad['interview_reviews']['complete_interview']['revision'] = 3
    rejected(lambda: execute.validate_plan(bad, profile), 'review complete revision')
    passed += 1
    bad = copy.deepcopy(base)
    bad['interview_reviews']['first_interview']['source_sha256'] = H
    rejected(lambda: execute.validate_plan(bad, profile), 'review source digest')
    passed += 1
    bad = copy.deepcopy(base)
    del bad['interview_reviews']['first_interview']
    rejected(lambda: execute.validate_plan(bad, profile), 'review missing')
    passed += 1
    bad = copy.deepcopy(base)
    bad['protected_files'] = dict(bad['protected_files'])
    bad['protected_files'].pop(next(iter(bad['protected_files'])))
    rejected(lambda: execute.validate_plan(bad, profile), 'protected one less')
    passed += 1
    bad = copy.deepcopy(base)
    bad['protected_files'] = dict(bad['protected_files'])
    bad['protected_files']['work/extra.json'] = H
    rejected(lambda: execute.validate_plan(bad, profile), 'protected one more')
    passed += 1
    bad = copy.deepcopy(base)
    key = next(iter(bad['protected_files']))
    bad['protected_files'][key] = 'x'
    rejected(lambda: execute.validate_plan(bad, profile), 'protected sha')
    passed += 1
    bad = copy.deepcopy(base)
    bad['source_file_sha256'] = dict(bad['source_file_sha256'])
    bad['source_file_sha256'].pop(next(iter(bad['source_file_sha256'])))
    rejected(lambda: execute.validate_plan(bad, profile), 'source hash missing')
    passed += 1
    bad = copy.deepcopy(base)
    bad['frozen_source_files']['extra.py'] = H
    rejected(lambda: execute.validate_plan(bad, profile), 'frozen extra')
    passed += 1
    return passed


def authorization_checks(profile):
    passed = 0
    base = build_plan(profile)
    a = authorization(profile)
    execute.validate_authorization(a, base, PLAN_SHA, MANIFEST_SHA, profile)
    passed += 1
    mixed = copy.deepcopy(a)
    mixed['question_ref'] = 'call_New_ID-1/q0'
    execute.validate_authorization(mixed, base, PLAN_SHA, MANIFEST_SHA, profile)
    passed += 1
    for ref in execute.OLD_REFS:
        bad = copy.deepcopy(a)
        bad['question_ref'] = ref
        rejected(lambda bad=bad: execute.validate_authorization(
            bad, base, PLAN_SHA, MANIFEST_SHA, profile), 'old ref')
        passed += 1
    for ref in ('call_x/q1', 'x', 'call_/q0', 'call_a b/q0'):
        bad = copy.deepcopy(a)
        bad['question_ref'] = ref
        rejected(lambda bad=bad: execute.validate_authorization(
            bad, base, PLAN_SHA, MANIFEST_SHA, profile), 'bad ref')
        passed += 1
    for key, value in (
            ('authorization_source', 'agent_decision'), ('scope', 'autonomous-dual371'),
            ('decision', 'reject'),
            ('reply', '允许改授366未派发范围并新增1次登录，执行独立371批'),
            ('approved_model_slots', 4), ('approved_model_slots', True),
            ('effective_model_http', 2), ('json_repair_http', 1),
            ('limits', {'model': True}), ('limits', dict(execute.LIMITS, model=3.0)),
            ('plan_sha256', 'f' * 64), ('manifest_sha256', 'f' * 64)):
        bad = copy.deepcopy(a)
        bad[key] = value
        rejected(lambda bad=bad: execute.validate_authorization(
            bad, base, PLAN_SHA, MANIFEST_SHA, profile), 'approval ' + key)
        passed += 1
    bad = copy.deepcopy(a)
    del bad['question_ref']
    rejected(lambda: execute.validate_authorization(
        bad, base, PLAN_SHA, MANIFEST_SHA, profile), 'approval missing')
    passed += 1
    return passed


def gate_checks(profile):
    passed = 0
    rejected(lambda: execute._canonical(HERE), 'noncanonical source dir')
    passed += 1
    rejected(lambda: execute._canonical(PROJECT / 'work' / derivation.SOURCE_DIR_337),
             'noncanonical work path')
    passed += 1
    if execute.PROJECT != Path(r'E:\workSpace\dify-agent'):
        rejected(lambda: execute._canonical(execute.PROJECT / 'work' / execute.BATCH),
                 'clone project rejected')
        passed += 1
    with patch.object(Path, 'is_symlink', return_value=True):
        rejected(lambda: execute._canonical(execute.PROJECT / 'work' / execute.BATCH),
                 'symlink rejected')
    passed += 1
    with tempfile.TemporaryDirectory(dir=WORK, prefix='autonomous-dual375-mark-') as tmp:
        root = Path(tmp)
        execute.assert_unconsumed(root, include_approval=True)
        passed += 1
        (root / 'attempt.json').write_text('{}', 'utf-8')
        rejected(lambda: execute.assert_unconsumed(root), 'attempt replay')
        passed += 1
        (root / 'attempt.json').unlink()
        (root / 'worker-started.json').write_text('{}', 'utf-8')
        rejected(lambda: execute.assert_unconsumed(root), 'worker replay')
        passed += 1
        (root / 'worker-started.json').unlink()
        (root / 'approval.json').write_text('{}', 'utf-8')
        rejected(lambda: execute.assert_unconsumed(root, include_approval=True),
                 'approval replay')
        passed += 1
    with tempfile.TemporaryDirectory(dir=WORK, prefix='autonomous-dual375-batch-') as tmp:
        root = Path(tmp)
        batch = root / 'batch'
        batch.mkdir()
        (root / 'README.md').write_bytes(b'project-readme')
        (batch / 'README.md').write_bytes(b'batch-readme')
        resolved = prepare._batch_sealed(batch.resolve(), 'README.md',
                                         derivation.sha_bytes(b'batch-readme'))
        require(resolved == (batch / 'README.md').resolve(), 'Batch seal path changed')
        passed += 1
        rejected(lambda: prepare._batch_sealed(
            batch.resolve(), 'README.md', derivation.sha_bytes(b'project-readme')),
            'sealed evidence changed')
        passed += 1
        rejected(lambda: prepare._batch_sealed(
            batch.resolve(), '../outside', derivation.sha_bytes(b'batch-readme')),
            'sealed path escaped')
        passed += 1
        rejected(lambda: prepare._batch_sealed(
            batch.resolve(), str(batch / 'README.md'),
            derivation.sha_bytes(b'batch-readme')), 'sealed path absolute')
        passed += 1
    with tempfile.TemporaryDirectory(dir=WORK, prefix='autonomous-dual375-group-') as tmp:
        root = Path(tmp).resolve()
        batch = root / 'work' / 'batch'
        batch.mkdir(parents=True)
        (root / 'README.md').write_bytes(b'project')
        (batch / 'README.md').write_bytes(b'batch')
        index = {'README.md': derivation.sha_bytes(b'batch')}
        (batch / 'seal.json').write_text(json.dumps(index), 'utf-8')
        spec = {'path': 'work/batch/seal.json', 'sha256': derivation.sha(batch / 'seal.json'),
                'entries': 1}
        group = prepare._seal_group(root, spec)
        require(len(group) == 2 and 'work/batch/README.md' in group
                and 'work/batch/seal.json' in group, 'Seal group binding changed')
        passed += 1
    base_count = 733 + 24 + 1
    added = 26 + 1 + 2 + 1 + 6 + 1 + 35 + 1
    require(base_count == 758 and added == 73 and base_count + added == 831,
            'Protected arithmetic changed')
    passed += 1
    counts_366 = {'model': 0, 'reads': 0, 'login': 1, 'import': 0,
                  'publish': 0, 'key': 0, 'run': 0}
    good366 = {'state': 'stopped', 'dispatch_counts': dict(counts_366), 'physical_http': 1}
    prepare._old366_not_dispatched(good366, 'dispatch_counts')
    passed += 1
    bad = copy.deepcopy(good366)
    bad['dispatch_counts']['model'] = 1
    rejected(lambda: prepare._old366_not_dispatched(bad, 'dispatch_counts'),
             'old 366 dispatched')
    passed += 1
    counts = {'model': 3, 'reads': 6, 'login': 1, 'import': 0,
              'publish': 0, 'key': 0, 'run': 0}
    target = profile['target_task_id']
    good371 = {'state': 'stopped', 'dispatch_counts': dict(counts), 'physical_http': 10,
               'task_id': target}
    prepare._old371_not_dispatched(good371, 'dispatch_counts', target, check_task=True)
    passed += 1
    for key, value in (('model', 2), ('reads', 7), ('login', 2), ('import', 1),
                       ('publish', 1), ('key', 1), ('run', 1)):
        bad = copy.deepcopy(good371)
        bad['dispatch_counts'][key] = value
        rejected(lambda bad=bad: prepare._old371_not_dispatched(
            bad, 'dispatch_counts', target, check_task=True), 'old 371 count ' + key)
        passed += 1
    for change in ('physical', 'task', 'graph', 'resource'):
        bad = copy.deepcopy(good371)
        if change == 'physical':
            bad['physical_http'] = 9
        elif change == 'task':
            bad['task_id'] = str(uuid.uuid4())
        elif change == 'graph':
            bad['workflow_plan'] = {'nodes': []}
        else:
            bad['deliveries'] = [{'x': 1}]
        rejected(lambda bad=bad: prepare._old371_not_dispatched(
            bad, 'dispatch_counts', target, check_task=True), 'old 371 ' + change)
        passed += 1
    with tempfile.TemporaryDirectory(dir=WORK, prefix='autonomous-dual375-old371-') as tmp:
        root = Path(tmp).resolve()
        batch = root / 'work' / 'batch'
        (batch / 'live-output').mkdir(parents=True)
        progress = batch / 'live-output' / 'progress.json'
        attempt = batch / 'attempt.json'
        progress.write_text(json.dumps(good371), 'utf-8')
        attempt.write_text(json.dumps({'state': 'stopped', 'counts': dict(counts),
                                       'physical_http': 10}), 'utf-8')
        files = {'work/batch/live-output/progress.json': derivation.sha(progress),
                 'work/batch/attempt.json': derivation.sha(attempt)}
        prepare._old371_gate(root, batch, files, target)
        passed += 1
        progress.write_text(json.dumps(dict(good371, physical_http=9)), 'utf-8')
        files['work/batch/live-output/progress.json'] = derivation.sha(progress)
        rejected(lambda: prepare._old371_gate(root, batch, files, target),
                 'old 371 gate physical')
        passed += 1
    return passed


def local_source_checks(profile):
    passed = 0
    with tempfile.TemporaryDirectory(dir=WORK, prefix='autonomous-dual375-git-') as tmp:
        repo = Path(tmp).resolve()
        folder = repo / derivation.LOCAL_DIR
        folder.mkdir(parents=True)
        for name in derivation.LOCAL_FILES + (derivation.FREEZE_SOURCE,):
            (folder / name).write_bytes((HERE / name).read_bytes())

        def git(*args):
            return subprocess.run(['git', '-C', str(repo)] + list(args),
                                  capture_output=True, check=True)

        git('init', '-q')
        git('add', '.')
        git('-c', 'user.name=public', '-c', 'user.email=public@example.invalid',
            'commit', '-q', '-m', 'public fixture')
        commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                                         text=True).strip()
        local = derivation.verified_local(repo, commit)
        require(set(local) == set(derivation.LOCAL_FILES) | {derivation.FREEZE_SOURCE},
                'Committed local set changed')
        passed += 1
        worker = folder / 'worker.py'
        worker.write_bytes(worker.read_bytes() + b'\n# uncommitted local change\n')
        rejected(lambda: derivation.verified_local(repo, commit),
                 'uncommitted local source')
        passed += 1
        worker.write_bytes((HERE / 'worker.py').read_bytes())
        with patch.object(Path, 'is_symlink', return_value=True):
            rejected(lambda: derivation.verified_local(repo, commit), 'local symlink')
        passed += 1
    return passed


def interview_checks(profile):
    passed = 0
    require(derivation.INTERVIEW_FACTS == {
        'first_interview': {
            'revision': 3,
            'source_sha256': 'b03bee47e7abb510d1b8bb8b695fa914e48d9b3c0979609ffcbdf87a389a2ca7'},
        'complete_interview': {
            'revision': 6,
            'source_sha256': '075790d95559ed63dc060d64a3515ac0eaa2b31117c6bad84c344ad5b61619e7'}},
        'Sealed interview facts changed')
    passed += 1
    target = profile['target_task_id']
    rows = fake_interviews(profile)
    execute._interview_rows(rows, target)
    passed += 1
    bad = copy.deepcopy(rows)
    bad['first_interview']['revision'] = 6
    rejected(lambda: execute._interview_rows(bad, target), 'interview first revision')
    passed += 1
    bad = copy.deepcopy(rows)
    bad['complete_interview']['revision'] = 3
    rejected(lambda: execute._interview_rows(bad, target), 'interview complete revision')
    passed += 1
    bad = copy.deepcopy(rows)
    bad['first_interview']['source_sha256'] = H
    rejected(lambda: execute._interview_rows(bad, target), 'interview source digest')
    passed += 1
    bad = copy.deepcopy(rows)
    bad['complete_interview']['actor'] = 'root'
    rejected(lambda: execute._interview_rows(bad, target), 'interview actor')
    passed += 1
    with tempfile.TemporaryDirectory(
            dir=WORK, prefix='autonomous-dual375-interview-') as tmp:
        root = Path(tmp).resolve()
        base = root / 'work' / 'autonomous-dual371'
        live = base / 'live-output'
        live.mkdir(parents=True)
        bodies = {}
        receipts = {}
        for stage, revision in (('first_interview', 3), ('complete_interview', 6)):
            bodies[stage] = {'stage': stage, 'task_id': target, 'revision': revision,
                             'public': 'synthetic interview shape'}
            receipts[stage] = {'stage': stage, 'task_id': target, 'revision': revision,
                               'decision': 'proceed', 'actor': 'agent_delegated',
                               'source_sha256': derivation.digest(bodies[stage])}
        original_bodies = copy.deepcopy(bodies)
        original_receipts = copy.deepcopy(receipts)
        files = {}

        def write(stage):
            for label, value in (('review-source-' + stage + '.json', bodies[stage]),
                                 ('review-' + stage + '.json', receipts[stage])):
                path = live / label
                path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), 'utf-8')
                files[path.relative_to(root).as_posix()] = derivation.sha(path)

        def reset():
            bodies.clear()
            bodies.update(copy.deepcopy(original_bodies))
            receipts.clear()
            receipts.update(copy.deepcopy(original_receipts))
            files.clear()
            for stage in bodies:
                write(stage)

        reset()
        facts = {stage: {'revision': receipts[stage]['revision'],
                         'source_sha256': receipts[stage]['source_sha256']}
                 for stage in receipts}
        run = lambda: prepare._interview_reviews(root, profile, files)
        with patch.object(derivation, 'INTERVIEW_FACTS', facts):
            value = run()
            require(set(value) == {'first_interview', 'complete_interview'}
                    and value['first_interview']['revision'] == 3
                    and value['complete_interview']['revision'] == 6,
                    'Interview helper result changed')
            passed += 1
            source = live / 'review-source-first_interview.json'
            moved = base / 'review-source-first_interview.json'
            moved.write_bytes(source.read_bytes())
            source.unlink()
            files.pop(source.relative_to(root).as_posix())
            files[moved.relative_to(root).as_posix()] = derivation.sha(moved)
            rejected(run, 'interview source path')
            passed += 1
            moved.unlink()
            reset()
            bodies['first_interview']['stage'] = 'other'
            write('first_interview')
            rejected(run, 'interview stage')
            passed += 1
            reset()
            bodies['complete_interview']['revision'] = 3
            receipts['complete_interview']['revision'] = 3
            write('complete_interview')
            rejected(run, 'interview revision')
            passed += 1
            reset()
            receipts['first_interview']['actor'] = 'root'
            write('first_interview')
            rejected(run, 'interview receipt actor')
            passed += 1
            reset()
            receipts['complete_interview']['source_sha256'] = H
            write('complete_interview')
            rejected(run, 'interview receipt digest')
            passed += 1
            reset()
            bodies['complete_interview']['public'] = 'changed synthetic shape'
            receipts['complete_interview']['source_sha256'] = derivation.digest(
                bodies['complete_interview'])
            write('complete_interview')
            rejected(run, 'interview sealed digest')
            passed += 1
        reset()
    return passed


def environment_checks(profile):
    passed = 0
    plan = build_plan(profile)
    env = {'id': profile['environment_id'],
           'base_url': 'https://public-dify.invalid',
           'console_workspace_id': profile['workspace_id'],
           'version': profile['console_version'],
           'console_checked_at': '2026-11-23T00:00:00Z',
           'connection_revision': 1,
           'capabilities': {'console': True, 'runtime': True}}
    plan['environment_sha256'] = derivation.digest(env)
    plan['environment_identity_sha256'] = execute.environment_identity_sha256(env)
    execute.check_environment_profile(plan, env)
    execute.check_environment_identity(plan, env)
    passed += 1
    legal = copy.deepcopy(env)
    legal.update(console_checked_at='2026-11-23T01:00:00Z', connection_revision=2,
                 console_auth_mode='password')
    execute.check_environment_identity(plan, legal)
    passed += 1
    rejected(lambda: execute.check_environment_profile(plan, legal),
             'startup full environment')
    passed += 1
    for key, value in (('base_url', 'https://other.invalid'),
                       ('console_workspace_id', str(uuid.uuid4())),
                       ('version', '1.18.0'), ('id', str(uuid.uuid4()))):
        changed = copy.deepcopy(env)
        changed[key] = value
        rejected(lambda changed=changed: execute.check_environment_identity(plan, changed),
                 'environment identity ' + key)
        passed += 1
    return passed


def worker_checks(profile):
    passed = 0
    with tempfile.TemporaryDirectory(dir=WORK, prefix='autonomous-dual375-worker-') as tmp:
        root = Path(tmp).resolve()
        (root / 'plan.json').write_text('{}', 'utf-8')
        approval = root / 'approval.json'
        approval.write_text('{}', 'utf-8')
        (root / 'attempt.json').write_text(json.dumps(
            {'state': 'admitted', 'approval_sha256': execute.sha(approval)}), 'utf-8')
        marker = root / 'worker-started.json'

        def authenticate(root_value, plan_value):
            require(root_value == root and not marker.exists(),
                    'Approval/order changed before worker marker')
            return True

        def history(plan_value):
            require(not marker.exists(), 'Marker before history protection')
            return True

        def production(plan_value):
            require(not marker.exists(), 'Marker before production protection')
            return True

        def runtime(plan_value, prof):
            require(not marker.exists(), 'Marker before runtime binding')
            return {'verified_pid': 12020}

        with patch.object(execute, '_canonical', return_value=root), \
                patch.object(execute, '_profile', return_value=profile), \
                patch.object(execute, 'authenticate_worker', side_effect=authenticate), \
                patch.object(execute, 'verify_history', side_effect=history), \
                patch.object(execute, '_production', side_effect=production), \
                patch.object(execute, '_runtime', side_effect=runtime):
            execute.authorize_worker(root, {})
            value = json.loads(marker.read_text('utf-8'))
            require(value == {'pid': os.getpid(), 'plan_sha256': execute.sha(
                root / 'plan.json'), 'single_worker': True}, 'Worker marker changed')
            passed += 1
            rejected(lambda: execute.authorize_worker(root, {}), 'second worker')
            passed += 1
    return passed


def wiring_checks(profile):
    passed = 0
    verified = derivation.verified_sources(PROJECT, profile['source_pins'])
    proposal = (PROJECT / profile['proposal_doc']).read_bytes()
    stage = Path(tempfile.mkdtemp(dir=WORK, prefix='autonomous-dual375-stage-'))
    fake_project = Path(tempfile.mkdtemp(dir=WORK, prefix='autonomous-dual375-plan-'))
    blocked = WORK / ('autonomous-dual375-live-' + uuid.uuid4().hex)
    try:
        local = derivation.local_bytes(PROJECT)
        prepare._write_package(stage, profile, proposal, verified, local)
        require(set(path.name for path in stage.iterdir()) ==
                set(derivation.FROZEN_SOURCE_FILES), 'Written package set changed')
        passed += 1
        snapshot = fake_project / '.runtime' / 'snapshots' / profile['runtime_build']
        snapshot.mkdir(parents=True)
        (snapshot / 'runtime-manifest.json').write_text(
            json.dumps({'files': {}, 'shared_data_copied': False}), 'utf-8')
        (fake_project / 'runtime-process.ps1').write_bytes(b'public-runtime')
        docs = fake_project / 'docs'
        docs.mkdir()
        (fake_project / profile['proposal_doc']).write_bytes(proposal)
        task = fake_task(profile)
        files = fake_files()
        interviews = fake_interviews(profile)
        plan = prepare._make_plan(
            stage, profile, proposal, fake_project, {'verified_pid': 12020},
            task, {}, None, files, interviews, 'd' * 40, H, H, H, [], verified)
        plan.update(protected_data={'objects': {}, 'secrets': {}, 'files': {}},
                    protected_isolated={key: {} for key in profile['isolated_paths']},
                    protected_files=files)
        require(set(plan) == execute.PLAN_KEYS, 'Built plan fields changed')
        execute.validate_plan(plan, profile, project=fake_project)
        passed += 1
        (stage / 'plan.json').write_text(json.dumps(plan, sort_keys=True, indent=2), 'utf-8')
        manifest = {'schema_version': 1, 'batch_id': execute.BATCH,
                    'files': {name: derivation.sha(stage / name)
                              for name in derivation.NAMES}}
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2), 'utf-8')
        require(set(manifest['files']) == set(derivation.NAMES)
                and len(manifest['files']) == len(derivation.NAMES), 'Built manifest changed')
        execute.verify_frozen_files(stage, plan, profile, source_project=PROJECT,
                                    project=fake_project, check_head=False,
                                    check_runtime=False)
        passed += 1
        (stage / 'common.py').write_bytes(b'changed')
        rejected(lambda: execute.verify_frozen_files(
            stage, plan, profile, source_project=PROJECT, project=fake_project,
            check_head=False, check_runtime=False), 'frozen package tamper')
        passed += 1
        (stage / 'common.py').write_bytes(
            derivation.derive('common.py', verified['common.py']))
        rejected(lambda: execute.validate_pending(HERE), 'validate-pending noncanonical')
        passed += 1
        rejected(lambda: prepare.cmd_pending(str(PROJECT)), 'pending clone project')
        passed += 1
        sys.path.insert(0, str(stage))
        import worker
        rejected(lambda: worker.run('live', blocked, plan), 'live without gate')
        require(not blocked.exists(), 'Live rejection created output')
        passed += 1

        def closed_gate(root_value, plan_value):
            require(root_value == stage.resolve(), 'Worker root changed')
            require(not blocked.exists(), 'Output created before worker authorization')
            raise RuntimeError('public worker authorization gate')

        with patch.object(worker.execute, 'authorize_worker', side_effect=closed_gate):
            rejected(lambda: worker.run('live', blocked, plan), 'worker startup order')
        require(not blocked.exists(), 'Rejected worker created output')
        passed += 1
        wrong = WORK / ('autonomous-dual375-live-' + uuid.uuid4().hex)

        def open_gate(root_value, plan_value):
            (root_value / 'worker-started.json').write_text(json.dumps(
                {'pid': os.getpid(), 'single_worker': True}), 'utf-8')
            return True

        with patch.object(worker.execute, 'authorize_worker', side_effect=open_gate):
            rejected(lambda: worker.run('live', wrong, plan), 'worker unique output root')
        require(not wrong.exists(), 'Wrong output root was created')
        (stage / 'worker-started.json').unlink()
        passed += 1
    finally:
        sys.path.remove(str(stage)) if str(stage) in sys.path else None
        for path, prefix in ((stage, 'autonomous-dual375-stage-'),
                             (fake_project, 'autonomous-dual375-plan-')):
            resolved = Path(path).resolve()
            if resolved.exists() and resolved.is_relative_to(WORK) \
                    and resolved != WORK and resolved.name.startswith(prefix):
                shutil.rmtree(resolved, ignore_errors=True)
    return passed


def main():
    profile = prepare.load_profile()
    trace = []
    total = 0
    total += profile_checks(profile)
    trace.append('profile_exact_and_tamper')
    total += source_checks(profile)
    trace.append('git_source_pins_and_exact_derivation')
    total += local_source_checks(profile)
    trace.append('committed_local_sources')
    total += interview_checks(profile)
    trace.append('sealed_interview_reviews_3_6')
    total += environment_checks(profile)
    trace.append('environment_identity_vs_full_profile')
    total += worker_checks(profile)
    trace.append('exclusive_worker_marker')
    total += plan_checks(profile)
    trace.append('plan_tamper_rejected')
    total += authorization_checks(profile)
    trace.append('authorization_and_old_ref_rejected')
    total += gate_checks(profile)
    trace.append('canonical_seals_831_old371_gate')
    total += wiring_checks(profile)
    trace.append('pending_package_and_live_gate_wiring')
    print(json.dumps({'state': 'passed', 'checks': total, 'cases': trace,
                      'physical_http': 0, 'secret_reads': 0,
                      'production_store': False, 'canonical_markers': 0},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
