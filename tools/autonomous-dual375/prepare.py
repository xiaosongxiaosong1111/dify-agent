"""Build the public source package and the one-shot 375 pending freeze; never dispatch.

The `sources` action reads fixed Git blobs and local 375 files only.  The
`pending` action runs on the original machine and reads DB summaries, the fixed
runtime snapshot and sealed old evidence; it never approves, attempts or logs in.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

import derivation
import execute

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
WORK = (PROJECT / 'work').resolve()
BATCH = derivation.BATCH


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha_bytes(value):
    return derivation.sha_bytes(value)


def sha(path):
    return derivation.sha(path)


def _int(value, label):
    require(type(value) is int, label + ' must be int')
    return value


def load(path):
    return execute.load(path)


def load_profile():
    return execute.load_profile(HERE / 'profile.json')


def _head(project):
    return subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'],
                                   text=True).strip()


def _load_module(name, raw, filename):
    module = types.ModuleType(name)
    module.__file__ = str(filename)
    exec(compile(raw, str(filename), 'exec'), module.__dict__)
    return module


def _source_common(project, p, verified):
    source = (Path(project) / p['source_dir']).resolve()
    expected = source / 'common.py'
    require(expected.is_file() and not expected.is_symlink(), 'Source common missing')
    module = _load_module('common', verified['common.py'], expected)
    require(Path(module.__file__).resolve() == expected,
            'Imported common came from a different path')
    require(module.PROJECT.resolve() == Path(project).resolve(),
            'Imported common project changed')
    return module


def _runtime_check(project, p, verified, probe):
    source = (Path(project) / p['source_dir']).resolve()
    common = _source_common(project, p, verified)
    saved = sys.modules.get('common')
    sys.modules['common'] = common
    try:
        filename = source / 'runtime_reference.py'
        module = _load_module('_dual375_runtime_reference',
                              derivation.derive('runtime_reference.py',
                                                verified['runtime_reference.py']),
                              filename)
        return module.runtime_check(probe)
    finally:
        if saved is None:
            sys.modules.pop('common', None)
        else:
            sys.modules['common'] = saved


def _reuse_policy(project, p, verified):
    source = (Path(project) / p['source_dir_base']).resolve()
    filename = source / 'reuse_policy.py'
    return _load_module('_dual375_reuse_policy', verified['reuse_policy.py'], filename)


def _hash_map(value):
    if isinstance(value, dict) and isinstance(value.get('files'), dict):
        value = value['files']
    if isinstance(value, dict) and isinstance(value.get('files'), list):
        value = value['files']
    if isinstance(value, list):
        rows = value
        value = {}
        for row in rows:
            require(isinstance(row, dict) and isinstance(row.get('path'), str)
                    and execute._hex(row.get('sha256')), 'Malformed sealed list')
            value[row['path']] = row['sha256']
    require(isinstance(value, dict) and value, 'Sealed file map missing')
    result = {}
    for name, item in value.items():
        require(isinstance(name, str) and name and execute._hex(item),
                'Malformed sealed entry')
        result[name.replace('\\', '/')] = item
    return result


def _batch_file(base, name):
    require(isinstance(name, str) and name, 'Sealed path missing')
    raw = Path(name)
    require(not raw.is_absolute() and not raw.drive and not raw.root, 'Sealed path absolute')
    path = (base / name).resolve()
    require(path.is_relative_to(base) and path != base and path.is_file(),
            'Sealed path escaped')
    return path


def _batch_sealed(base, name, value):
    require(execute._hex(value), 'Sealed hash invalid')
    path = _batch_file(base, name)
    require(sha(path) == value, 'Sealed evidence changed')
    return path


def _seal_group(project, spec):
    seal = project / spec['path']
    base = seal.parent.resolve()
    require(not seal.is_symlink() and seal.is_file() and sha(seal) == spec['sha256'],
            'Seal index changed')
    require(base.is_relative_to((project / 'work').resolve()) and base.is_dir(),
            'Seal directory escaped')
    entries = _hash_map(load(seal))
    require(len(entries) == spec['entries'], 'Seal count changed')
    result = {}
    for name, value in entries.items():
        path = _batch_sealed(base, name, value)
        key = path.relative_to(project).as_posix()
        require(key not in result, 'Seal path collision: ' + key)
        result[key] = value
    key = seal.relative_to(project).as_posix()
    require(key not in result, 'Seal index collision')
    result[key] = sha(seal)
    require(len(result) == spec['entries'] + 1, 'Seal total changed')
    return result


def _sealed_record(project, base, name, files):
    path = _batch_file(base, name)
    key = path.relative_to(project).as_posix()
    require(key in files and sha(path) == files[key], 'Old record not sealed: ' + name)
    value = load(path)
    require(isinstance(value, dict), 'Old record malformed')
    return value


def _old366_not_dispatched(value, count_key):
    require(isinstance(value, dict) and value.get('state') == 'stopped',
            'Old 366 is not stopped')
    counts = value.get(count_key)
    expected = {'model': 0, 'reads': 0, 'login': 1, 'import': 0,
                'publish': 0, 'key': 0, 'run': 0}
    require(isinstance(counts, dict) and set(counts) == set(expected)
            and all(type(counts[key]) is int and counts[key] == expected[key]
                    for key in expected), 'Old 366 was dispatched')
    require(_int(value.get('physical_http'), 'physical_http') == 1
            and not value.get('task_id'), 'Old 366 scope changed')


def _old366_gate(project, base, files):
    progress = _sealed_record(project, base, 'live-output/progress.json', files)
    attempt = _sealed_record(project, base, 'attempt.json', files)
    _old366_not_dispatched(progress, 'dispatch_counts')
    _old366_not_dispatched(attempt, 'counts')


def _old371_not_dispatched(value, count_key, target, check_task=False):
    require(isinstance(value, dict) and value.get('state') == 'stopped',
            'Old 371 is not stopped')
    counts = value.get(count_key)
    expected = {'model': 3, 'reads': 6, 'login': 1, 'import': 0,
                'publish': 0, 'key': 0, 'run': 0}
    require(isinstance(counts, dict) and set(counts) == set(expected)
            and all(type(counts[key]) is int and counts[key] == expected[key]
                    for key in expected), 'Old 371 dispatch changed')
    require(_int(value.get('physical_http'), 'physical_http') == 10,
            'Old 371 physical count changed')
    require(not value.get('deliveries') and not value.get('apps')
            and not value.get('bundles'), 'Old 371 resources changed')
    require(value.get('workflow_plan') is None and value.get('dify_app_id') is None
            and value.get('artifact') is None, 'Old 371 graph/App/artifact changed')
    if check_task:
        require(value.get('task_id') == target, 'Old 371 task changed')


def _old371_gate(project, base, files, target):
    progress = _sealed_record(project, base, 'live-output/progress.json', files)
    attempt = _sealed_record(project, base, 'attempt.json', files)
    _old371_not_dispatched(progress, 'dispatch_counts', target, check_task=True)
    _old371_not_dispatched(attempt, 'counts', target, check_task=False)


def _history(project, p):
    sealed = project / 'work/reviewed-spec-planning420/sealed-evidence-sha256.json'
    require(sha(sealed) == p['sealed_index_sha256'], 'Old sealed index changed')
    old = _hash_map(load(sealed))
    old[sealed.relative_to(project).as_posix()] = sha(sealed)
    require(len(old) == p['protected_old_count'] == 733, 'Old sealed count changed')
    for name, value in old.items():
        path = (project / name).resolve()
        require(path.is_relative_to(project / 'work') and path.is_file()
                and sha(path) == value, 'Old sealed evidence changed')
    seal = project / 'work/autonomous-dual337/seal-after-stop.json'
    base = seal.parent.resolve()
    require(base.is_relative_to((project / 'work').resolve()) and base.is_dir()
            and not seal.is_symlink(), '337 seal directory changed')
    recent = _hash_map(load(seal))
    require(len(recent) == p['protected_337_count'] == 24, '337 seal count changed')
    files = dict(old)
    for name, value in recent.items():
        candidate = _batch_sealed(base, name, value)
        key = candidate.relative_to(project).as_posix()
        require(key not in files, '337 seal path collision')
        files[key] = value
    key = seal.relative_to(project).as_posix()
    require(key not in files, '337 seal index collision')
    files[key] = sha(seal)
    require(len(files) == 758, '337 protected count changed')
    for label, spec in p['protected_seals'].items():
        if label == 'autonomous-dual371':
            continue
        group = _seal_group(project, spec)
        for name, value in group.items():
            require(name not in files, 'New seal path collision: ' + name)
            files[name] = value
    require(len(files) == p['protected_base_count'] == 795,
            'Base protected count changed')
    spec = p['protected_seals']['autonomous-dual371']
    group = _seal_group(project, spec)
    for name, value in group.items():
        require(name not in files, '371 seal path collision: ' + name)
        files[name] = value
    require(len(files) == p['protected_total_count'] == 831,
            'Total protected count changed')
    _old366_gate(project,
                 (project / derivation.SEALS['autonomous-dual366']['path']).parent.resolve(),
                 files)
    _old371_gate(project,
                 (project / derivation.SEALS['autonomous-dual371']['path']).parent.resolve(),
                 files, p['target_task_id'])
    return files


def _interview_reviews(project, p, files):
    base = (project / 'work/autonomous-dual371').resolve()
    require(base.is_relative_to((project / 'work').resolve()) and base.is_dir(),
            '371 interview directory changed')
    target = p['target_task_id']
    result = {}
    for stage in ('first_interview', 'complete_interview'):
        fact = derivation.INTERVIEW_FACTS[stage]
        source_name = 'live-output/review-source-' + stage + '.json'
        receipt_name = 'live-output/review-' + stage + '.json'
        source_path = _batch_file(base, source_name)
        source_key = source_path.relative_to(project).as_posix()
        require(source_key in files and sha(source_path) == files[source_key],
                '371 interview source not sealed: ' + stage)
        receipt_path = _batch_file(base, receipt_name)
        receipt_key = receipt_path.relative_to(project).as_posix()
        require(receipt_key in files and sha(receipt_path) == files[receipt_key],
                '371 interview receipt not sealed: ' + stage)
        body = load(source_path)
        receipt = load(receipt_path)
        require(isinstance(body, dict) and body.get('stage') == stage
                and body.get('task_id') == target, '371 interview source binding changed: ' + stage)
        revision = body.get('revision')
        require(type(revision) is int and revision == fact['revision'],
                '371 interview revision changed: ' + stage)
        require(isinstance(receipt, dict) and receipt.get('stage') == stage
                and receipt.get('task_id') == target
                and receipt.get('revision') == revision
                and receipt.get('decision') == 'proceed'
                and receipt.get('actor') == 'agent_delegated',
                '371 interview review binding changed: ' + stage)
        source_sha = derivation.digest(body)
        require(source_sha == fact['source_sha256'],
                '371 interview source digest changed: ' + stage)
        require(receipt.get('source_sha256') == source_sha,
                '371 interview source receipt digest changed: ' + stage)
        result[stage] = {'source_sha256': source_sha,
                         'receipt_sha256': sha(receipt_path),
                         'task_id': target, 'revision': revision,
                         'decision': 'proceed', 'actor': 'agent_delegated'}
    return result


def _roots(project, p, common):
    data = common.ReadOnly(project / 'data')
    protected_data = common.capture(data)
    isolated = {label: common.capture(common.ReadOnly(project / path))
                for label, path in p['isolated_paths'].items()}
    require(len(isolated) + 1 == 12, 'Twelve protected roots required')
    return data, protected_data, isolated


def _write_package(stage, p, proposal, verified, local):
    for name, raw in verified.items():
        (stage / name).write_bytes(derivation.derive(name, raw))
    for name in derivation.LOCAL_FILES:
        (stage / name).write_bytes(local[name])
    (stage / 'freeze.py').write_bytes(local[derivation.FREEZE_SOURCE])
    (stage / 'approved_scope.md').write_bytes(proposal)
    require(set(x.name for x in stage.iterdir() if x.is_file()) ==
            set(derivation.FROZEN_SOURCE_FILES), 'Frozen file set changed')


def _make_plan(stage, p, proposal, project, runtime, task, budget, limits, files,
               interviews, source_commit, provider_sha256, environment_sha256,
               environment_identity_sha256, apps, verified):
    folder = Path(project) / '.runtime' / 'snapshots' / p['runtime_build']
    source_hashes = {name: sha_bytes(raw) for name, raw in verified.items()}
    frozen_source_files = {name: sha(stage / name)
                           for name in sorted(derivation.FROZEN_SOURCE_FILES)}
    planning = task.get('planning_runs') or []
    require(planning and isinstance(planning[0], dict)
            and isinstance(planning[0].get('decision_report'), dict),
            'Previous decision report missing')
    plan = {
        'schema_version': 1, 'batch_id': BATCH, 'approval_state': 'pending',
        'proposal_state': 'proposed_not_approved',
        'source_commit': source_commit,
        'source_commit_shared': p['source_commit'],
        'source_commit_base': p['source_commit_base'],
        'source_dir': p['source_dir'], 'source_dir_base': p['source_dir_base'],
        'source_normalization': p['source_normalization'],
        'source_pins': p['source_pins'], 'source_file_sha256': source_hashes,
        'frozen_source_files': frozen_source_files,
        'proposal_doc': p['proposal_doc'], 'proposal_sha256': sha_bytes(proposal),
        'approved_scope_sha256': sha_bytes(proposal),
        'limits': p['limits'], 'new_conservative_upper': p['new_conservative_upper'],
        'approved_model_slots': p['approved_model_slots'],
        'effective_model_http': p['effective_model_http'],
        'json_repair_http': p['json_repair_http'],
        'per_model_reserve_usd': p['per_model_reserve_usd'],
        'model_total_usd': p['model_total_usd'],
        'model_estimate_book_upper_usd': p['model_estimate_book_upper_usd'],
        'dify_estimate_usd': p['dify_estimate_usd'],
        'combined_estimate_usd': p['combined_estimate_usd'],
        'billing_hard_cap': p['billing_hard_cap'], 'wall_seconds': p['wall_seconds'],
        'task_start_cap': p['task_start_cap'], 'task_minutes': p['task_minutes'],
        'runtime_build': p['runtime_build'], 'runtime_version': p['runtime_version'],
        'runtime_file_count': p['runtime_file_count'],
        'runtime_pid': _int(runtime['verified_pid'], 'verified_pid'),
        'runtime_manifest_sha256': sha(folder / 'runtime-manifest.json'),
        'runtime_process_sha256': sha(Path(project) / 'runtime-process.ps1'),
        'backend_path': str(folder / 'backend'),
        'provider_id': p['provider_id'], 'provider_sha256': provider_sha256,
        'environment_id': p['environment_id'], 'environment_sha256': environment_sha256,
        'environment_identity_sha256': environment_identity_sha256,
        'target_task_id': task['id'],
        'target_task_revision': _int(task['revision'], 'target task revision'),
        'target_task_sha256': derivation.digest(task),
        'target_budget_sha256': derivation.digest(budget),
        'execution_limits_present': limits is not None,
        'history_prefix': derivation.history_prefix(task),
        'intake_review_sha256': derivation.digest(task.get('intake_review')),
        'decision_report_sha256': derivation.digest(planning[0]['decision_report']),
        'cases_sha256': derivation.digest(task.get('test_cases')),
        'configuration_sha256': derivation.digest(task.get('configuration')),
        'requirements_sha256': derivation.digest(task.get('requirements')),
        'interview_reviews': interviews,
        'expected_counts': p['expected_counts'],
        'protected_data': None, 'isolated_paths': p['isolated_paths'],
        'protected_isolated': None, 'protected_files': files,
        'protected_old_count': p['protected_old_count'],
        'protected_337_count': p['protected_337_count'],
        'protected_base_count': p['protected_base_count'],
        'protected_371_entries': p['protected_371_entries'],
        'protected_total_count': p['protected_total_count'],
        'sealed_index_sha256': p['sealed_index_sha256'],
        'protected_seals': p['protected_seals'],
        'known_apps': sorted(apps),
    }
    require(set(plan) == execute.PLAN_KEYS, 'Plan fields changed')
    return plan


def cmd_sources(output):
    out = Path(output).resolve()
    p = load_profile()
    require(out.parent == WORK and not out.exists() and not out.is_symlink(),
            'New direct work output required')
    require(out.name == BATCH or out.name.startswith(BATCH + '-'),
            'Output name must identify 375')
    verified = derivation.verified_sources(PROJECT, p['source_pins'])
    local = derivation.local_bytes(PROJECT)
    out.mkdir()
    for name, raw in verified.items():
        (out / name).write_bytes(derivation.derive(name, raw))
    for name in derivation.LOCAL_FILES:
        (out / name).write_bytes(local[name])
    (out / 'freeze.py').write_bytes(local[derivation.FREEZE_SOURCE])
    require(set(x.name for x in out.iterdir() if x.is_file()) ==
            set(derivation.PACKAGE_FILES) | {'freeze.py'}, 'Source file set changed')
    print(json.dumps({'state': 'public_sources_ready', 'output': str(out),
                      'files': len(derivation.PACKAGE_FILES) + 1,
                      'physical_http': 0, 'secret_reads': 0}, ensure_ascii=False))


def cmd_pending(project_root):
    project = Path(project_root).resolve()
    require(project == Path(r'E:\workSpace\dify-agent'), 'Original project only')
    require(not subprocess.check_output(['git', 'status', '--porcelain'],
                                        cwd=project, text=True).strip(),
            'Clean original checkout required')
    head = _head(project)
    require(execute._githex(head), 'Source commit invalid')
    local = derivation.verified_local(project, head)
    p = load_profile()
    work = (project / 'work').resolve()
    require(work == project / 'work' and not (project / 'work').is_symlink()
            and work.parent == project, 'Work path changed')
    root = work / BATCH
    require(not root.exists() and not root.is_symlink() and root.parent.resolve() == work,
            'Canonical package already exists')
    verified = derivation.verified_sources(project, p['source_pins'])
    with sqlite3.connect((project / 'data/flowcraft.sqlite3').as_uri() + '?mode=ro',
                         uri=True) as db:
        counts = {kind: count for kind, count in db.execute(
            "select kind,count(*) from objects where kind in "
            "('task','environment','provider') group by kind")}
        secret_ids = {row[0] for row in db.execute('select id from secrets')}
    require(counts == p['expected_counts']
            and all(type(value) is int for value in counts.values()),
            'Protected counts changed')
    common = _source_common(project, p, verified)
    data = common.ReadOnly(project / 'data')
    provider = data.get('provider', p['provider_id'])
    env = data.get('environment', p['environment_id'])
    require(provider and env, 'Provider or environment missing')
    require(provider.get('id') == p['provider_id']
            and provider.get('model') == p['provider_model']
            and provider.get('protocol') == p['provider_protocol']
            and isinstance(provider.get('pricing'), dict), 'Provider profile changed')
    require(env.get('id') == p['environment_id']
            and env.get('console_workspace_id') == p['workspace_id']
            and env.get('version') == p['console_version'],
            'Workspace/environment changed')
    require({p['environment_id'] + ':' + key for key in
             ('console_login_email', 'console_login_password')}
            | {p['provider_id'] + ':api_key'} <= secret_ids,
            'Encrypted credentials missing')
    fixture = json.loads(verified['fixture.json'])
    task = data.get('task', p['target_task_id'])
    budget = data.get('task_budget', p['target_task_id'])
    limits = data.get('execution_limits', p['target_task_id'])
    require(isinstance(task, dict) and isinstance(budget, dict),
            'Target Task/budget missing')
    require(task.get('id') == p['target_task_id']
            and task.get('revision') == p['target_task_revision'],
            'Target Task changed')
    require(limits is None, 'Execution policy must start absent')
    require(isinstance(task.get('intake_review'), dict),
            'Existing model intake review missing')
    policy = _reuse_policy(project, p, verified)
    policy.validate_start(task, budget, limits, fixture, env['id'], provider['id'],
                          target_id=p['target_task_id'],
                          expected={'task_id': p['target_task_id'],
                                    'task_digest': derivation.digest(task),
                                    'budget_digest': derivation.digest(budget)})
    folder = project / '.runtime' / 'snapshots' / p['runtime_build']
    manifest = load(folder / 'runtime-manifest.json')
    require(len(manifest['files']) == p['runtime_file_count'] == 298
            and manifest.get('shared_data_copied') is False, 'Runtime manifest changed')
    require(all(sha(project / name) == value and sha(folder / name) == value
                for name, value in manifest['files'].items()),
            'Runtime source/snapshot mismatch')
    probe = {'runtime_build': p['runtime_build'],
             'runtime_manifest_sha256': sha(folder / 'runtime-manifest.json'),
             'runtime_process_sha256': sha(project / 'runtime-process.ps1')}
    runtime = _runtime_check(project, p, verified, probe)
    files = _history(project, p)
    interviews = _interview_reviews(project, p, files)
    data, protected_data, isolated = _roots(project, p, common)
    proposal = project / p['proposal_doc']
    require(proposal.is_file() and not proposal.is_symlink(),
            '375 proposal document missing')
    proposal_bytes = proposal.read_bytes()
    stage = work / ('.autonomous-dual375-staging-' + str(os.getpid()))
    require(not stage.exists() and not stage.is_symlink()
            and stage.parent.resolve() == work, 'Staging path invalid')
    stage.mkdir()
    _write_package(stage, p, proposal_bytes, verified, local)
    plan = _make_plan(stage, p, proposal_bytes, project, runtime, task, budget, limits,
                      files, interviews, head, derivation.digest(provider),
                      derivation.digest(env),
                      derivation.digest({key: env.get(key) for key in
                                         ('id', 'base_url', 'console_workspace_id',
                                          'version')}),
                      common.known_apps(data), verified)
    plan.update(protected_data=protected_data, protected_isolated=isolated,
                protected_files=files)
    require(set(plan) == execute.PLAN_KEYS, 'Plan fields changed')
    (stage / 'plan.json').write_text(
        json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2), 'utf-8')
    manifest = {'schema_version': 1, 'batch_id': BATCH,
                'files': {name: sha(stage / name) for name in sorted(derivation.NAMES)}}
    (stage / 'manifest.json').write_text(
        json.dumps(manifest, sort_keys=True, indent=2), 'utf-8')
    require(stage.resolve().parent == work and not stage.is_symlink(),
            'Staging escaped work')
    require(root.parent.resolve() == work and not root.exists() and not root.is_symlink(),
            'Canonical target changed')
    require(set(x.name for x in stage.iterdir()) ==
            set(derivation.NAMES) | {'manifest.json'}, 'Frozen file set changed')
    require(set(manifest['files']) == set(derivation.NAMES)
            and len(manifest['files']) == len(derivation.NAMES),
            'Manifest file set changed')
    require(all((stage / name).is_file() and not (stage / name).is_symlink()
                and sha(stage / name) == value
                for name, value in manifest['files'].items()),
            'Frozen package hash mismatch')
    require(not (stage / 'approval.json').exists()
            and not (stage / 'attempt.json').exists()
            and not (stage / 'worker-started.json').exists(),
            'Pending package contains live marker')
    os.rename(stage, root)
    print(json.dumps({'state': 'pending_frozen_not_approved', 'root': str(root),
                      'plan_sha256': sha(root / 'plan.json'),
                      'manifest_sha256': sha(root / 'manifest.json'),
                      'physical_http': 0}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sources = sub.add_parser('sources')
    sources.add_argument('--output', required=True)
    pending = sub.add_parser('pending')
    pending.add_argument('--project-root', required=True)
    args = parser.parse_args()
    if args.command == 'sources':
        cmd_sources(args.output)
    else:
        cmd_pending(args.project_root)


if __name__ == '__main__':
    main()
