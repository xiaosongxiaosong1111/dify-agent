import copy
import pytest
import yaml

from test_api import client
from test_dsl_roundtrip import prepared, capture, apply
from test_iteration import batch_plan, task, iteration, llm_body
from app import main
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved, digest, merge


def native(plan=None, **config):
    content, result = compile_workflow_plan(task(plan, **config))
    assert result['valid'], result['errors']
    return yaml.safe_load(content)


def parts(root):
    graph = root['workflow']['graph']
    return graph, {n['id']: n for n in graph['nodes']}


def test_shuffled_native_chain_preserves_all_content_without_execution():
    plan = batch_plan()
    iteration(plan)['nodes'].append({'id': 'format', 'type': 'template-transform', 'config': {'template': '{{ value }}!', 'variables': [{'variable': 'value', 'value_selector': ['clean', 'result'], 'value_type': 'string'}]}})
    iteration(plan)['output_selector'] = ['format', 'output']
    root = native(plan)
    graph, nodes = parts(root)
    nodes['clean']['data']['code'] = 'def main(item: str) -> dict:\n    return {"result": item.lower()}\n'
    nodes['clean']['position']['x'] += 31
    nodes['batch']['data']['desc'] = '手工业务说明'
    graph['nodes'].reverse()
    graph['edges'].reverse()
    before = copy.deepcopy(root)
    checked = validate_preserved(root)
    assert checked['valid'], checked['errors']
    assert root == before and any('尚未执行 Dify 整图' in w for w in checked['warnings'])


def test_multiple_sequential_containers_keep_separate_scopes():
    plan = batch_plan()
    second = copy.deepcopy(plan['nodes'][2])
    second['id'] = 'second'
    cfg = second['config']
    cfg['iterator_selector'] = ['batch', 'output']
    cfg['output_selector'] = ['clean_second', 'result']
    cfg['nodes'][0]['id'] = 'clean_second'
    cfg['nodes'][0]['config']['variables'][0]['value_selector'] = ['second', 'item']
    plan['nodes'].insert(-1, second)
    plan['nodes'][-1]['config']['outputs'][0]['value_selector'] = ['second', 'output']
    plan['edges'][-1]['target'] = 'second'
    plan['edges'].append({'source': 'second', 'target': 'end'})
    assert validate_preserved(native(plan))['valid']


def test_chatflow_container_keeps_answer_terminal():
    value = task()
    value['app_type'] = 'advanced-chat'
    value['workflow_plan']['nodes'][0]['config']['variables'] = []
    value['workflow_plan']['nodes'][1]['config']['variables'][0]['value_selector'] = ['sys', 'query']
    value['workflow_plan']['nodes'][-1] = {'id': 'end', 'type': 'answer', 'config': {'answer': '{{#batch.output#}}'}}
    text, checked = compile_workflow_plan(value)
    assert checked['valid'], checked['errors']
    assert validate_preserved(yaml.safe_load(text))['valid']


def test_llm_model_and_prompt_are_retained_in_body():
    plan = batch_plan()
    llm_body(plan)
    root = native(plan, dify_model_provider='actual/provider', dify_model='actual-model', temperature=.2, max_tokens=256)
    _, nodes = parts(root)
    nodes['item_llm']['data']['prompt_template'][0]['text'] = '人工规则 {{#batch.item#}}'
    before = copy.deepcopy(root)
    assert validate_preserved(root)['valid'] and root == before
    nodes['item_llm']['data']['model']['completion_params']['temperature'] = 9
    assert not validate_preserved(root)['valid']


