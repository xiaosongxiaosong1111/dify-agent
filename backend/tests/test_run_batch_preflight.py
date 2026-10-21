import copy
import json
import pytest
from test_api import client, forbid_api_external_calls
from test_execution_limits import prepared, save as save_limits
from app import main
from app.storage import Store


def preflight(client, task, count=2, **extra):
    return client.get(f"/api/tasks/{task['id']}/execution-limits/preflight", params={'revision': task['revision'], 'requested_runs': count} | extra)


def snapshot():
    with main.store.connect() as db: return list(db.execute('SELECT * FROM objects')), list(db.execute('SELECT * FROM secrets'))


def add_runs(task, count, status='success'):
    task['runs'] += [{'id': 'saved-' + str(i), 'kind': 'run', 'revision': max(1, task['revision'] - 1), 'status': status, 'created_at': '2026-10-21T00:00:00+00:00', 'completed_at': '2026-10-21T00:00:01+00:00'} for i in range(count)]
    main.store.put('task', task['id'], task)


def test_persisted_four_of_four_blocks_two_before_any_resource_creation(client):
    task, _ = prepared(client); assert save_limits(client, task, count=4, minutes=10).status_code == 200
    add_runs(task, 4); task['revision'] += 1; main.store.put('task', task['id'], task)
    before = snapshot(); r = preflight(client, task); assert r.status_code == 200, r.text
    value = r.json(); assert value['started_runs'] == 4 and value['requested_runs'] == 2 and value['minimum_finite_start_cap'] == 6
    assert value['remaining_start_slots'] == 0 and not value['count_fits'] and not value['limits_allow_requested_runs']
    assert any('至少' in b and '6' in b for b in value['blockers'])
    assert not value['network_requested'] and not value['task_changed'] and not value['limits_changed'] and value['start_slots_reserved'] == 0 and not value['resource_permission_granted']
    assert snapshot() == before
    main.store = Store(main.store.root); again = preflight(client, task).json()
    assert again['review_token'] == value['review_token'] and again['started_runs'] == 4


def test_whole_batch_capacity_is_checked_even_if_single_start_is_allowed(client):
    task, _ = prepared(client); assert save_limits(client, task, count=5).status_code == 200; add_runs(task, 4)
    value = preflight(client, task).json(); assert value['limits']['can_start'] and value['remaining_start_slots'] == 1
    assert not value['limits_allow_requested_runs'] and not value['count_fits']
    assert preflight(client, task, 1).json()['limits_allow_requested_runs']


def test_explicit_policy_update_does_not_reset_counts_and_invalidates_snapshot(client):
    task, _ = prepared(client); assert save_limits(client, task, count=4, minutes=10).status_code == 200; add_runs(task, 4)
    before = preflight(client, task).json(); old_task = main.store.get('task', task['id'])
    assert save_limits(client, task, count=6, minutes=10).status_code == 200
    after = preflight(client, task).json(); assert after['limits_allow_requested_runs'] and after['remaining_start_slots'] == 2
    assert after['started_runs'] == 4 and after['review_token'] != before['review_token']
    assert main.store.get('task', task['id']) == old_task


@pytest.mark.parametrize('kind', ['unknown_time', 'time_used', 'quote_unknown'])
def test_other_existing_limit_blockers_remain_even_when_count_fits(client, kind):
    task, _ = prepared(client)
    assert save_limits(client, task, count=10, minutes=1 if kind != 'quote_unknown' else None, **({'max_reported_cost_usd':'0.01'} if kind == 'quote_unknown' else {})).status_code == 200
    add_runs(task, 1, status='unknown' if kind == 'unknown_time' else 'success')
    if kind == 'time_used':
        task['runs'][-1]['completed_at'] = '2026-10-21T00:01:01+00:00'; main.store.put('task', task['id'], task)
    value = preflight(client, task).json(); assert value['count_fits'] and not value['limits_allow_requested_runs'] and value['blockers']


@pytest.mark.parametrize('count', [0, -1, 101, 'true', 'PRIVATE-DO-NOT-ECHO'])
def test_invalid_requested_batch_is_rejected_without_mutation_or_echo(client, count):
    task, _ = prepared(client); before = snapshot(); r = preflight(client, task, count)
    assert r.status_code == 422 and 'PRIVATE-DO-NOT-ECHO' not in r.text and snapshot() == before


def test_old_revision_other_task_scope_and_no_limit_do_not_grant_permissions(client):
    task, _ = prepared(client); assert preflight(client, task, revision=task['revision'] + 1).status_code == 409
    value = preflight(client, task, 100).json(); assert value['remaining_start_slots'] is None and value['count_fits']
    assert not value['resource_permission_granted'] and value['start_slots_reserved'] == 0
    other, _ = prepared(client); other_value = preflight(client, other, 100).json()
    assert other_value['task_id'] != value['task_id'] and other_value['review_token'] != value['review_token']


def test_failed_unknown_and_older_revision_runs_are_not_refunded(client):
    task, _ = prepared(client); assert save_limits(client, task, count=3).status_code == 200
    add_runs(task, 1, status='failed'); add_runs(task, 1, status='unknown')
    value = preflight(client, task).json(); assert value['started_runs'] == 2 and value['minimum_finite_start_cap'] == 4 and not value['count_fits']
