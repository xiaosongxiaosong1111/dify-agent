"""Material-level reference preservation through the normal plan/confirm/build APIs."""
import copy
import json

import httpx
import pytest
import yaml

from test_api import client, approved, create
from test_material_parsing import upload
from test_planning import plan
from test_task_budget import provider
from app import main
from app.workflow_plan import compile_workflow_plan


@pytest.fixture(autouse=True)
def forbid_reference_preservation_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('参考保留隔离检查不得访问真实 HTTP 或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main.DifyClient, 'request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def source_text(task, mutate=None):
    source = copy.deepcopy(task); source['workflow_plan'] = plan()
    text = compile_workflow_plan(source)[0]
    if mutate is not None:
        root = yaml.safe_load(text); mutate(root)
        text = yaml.safe_dump(root, allow_unicode=True, sort_keys=False)
    return text


def preview(client, task, mutate=None):
    text = source_text(task, mutate)
    response = client.post(f"/api/tasks/{task['id']}/reference-dsl/preview",
                           json={'revision': task['revision'], 'content': text, 'filename': '参考流程.yaml'})
    return response, text


def adopt(client, task, mode, ids=None, items='', mutate=None):
    response, text = preview(client, task, mutate)
    assert response.status_code == 200, response.text
    record = response.json()['record']
    body = {'revision': task['revision'], 'preview_id': record['id'], 'preview_token': record['preview_token'],
            'reference_mode': mode, 'acknowledge_limits': True}
    if items: body['preserve_items'] = items
    if ids is not None: body['preserve_node_ids'] = ids
    return client.post(f"/api/tasks/{task['id']}/reference-dsl/adopt", json=body), text


def save_plan(client, task, value=None):
    response = client.post(f"/api/tasks/{task['id']}/plan",
                           json={'revision': task['revision'], 'plan': value if value is not None else plan()})
    assert response.status_code == 200, response.text
    return response.json()


def confirm_both(client, task):
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': kind, 'revision': task['revision']})
        assert response.status_code == 200, response.text
        task = response.json()
    return task


def preserve_task(client, plan_after=None, mutate=None):
    task = approved(client)
    response, text = adopt(client, task, 'preserve', ids=['code'], items='保留代码节点规则', mutate=mutate)
    assert response.status_code == 200, response.text
    return save_plan(client, response.json(), plan_after), text


def strict_task(client, mutate=None):
    task = approved(client)
    response, text = adopt(client, task, 'replicate', mutate=mutate)
    assert response.status_code == 200, response.text
    return save_plan(client, response.json()), text


def test_preserve_keeps_selected_code_while_other_node_changes(client):
    changed = plan(); changed['nodes'][2]['title'] = '结束-业务改名'
    task, text = preserve_task(client, plan_after=changed)
    task = confirm_both(client, task)
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    report = task['artifact']['validation']['reference_preservation']
    assert report['verification'] == 'local_static_only'
    assert report['business_verified'] is False and report['platform_verified'] is False
    assert report['materials'][0]['mode'] == 'preserve' and report['materials'][0]['node_ids'] == ['code']
    assert report['materials'][0]['complete_node_config'] is True and report['materials'][0]['connections_locked'] is False
    assert task['workflow_plan']['nodes'][1]['config'] == plan()['nodes'][1]['config']
    material = task['materials'][0]
    assert (main.DATA_ROOT / task['id'] / 'materials' / (material['id'] + '.yaml')).read_text(encoding='utf-8') == text
    assert any(version.get('materials') and version['materials'][0].get('preserve_node_ids') == ['code'] for version in task['versions'])


def test_preserve_selected_code_change_refused_at_confirm_and_build(client):
    changed = plan(code="def main(query):\n    return {'result': 'changed'}\n")
    task, _ = preserve_task(client, plan_after=changed)
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'requirements', 'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    before = main.get_task(task['id'])
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'configuration', 'revision': task['revision']})
    assert response.status_code == 422 and '选中节点' in response.text
    assert main.get_task(task['id']) == before
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 422
    after = main.get_task(task['id'])
    assert after['artifact'] is None and after == before


def test_replicate_equal_core_builds_with_static_report(client):
    task, text = strict_task(client)
    task = confirm_both(client, task)
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    report = task['artifact']['validation']['reference_preservation']
    material = report['materials'][0]
    assert material['mode'] == 'replicate' and material['verification'] == 'local_static_core_equal'
    assert material['source_core_sha256'] == material['candidate_core_sha256']
    assert report['business_verified'] is False and report['platform_verified'] is False


def _change_code(root):
    next(node for node in root['workflow']['graph']['nodes'] if node['data']['type'] == 'code')['data']['code'] = '# changed\n'


