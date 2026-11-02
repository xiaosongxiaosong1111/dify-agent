import copy
import json

import httpx
import pytest
import yaml

from test_api import client, approved, create
from test_planning import plan
from app import main
from app.reference_dsl import summarize, material_text
from app.workflow_plan import compile_workflow_plan


@pytest.fixture(autouse=True)
def forbid_reference_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('参考程度隔离检查不得访问真实 HTTP 或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def content(task):
    task = copy.deepcopy(task); task['workflow_plan'] = plan()
    return compile_workflow_plan(task)[0]


def preview(client, task, text=None, **patch):
    return client.post(f"/api/tasks/{task['id']}/reference-dsl/preview", json={'revision': task['revision'], 'content': text or content(task), 'filename': '参考流程.yaml', **patch})


def state(client, task):
    return client.get(f"/api/tasks/{task['id']}/reference-dsl").json()


def adopt(client, task, **patch):
    record = state(client, task)['record']
    return client.post(f"/api/tasks/{task['id']}/reference-dsl/adopt", json={'revision': task['revision'], 'preview_id': record['id'], 'preview_token': record['preview_token'], 'reference_mode': 'borrow', 'acknowledge_limits': True, **patch})


def test_preview_local_only_does_not_change_task_or_expose_source(client):
    task = approved(client); before = copy.deepcopy(task)
    response = preview(client, task); assert response.status_code == 200, response.text
    result = response.json(); assert main.get_task(task['id']) == before
    record = result['record']; assert 'content' not in record and not result['stale']
    summary = record['summary']; assert summary['verification'] == 'local_structure_only'
    assert len(summary['nodes']) == 3 and len(summary['edges']) == 2
    assert summary['inputs'][0]['variable'] == 'query' and summary['outputs'][0]['variable'] == 'result'
    assert next(n for n in summary['nodes'] if n['type'] == 'code')['details'][-1]['field'] == 'code'
    assert not list((main.DATA_ROOT / task['id']).glob('materials/*'))


def test_adopt_material_preserves_source_plan_and_invalidates(client):
    task = approved(client); source = content(task); task['workflow_plan'] = plan(); main.save_task(task)
    assert preview(client, task, source).status_code == 200
    assert adopt(client, task, acknowledge_limits=False).status_code == 422
    response = adopt(client, task); assert response.status_code == 200, response.text
    new = response.json(); m = new['materials'][0]
    assert m['source_kind'] == 'reference_dsl' and m['status'] == 'parsed' and m['reference_mode'] == 'borrow'
    assert '结构摘要' in m['text']
    assert new['app_type'] == task['app_type'] and new['workflow_plan'] == task['workflow_plan'] and new['plan_stale']
    assert new['revision'] == task['revision'] + 1 and not new['requirements_confirmed'] and not new['configuration_confirmed']
    assert not new['dify_app_id'] and not new['runs'] and not new.get('dsl_reference')
    assert (main.DATA_ROOT / new['id'] / 'materials' / (m['id'] + '.yaml')).read_text(encoding='utf-8') == source
    assert adopt(client, new).status_code == 409
    assert '参考 DSL 材料摘要' in client.get(f"/api/tasks/{task['id']}/report").text


@pytest.mark.parametrize('mode', ['preserve', 'replicate'])
def test_preserve_replicate_not_silently_borrowed(client, mode):
    task = approved(client); preview(client, task)
    if mode == 'preserve': assert adopt(client, task, reference_mode=mode).status_code == 422
    task = adopt(client, task, reference_mode=mode, preserve_items='保留代码规则').json()
    assert task['materials'][0]['reference_mode'] == mode
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': kind, 'revision': task['revision']}); assert response.status_code == 200, response.text
        task = response.json()
    result = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert result.status_code == 422 and ('严格复现' in result.text or '保留' in result.text)


def test_different_source_type_is_reference_only(client):
    task = approved(client); source_task = copy.deepcopy(task); source_task['app_type'] = 'advanced-chat'
    from app.dsl import compile_dsl
    source = compile_dsl(source_task)[0]
    response = preview(client, task, source); assert response.status_code == 200
    summary = response.json()['record']['summary']
    assert summary['source']['app_type'] == 'advanced-chat' and summary['target_type'] == 'workflow'
    assert any('不会自动更换' in w for w in summary['warnings'])
    assert adopt(client, task).json()['app_type'] == 'workflow'


def test_unknown_and_http_and_iteration_not_removed(client):
    task = approved(client); root = yaml.safe_load(content(task))
    root['workflow']['graph']['nodes'].extend([{'id': 'human', 'data': {'type': 'human-input', 'title': '人工审批'}}, {'id': 'http', 'data': {'type': 'http-request', 'method': 'POST', 'url': 'https://example.org/side-effect'}}, {'id': 'iter', 'data': {'type': 'iteration', 'is_parallel': True}}])
    response = preview(client, task, yaml.safe_dump(root)); assert response.status_code == 200
    summary = response.json()['record']['summary']
    assert {n['id'] for n in summary['nodes']} >= {'human', 'http', 'iter'}
    assert not next(n for n in summary['nodes'] if n['id'] == 'human')['planning_supported_type']
    assert any('尚未适配' in w and 'human' in w for w in summary['warnings'])
    assert any('副作用' in w for w in summary['warnings']) and any('并行' in w for w in summary['warnings'])


@pytest.mark.parametrize('attack', ['secret_key', 'bearer', 'sk_key', 'secret_env', 'alias', 'duplicate_yaml', 'too_large', 'version', 'mode', 'missing_graph', 'duplicate_node', 'bad_edge', 'bad_title', 'bad_input'])
def test_bad_or_secret_reference_not_persisted(client, attack):
    task = approved(client); root = yaml.safe_load(content(task)); text = None
    if attack == 'secret_key': root['api_key'] = 'secret-example'
    elif attack == 'bearer': root['app']['description'] = 'Bearer abcdefghijklmnopqrstuvwxyz'
    elif attack == 'sk_key': root['app']['description'] = 'sk-abcdefghijklmnopqrstuv'
    elif attack == 'secret_env': root['workflow']['environment_variables'] = [{'value_type': 'secret', 'value': 'hidden-value'}]
    elif attack == 'alias': text = 'kind: app\napp: &x {mode: workflow}\nother: *x\nversion: 0.7.0'
    elif attack == 'duplicate_yaml': text = 'kind: app\nkind: app'
    elif attack == 'too_large': text = 'x' * 2_000_001
    elif attack == 'version': root['version'] = '0.6.0'
    elif attack == 'mode': root['app']['mode'] = 'unknown'
    elif attack == 'missing_graph': root['workflow'].pop('graph')
    elif attack == 'duplicate_node': root['workflow']['graph']['nodes'].append(root['workflow']['graph']['nodes'][0])
    elif attack == 'bad_edge': root['workflow']['graph']['edges'][0]['source'] = 'missing'
    elif attack == 'bad_title': root['workflow']['graph']['nodes'][0]['data']['title'] = {'bad': True}
    else: root['workflow']['graph']['nodes'][0]['data']['variables'] = ['bad']
    result = preview(client, task, text or yaml.safe_dump(root)); assert result.status_code == 422, result.text
    assert not main.store.list('reference_dsl_preview') and not main.get_task(task['id'])['materials']
    assert not list((main.DATA_ROOT / task['id']).glob('materials/*'))


def test_original_native_package_summary(client):
    from test_agent_plan import fixture_task
    from app.agent_plan import compile_agent_plan
    task = approved(client); source = compile_agent_plan(fixture_task())[0]
    response = preview(client, task, source); assert response.status_code == 200, response.text
    summary = response.json()['record']['summary']
    assert summary['source']['app_type'] == 'agent' and summary['agent']['package_ref'] == 'agent_1'
    assert '虚构编号' in summary['agent']['system_prompt']['text'] and not summary['nodes']
    assert any('单个文本或已选知识集包' in w and '工具／文件等完整原生包保留尚待适配' in w for w in summary['warnings'])


@pytest.mark.parametrize('change', ['revision', 'latest', 'cross_task'])
def test_stale_and_cross_task_cannot_adopt(client, change):
    task = approved(client); preview(client, task); record = state(client, task)['record']
    if change == 'revision': task = client.patch(f"/api/tasks/{task['id']}", json={'requirements': {'goal': '变更目标'}}).json()
    elif change == 'latest': preview(client, task)
    else: task = approved(client)
    result = client.post(f"/api/tasks/{task['id']}/reference-dsl/adopt", json={'revision': task['revision'], 'preview_id': record['id'], 'preview_token': record['preview_token'], 'reference_mode': 'borrow', 'acknowledge_limits': True})
    assert result.status_code == 409


def test_duplicate_content_and_invalid_mode(client):
    task = approved(client); source = content(task); preview(client, task, source)
    assert adopt(client, task, reference_mode='automatic').status_code == 422
    task = adopt(client, task).json(); preview(client, task, source)
    assert adopt(client, task).status_code == 409 and len(main.get_task(task['id'])['materials']) == 1


def test_excerpt_truncation_declared_and_source_retained(client):
    task = approved(client); root = yaml.safe_load(content(task)); code = next(n for n in root['workflow']['graph']['nodes'] if n['data']['type'] == 'code'); code['data']['code'] = '# note\n' * 1000
    response = preview(client, task, yaml.safe_dump(root)); assert response.status_code == 200
    summary = response.json()['record']['summary']; excerpt = next(d for n in summary['nodes'] if n['id'] == code['id'] for d in n['details'] if d['field'] == 'code')
    assert excerpt['truncated'] and len(excerpt['text']) == 1600
    assert len(material_text({**summary, 'extra': 'x' * 120000})) <= 100000
    assert '片段' in material_text({**summary, 'extra': 'x' * 120000})[:100]


def test_preview_survives_restart_and_busy_block(client):
    task = approved(client); preview(client, task)
    from app.storage import Store
    main.store = Store(main.DATA_ROOT); assert state(client, task)['record']['status'] == 'proposed'
    task['status'] = 'running'; main.save_task(task)
    assert preview(client, task).status_code == 409 and adopt(client, task).status_code == 409


def test_filename_sanitized_and_atomic_adoption(client, monkeypatch):
    task = approved(client); response = preview(client, task, filename='../../../../outside.yaml')
    assert response.json()['record']['summary']['source']['filename'] == 'outside.yaml'
    prior = copy.deepcopy(task); record = state(client, task)['record']
    def fail(records): raise RuntimeError('模拟原子提交失败')
    monkeypatch.setattr(main.store, 'put_many', fail)
    with pytest.raises(RuntimeError): adopt(client, task)
    assert main.get_task(task['id']) == prior
    assert main.store.get('reference_dsl_preview', record['id'])['status'] == 'proposed'


def test_changed_original_rejected(client):
    task = approved(client); preview(client, task); record = main.store.list('reference_dsl_preview')[0]
    record['content'] += '\n# changed\n'; main.store.put('reference_dsl_preview', record['id'], record)
    assert adopt(client, task).status_code == 409 and not main.get_task(task['id'])['materials']


def test_summary_is_in_planning_context_with_limitations(client, monkeypatch):
    from test_task_budget import provider
    task = approved(client); preview(client, task); task = adopt(client, task).json(); provider(client)
    observed = []
    async def model(*args, **kwargs):
        observed.append(json.loads(args[2][1]['content']))
        return json.dumps(plan()), {'prompt_tokens': 100, 'completion_tokens': 100}
    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    materials = observed[0]['reference_materials']
    assert len(materials) == 1 and materials[0]['reference_mode'] == 'borrow'
    assert '没有执行、导入或复现' in materials[0]['excerpt'] and '代码' in materials[0]['excerpt']
    assert 'source' in materials[0]['excerpt'] and 'nodes' in materials[0]['excerpt']


@pytest.mark.parametrize('choice', ['omitted', None, '', 'automatic'])
def test_at04_preview_requires_explicit_choice_without_side_effects(client, choice):
    task = approved(client)
    assert preview(client, task).status_code == 200
    record = state(client, task)['record']
    before = main.get_task(task['id'])
    stored = copy.deepcopy(main.store.get('reference_dsl_preview', record['id']))
    payload = {'revision': task['revision'], 'preview_id': record['id'],
               'preview_token': record['preview_token'], 'acknowledge_limits': True}
    if choice != 'omitted':
        payload['reference_mode'] = choice
    response = client.post(f"/api/tasks/{task['id']}/reference-dsl/adopt", json=payload)
    assert response.status_code == 422, response.text
    if choice in ('', 'automatic'):
        assert '请主动选择借鉴、保留指定部分或严格复现' in response.text
    assert main.get_task(task['id']) == before
    assert main.store.get('reference_dsl_preview', record['id']) == stored
    assert not list((main.DATA_ROOT / task['id']).glob('materials/*'))
    # A rejected attempt must leave the preview usable for a later user choice.
    response = adopt(client, task)
    assert response.status_code == 200, response.text
    assert response.json()['materials'][0]['reference_mode'] == 'borrow'


def test_at04_preserve_requires_specific_items_without_consuming_preview(client):
    task = approved(client)
    assert preview(client, task).status_code == 200
    before = main.get_task(task['id'])
    record = state(client, task)['record']
    for items in ('', ' \n\t '):
        response = adopt(client, task, reference_mode='preserve', preserve_items=items)
        assert response.status_code == 422 and '请明确填写必须保留' in response.text
        assert main.get_task(task['id']) == before
        assert state(client, task)['record'] == record
        assert not list((main.DATA_ROOT / task['id']).glob('materials/*'))


@pytest.mark.parametrize('mode', ['borrow', 'preserve', 'replicate'])
def test_at04_explicit_choices_persist_with_source_and_revision(client, mode, monkeypatch):
    from app.storage import Store
    task = approved(client)
    source = content(task)
    assert preview(client, task, source).status_code == 200
    record = state(client, task)['record']
    items = '保留代码节点的计算规则' if mode == 'preserve' else ''
    response = adopt(client, task, reference_mode=mode, preserve_items=f' {items} ')
    assert response.status_code == 200, response.text
    selected = response.json()
    monkeypatch.setattr(main, 'store', Store(main.DATA_ROOT))
    persisted = client.get(f"/api/tasks/{task['id']}").json()
    assert persisted == selected
    material = persisted['materials'][0]
    adopted = state(client, persisted)['record']
    assert material['reference_mode'] == adopted['reference_mode'] == mode
    assert material['preserve_items'] == adopted['preserve_items'] == items
    assert adopted['id'] == record['id'] and adopted['status'] == 'adopted'
    assert adopted['revision'] == task['revision']
    assert adopted['applied_revision'] == persisted['revision'] == task['revision'] + 1
    assert adopted['acknowledge_limits'] is True
    assert material['sha256'] == record['summary']['source']['sha256']
    assert material['dsl_summary']['verification'] == 'local_structure_only'
    assert (main.DATA_ROOT / task['id'] / 'materials' / (material['id'] + '.yaml')).read_text(encoding='utf-8') == source
    assert persisted['app_type'] == task['app_type'] and persisted['requirements'] == task['requirements']
    assert not persisted['requirements_confirmed'] and not persisted['configuration_confirmed']
    assert not persisted['artifact'] and not persisted['dify_app_id'] and not persisted['runs']
    report = client.get(f"/api/tasks/{task['id']}/report")
    assert report.status_code == 200 and f'"reference_mode": "{mode}"' in report.text
    assert '不是已复现或已运行' in report.text


def test_at04_uploaded_reference_without_choice_is_questioned_and_blocked(client):
    task = approved(client)
    response = client.post(f"/api/tasks/{task['id']}/materials",
                           files={'file': ('参考.yaml', content(task).encode('utf-8'), 'application/yaml')})
    assert response.status_code == 200, response.text
    task = response.json()
    assert task['materials'][0]['status'] == 'parsed'
    assert task['materials'][0]['reference_mode'] is None
    response = client.get(f"/api/tasks/{task['id']}/intake")
    assert response.status_code == 200, response.text
    gaps = [g for g in response.json()['gaps'] if g['topic'] == 'materials']
    assert len(gaps) == 1 and '借鉴、保留指定内容或严格复现' in gaps[0]['question']
    before = main.get_task(task['id'])
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': task['revision'], 'kind': 'requirements'})
    assert response.status_code == 422 and '确认参考方式' in response.text
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422 and '不会自动改为借鉴' in response.text
    assert client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']}).status_code == 422
    assert main.get_task(task['id']) == before
    mid = task['materials'][0]['id']
    for payload in ({}, {'reference_mode': None}, {'reference_mode': ''}, {'reference_mode': 'automatic'},
                    {'reference_mode': 'preserve', 'preserve_items': ' \n '}):
        response = client.patch(f"/api/tasks/{task['id']}/materials/{mid}", json={**payload, 'revision':task['revision']})
        assert response.status_code == 422, response.text
        assert main.get_task(task['id']) == before
    response = client.patch(f"/api/tasks/{task['id']}/materials/{mid}", json={'revision':task['revision'],'reference_mode': 'borrow'})
    assert response.status_code == 200, response.text
    selected = response.json()
    assert selected['materials'][0]['reference_mode'] == 'borrow'
    assert selected['revision'] == task['revision'] + 1
    assert not [g for g in client.get(f"/api/tasks/{task['id']}/intake").json()['gaps'] if g['topic'] == 'materials']
    assert client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': selected['revision'], 'kind': 'requirements'}).status_code == 200


@pytest.mark.parametrize('mode', ['preserve', 'replicate'])
def test_at04_changing_choice_invalidates_approvals_and_never_falls_back(client, mode):
    task = approved(client)
    assert preview(client, task).status_code == 200
    task = adopt(client, task).json()
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': task['revision'], 'kind': kind})
        assert response.status_code == 200, response.text
        task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    assert task['artifact']['verification'] == 'static_only'
    mid = task['materials'][0]['id']
    response = client.patch(f"/api/tasks/{task['id']}/materials/{mid}",
                            json={'revision':task['revision'],'reference_mode': mode, 'preserve_items': '保留代码规则' if mode == 'preserve' else ''})
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed['revision'] == task['revision'] + 1
    assert changed['materials'][0]['reference_mode'] == mode
    assert not changed['requirements_confirmed'] and not changed['configuration_confirmed'] and not changed['artifact']
    assert client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': task['revision'], 'kind': 'requirements'}).status_code == 409
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': changed['revision'], 'kind': kind})
        assert response.status_code == 200, response.text
        changed = response.json()
    before = main.get_task(task['id'])
    for action, message in (('plan/generate', '不会自动改为借鉴'), ('build', '尚未实现指定参考内容保留或严格复现')):
        response = client.post(f"/api/tasks/{task['id']}/{action}", json={'revision': changed['revision']})
        assert response.status_code == 422 and message in response.text
        assert main.get_task(task['id']) == before
    assert not before['dify_app_id'] and not before['runs']
