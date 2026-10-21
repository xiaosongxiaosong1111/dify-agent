import copy
import json
import pytest
from test_api import client, forbid_api_external_calls
from test_replanning_changes import prepared
from app import main
from app.storage import Store
from app.planning_candidate_selection import changes


def setup(client, mode='workflow'):
    task, old = prepared(client)
    if mode == 'agent':
        old = {'schema_version': 1, 'system_prompt': 'original agent prompt', 'mode': 'text', 'model': {'name': 'original-model'}}
        task['agent_plan'] = copy.deepcopy(old); task['workflow_plan'] = None
    task['app_type'] = mode
    candidate = copy.deepcopy(old)
    if mode == 'agent':
        candidate['system_prompt'] = 'new agent prompt'; candidate['model']['name'] = 'unwanted-model'
    else:
        candidate['nodes'][1]['config']['system_prompt'] = 'the only requested prompt'
        candidate['nodes'][0]['config']['variables'][0]['type'] = 'paragraph'
        candidate['nodes'][1]['title'] = 'unwanted title'
    task['status'] = 'paused'; task['planning_runs'].append({'id': 'selection-run', 'revision': task['revision'], 'status': 'paused', 'kind': 'plan', 'last_candidate': candidate, 'attempts': [], 'stop_reason': 'replanning_review'})
    main.store.put('task', task['id'], task)
    return task, old, candidate


def read(client, task): return client.get(f"/api/tasks/{task['id']}/planning/selection-run/candidate-selection", params={'revision': task['revision']})


def compose(client, task, review, selected, **extra):
    return client.post(f"/api/tasks/{task['id']}/planning/selection-run/candidate-selection/compose", json={'revision': task['revision'], 'review_token': review['review_token'], 'selected_ids': selected} | extra)


def snapshot():
    with main.store.connect() as db: return list(db.execute('SELECT * FROM objects')), list(db.execute('SELECT * FROM secrets'))


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat', 'agent'])
def test_only_selected_prompt_composed_without_mutating_anything(client, mode):
    t, old, full = setup(client, mode); before = snapshot()
    r = read(client, t); assert r.status_code == 200, r.text
    review = r.json(); assert review['verification'] == 'explicit_candidate_difference_review' and not review['truncated']
    chosen = next(c for c in review['changes'] if c['path'][-1] == ('system_prompt'))
    assert chosen['before']['text'] != chosen['after']['text'] and chosen['operation'] == 'replace'
    r = compose(client, t, review, [chosen['id']]); assert r.status_code == 200, r.text
    result = r.json(); draft = json.loads(result['plan_text']); expected = copy.deepcopy(old)
    if mode == 'agent': expected['system_prompt'] = full['system_prompt']
    else: expected['nodes'][1]['config']['system_prompt'] = full['nodes'][1]['config']['system_prompt']
    assert draft == expected and draft != full
    assert result['selected_count'] == 1 and result['unselected_count'] >= 1
    assert not result['formal_plan_changed'] and not result['static_validated'] and not result['network_requested'] and not result['business_verified']
    assert result['app_type'] == mode and snapshot() == before
    assert Store(main.store.root).get('task', t['id'])['planning_runs'][-1]['last_candidate'] == full


@pytest.mark.parametrize('change', ['revision', 'baseline', 'candidate', 'requirements', 'config', 'pause_generation', 'run_active', 'run_kind', 'run_revision'])
def test_stale_sources_cannot_reuse_field_selection(client, change):
    t, old, full = setup(client); review = read(client, t).json(); chosen = review['changes'][0]['id']; current = main.store.get('task', t['id'])
    if change == 'revision': current['revision'] += 1
    elif change == 'baseline': current['workflow_plan']['nodes'][1]['title'] = 'edited'
    elif change == 'candidate': current['planning_runs'][-1]['last_candidate']['nodes'][1]['title'] = 'other candidate'
    elif change == 'requirements': current['requirements']['rules'] = 'changed rule'
    elif change == 'config': current['configuration']['temperature'] = 0.9
    elif change == 'pause_generation': current['pause_generation'] = 2
    elif change == 'run_active': current['planning_runs'][-1]['status'] = 'running'
    elif change == 'run_kind': current['planning_runs'][-1]['kind'] = 'repair'
    else: current['planning_runs'][-1]['revision'] -= 1
    main.store.put('task', t['id'], current); before = snapshot()
    r = compose(client, t, review, [chosen]); assert r.status_code in {409, 422}, r.text
    assert snapshot() == before