@pytest.mark.parametrize('change', [
    'parallel', 'parallel_count', 'failure_continue', 'flatten', 'missing_start',
    'orphan_start', 'unknown_parent', 'nested', 'scope_mismatch', 'missing_scope',
    'cross_edge', 'extra_edge', 'edge_handle', 'edge_scope', 'outer_scope',
    'no_edge', 'unknown_edge', 'body_branch', 'body_memory', 'duplicate_id',
    'body_bad_ref', 'leaked_item', 'wrong_output_type', 'bad_syntax', 'general_loop',
])
def test_unsupported_native_scope_is_rejected_and_original_unchanged(change):
    root = native()
    graph, nodes = parts(root)
    parent, child = nodes['batch']['data'], nodes['clean']
    inner = next(e for e in graph['edges'] if e['source'] == 'batch__iteration_start')
    if change == 'parallel': parent.update(is_parallel=True, parallel_nums=2)
    elif change == 'parallel_count': parent['parallel_nums'] = 5
    elif change == 'failure_continue': parent['error_handle_mode'] = 'continue-on-error'
    elif change == 'flatten': parent['flatten_output'] = True
    elif change == 'missing_start': parent['start_node_id'] = 'ghost'
    elif change == 'orphan_start': nodes['batch__iteration_start'].pop('parentId')
    elif change == 'unknown_parent': child['parentId'] = 'ghost'
    elif change == 'nested': child['data']['type'] = 'iteration'
    elif change == 'scope_mismatch': child['data']['iteration_id'] = 'ghost'
    elif change == 'missing_scope': child['data'].pop('isInIteration')
    elif change == 'cross_edge': inner['target'] = 'end'
    elif change == 'extra_edge': graph['edges'].append(copy.deepcopy(inner))
    elif change == 'edge_handle': inner['sourceHandle'] = 'false'
    elif change == 'edge_scope': inner['data']['iteration_id'] = 'ghost'
    elif change == 'outer_scope': graph['edges'][0].setdefault('data', {})['iteration_id'] = 'batch'
    elif change == 'no_edge': graph['edges'].remove(inner)
    elif change == 'unknown_edge': inner['target'] = 'ghost'
    elif change == 'body_branch': child['data']['type'] = 'if-else'
    elif change == 'body_memory': child['data']['memory'] = {'window': {'enabled': True, 'size': 3}}
    elif change == 'duplicate_id': graph['nodes'].append(copy.deepcopy(child))
    elif change == 'body_bad_ref': child['data']['variables'][0]['value_selector'] = ['end', 'results']
    elif change == 'leaked_item': nodes['end']['data']['outputs'][0]['value_selector'] = ['batch', 'item']
    elif change == 'wrong_output_type': parent['output_type'] = 'array[number]'
    elif change == 'bad_syntax': child['data']['code'] = 'def main(:'
    else: child['data']['isInLoop'] = True
    before = copy.deepcopy(root)
    checked = validate_preserved(root)
    assert not checked['valid'] and checked['errors'] and root == before


def test_disconnected_cycle_is_not_silently_omitted():
    root = native()
    graph, nodes = parts(root)
    for nid in ('extra_a', 'extra_b'):
        extra = copy.deepcopy(nodes['clean'])
        extra['id'] = nid
        graph['nodes'].append(extra)
    graph['edges'].extend([{'source': 'extra_a', 'target': 'extra_b'}, {'source': 'extra_b', 'target': 'extra_a'}])
    assert not validate_preserved(root)['valid']


def test_manual_body_conflict_requires_explicit_choice():
    base = native()
    current, generated = copy.deepcopy(base), copy.deepcopy(base)
    parts(current)[1]['clean']['data']['code'] += '\n# 人工修改\n'
    parts(generated)[1]['clean']['data']['code'] += '\n# 新生成修改\n'
    result = merge(base, current, generated)
    assert result['unresolved'] == 1
    path = result['conflicts'][0]['path']
    assert path.endswith('/@clean/data/code')
    for choice, source in [('current', current), ('generated', generated)]:
        accepted = merge(base, current, generated, {path: choice})
        assert not accepted['unresolved'] and accepted['root'] == source
        assert validate_preserved(accepted['root'])['valid']


def test_capture_confirm_and_rebuild_keep_manual_body_without_dify_writes(client):
    old, _ = prepared(client)
    response = client.post(f"/api/tasks/{old['id']}/plan", json={'revision': old['revision'], 'plan': batch_plan()})
    assert response.status_code == 200, response.text
    t = response.json()
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{t['id']}/confirm", json={'revision': t['revision'], 'kind': kind})
        assert response.status_code == 200, response.text
        t = response.json()
    t = client.post(f"/api/tasks/{t['id']}/build", json={'revision': t['revision']}).json()
    root = yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'))
    _, nodes = parts(root)
    nodes['clean']['data']['code'] += '\n# 人工保留规则\n'
    nodes['clean']['position']['x'] += 19
    t = capture(client, t, root)
    response, preview = apply(client, t)
    assert response.status_code == 200, (response.text, preview['validation'])
    t = response.json()
    assert not t['requirements_confirmed'] and not t['configuration_confirmed']
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{t['id']}/confirm", json={'revision': t['revision'], 'kind': kind})
        assert response.status_code == 200, response.text
        t = response.json()
    response = client.post(f"/api/tasks/{t['id']}/build", json={'revision': t['revision']})
    assert response.status_code == 200, response.text
    built = response.json()
    final = yaml.safe_load(main.artifact_path(built).read_text(encoding='utf-8'))
    assert digest(final) == digest(root) and not built['dify_app_id']
