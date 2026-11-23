"""Actual-behaviour checks for the 374 reuse guard; no production store or network."""
import copy
import json
import sys
import tempfile
import uuid
import atexit
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
WORK = (PROJECT / 'work').resolve()

sys.path.insert(0, str(PROJECT / 'backend'))
import prepare  # local builder, no DB/secret access


def require(value, message):
    if not value:
        raise RuntimeError(message)


def rejected(label, fn):
    try:
        fn()
    except RuntimeError:
        return label
    raise AssertionError('Accepted ' + label)


def main():
    checks = []
    output = WORK / ('autonomous-dual374-checks-' + uuid.uuid4().hex)

    def cleanup_output():
        try:
            work = WORK.resolve()
            path = output.resolve()
            if path.exists() and path.is_relative_to(work) and path != work \
                    and path.name.startswith('autonomous-dual374-checks-'):
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
    atexit.register(cleanup_output)
    prepare.build(output)
    sys.path.insert(0, str(output))
    from app.storage import Store
    from common import capture, digest
    from reuse_policy import validate_start, preserve_task, preserve_budget, new_entries
    from storage_guard import guarded, verify
    from boundary import Boundary
    import worker

    fixture = json.loads((output / 'fixture.json').read_text('utf-8'))
    tid, eid, pid = [str(uuid.uuid4()) for _ in range(3)]
    now = lambda: '2026-11-23T00:00:00+00:00'
    env = {'id': eid, 'base_url': 'https://public-dify.invalid',
           'console_workspace_id': fixture['workspace_id'],
           'service_app_id': None, 'capabilities': {}}
    provider = {'id': pid, 'provider': 'deepseek', 'protocol': 'openai-compatible',
                'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash',
                'pricing': {'input_per_million_usd': .3, 'output_per_million_usd': 1.2}}
    from synthetic_seed import build_task, build_budget
    task = build_task(now, tid, fixture, pid, eid)
    budget = build_budget(now, tid, provider)
    expected = {'task_id': tid, 'task_digest': digest(task), 'budget_digest': digest(budget)}

    def candidate_start(t=task, b=budget):
        return validate_start(t, b, None, fixture, eid, pid,
                              expected={'task_id': tid, 'task_digest': digest(t),
                                        'budget_digest': digest(b)})

    require(validate_start(task, budget, None, fixture, eid, pid, expected=expected),
            'Preserved Task not admitted')
    rejected('missing target id', lambda: validate_start(
        task, budget, None, fixture, eid, pid,
        expected={'task_digest': digest(task), 'budget_digest': digest(budget)}))
    rejected('missing task digest', lambda: validate_start(
        task, budget, None, fixture, eid, pid, expected={'task_id': tid}))
    rejected('missing budget digest', lambda: validate_start(
        task, budget, None, fixture, eid, pid,
        expected={'task_id': tid, 'task_digest': digest(task)}))
    rejected('wrong target id', lambda: validate_start(
        task, budget, None, fixture, eid, pid,
        expected={'task_id': str(uuid.uuid4()), 'task_digest': digest(task),
                  'budget_digest': digest(budget)}))
    changed = copy.deepcopy(task)
    changed['messages'][1]['content'] = 'same count but changed history content'
    rejected('same counts changed history', lambda: validate_start(
        changed, budget, None, fixture, eid, pid, expected=expected))
    checks.append('preserved_task_admitted')

    for field, value in [('revision', 5), ('status', 'ready'), ('app_type', 'workflow'),
                         ('environment_id', str(uuid.uuid4())),
                         ('requirements_confirmed', False), ('configuration_confirmed', True),
                         ('workflow_plan', {'nodes': []}), ('artifact', {'x': 1}),
                         ('dify_app_id', str(uuid.uuid4())), ('runs', [{'kind': 'run'}]),
                         ('active_interview_id', str(uuid.uuid4())), ('materials', [{'id': 'x'}])]:
        changed = copy.deepcopy(task)
        changed[field] = value
        rejected('preflight drift ' + field,
                 lambda changed=changed: candidate_start(changed, budget))
    changed = copy.deepcopy(task)
    changed['requirements']['goal'] = ''
    rejected('preflight empty requirement',
             lambda: candidate_start(changed, budget))
    changed = copy.deepcopy(task)
    changed['configuration']['temperature'] = .9
    rejected('preflight changed configuration',
             lambda: candidate_start(changed, budget))
    changed = copy.deepcopy(task)
    changed['test_cases'][1]['input'] = {'query': 'different'}
    rejected('preflight changed case',
             lambda: candidate_start(changed, budget))
    changed = copy.deepcopy(task)
    changed['intake_review']['source'] = 'user_declared'
    rejected('preflight changed review source',
             lambda: candidate_start(changed, budget))
    changed = copy.deepcopy(task)
    changed['planning_runs'][0]['last_candidate'] = {'nodes': []}
    rejected('preflight saved old candidate',
             lambda: candidate_start(changed, budget))
    changed_budget = copy.deepcopy(budget)
    changed_budget['entries'] = []
    rejected('preflight deleted settled ledger',
             lambda: candidate_start(task, changed_budget))
    changed_budget = copy.deepcopy(budget)
    changed_budget['limit_usd'] = '1'
    rejected('preflight changed budget limit',
             lambda: candidate_start(task, changed_budget))
    changed_budget = copy.deepcopy(budget)
    changed_budget['policy_revision'] = 0
    rejected('preflight changed budget policy',
             lambda: candidate_start(task, changed_budget))
    changed_budget = copy.deepcopy(budget)
    changed_budget['entries'][0]['status'] = 'reserved'
    rejected('preflight unsettled old ledger',
             lambda: candidate_start(task, changed_budget))
    for label, changed_budget in (
            ('budget limit', budget | {'limit_usd': '1'}),
            ('budget policy', budget | {'policy_revision': 0}),
            ('budget entries', budget | {'entries': []})):
        rejected('preflight ' + label,
                 lambda changed_budget=changed_budget: candidate_start(task, changed_budget))
    for bad in (None, {}):
        changed = copy.deepcopy(task)
        changed['interview_attempts'] = bad
        rejected('preflight non-list interview_attempts ' + repr(bad),
                 lambda changed=changed: candidate_start(changed))
    with_empty_attempts = copy.deepcopy(task)
    with_empty_attempts['interview_attempts'] = []
    require(candidate_start(with_empty_attempts), 'Explicit empty interview_attempts rejected')
    checks.append('preflight_drift_rejected')

    old_reply = fixture['inputs']['no_hit_reply']
    new_reply = fixture['changed_no_hit_reply']
    exact = copy.deepcopy(task)
    exact['requirements']['output'] = exact['requirements']['output'].replace(old_reply, new_reply)
    require(preserve_task(task, exact, fixture), 'Exact fixed output replacement rejected')
    smuggled = copy.deepcopy(exact)
    smuggled['requirements']['output'] += ' 另加一条新规则'
    rejected('output replacement with extra rule',
             lambda: preserve_task(task, smuggled, fixture))
    changed_rules = copy.deepcopy(task)
    changed_rules['requirements']['rules'] += ' 另加一条新规则'
    rejected('non-output requirement rewrite',
             lambda: preserve_task(task, changed_rules, fixture))
    different_requirements = copy.deepcopy(task)
    different_requirements['requirements']['goal'] = '模型整理后的不同表述，不逐字等于公开fixture'
    require(candidate_start(different_requirements), 'Real requirements were forced to fixture wording')
    checks.append('exact_output_replacement_only')

    store = Store(Path(tempfile.mkdtemp(dir=WORK, prefix='autonomous-dual374-store-')))

    def cleanup_store():
        try:
            work = WORK.resolve()
            path = Path(store.root).resolve()
            if path.exists() and path.is_relative_to(work) and path != work \
                    and path.name.startswith('autonomous-dual374-store-'):
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
    atexit.register(cleanup_store)
    store.put('task', tid, task)
    store.put('task_budget', tid, budget)
    other_id = str(uuid.uuid4())
    for index in range(26):
        oid = other_id if index == 0 else str(uuid.uuid4())
        store.put('task', oid, {'id': oid, 'name': 'unrelated public Task ' + str(index)})
    store.put('task_budget', other_id, {'id': other_id, 'entries': []})
    old = capture(store)
    boundary = Boundary(env, provider, 'PUBLIC_KEY', fixture, {}, {})
    boundary.owner = tid
    boundary.owner_configured = True
    boundary.default_config = copy.deepcopy(task['configuration'])
    boundary.expected_config = copy.deepcopy(task['configuration'])
    boundary.candidates = set()
    reuse = {'task': task, 'budget': budget, 'limits': None,
             'provider_id': pid, 'target': tid, 'fixture': fixture}
    Guarded = guarded(Store, env, provider, fixture, {}, boundary, old, reuse)
    guard = Guarded(store.root)
    early = verify(guard, env, boundary, old, reuse)
    require(early['new_tasks'] == 0 and early['execution_policy_12_45'] is False
            and early['original_execution_policy_none_kept'] is True,
            'Early stop with no policy and no work did not verify truthfully')

    for field in ('messages', 'versions', 'planning_runs', 'intake_history'):
        changed = copy.deepcopy(task)
        changed[field] = []
        rejected('actual Store cannot erase non-empty ' + field,
                 lambda changed=changed: guard.put('task', tid, changed))
        require(store.get('task', tid) == task, 'Guarded Store mutated after rejection')
    same_runs = copy.deepcopy(task)
    same_runs['runs'] = []
    guard.put('task', tid, same_runs)
    for bad in (None, {}):
        changed = copy.deepcopy(task)
        changed['runs'] = bad
        rejected('actual Store rejects non-list runs ' + repr(bad),
                 lambda changed=changed: guard.put('task', tid, changed))
        require(store.get('task', tid) == same_runs, 'Guarded Store mutated after rejection')
    missing_runs = copy.deepcopy(task)
    del missing_runs['runs']
    rejected('actual Store rejects missing runs',
             lambda: guard.put('task', tid, missing_runs))
    require(store.get('task', tid) == same_runs, 'Guarded Store mutated after rejection')
    guard.put('task', tid, task)

    same_attempts = copy.deepcopy(task)
    same_attempts['interview_attempts'] = []
    guard.put('task', tid, same_attempts)
    for bad in (None, {}):
        changed = copy.deepcopy(task)
        changed['interview_attempts'] = bad
        rejected('actual Store rejects non-list interview_attempts ' + repr(bad),
                 lambda changed=changed: guard.put('task', tid, changed))
        require(store.get('task', tid) == same_attempts,
                'Guarded Store mutated after rejection')
    missing_attempts = copy.deepcopy(same_attempts)
    del missing_attempts['interview_attempts']
    guard.put('task', tid, missing_attempts)
    require(store.get('task', tid) == missing_attempts,
            'Missing interview_attempts was not preserved')
    checks.append('missing_interview_attempts_allowed')

    pure_empty = copy.deepcopy(task)
    pure_empty['interview_attempts'] = []
    require(candidate_start(pure_empty), 'Explicit empty interview_attempts rejected by admission')
    require(preserve_task(pure_empty, copy.deepcopy(pure_empty), fixture),
            'Explicit empty list -> same list rejected by preservation')
    for bad in (None, {}):
        changed = copy.deepcopy(pure_empty)
        changed['interview_attempts'] = bad
        rejected('preserve rejects explicit empty list -> non-list ' + repr(bad),
                 lambda changed=changed: preserve_task(pure_empty, changed, fixture))
    deleted_empty = copy.deepcopy(pure_empty)
    del deleted_empty['interview_attempts']
    rejected('preserve rejects existing empty list -> missing',
             lambda: preserve_task(pure_empty, deleted_empty, fixture))
    attempts_old = copy.deepcopy(task)
    attempts_old['interview_attempts'] = [{'applied': False, 'reason': 'public old shape'}]
    attempts_ok = copy.deepcopy(attempts_old)
    attempts_ok['interview_attempts'].append({'applied': True, 'reason': 'public append'})
    require(preserve_task(attempts_old, attempts_ok, fixture),
            'Non-empty interview_attempts append rejected')
    attempts_cleared = copy.deepcopy(attempts_old)
    attempts_cleared['interview_attempts'] = []
    rejected('preserve rejects clearing non-empty interview_attempts',
             lambda: preserve_task(attempts_old, attempts_cleared, fixture))
    attempts_deleted = copy.deepcopy(attempts_old)
    del attempts_deleted['interview_attempts']
    rejected('preserve rejects deleting non-empty interview_attempts',
             lambda: preserve_task(attempts_old, attempts_deleted, fixture))
    checks.append('interview_attempts_absent_empty_prefix_distinguished')
    changed = copy.deepcopy(task)
    changed['planning_runs'][0]['decision_report'] = {}
    rejected('actual Store cannot change old decision_report',
             lambda: guard.put('task', tid, changed))
    require(store.get('task', tid) == missing_attempts,
            'Guarded Store mutated after decision report rejection')
    rejected('actual Store cannot overwrite other Task',
             lambda: guard.put('task', other_id, {'id': other_id, 'name': 'changed'}))
    rejected('actual Store cannot create a replacement Task',
             lambda: guard.put('task', str(uuid.uuid4()), task))
    rejected('actual Store cannot write other Task budget',
             lambda: guard.put('task_budget', other_id, {'id': other_id, 'entries': []}))
    checks.append('old_task_prefix_and_other_tasks_protected')

    for change in ('delete', 'cost', 'status', 'policy', 'limit', 'history'):
        changed = copy.deepcopy(budget)
        if change == 'delete':
            changed['entries'] = []
        elif change == 'cost':
            changed['entries'][0]['charged_usd'] = '9'
        elif change == 'status':
            changed['entries'][0]['status'] = 'unknown'
        elif change == 'policy':
            changed['policy_revision'] = 2
        elif change == 'limit':
            changed['limit_usd'] = '1'
        else:
            changed['policy_history'][0]['after'] = '1'
        rejected('actual Store protects old ledger ' + change,
                 lambda changed=changed: guard.put('task_budget', tid, changed))
        require(store.get('task_budget', tid) == budget, 'Guarded Store mutated budget after rejection')
    checks.append('old_budget_policy_and_prefix_protected')

    def entry(amount):
        return {'id': str(uuid.uuid4()), 'provider_id': pid, 'status': 'reserved',
                'reserved_usd': amount}

    for amount in ('0.1001', '-0.001', 'NaN'):
        changed = copy.deepcopy(budget)
        changed['entries'].append(entry(amount))
        rejected('new ledger quote rejected ' + amount,
                 lambda changed=changed: guard.put('task_budget', tid, changed))
    appended = copy.deepcopy(budget)
    for _ in range(3):
        appended['entries'].append(entry('0.001'))
    guard.put('task_budget', tid, appended)
    require(len(new_entries(budget, store.get('task_budget', tid))) == 3,
            'New suffix count wrong')
    from decimal import Decimal
    require(sum((Decimal(e['reserved_usd']) for e in
                 new_entries(budget, store.get('task_budget', tid))), Decimal(0)) == Decimal('0.003'),
            'New suffix quote sum wrong')
    require(store.get('task_budget', tid)['entries'][:3] == budget['entries'],
            'Old settled prefix changed')
    rejected('new model without execution policy',
             lambda: verify(guard, env, boundary, old, reuse))
    changed = copy.deepcopy(appended)
    changed['entries'].append(entry('0.001'))
    rejected('fourth new ledger entry rejected',
             lambda: guard.put('task_budget', tid, changed))
    checks.append('only_three_new_entries_and_old_entries_not_counted')

    changed = copy.deepcopy(task)
    changed['messages'].append({'role': 'user', 'content': '公开新说明'})
    changed['revision'] = 7
    guard.put('task', tid, changed)
    require(store.get('task', tid)['messages'][:6] == task['messages'],
            'Normal append changed old messages')
    limits = {'id': tid, 'policy_revision': 1, 'max_started_runs': 12,
              'max_total_minutes': 45, 'max_reported_cost_usd': None,
              'history': [{'before': {}, 'after': {}, 'note': '公开合成首次设置',
                           'created_at': now(), 'source': 'user'}]}
    guard.put('execution_limits', tid, limits)
    rejected('execution policy cannot be widened',
             lambda: guard.put('execution_limits', tid, limits | {'max_started_runs': 13}))
    checks.append('normal_task_append_and_execution_policy')

    boundary.counts['model'] = 3
    rejected('fourth model rejected',
             lambda: boundary._count('POST', '/model', 'model', {}))
    boundary.counts['reads'] = 122
    rejected('123rd GET rejected',
             lambda: boundary._count('GET', '/read', 'reads', {}))
    boundary.counts['login'] = 1
    rejected('second login rejected',
             lambda: boundary._count('POST', '/login', 'login', {}))
    checks.append('model_read_login_caps')

    result = verify(guard, env, boundary, old, reuse)
    require(result['original_objects_kept'] and result['new_tasks'] == 0
            and result['execution_policy_12_45'] is True,
            'Protection summary changed')
    checks.append('final_verify_passes')

    blocked = WORK / ('autonomous-dual374-live-' + uuid.uuid4().hex)
    rejected('live entry rejected early', lambda: worker.run('live', blocked))
    require(not blocked.exists(), 'Live rejection touched output/DB path')
    checks.append('live_rejected_before_output')

    work = WORK.resolve()
    store_root = Path(store.root).resolve()
    package_root = output.resolve()
    require(store_root.is_relative_to(work) and store_root != work
            and store_root.name.startswith('autonomous-dual374-store-'),
            'Refusing to remove unproven store path')
    require(package_root.is_relative_to(work) and package_root != work
            and package_root.name.startswith('autonomous-dual374-checks-'),
            'Refusing to remove unproven package path')
    shutil.rmtree(store_root, ignore_errors=True)
    shutil.rmtree(package_root, ignore_errors=True)
    print(json.dumps({'state': 'passed', 'checks': len(checks), 'cases': checks,
                      'physical_http': 0, 'production_store': False,
                      'secret_reads': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
