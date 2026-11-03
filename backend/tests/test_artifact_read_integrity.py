"""Every current-artifact reader must respect its task owner and build bytes."""
import copy
import hashlib
import pytest
from fastapi.testclient import TestClient
from test_api import client, create_env, forbid_api_external_calls
from test_delivery_bundle import built
from app import main

READERS = ['dsl', 'artifact', 'run-input-schema']


@pytest.mark.parametrize('reader', READERS)
def test_changed_build_bytes_do_not_keep_old_validation_or_return_file(client, reader):
    task = built(client)
    path = main.artifact_path(task)
    changed = path.read_bytes() + b'\n# PRIVATE_EXTERNAL_EDIT\n'
    path.write_bytes(changed)
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.get(f"/api/tasks/{task['id']}/{reader}")
    assert response.status_code == 409, response.text
    assert 'PRIVATE' not in response.text
    assert main.get_task(task['id']) == before and path.read_bytes() == changed


@pytest.mark.parametrize('reader', READERS)
def test_foreign_path_rejected_without_reading_other_task_or_external_file(client, tmp_path, reader):
    task = built(client)
    outside = tmp_path / 'private-other-file.yaml'
    outside.write_text('PRIVATE_OTHER_FILE', 'utf-8')
    task['artifact']['filename'] = str(outside)
    main.store.put('task', task['id'], task)
    response = client.get(f"/api/tasks/{task['id']}/{reader}")
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text and outside.read_text('utf-8') == 'PRIVATE_OTHER_FILE'
    assert main.get_task(task['id']) == task


@pytest.mark.parametrize('reader', READERS)
@pytest.mark.parametrize('filename', [None, [], ''])
def test_malformed_file_identity_has_safe_error_without_changing_task(client, reader, filename):
    task = built(client)
    task['artifact']['filename'] = filename
    main.store.put('task', task['id'], task)
    with TestClient(main.app, raise_server_exceptions=False) as safe:
        response = safe.get(f"/api/tasks/{task['id']}/{reader}")
    assert response.status_code == 422, response.text
    assert main.get_task(task['id']) == task


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat', 'agent'])
def test_valid_build_download_keeps_bytes_revision_and_record(client, mode):
    task = built(client, mode)
    raw = main.artifact_path(task).read_bytes()
    response = client.get(f"/api/tasks/{task['id']}/artifact")
    assert response.status_code == 200, response.text
    assert response.content == raw and f"r{task['revision']}.yaml" in response.headers['content-disposition']
    assert response.headers['x-sierra-artifact-integrity'] == 'recorded_build_sha256'
    assert response.headers['cache-control'] == 'no-store'
    assert main.get_task(task['id']) == task


@pytest.mark.parametrize('reader', ['dsl', 'artifact'])
def test_legacy_no_hash_is_exported_with_explicit_basis_and_not_rewritten(client, reader):
    task = built(client)
    path = main.artifact_path(task)
    raw = path.read_bytes() + b'\n# legacy bytes only\n'
    path.write_bytes(raw)
    task['artifact'].pop('sha256')
    main.store.put('task', task['id'], task)
    response = client.get(f"/api/tasks/{task['id']}/{reader}")
    assert response.status_code == 200, response.text
    if reader == 'dsl':
        data = response.json()
        assert data['artifact_integrity_basis'] == 'legacy_export_bytes_only'
        assert '构建摘要' in '\n'.join(data['validation']['warnings'])
    else:
        assert response.content == raw
        assert response.headers['x-sierra-artifact-integrity'] == 'legacy_export_bytes_only'
    assert main.get_task(task['id']) == task and 'sha256' not in task['artifact']


def test_raw_hash_verification_keeps_existing_text_newline_contract(client):
    task = built(client)
    path = main.artifact_path(task)
    raw = path.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n').replace(b'\n', b'\r\n')
    path.write_bytes(raw)
    task['artifact']['sha256'] = hashlib.sha256(raw).hexdigest()
    main.store.put('task', task['id'], task)
    assert client.get(f"/api/tasks/{task['id']}/artifact").content == raw
    value = client.get(f"/api/tasks/{task['id']}/dsl").json()
    assert value['content'] == raw.decode('utf-8').replace('\r\n', '\n')
    assert main.get_task(task['id']) == task


def test_import_drift_stops_before_key_budget_or_external_operation(client, monkeypatch):
    env = create_env(client)
    task = built(client)
    task['environment_id'] = env['id']
    main.store.put('task', task['id'], task)
    path = main.artifact_path(task)
    path.write_bytes(path.read_bytes() + b'\n# changed before import\n')
    before = copy.deepcopy(main.get_task(task['id']))
    ledger = copy.deepcopy(main.store.get('task_budget', task['id']))
    keys = []; external = []
    def key(*args, **kwargs):
        keys.append(True)
        return 'isolated-unused-key'
    def request(*args, **kwargs):
        external.append(True)
        raise main.DifyError('isolated blocked dispatch')
    monkeypatch.setattr(main.store, 'secret', key)
    monkeypatch.setattr(main.DifyClient, 'request', request)
    response = client.post(f"/api/tasks/{task['id']}/import", json={'revision': task['revision']})
    assert response.status_code == 409, response.text
    assert main.get_task(task['id']) == before
    assert main.store.get('task_budget', task['id']) == ledger
    assert keys == external == []


@pytest.mark.parametrize('reader', READERS)
def test_oversized_legacy_file_is_not_read_as_unbounded_current_artifact(client, reader):
    task = built(client)
    path = main.artifact_path(task)
    path.write_bytes(b'x' * 2_000_001)
    task['artifact'].pop('sha256')
    main.store.put('task', task['id'], task)
    response = client.get(f"/api/tasks/{task['id']}/{reader}")
    assert response.status_code == 422, response.text
    assert main.get_task(task['id']) == task


def test_report_remains_available_as_saved_records_when_file_has_drifted(client):
    task = built(client)
    path = main.artifact_path(task)
    path.write_bytes(path.read_bytes() + b'\n# PRIVATE_EXTERNAL_EDIT\n')
    response = client.get(f"/api/tasks/{task['id']}/report")
    assert response.status_code == 200, response.text
    assert '保存的构建记录' in response.text and '未重新读取' in response.text
    assert 'PRIVATE_EXTERNAL_EDIT' not in response.text
    assert main.get_task(task['id']) == task


def test_file_link_to_other_source_is_rejected_without_returning_its_bytes(client, tmp_path):
    task = built(client)
    path = main.artifact_path(task)
    other = tmp_path / 'other-source.yaml'
    other.write_text('PRIVATE_OTHER_SOURCE', 'utf-8')
    path.unlink()
    try:
        path.symlink_to(other)
    except OSError:
        pytest.skip('Current Windows token cannot create symbolic links')
    response = client.get(f"/api/tasks/{task['id']}/artifact")
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text and other.read_text('utf-8') == 'PRIVATE_OTHER_SOURCE'
    assert main.get_task(task['id']) == task
