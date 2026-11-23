"""Admission and prefix-preservation policy for reusing one stopped Task.

This module is deliberately independent of the backend.  It binds an existing
Task/Budget snapshot and never rewrites old history.  All public rehearsal state
must be marked as a synthetic prior shape; production receipts are not copied.
"""
import copy
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

REQUIRED = ('goal', 'audience', 'input', 'output', 'rules', 'knowledge', 'exceptions', 'tests')
EXPECTED_REVISION = 6
EXPECTED_COUNTS = {'messages': 6, 'versions': 5, 'planning_runs': 1, 'runs': 0,
                   'interview_attempts': 0, 'intake_history': 1}
EXPECTED_ENTRIES = 3
EXPECTED_SETTLED_USD = '0.020125524'
EXPECTED_LIMIT_USD = '0.600'
EXPECTED_POLICY_REVISION = 1
PER_CALL_USD = Decimal('0.100')
BATCH_USD = Decimal('0.300')
UNKNOWN_PREFIX = ('待补充', '待确认', '未知')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def _hex(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{64}', value))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _money(value, label='amount'):
    require(isinstance(value, str) and value, label + ' must be decimal text')
    try:
        amount = Decimal(value)
    except InvalidOperation:
        require(False, label + ' is not decimal')
    require(amount.is_finite() and amount >= 0, label + ' must be finite and non-negative')
    return amount


def _expected_config(fixture, provider_id):
    value = copy.deepcopy(fixture['configuration'])
    value['assistant_provider_id'] = provider_id
    return value


def _cases_match(actual, fixture):
    wanted = fixture.get('cases')
    require(isinstance(actual, list) and isinstance(wanted, list) and len(actual) == len(wanted), 'Six saved cases required')
    for row, expected in zip(actual, wanted):
        require(isinstance(row, dict) and all(row.get(k) == expected.get(k) for k in expected),
                'Saved case source changed')


def _case_update_allowed(old_cases, new_cases, fixture):
    if old_cases == new_cases:
        return True
    if not isinstance(old_cases, list) or not isinstance(new_cases, list) or len(old_cases) != len(new_cases):
        return False
    old_reply = fixture.get('inputs', {}).get('no_hit_reply')
    new_reply = fixture.get('changed_no_hit_reply')
    changed = []
    for before, after in zip(old_cases, new_cases):
        if before == after:
            continue
        if not isinstance(before, dict) or not isinstance(after, dict):
            return False
        if before.get('id') != 'faq-no-answer' or after.get('id') != 'faq-no-answer':
            return False
        if not isinstance(old_reply, str) or not isinstance(new_reply, str):
            return False
        before_expectation = before.get('expectation')
        after_expectation = after.get('expectation')
        if not isinstance(before_expectation, dict) or not isinstance(after_expectation, dict):
            return False
        if before_expectation.get('expected') != old_reply or after_expectation.get('expected') != new_reply:
            return False
        repaired = copy.deepcopy(before)
        repaired['expectation']['expected'] = new_reply
        if repaired != after:
            return False
        changed.append(before.get('id'))
    return len(changed) == 1


def validate_start(task, budget, limits, fixture, environment_id, provider_id, target_id=None, expected=None):
    """Bind exactly the preserved paused Task and its settled ledger before any write."""
    expected = expected or {}
    require(isinstance(expected, dict), 'Expected binding must be a mapping')
    require(isinstance(task, dict) and isinstance(budget, dict), 'Task and budget snapshots required')
    wanted_id = target_id or expected.get('task_id')
    require(isinstance(wanted_id, str) and wanted_id, 'Explicit target Task id required')
    require(task.get('id') == wanted_id, 'Target Task id changed')
    require(_hex(expected.get('task_digest')), 'Frozen full Task digest required')
    require(_hex(expected.get('budget_digest')), 'Frozen budget digest required')
    require(digest(task) == expected['task_digest'], 'Frozen Task digest changed')
    require(digest(budget) == expected['budget_digest'], 'Frozen budget digest changed')
    require(task.get('revision') == EXPECTED_REVISION, 'Existing Task revision changed')
    require(task.get('status') == 'paused', 'Existing Task must remain paused')
    require(task.get('app_type') == 'advanced-chat', 'Existing Task type changed')
    require(task.get('environment_id') == environment_id, 'Existing Task environment changed')
    require(task.get('requirements_confirmed') is True and task.get('configuration_confirmed') is False,
            'Existing confirmation state changed')
    require(task.get('intake_required') is True and task.get('plan_review_required') is True,
            'Existing intake/review gates changed')
    require(not task.get('active_interview_id') and not task.get('active_image_operation_id'),
            'Existing Task has an active operation')
    require(task.get('workflow_plan') is None and task.get('agent_plan') is None
            and task.get('artifact') is None and task.get('dify_app_id') is None,
            'Existing Task is no longer blank of graph/artifact/App')
    require(task.get('materials') == [], 'Existing Task materials changed')
    requirements = task.get('requirements')
    require(isinstance(requirements, dict) and set(requirements) == set(REQUIRED), 'Eight requirements required')
    require(all(isinstance(v, str) and v.strip() and not v.strip().startswith(UNKNOWN_PREFIX)
                for v in requirements.values()), 'Existing requirements are incomplete')
    require(task.get('configuration') == _expected_config(fixture, provider_id),
            'Existing fixed configuration changed')
    _cases_match(task.get('test_cases'), fixture)
    review = task.get('intake_review')
    require(isinstance(review, dict) and review.get('source') == 'model', 'Existing model intake review missing')
    body = review.get('review')
    require(isinstance(body, dict) and isinstance(body.get('checks'), list)
            and body.get('questions') == [], 'Existing intake review body changed')
    require(all(isinstance(row, dict) and row.get('status') == 'complete' for row in body['checks']),
            'Existing intake review is not complete')
    for key, wanted in EXPECTED_COUNTS.items():
        if key == 'interview_attempts':
            if key in task:
                actual = task[key]
                require(isinstance(actual, list) and len(actual) == wanted,
                        'History count changed: interview_attempts')
            continue
        actual = task.get(key)
        require(isinstance(actual, list) and len(actual) == wanted, 'History count changed: ' + key)
    require(task.get('runs') == [], 'Existing Task already has runs')
    runs = task.get('planning_runs') or []
    require(len(runs) == 1 and isinstance(runs[0], dict), 'Previous planning run missing')
    old_run = runs[0]
    require(old_run.get('status') == 'paused' and old_run.get('stop_reason') == 'needs_decision',
            'Previous planning run is not the preserved needs_decision stop')
    require(isinstance(old_run.get('decision_report'), dict) and old_run.get('last_candidate') is None,
            'Previous decision report/candidate changed')
    require(budget.get('id') == task['id'], 'Budget Task binding changed')
    require(budget.get('limit_usd') == EXPECTED_LIMIT_USD and budget.get('policy_revision') == EXPECTED_POLICY_REVISION,
            'Existing budget limit/policy changed')
    entries = budget.get('entries')
    require(isinstance(entries, list) and len(entries) == EXPECTED_ENTRIES, 'Existing settled ledger count changed')
    total = Decimal(0)
    for entry in entries:
        require(isinstance(entry, dict) and entry.get('status') == 'settled'
                and entry.get('call_status') == 'returned' and entry.get('cost_basis') == 'reported_usage',
                'Existing ledger is not fully settled')
        require(entry.get('provider_id') == provider_id and entry.get('charged_usd') is not None,
                'Existing ledger provider/charge changed')
        total += _money(entry.get('charged_usd'), 'charged_usd')
    require(str(total) == EXPECTED_SETTLED_USD, 'Existing settled total changed')
    if limits is not None:
        require(isinstance(limits, dict) and limits.get('max_started_runs') == 12
                and limits.get('max_total_minutes') == 45
                and limits.get('max_reported_cost_usd') is None,
                'Existing execution policy changed')
    return True


def preserve_task(old, current, fixture):
    """Allow only the declared single-sentence change; every old prefix stays byte-equal."""
    require(isinstance(current, dict), 'Task must remain a mapping')
    require(all(current.get(k) == old.get(k) for k in ('id', 'name', 'app_type', 'created_at', 'environment_id')),
            'Existing Task identity overwritten')
    require(isinstance(current.get('revision'), int) and current['revision'] >= old['revision'],
            'Task revision moved backwards')
    before, after = old.get('requirements') or {}, current.get('requirements') or {}
    require(set(before) == set(after), 'Requirement fields changed')
    for key in before:
        if key == 'output':
            continue
        require(after.get(key) == before.get(key), 'Non-output requirement changed')
    if after.get('output') != before.get('output'):
        old_reply = fixture.get('inputs', {}).get('no_hit_reply')
        new_reply = fixture.get('changed_no_hit_reply')
        require(isinstance(old_reply, str) and isinstance(new_reply, str)
                and isinstance(before.get('output'), str) and isinstance(after.get('output'), str),
                'Requirement output change lacks fixed literals')
        expected_output = before['output'].replace(old_reply, new_reply)
        require(expected_output != before['output'] and after['output'] == expected_output,
                'Requirement output change is not exactly the fixed literal replacement')
    require(current.get('configuration') == old.get('configuration'), 'Fixed configuration changed')
    require(current.get('materials') == old.get('materials'), 'Material history changed')
    require(_case_update_allowed(old.get('test_cases') or [], current.get('test_cases') or [], fixture),
            'Saved cases changed beyond the fixed no-answer expectation')
    for key in ('messages', 'versions', 'interview_attempts', 'runs', 'planning_runs', 'intake_history'):
        if key == 'interview_attempts':
            if key in old:
                require(isinstance(old.get(key), list), 'Original interview_attempts not a list')
                require(key in current and isinstance(current.get(key), list),
                        'Original interview_attempts overwritten')
                require(current[key][:len(old[key])] == old[key],
                        'Original Task history overwritten: interview_attempts')
            elif key in current:
                require(isinstance(current.get(key), list),
                        'New interview_attempts must be a list')
            continue
        require(key in old and isinstance(old.get(key), list) and key in current
                and isinstance(current.get(key), list), 'Task history field missing or not list: ' + key)
        prefix = old[key]
        value = current[key]
        require(value[:len(prefix)] == prefix, 'Original Task history overwritten: ' + key)
    return True


def new_entries(old, current):
    prefix = old.get('entries') or []
    entries = current.get('entries') or []
    require(isinstance(entries, list) and entries[:len(prefix)] == prefix, 'Original settled ledger changed')
    return entries[len(prefix):]


def preserve_budget(old, current, provider_id):
    """Keep every old field and only append up to three new settled/reserved/unknown entries."""
    require(isinstance(current, dict), 'Budget must remain a mapping')
    require(set(current) == set(old), 'Budget fields changed')
    require(all(current.get(k) == v for k, v in old.items() if k != 'entries'), 'Original budget policy changed')
    extra = new_entries(old, current)
    require(len(extra) <= 3, 'New model ledger count exceeded')
    total = Decimal(0)
    for entry in extra:
        require(isinstance(entry, dict) and entry.get('provider_id') == provider_id,
                'New ledger provider changed')
        require(entry.get('status') in {'reserved', 'settled', 'unknown'}, 'Unexpected new ledger status')
        reserved = _money(entry.get('reserved_usd'), 'reserved_usd')
        require(reserved <= PER_CALL_USD, 'Per-call estimate exceeded')
        total += reserved
    require(total <= BATCH_USD, 'Batch model estimate exceeded')
    return extra
