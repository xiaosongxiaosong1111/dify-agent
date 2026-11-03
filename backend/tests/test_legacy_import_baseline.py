"""Never infer an old import baseline from unbound or subsequently rebuilt bytes."""
import copy
import pytest
import yaml
from test_api import client
from test_dsl_roundtrip import prepared, forbid_external_calls, APP
from app import main


def legacy(client, historical=False):
    task, root = prepared(client)
    run = task['runs'][-1]
    run.pop('dsl_baseline')
    run.pop('baseline_kind', None)
    run['created_at'] = '2026-01-02T00:00:00+00:00'
    task['artifact']['created_at'] = '2026-01-01T00:00:00+00:00'
    if historical:
        main.snapshot(task, '公开旧生成记录')
        task['revision'] += 1
        task['artifact'] = None
    main.store.put('task', task['id'], task)
    return task, root


@pytest.mark.parametrize('historical', [False, True])
def test_verified_old_build_remains_available_without_mutating_task(client, historical):
    task, expected = legacy(client, historical)
    before = copy.deepcopy(main.get_task(task['id']))
    root, note = main.baseline_for(task, APP)
    assert root == expected and '摘要' in note
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('fault', ['bytes', 'foreign', 'hash_missing', 'build_time_missing', 'import_time_missing', 'later_build', 'bad_revision_type'])
@pytest.mark.parametrize('historical', [False, True])
def test_unproven_old_file_cannot_become_three_way_merge_baseline(client, tmp_path, historical, fault):
    task, root = legacy(client, historical)
    artifact = next(v['artifact'] for v in reversed(task['versions']) if v.get('artifact') and v['revision'] == task['runs'][-1]['revision']) if historical else task['artifact']
    path = main.DATA_ROOT / task['id'] / artifact['filename']
    if fault == 'bytes':
        path.write_bytes(path.read_bytes() + b'\n# PRIVATE_REPLACED_BASELINE\n')
    elif fault == 'foreign':
        other = tmp_path / 'other-source.yaml'
        other.write_text(yaml.safe_dump(root), 'utf-8')
        artifact['filename'] = str(other)
    elif fault == 'hash_missing':
        artifact.pop('sha256')
    elif fault == 'build_time_missing':
        artifact.pop('created_at')
    elif fault == 'import_time_missing':
        task['runs'][-1].pop('created_at')
    elif fault == 'bad_revision_type':
        artifact['revision'] = float(artifact['revision'])
    else:
        artifact['created_at'] = '2026-01-03T00:00:00+00:00'
    main.store.put('task', task['id'], task)
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={
        'revision': task['revision'], 'content': yaml.safe_dump(root), 'filename':'公开当前.yaml'})
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text
    assert main.get_task(task['id']) == before
    assert main.store.list('dsl_reference') == []


def test_saved_import_baseline_does_not_depend_on_old_generation_file(client):
    task, expected = prepared(client)
    path = main.artifact_path(task)
    path.unlink()
    before = copy.deepcopy(main.get_task(task['id']))
    result, _ = main.baseline_for(task, APP)
    assert result == expected and main.get_task(task['id']) == before


def test_later_rebuild_uses_an_eligible_historical_record_not_later_timestamp(client):
    task, expected = legacy(client)
    main.snapshot(task, '公开原构建')
    task['artifact']['created_at'] = '2026-01-03T00:00:00+00:00'
    main.store.put('task', task['id'], task)
    root, _ = main.baseline_for(task, APP)
    assert root == expected
