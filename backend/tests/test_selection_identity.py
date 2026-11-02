"""Malformed selections cannot change a task or dispatch to a fallback model."""
import copy
import pytest
from fastapi.testclient import TestClient
from test_api import client, approved, planning_provider, forbid_api_external_calls
from app import main


BAD = [[], {}, False, True, 0, 17, 1.5, ['PRIVATE-SELECTION'], {'id': 'PRIVATE-SELECTION'}]


@pytest.mark.parametrize('field', ['assistant_provider_id', 'environment_id'])
@pytest.mark.parametrize('value', BAD)
def test_patch_refuses_non_text_identity_before_invalidating_task(client, field, value):
    task = approved(client)
    before = copy.deepcopy(main.get_task(task['id']))
    body = {'configuration': {field: value}} if field == 'assistant_provider_id' else {field: value}
    with TestClient(main.app, raise_server_exceptions=False) as safe:
        response = safe.patch(f"/api/tasks/{task['id']}", json={'expected_revision': task['revision'], **body})
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('action', ['planning', 'interview', 'stream'])
@pytest.mark.parametrize('value', [[], False, 0, ['PRIVATE-SELECTION'], {'id': 'PRIVATE-SELECTION'}])
def test_legacy_bad_model_selection_rejected_before_lookup_checkpoint_key_or_call(client, monkeypatch, action, value):
    planning_provider(client)
    task = approved(client)
    task['configuration']['assistant_provider_id'] = value
    main.store.put('task', task['id'], task)
    before = copy.deepcopy(main.get_task(task['id']))
    ledger = copy.deepcopy(main.store.get('task_budget', task['id']))
    calls = []
    async def model(*args, **kwargs):
        calls.append(True)
        raise RuntimeError('isolated unexpected model dispatch')
    def key(*args, **kwargs):
        pytest.fail('Bad identity must stop before key decryption')
    monkeypatch.setattr(main, 'call_model', model)
    monkeypatch.setattr(main.store, 'secret', key)
    path = 'plan/generate' if action == 'planning' else 'messages'
    body = {'revision': task['revision']} if action == 'planning' else {
        'revision': task['revision'], 'content': '公开要求核对', 'stream_response': action == 'stream'}
    with TestClient(main.app, raise_server_exceptions=False) as safe:
        response = safe.post(f"/api/tasks/{task['id']}/{path}", json=body)
    assert response.status_code == 422, response.text
    assert '选择' in response.text and 'PRIVATE' not in response.text
    assert main.get_task(task['id']) == before
    assert main.store.get('task_budget', task['id']) == ledger
    assert calls == []


@pytest.mark.parametrize('selected', [None, ''])
def test_explicit_unselected_model_keeps_default_selection_behavior(client, selected):
    provider = planning_provider(client)
    task = approved(client)
    response = client.patch(f"/api/tasks/{task['id']}", json={'configuration': {'assistant_provider_id': selected}, 'expected_revision': task['revision']})
    assert response.status_code == 200, response.text
    assert main.main_provider(response.json())['id'] == provider['id']


def test_explicit_provider_id_is_retained_and_missing_id_does_not_switch_to_default(client):
    fallback = planning_provider(client)
    selected = planning_provider(client)
    task = approved(client)
    saved = client.patch(f"/api/tasks/{task['id']}", json={'configuration': {'assistant_provider_id': selected['id']}, 'expected_revision': task['revision']}).json()
    assert main.main_provider(saved)['id'] == selected['id'] != fallback['id']
    saved['configuration']['assistant_provider_id'] = 'missing-public-provider'
    with pytest.raises(main.HTTPException) as exc:
        main.main_provider(saved)
    assert exc.value.status_code == 422


@pytest.mark.parametrize('value', [None, ''])
def test_unselected_environment_remains_supported(client, value):
    task = approved(client)
    response = client.patch(f"/api/tasks/{task['id']}", json={'environment_id': value, 'expected_revision': task['revision']})
    assert response.status_code == 200, response.text
    assert response.json()['environment_id'] == value
