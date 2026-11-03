"""Inspect saved JSON without granting or requiring permission to restore it."""
import copy
import json
import pytest
from test_api import client, forbid_api_external_calls, approved
from test_version_content import seeded, read
from app import main
from app.version_restore import token


def index(client, task, version):
    return client.get(f"/api/tasks/{task['id']}/versions/{version['id']}/content-index", params={'revision': task['revision']})


@pytest.mark.parametrize('fault', ['requirements', 'configuration', 'materials', 'missing_restore_field'])
def test_existing_read_api_is_not_blocked_by_restore_only_constraints(client, fault):
    task, _ = seeded(client); version = task['versions'][0]
    if fault == 'requirements':version['requirements']['goal'] = None
    elif fault == 'configuration':version['configuration']['suggested_questions'] = 42
    elif fault == 'materials':version['materials'] = None
    else:version.pop('environment_id')
    main.store.put('task', task['id'], task)
    before = copy.deepcopy(main.get_task(task['id']))
    restore = client.get(f"/api/tasks/{task['id']}/versions/{version['id']}/restore-preview", params={'revision': task['revision']})
    assert restore.status_code == 422
    result = read(client, task, version, section='configuration')
    assert result.status_code == 200, result.text
    assert json.loads(result.json()['text']) == version['configuration']
    assert main.get_task(task['id']) == before


def test_read_index_mints_read_only_source_and_cannot_be_used_to_restore(client):
    task, version = seeded(client); before = copy.deepcopy(main.get_task(task['id']))
    response = index(client, task, version)
    assert response.status_code == 200, response.text
    meta = response.json()
    assert meta['verification'] == 'local_history_content_index_only' and meta['restore_allowed'] is False
    assert meta['snapshot_token'] != token(task, version)
    assert len(meta['sections']) == 5 and 'text' not in meta
    page = read(client, task, version, snapshot_token=meta['snapshot_token'], section='configuration')
    assert page.status_code == 200 and '9007199254740993' in page.json()['text']
    restore = client.post(f"/api/tasks/{task['id']}/restore", json={'revision':task['revision'],'version_id':version['id'],
        'review_token':meta['snapshot_token'],'acknowledge_restore':True})
    assert restore.status_code == 409
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('bad', ['secret', 'oversize', 'missing'])
def test_each_section_has_explicit_readability_without_partial_or_current_values(client, bad):
    task, _ = seeded(client); version = task['versions'][0]
    if bad == 'secret':version['workflow_plan'] = {'api_key':'sk-SYNTHETIC-SECRET-ONLY-0123456789'}
    elif bad == 'oversize':version['workflow_plan'] = {'code':'x'*2_000_001}
    else:version.pop('workflow_plan')
    main.store.put('task', task['id'], task); before = copy.deepcopy(main.get_task(task['id']))
    response = index(client, task, version); assert response.status_code == 200, response.text
    meta = response.json(); section = next(s for s in meta['sections'] if s['key']=='workflow_plan')
    assert section['state'] == ('missing' if bad=='missing' else 'unavailable')
    assert section['content_sha256'] is None and 'SYNTHETIC' not in response.text
    page = read(client, task, version, snapshot_token=meta['snapshot_token'], section='workflow_plan')
    assert page.status_code == (404 if bad=='missing' else 422) and 'text' not in page.json()
    assert read(client,task,version,snapshot_token=meta['snapshot_token'],section='configuration').status_code == 200
    assert main.get_task(task['id']) == before


def test_readable_section_not_blocked_by_unencodable_other_section_or_large_current_materials(client):
    task, _ = seeded(client); version = task['versions'][0]
    version['workflow_plan'] = {'code':'SYNTHETIC\ud800'}
    task['materials'] = [{'id':'public','status':'needs_input','text':'x'*8_000_001}]
    with main.store.connect() as db:
        db.execute('UPDATE objects SET value=? WHERE kind=? AND id=?',(json.dumps(task,ensure_ascii=True),'task',task['id']))
    meta = index(client,task,version).json()
    assert next(s for s in meta['sections'] if s['key']=='workflow_plan')['state'] == 'unavailable'
    assert 'SYNTHETIC' not in json.dumps(meta)
    page = read(client,task,version,snapshot_token=meta['snapshot_token'],section='configuration')
    assert page.status_code == 200 and '9007199254740993' in page.json()['text']


@pytest.mark.parametrize('change', ['revision','history','other_task','duplicate'])
def test_read_source_never_follows_stale_or_foreign_history(client, change):
    task, version = seeded(client); meta = index(client,task,version).json()
    if change == 'revision':task['revision'] += 1
    elif change == 'history':task['versions'][0]['configuration']['temperature'] = .9
    elif change == 'duplicate':task['versions'].append(copy.deepcopy(version))
    else:
        other = approved(client);other['versions'] = [version];task = other
    main.store.put('task',task['id'],task)
    response = read(client,task,version,snapshot_token=meta['snapshot_token'],section='configuration')
    assert response.status_code == (404 if change=='duplicate' else 409) and 'text' not in response.json()


def test_read_source_independent_of_current_flags_and_busy_operation_without_writes(client):
    task, version = seeded(client); meta = index(client,task,version).json()
    task['configuration']['temperature'] = .9
    task['requirements_confirmed'] = False;task['status'] = 'planning'
    main.store.put('task',task['id'],task);before=copy.deepcopy(main.get_task(task['id']))
    response = read(client,task,version,snapshot_token=meta['snapshot_token'],section='configuration')
    assert response.status_code == 200, response.text
    assert main.get_task(task['id']) == before