def _change_edges(root):
    root['workflow']['graph']['edges'] = [edge for edge in root['workflow']['graph']['edges'] if edge['target'] != 'code']


def _change_features(root):
    root['workflow']['features'] = {'business_note': {'enabled': True}}


@pytest.mark.parametrize('mutate', [_change_code, _change_edges, _change_features], ids=['node', 'edges', 'features'])
def test_replicate_mismatch_refused_without_artifact(client, mutate):
    task, _ = strict_task(client, mutate=mutate)
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'requirements', 'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    before = main.get_task(task['id'])
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'configuration', 'revision': task['revision']})
    assert response.status_code == 422 and '不一致' in response.text
    assert main.get_task(task['id']) == before
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 422 and main.get_task(task['id'])['artifact'] is None


def test_policy_requires_complete_explicit_plan(client):
    task = approved(client)
    response, _ = adopt(client, task, 'replicate')
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'requirements', 'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'configuration', 'revision': task['revision']})
    assert response.status_code == 422 and '完整显式流程计划' in response.text
    assert not main.get_task(task['id'])['configuration_confirmed']
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 422 and main.get_task(task['id'])['artifact'] is None


def test_preserve_free_text_without_nodes_saves_but_cannot_plan_or_build(client):
    task = approved(client)
    task, material = upload(client, task, '公开说明.txt', b'public rule text')
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'preserve', 'preserve_items': '保留公开术语'})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422 and '普通文字材料' in response.text
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'requirements', 'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'configuration', 'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 422 and '普通文字材料' in response.text
    current = main.get_task(task['id'])
    assert current['materials'][0]['reference_mode'] == 'preserve' and current['artifact'] is None


def test_unselected_material_blocks_before_provider_or_key(client, monkeypatch):
    task = approved(client)
    task, material = upload(client, task, '公开说明.txt', b'public rule text')
    assert task['materials'][0]['reference_mode'] is None

    def forbidden(*args, **kwargs):
        pytest.fail('未明确选择参考方式时不得读取模型配置或密钥')

    monkeypatch.setattr(main, 'main_provider', forbidden)
    monkeypatch.setattr(main.store, 'secret', forbidden)
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422 and '不会自动改为借鉴' in response.text
    current = main.get_task(task['id'])
    assert current == before and not current['planning_runs']
    assert current['materials'][0]['reference_mode'] is None


@pytest.mark.parametrize('ids', [['code', 'code'], ['missing'], ['end'], [1]])
def test_invalid_patch_selection_does_not_change_task(client, ids):
    task = approved(client)
    response, _ = adopt(client, task, 'borrow')
    assert response.status_code == 200, response.text
    task = response.json(); material = task['materials'][0]
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'preserve',
                                  'preserve_items': '保留代码节点规则', 'preserve_node_ids': ids})
    assert response.status_code == 422, response.text
    assert main.get_task(task['id']) == before


def test_non_preserve_cannot_carry_selection_and_leaving_preserve_clears(client):
    task = approved(client)
    response, _ = adopt(client, task, 'borrow')
    assert response.status_code == 200, response.text
    task = response.json(); material = task['materials'][0]
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'borrow', 'preserve_node_ids': ['code']})
    assert response.status_code == 422 and main.get_task(task['id']) == before
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'preserve',
                                  'preserve_items': '保留代码节点规则', 'preserve_node_ids': ['code']})
    assert response.status_code == 200, response.text
    task = response.json()
    assert task['materials'][0]['preserve_node_ids'] == ['code']
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'preserve', 'preserve_items': '保留代码节点规则'})
    assert response.status_code == 200 and response.json()['materials'][0]['preserve_node_ids'] == ['code']
    task = response.json()
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'preserve',
                                  'preserve_items': '保留代码节点规则', 'preserve_node_ids': []})
    assert response.status_code == 200 and response.json()['materials'][0]['preserve_node_ids'] == []
    task = response.json()
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'preserve',
                                  'preserve_items': '保留代码节点规则', 'preserve_node_ids': ['code']})
    task = response.json()
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'borrow'})
    assert response.status_code == 200 and response.json()['materials'][0]['preserve_node_ids'] == []


