"""A stale materials panel must not change a newer task revision."""
import copy
import pytest
from test_api import client, approved
from app import main


def source(client):
    task = approved(client)
    response = client.post(f"/api/tasks/{task['id']}/materials", files={'file': ('rules.txt', '保修一年'.encode(), 'text/plain')})
    assert response.status_code == 200
    task = response.json()
    return task, task['materials'][-1]


def change(client, task, material, action, revision):
    url = f"/api/tasks/{task['id']}/materials/{material['id']}"
    if action == 'delete':
        return client.delete(url, params={} if revision is None else {'revision': revision})
    body = {'reference_mode': 'preserve', 'preserve_items': '保修一年'}
    if revision is not None:
        body['revision'] = revision
    return client.patch(url, json=body)


@pytest.mark.parametrize('action', ['patch', 'delete'])
def test_old_material_panel_cannot_mutate_new_task(client, action):
    task, material = source(client)
    latest = copy.deepcopy(main.get_task(task['id']))
    latest['revision'] += 1
    latest['requirements_confirmed'] = latest['configuration_confirmed'] = True
    latest['requirements']['goal'] = '另一个页面已保存的新要求'
    main.store.put('task', task['id'], latest)
    response = change(client, task, material, action, task['revision'])
    assert response.status_code == 409, response.text
    assert main.get_task(task['id']) == latest
    assert (main.DATA_ROOT / task['id'] / 'materials' / (material['id'] + '.txt')).read_bytes() == '保修一年'.encode()


@pytest.mark.parametrize('action', ['patch', 'delete'])
@pytest.mark.parametrize('revision', [None, 0, -1, True, 1.5, '1.0', 'bad', 9007199254740992])
def test_missing_or_invalid_source_revision_does_not_change_state(client, action, revision):
    task, material = source(client)
    before = main.get_task(task['id'])
    response = change(client, task, material, action, revision)
    assert response.status_code == 422, response.text
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('action', ['patch', 'delete'])
def test_current_material_action_keeps_recoverable_version_and_original_file(client, action):
    task, material = source(client)
    response = change(client, task, material, action, task['revision'])
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['revision'] == task['revision'] + 1
    assert saved['versions'][-1]['materials'] == task['materials']
    assert not saved['requirements_confirmed'] and not saved['configuration_confirmed']
    if action == 'delete':
        assert saved['materials'] == []
    else:
        assert saved['materials'][-1]['reference_mode'] == 'preserve'
        assert saved['materials'][-1]['preserve_items'] == '保修一年'
    assert (main.DATA_ROOT / task['id'] / 'materials' / (material['id'] + '.txt')).exists()
