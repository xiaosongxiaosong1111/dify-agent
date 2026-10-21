import copy
import json
import pytest
from test_api import client, forbid_api_external_calls
from test_planning_candidate_selection import setup, snapshot
from app import main
from app.candidate_text_mapping import fields, transfer


def read(client, task): return client.get(f"/api/tasks/{task['id']}/planning/selection-run/candidate-text-mapping", params={'revision': task['revision']})


def compose(client, task, review, src, dst, **extra):
    return client.post(f"/api/tasks/{task['id']}/planning/selection-run/candidate-text-mapping/compose", json={'revision': task['revision'], 'review_token': review['review_token'], 'source_id': src['id'], 'target_id': dst['id'], 'confirm_transfer': True} | extra)


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat', 'agent'])
def test_explicit_same_field_transfer_across_renamed_nodes_changes_only_target(client, mode):
    t, baseline, full = setup(client, mode)
    if mode != 'agent':
        full['nodes'][1]['id'] = 'renamed-candidate-node'; full['nodes'].reverse()
        current = main.store.get('task', t['id']); current['planning_runs'][-1]['last_candidate'] = full; main.store.put('task', t['id'], current)
    before = snapshot(); r = read(client, t); assert r.status_code == 200, r.text
    review = r.json(); src = next(v for v in review['sources'] if v['field'] == 'system_prompt'); dst = next(v for v in review['targets'] if v['field'] == 'system_prompt')
    if mode != 'agent': assert src['node_id'] != dst['node_id']
    r = compose(client, t, review, src, dst); assert r.status_code == 200, r.text
    result = r.json(); expected = copy.deepcopy(baseline)
    if mode == 'agent': expected['system_prompt'] = src['value_text']
    else: expected['nodes'][1]['config']['system_prompt'] = src['value_text']
    assert json.loads(result['plan_text']) == expected and result['changed_fields'] == 1 and not result['static_validated'] and not result['formal_plan_changed']
    assert snapshot() == before and result['app_type'] == mode


@pytest.mark.parametrize('bad', ['ack', 'unknown_source', 'unknown_target', 'stale', 'wrong_field', 'extra'])
def test_invalid_or_stale_pair_cannot_compose(client, bad):
    t, _, _ = setup(client); review = read(client, t).json(); src = next(v for v in review['sources'] if v['field'] == 'system_prompt'); dst = next(v for v in review['targets'] if v['field'] == 'system_prompt'); extra = {}
    if bad == 'ack': extra['confirm_transfer'] = False
    elif bad == 'unknown_source': extra['source_id'] = '0' * 64
    elif bad == 'unknown_target': extra['target_id'] = '0' * 64
    elif bad == 'stale':
        task = main.store.get('task', t['id']); task['workflow_plan']['nodes'][1]['config']['system_prompt'] = 'changed'; main.store.put('task', t['id'], task)
    elif bad == 'wrong_field': dst = next(v for v in review['targets'] if v['field'] == 'user_prompt')
    else: extra['password'] = 'DO-NOT-ECHO'
    before = snapshot(); r = compose(client, t, review, src, dst, **extra)
    assert r.status_code in {409, 422} and 'DO-NOT-ECHO' not in r.text and snapshot() == before


@pytest.mark.parametrize('after', ['new {{ variable }}', '{% if new %}new{% endif %}', '{# changed comment #}new', '{{ incomplete', 'unmatched }}'])
def test_new_references_or_template_statements_are_rejected(after):
    before = {'nodes': [{'id': 'old', 'type': 'template-transform', 'config': {'template': 'original plain text'}}]}
    candidate = {'nodes': [{'id': 'new', 'type': 'template-transform', 'config': {'template': after}}]}
    with pytest.raises(Exception, match='占位符|模板语句'): transfer(before, fields(candidate, 'workflow')[0], fields(before, 'workflow')[0])
    assert before['nodes'][0]['config']['template'] == 'original plain text'


def test_template_constant_transfer_preserves_graph_parameters_and_precision():
    old = {'nodes': [{'id': 'answer_miss', 'type': 'template-transform', 'config': {'template': 'original answer', 'variables': []}}, {'id': 'other', 'type': 'code', 'config': {'code': 'keep all code'}}], 'edges': [{'source': 'answer_miss', 'target': 'other'}], 'number': 900719925474099312345}
    new = {'nodes': [{'id': 'no_hit', 'type': 'template-transform', 'config': {'template': 'new answer', 'variables': [{'unwanted': True}]}}]}
    result = transfer(old, fields(new, 'workflow')[0], fields(old, 'workflow')[0]); expected = copy.deepcopy(old); expected['nodes'][0]['config']['template'] = 'new answer'
    assert result == expected and fields(old, 'workflow')[0]['node_id'] == 'answer_miss'


def test_ambiguous_nodes_and_code_never_become_transfer_sources():
    plan = {'nodes': [{'id': 'code', 'type': 'code', 'config': {'code': 'never execute this'}}]}
    assert fields(plan, 'workflow') == []
    plan['nodes'] += [{'id': 'same', 'type': 'llm', 'config': {'system_prompt': 'a'}}, {'id': 'same', 'type': 'llm', 'config': {'system_prompt': 'b'}}]
    with pytest.raises(Exception, match='重复'): fields(plan, 'workflow')


def test_malformed_node_type_is_rejected_as_input_limit():
    with pytest.raises(Exception, match='类型不明确'):
        fields({'nodes': [{'id': 'node', 'type': [], 'config': {'template': 'text'}}]}, 'workflow')
