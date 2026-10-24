import copy

import pytest
import yaml

from test_mock_dependency_exports import export_task, compiler
from test_api import client, create, forbid_api_external_calls
from app import main
from app.storage import Store


DEPENDENCY = '订单接口'
TODO = '提供真实查询地址和鉴权引用；替换固定样例后重新验证有订单、无订单和接口故障。'


def binding(path, node_id=None):
    return {'dependency': DEPENDENCY, 'node_id': node_id or ('agent.system_prompt' if path == 'agent' else 'llm'),
            'replacement_todo': TODO}


@pytest.mark.parametrize('path', ['basic-workflow', 'basic-chat', 'explicit-workflow', 'explicit-chat', 'agent'])
def test_declared_position_and_todo_survive_export_but_never_change_executable_graph(path):
    task = export_task(path)
    task['configuration']['mock_dependencies'] = [DEPENDENCY]
    baseline, _ = compiler(path)(task)
    task['configuration']['mock_dependency_bindings'] = [binding(path)]
    original = copy.deepcopy(task)
    content, validation = compiler(path)(task)
    assert task == original and validation['valid']
    assert any('仅通过节点存在检查' in warning for warning in validation['warnings'])
    actual, expected = yaml.safe_load(content), yaml.safe_load(baseline)
    description = actual['app']['description']
    assert TODO in description and binding(path)['node_id'] in description
    assert '未验证模拟实现或真实接入' in description
    actual['app']['description'] = expected['app']['description']
    if path == 'agent':
        package = actual['agent_packages'][actual['agent']['package_ref']]
        assert TODO in package['metadata']['description']
        package['metadata']['description'] = expected['agent_packages'][expected['agent']['package_ref']]['metadata']['description']
    assert actual == expected


@pytest.mark.parametrize('path', ['explicit-workflow', 'explicit-chat', 'agent'])
@pytest.mark.parametrize('orphan', [False, True])
def test_stale_node_or_removed_dependency_cannot_produce_valid_artifact(path, orphan):
    task = export_task(path)
    task['configuration'].update(mock_dependencies=[] if orphan else [DEPENDENCY],
        mock_dependency_bindings=[binding(path, 'deleted-node') if not orphan else binding(path)])
    if path == 'agent':
        with pytest.raises(ValueError, match='不再对应当前声明' if orphan else '当前成果中不存在'):
            compiler(path)(task)
    else:
        content, validation = compiler(path)(task)
        assert not content and not validation['valid']
        assert any(('不再对应当前声明' if orphan else '当前成果中不存在') in error for error in validation['errors'])


@pytest.mark.parametrize('invalid', [None, {}, [True], [{}], [binding('agent') | {'completed': True}],
    [binding('agent') | {'replacement_todo': ''}], [binding('agent'), binding('agent')],
    [binding('agent') | {'node_id': 7}]])
def test_malformed_or_self_certified_completion_is_rejected_without_writing(client, invalid):
    task = create(client)
    before = client.get('/api/tasks/' + task['id']).json()
    response = client.patch('/api/tasks/' + task['id'], json={'configuration': {'mock_dependency_bindings': invalid}})
    assert response.status_code == 422
    assert client.get('/api/tasks/' + task['id']).json() == before


def prepare(client, path='explicit-workflow'):
    source = export_task(path)
    task = create(client, source['app_type'])
    tid = task['id']
    task = client.patch(f'/api/tasks/{tid}', json={'requirements': source['requirements'],
        'configuration': source['configuration'] | {'mock_dependencies': [DEPENDENCY]}}).json()
    assert client.post(f'/api/tasks/{tid}/confirm', json={'revision': task['revision'], 'kind': 'requirements'}).status_code == 200
    response = client.post(f'/api/tasks/{tid}/plan', json={'revision': task['revision'],
        'plan': source.get('agent_plan', source.get('workflow_plan'))})
    assert response.status_code == 200, response.text
    task = response.json()
    assert client.post(f'/api/tasks/{tid}/confirm', json={'revision': task['revision'], 'kind': 'configuration'}).status_code == 200
    assert client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']}).status_code == 200
    return client.get('/api/tasks/' + tid).json()