def test_adopt_validates_selection_before_consuming_preview(client):
    task = approved(client)
    response, _ = preview(client, task)
    assert response.status_code == 200, response.text
    record = response.json()['record']

    def attempt(**patch):
        body = {'revision': task['revision'], 'preview_id': record['id'], 'preview_token': record['preview_token'],
                'acknowledge_limits': True, **patch}
        return client.post(f"/api/tasks/{task['id']}/reference-dsl/adopt", json=body)

    before = copy.deepcopy(main.get_task(task['id']))
    for body in ({'reference_mode': 'borrow', 'preserve_node_ids': ['code']},
                 {'reference_mode': 'preserve', 'preserve_items': '保留规则', 'preserve_node_ids': ['end']},
                 {'reference_mode': 'preserve', 'preserve_items': '保留规则', 'preserve_node_ids': ['code', 'code']},
                 {'reference_mode': 'preserve', 'preserve_items': '保留规则', 'preserve_node_ids': [1]}):
        response = attempt(**body)
        assert response.status_code == 422, response.text
        assert main.get_task(task['id']) == before
    response = attempt(reference_mode='preserve', preserve_items='保留代码节点规则', preserve_node_ids=['code'])
    assert response.status_code == 200, response.text
    task = response.json()
    assert task['materials'][0]['preserve_node_ids'] == ['code']
    adopted = client.get(f"/api/tasks/{task['id']}/reference-dsl").json()['record']
    assert adopted['preserve_node_ids'] == ['code']


def test_changed_source_bytes_block_planning_before_provider(client):
    task, _ = preserve_task(client)
    material = task['materials'][0]
    path = main.DATA_ROOT / task['id'] / 'materials' / (material['id'] + '.yaml')
    path.write_bytes(path.read_bytes() + b'\n')
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 409 and '原文件' in response.text
    assert main.get_task(task['id']) == before and not before['planning_runs']


def test_planning_receives_complete_policy_context(client, monkeypatch):
    task, _ = preserve_task(client)
    provider(client)
    observed = []

    async def model(*args, **kwargs):
        observed.append((args[2][0]['content'], json.loads(args[2][1]['content'])))
        return json.dumps(plan()), {'prompt_tokens': 100, 'completion_tokens': 100}

    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    system, context = observed[0]
    assert 'reference_preservation' in system
    policy = context['reference_preservation']
    assert policy['verification'] == 'local_static_policy_only'
    entry = policy['materials'][0]
    assert entry['mode'] == 'preserve' and entry['node_ids'] == ['code']
    assert entry['source_sha256'] == task['materials'][0]['sha256']
    assert entry['selected_nodes'][0]['config']['code'] == plan()['nodes'][1]['config']['code']
    assert response.json()['workflow_plan'] == plan()


def test_unsatisfied_candidate_is_not_saved(client, monkeypatch):
    task, _ = preserve_task(client)
    provider(client)
    changed = plan(code="def main(query):\n    return {'result': 'changed'}\n")

    async def model(*args, **kwargs):
        return json.dumps(changed), {'prompt_tokens': 100, 'completion_tokens': 100}

    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422
    current = main.get_task(task['id'])
    assert current['workflow_plan'] == plan()
    assert not any(run.get('status') == 'succeeded' for run in current['planning_runs'])


def test_agent_material_policy_stays_limited(client):
    task = create(client, app_type='agent')
    task = client.patch(f"/api/tasks/{task['id']}",
                        json={'requirements': {k: '明确的测试规则' for k in main.REQ_KEYS}}).json()
    task, material = upload(client, task, '公开说明.txt', b'public rule text')
    response = client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",
                            json={'revision': task['revision'], 'reference_mode': 'preserve', 'preserve_items': '保留公开术语'})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 422 and '仅适配 Workflow／Chatflow' in response.text


def test_replicate_container_source_stays_limited(client):
    def add_container(root):
        graph = root['workflow']['graph']
        graph['nodes'].append({'id': 'iter', 'data': {'type': 'iteration', 'title': '迭代'}})
        graph['nodes'].append({'id': 'inner', 'parentId': 'iter', 'data': {'type': 'code', 'title': '内部'}})

    task, _ = strict_task(client, mutate=add_container)
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'requirements', 'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'configuration', 'revision': task['revision']})
    assert response.status_code == 422 and '容器' in response.text


def test_batch_change_clears_node_selection_and_asks_to_reselect(client):
    task = approved(client)
    response, _ = adopt(client, task, 'preserve', ids=['code'], items='保留代码节点规则')
    assert response.status_code == 200, response.text
    task = response.json(); material = task['materials'][0]
    payload = {'revision': task['revision'], 'items': [{'id': material['id'], 'source_sha256': material['sha256'],
                                                        'reference_mode': 'preserve', 'preserve_items': '新的保留说明'}]}
    value = client.post(f"/api/tasks/{task['id']}/materials/reference-batch/preview", json=payload)
    assert value.status_code == 200, value.text
    applied = client.post(f"/api/tasks/{task['id']}/materials/reference-batch/apply",
                          json={**payload, 'review_token': value.json()['review_token'], 'acknowledge': True})
    assert applied.status_code == 200, applied.text
    saved = applied.json()
    assert saved['materials'][0]['preserve_node_ids'] == []
    assert saved['materials'][0]['preserve_items'] == '新的保留说明'
    assert any('重新选择' in message.get('content', '') for message in saved['messages'])