@pytest.mark.parametrize('bad', ['empty', 'duplicate', 'unknown', 'extra', 'bool_revision', 'bad_token'])
def test_invalid_selection_never_mutates_or_echoes(client, bad):
    t, _, _ = setup(client); review = read(client, t).json(); chosen = review['changes'][0]['id']; selected = [chosen]; extra = {}
    if bad == 'empty': selected = []
    elif bad == 'duplicate': selected = [chosen, chosen]
    elif bad == 'unknown': selected = ['NOT-A-FIELD']
    elif bad == 'extra': extra['secret'] = 'DO-NOT-ECHO'
    elif bad == 'bool_revision': extra['revision'] = True
    else: extra['review_token'] = 'DO-NOT-ECHO'
    before = snapshot(); r = compose(client, t, review, selected, **extra)
    assert r.status_code in {409, 422} and 'DO-NOT-ECHO' not in r.text and snapshot() == before


def test_type_exactness_add_remove_and_lists_are_explicit_groups(client):
    t, old, full = setup(client); current = main.store.get('task', t['id'])
    old = {'nodes': [{'id': 'node', 'config': {'precise': 900719925474099312345, 'flag': True, 'items': [1, 2], 'removed': 'original'}}]}
    full = copy.deepcopy(old); cfg = full['nodes'][0]['config']; cfg.update(precise=900719925474099312346, flag=1, items=[2, 1], added=None); del cfg['removed']
    current['workflow_plan'] = old; current['planning_runs'][-1]['last_candidate'] = full; main.store.put('task', t['id'], current)
    review = read(client, t).json(); assert len(review['changes']) == 5
    precise = next(c for c in review['changes'] if c['path'][-1] == 'precise'); assert '900719925474099312346' in precise['after']['text']
    assert next(c for c in review['changes'] if c['path'][-1] == 'items')['whole_list']
    result = compose(client, t, review, [c['id'] for c in review['changes']]).json()
    assert json.loads(result['plan_text']) == full and '900719925474099312346' in result['plan_text'] and result['unselected_count'] == 0


def test_node_reorder_is_whole_list_never_positional_mix():
    old = {'nodes': [{'id': 'a', 'config': {'x': 1}}, {'id': 'b', 'config': {'x': 2}}]}
    candidate = {'nodes': list(reversed(old['nodes']))}
    rows = changes(old, candidate); assert len(rows) == 1 and rows[0]['path'] == ['nodes'] and rows[0]['whole_list']


@pytest.mark.parametrize('bad', ['too_many', 'credential', 'deep', 'missing_baseline'])
def test_unreadable_or_sensitive_source_stops_without_partial_review(client, bad):
    t, old, full = setup(client); current = main.store.get('task', t['id'])
    if bad == 'too_many':
        current['workflow_plan'] = {'fields': {str(i): 0 for i in range(401)}}
        current['planning_runs'][-1]['last_candidate'] = {'fields': {str(i): 1 for i in range(401)}}
    elif bad == 'credential': current['planning_runs'][-1]['last_candidate']['private_key'] = 'DO-NOT-ECHO'
    elif bad == 'deep':
        value = {}; cursor = value
        for _ in range(65): cursor['nested'] = {}; cursor = cursor['nested']
        current['planning_runs'][-1]['last_candidate'] = value
    else: current['workflow_plan'] = None
    main.store.put('task', t['id'], current); before = snapshot(); r = read(client, t)
    assert r.status_code in {409, 422} and 'DO-NOT-ECHO' not in r.text and snapshot() == before


def test_preview_truncation_does_not_truncate_composed_draft(client):
    t, old, full = setup(client); current = main.store.get('task', t['id']); text = '中' * 2400
    current['planning_runs'][-1]['last_candidate']['nodes'][1]['config']['system_prompt'] = text; main.store.put('task', t['id'], current)
    review = read(client, t).json(); chosen = next(c for c in review['changes'] if c['path'][-1] == 'system_prompt')
    assert chosen['after']['truncated'] and len(chosen['after']['text']) == 1200
    result = compose(client, t, review, [chosen['id']]).json(); assert json.loads(result['plan_text'])['nodes'][1]['config']['system_prompt'] == text