@pytest.mark.parametrize('path', ['explicit-workflow', 'explicit-chat', 'agent'])
def test_saved_handoff_invalidates_confirmation_persists_and_enters_downloads(client, path):
    old = prepare(client, path); tid = old['id']
    value = [binding(path)]
    response = client.patch(f'/api/tasks/{tid}', json={'configuration': {'mock_dependency_bindings': value}})
    assert response.status_code == 200, response.text
    task = response.json()
    assert task['revision'] == old['revision'] + 1 and task['requirements_confirmed']
    assert not task['configuration_confirmed'] and task['artifact'] is None
    assert client.get(f'/api/tasks/{tid}/artifact').status_code == 404
    assert client.post(f'/api/tasks/{tid}/build', json={'revision': old['revision']}).status_code == 409
    assert client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']}).status_code == 422
    assert client.post(f'/api/tasks/{tid}/confirm', json={'revision': task['revision'], 'kind': 'configuration'}).status_code == 200
    assert client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']}).status_code == 200
    downloaded = client.get(f'/api/tasks/{tid}/artifact').text
    report = client.get(f'/api/tasks/{tid}/report').text
    assert TODO in downloaded and TODO in report and '未验证完成' in report
    assert Store(main.store.root).get('task', tid)['configuration']['mock_dependency_bindings'] == value
    assert not client.get(f'/api/tasks/{tid}').json()['runs']


def test_legacy_declaration_without_binding_stays_visible_and_can_build(client):
    task = prepare(client)
    assert any('尚未填写节点位置' in warning for warning in task['artifact']['validation']['warnings'])
    assert '尚未填写节点位置与逐项接入待办' in client.get('/api/tasks/' + task['id'] + '/report').text


@pytest.mark.parametrize('keep_note', [False, True])
def test_final_preserved_file_is_checked_without_overwriting_manual_content(client, keep_note):
    from test_dsl_roundtrip import prepared, changed, capture, apply
    task, _ = prepared(client); tid = task['id']
    response = client.patch(f'/api/tasks/{tid}', json={'configuration': {'mock_dependencies': [DEPENDENCY],
        'mock_dependency_bindings': [binding('explicit-workflow', 'code')]}})
    assert response.status_code == 200, response.text
    task = response.json()
    content, _ = main.compile_current(task)
    current = changed(yaml.safe_load(content))
    if not keep_note:
        current['app']['description'] = '保留这段人工说明，不允许自动覆盖。'
    task = capture(client, task, current)
    preview = client.get(f'/api/tasks/{tid}/dsl-merge').json()
    choices = {item['path']: 'current' for item in preview['conflicts']}
    response, _ = apply(client, task, choices)
    assert response.status_code == 200, response.text
    task = response.json()
    for kind in ('requirements', 'configuration'):
        response = client.post(f'/api/tasks/{tid}/confirm', json={'revision': task['revision'], 'kind': kind})
        assert response.status_code == 200, response.text
    before = copy.deepcopy(main.store.get('task', tid)['dsl_overlay'])
    overlay_file = main.DATA_ROOT / tid / before['filename']; original_bytes = overlay_file.read_bytes()
    response = client.post(f'/api/tasks/{tid}/build', json={'revision': task['revision']})
    assert response.status_code == (200 if keep_note else 422), response.text
    if keep_note:
        assert client.get(f'/api/tasks/{tid}/artifact').content == original_bytes
    else:
        assert '不会自动覆盖手改' in response.text
        assert not main.store.get('task', tid)['artifact']
    assert overlay_file.read_bytes() == original_bytes
    assert main.store.get('task', tid)['dsl_overlay'] == before
