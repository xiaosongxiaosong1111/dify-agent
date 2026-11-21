"""Native root targetHandle must reach preserved validation without coercion."""
import copy

import httpx
import pytest
import yaml

from test_api import client  # noqa: F401  正常API替身夹具
from test_dsl_roundtrip import prepared, changed
from app import main
from app.dify import DifyClient
from app.dsl_roundtrip import digest, parse, validate_preserved


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('目标句柄检查不得访问真实 HTTP、Dify 请求或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)
    monkeypatch.setattr(DifyClient, 'request', forbidden)


def native(client):
    task, root = prepared(client)
    return task, root


def edge_for(root, source):
    return next(edge for edge in root['workflow']['graph']['edges'] if edge['source'] == source)


def node_for(root, node_id):
    return next(node for node in root['workflow']['graph']['nodes'] if node['id'] == node_id)


@pytest.mark.parametrize('value', [False, ['target'], None, 1, '', 'unknown-target'])
def test_native_target_handle_is_validated_without_mutation(client, value):
    _, root = native(client)
    edge_for(root, 'code')['targetHandle'] = value
    before = copy.deepcopy(root)
    result = validate_preserved(root)
    assert not result['valid'] and result['errors']
    assert any('target' in error for error in result['errors'])
    assert root == before


@pytest.mark.parametrize('explicit', [False, True])
def test_omitted_or_explicit_native_target_stays_valid(client, explicit):
    _, root = native(client)
    edge = edge_for(root, 'code')
    if explicit:
        edge['targetHandle'] = 'target'
    else:
        edge.pop('targetHandle', None)
    before = copy.deepcopy(root)
    result = validate_preserved(root)
    assert result['valid'], result
    assert root == before


@pytest.mark.parametrize('value', [False, ['target']])
def test_normal_api_rejects_native_target_without_confirming(client, monkeypatch, value):
    task, root = native(client)
    current = changed(root)
    edge_for(current, 'start')['targetHandle'] = value
    manual = node_for(current, 'code')
    async def exported(*args):
        return yaml.safe_dump(current, allow_unicode=True)
    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()['task']
    reference = main.store.get('dsl_reference', task['dsl_reference']['id'])
    stored = reference['current']
    assert edge_for(stored, 'start')['targetHandle'] == value
    assert node_for(stored, 'code')['position']['x'] == manual['position']['x']
    assert 'upper()' in node_for(stored, 'code')['data']['code']
    preview = client.get(f"/api/tasks/{task['id']}/dsl-merge")
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert p['validation']['valid'] is False
    assert any('target' in error for error in p['validation']['errors'])
    before_apply = copy.deepcopy(main.get_task(task['id']))
    applied = client.post(f"/api/tasks/{task['id']}/dsl-merge/apply", json={'revision': task['revision'], 'reference_id': p['reference_id'], 'merge_token': p['merge_token'], 'choices': {}})
    assert applied.status_code == 422, applied.text
    assert main.get_task(task['id']) == before_apply
    assert not main.get_task(task['id']).get('dsl_overlay')
    assert main.store.get('dsl_reference', task['dsl_reference']['id']) == reference
    assert not list((main.DATA_ROOT / task['id']).glob('preserved-*.yaml'))


def test_uploaded_native_target_is_readable_but_never_adopted(client):
    task, root = native(client)
    current = changed(root)
    edge_for(current, 'code')['targetHandle'] = ['target']
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision'], 'content': yaml.safe_dump(current, allow_unicode=True), 'filename': 'manual-edit.yaml'})
    assert response.status_code == 200, response.text
    task = response.json()['task']
    assert task['dsl_reference']['source'] == 'uploaded_file'
    reference = main.store.get('dsl_reference', task['dsl_reference']['id'])
    assert edge_for(reference['current'], 'code')['targetHandle'] == ['target']
    preview = client.get(f"/api/tasks/{task['id']}/dsl-merge").json()
    assert preview['validation']['valid'] is False
    applied = client.post(f"/api/tasks/{task['id']}/dsl-merge/apply", json={'revision': task['revision'], 'reference_id': preview['reference_id'], 'merge_token': preview['merge_token'], 'choices': {}})
    assert applied.status_code == 422, applied.text
    assert main.store.get('dsl_reference', task['dsl_reference']['id']) == reference
    assert not list((main.DATA_ROOT / task['id']).glob('preserved-*.yaml'))


def test_stored_legacy_overlay_cannot_build_after_revalidation(client):
    task, root = native(client)
    current = changed(root)
    edge_for(current, 'start')['targetHandle'] = False
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision'], 'content': yaml.safe_dump(current, allow_unicode=True), 'filename': 'legacy-edit.yaml'})
    assert response.status_code == 200, response.text
    task = response.json()['task']
    reference = main.store.get('dsl_reference', task['dsl_reference']['id'])
    folder = main.DATA_ROOT / task['id']
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"preserved-r{task['revision']}.yaml"
    content = yaml.safe_dump(reference['current'], allow_unicode=True)
    (folder / filename).write_text(content, encoding='utf-8')
    task['dsl_overlay'] = {'revision': task['revision'], 'reference_id': reference['id'], 'environment_id': task['environment_id'], 'filename': filename, 'digest': digest(parse(content, task['app_type'])), 'validation': {'valid': True, 'errors': [], 'warnings': [], 'nodes': 3, 'verification': 'static_only'}, 'choices': {}, 'parallel_reviews': {}, 'loop_reviews': {}, 'preserved_paths': [], 'created_at': task['dsl_reference']['created_at']}
    main.save_task(task)
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': task['revision'], 'kind': kind})
        assert response.status_code == 200, response.text
    task = main.get_task(task['id'])
    assert task['requirements_confirmed'] and task['configuration_confirmed'] and not task.get('plan_stale')
    before = copy.deepcopy(main.get_task(task['id']))
    assert before['dsl_overlay']['validation']['valid'] is True
    files_before = sorted(path.name for path in folder.iterdir())
    file_before = (folder / filename).read_bytes()
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 422 and 'target' in response.text
    assert main.get_task(task['id']) == before
    assert sorted(path.name for path in folder.iterdir()) == files_before
    assert (folder / filename).read_bytes() == file_before
    assert main.store.get('dsl_reference', reference['id']) == reference
