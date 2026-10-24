"""A manual copy may be previewed; a failed model candidate remains failed."""
import copy
import hashlib
import json

import pytest
from fastapi import HTTPException

from test_api import client, approved, forbid_api_external_calls
from app import main
from app.retained_boolean_preview import preview
from test_planning_format_diagnostics import boolean_plan
from test_workflow_plan import task as compiler_task, base_plan


def source(value='true'):
    task = compiler_task()
    task.update(id='public-task', revision=3, app_type='workflow', planning_runs=[{
        'id': 'public-run', 'kind': 'plan', 'status': 'paused', 'revision': 3,
        'stop_reason': 'invalid_plan_format', 'last_candidate': boolean_plan(value)}])
    return task


@pytest.mark.parametrize('literal', ['true', 'false'])
def test_exact_one_field_copy_is_valid_without_mutating_original(literal):
    task = source(literal); before = copy.deepcopy(task)
    value = preview(task, 'public-run'); corrected = json.loads(value['plan_text'])
    path = value['change']['path']; row = corrected
    for part in path[:-1]: row = row[part]
    assert row[path[-1]] is (literal == 'true')
    row[path[-1]] = literal
    assert corrected == before['planning_runs'][0]['last_candidate'] and task == before
    assert value['change']['before'] == literal and value['static_validated']
    assert value['source_sha256'] == hashlib.sha256(value['plan_text'].encode()).hexdigest()
    assert value['byte_count'] == len(value['plan_text'].encode())
    assert not any(value[k] for k in ('formal_plan_changed', 'network_requested', 'platform_checked', 'business_verified'))


@pytest.mark.parametrize('mode', ['multiple', 'mixed', 'unknown', 'already_boolean', 'unknown_selector', 'wrong_var_type', 'bad_operator', 'nested_only'])
def test_ambiguous_or_other_graph_errors_are_refused(mode):
    task = source(); plan = task['planning_runs'][0]['last_candidate']
    row = plan['nodes'][-1]['config']['cases'][0]['conditions'][0]
    if mode == 'multiple': plan['nodes'][-1]['config']['cases'][0]['conditions'].append(copy.deepcopy(row))
    elif mode == 'mixed': plan['edges'] = [e for e in plan['edges'] if e.get('source_handle') != 'false']
    elif mode == 'unknown': row['value'] = 'yes'
    elif mode == 'already_boolean': row['value'] = True
    elif mode == 'unknown_selector': row['variable_selector'] = ['start', 'not_known']
    elif mode == 'wrong_var_type': row['varType'] = 'string'
    elif mode == 'bad_operator': row['comparison_operator'] = {}
    elif mode == 'nested_only': plan['nodes'][-1]['type'] = 'loop'
    before = copy.deepcopy(task)
    with pytest.raises(HTTPException) as caught: preview(task, 'public-run')
    assert caught.value.status_code == 422 and task == before


@pytest.mark.parametrize('mode', ['history', 'active', 'agent', 'other_kind', 'secret'])
def test_existing_candidate_guards_still_apply(mode):
    task = source(); run = task['planning_runs'][0]
    if mode == 'history': task['revision'] += 1
    elif mode == 'active': run['status'] = 'running'
    elif mode == 'agent': task['app_type'] = 'agent'
    elif mode == 'other_kind': run['kind'] = 'repair'
    elif mode == 'secret': run['last_candidate']['private'] = 'sk-' + 'Z' * 32
    with pytest.raises(HTTPException): preview(task, 'public-run')


def test_chatflow_keeps_its_entry_and_answer_node():
    task = source(); task['app_type'] = 'advanced-chat'
    plan = task['planning_runs'][0]['last_candidate']
    chat = base_plan('advanced-chat')
    plan['nodes'][0] = chat['nodes'][0]
    plan['nodes'][0]['config']['variables'].append({'variable': 'flag', 'type': 'checkbox', 'required': True})
    plan['nodes'][1:3] = chat['nodes'][1:3]
    plan['edges'][-1]['target'] = 'answer'
    value = preview(task, 'public-run')
    assert value['app_type'] == 'advanced-chat'
    corrected = json.loads(value['plan_text'])
    assert corrected['nodes'][2] == chat['nodes'][2]


def seed(client):
    task = approved(client)
    task['planning_runs'] = source()['planning_runs']
    task['planning_runs'][0]['revision'] = task['revision']
    task['workflow_plan'] = base_plan()
    main.store.put('task', task['id'], task)
    return task, f"/api/tasks/{task['id']}/planning/public-run/boolean-format-preview"


def test_read_and_compose_are_read_only_and_never_call_model_or_dify(client, monkeypatch):
    task, url = seed(client)
    before = main.store.get('task', task['id'])
    def forbidden(*a, **kw): raise AssertionError('预览不得写存储')
    monkeypatch.setattr(main.store, 'put', forbidden)
    response = client.get(url, params={'revision': task['revision']})
    assert response.status_code == 200, response.text
    value = response.json()
    response = client.post(url + '/compose', json={'revision': task['revision'], 'review_token': value['review_token']})
    assert response.status_code == 200 and response.json() == value
    assert main.store.get('task', task['id']) == before


@pytest.mark.parametrize('change', ['candidate', 'requirements', 'configuration', 'formal_plan', 'revision', 'active'])
def test_stale_review_cannot_compose(client, change):
    task, url = seed(client)
    value = client.get(url, params={'revision': task['revision']}).json()
    updated = copy.deepcopy(task)
    if change == 'candidate': updated['planning_runs'][0]['last_candidate']['nodes'][0]['title'] = '变更'
    elif change == 'requirements': updated['requirements']['goal'] = '新的需求'
    elif change == 'configuration': updated['configuration']['dify_model'] = 'different'
    elif change == 'formal_plan': updated['workflow_plan']['nodes'][0]['title'] = '另一个方案'
    elif change == 'revision': updated['revision'] += 1
    elif change == 'active': updated['status'] = 'running'
    main.store.put('task', updated['id'], updated)
    response = client.post(url + '/compose', json={'revision': task['revision'], 'review_token': value['review_token']})
    assert response.status_code == 409
    assert main.store.get('task', updated['id']) == updated


def test_explicit_manual_save_uses_existing_confirmation_invalidation(client):
    task, url = seed(client)
    value = client.get(url, params={'revision': task['revision']}).json()
    api = '/api/tasks/' + task['id']
    original = task['planning_runs'][0]['last_candidate']
    assert client.post(api + '/plan', json={'revision': task['revision'], 'plan': original}).status_code == 422
    response = client.post(api + '/plan', json={'revision': task['revision'], 'plan': json.loads(value['plan_text'])})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['plan_source'] == 'manual' and not saved['configuration_confirmed']
    assert saved['planning_runs'][0]['last_candidate'] == original
    assert saved['planning_runs'][0]['stop_reason'] == 'invalid_plan_format'


@pytest.mark.parametrize('extra', [{'revision': True}, {'review_token': 'wrong'}, {'acknowledge': True}])
def test_compose_rejects_coercion_or_extra_fields(client, extra):
    task, url = seed(client)
    value = client.get(url, params={'revision': task['revision']}).json()
    payload = {'revision': task['revision'], 'review_token': value['review_token']} | extra
    assert client.post(url + '/compose', json=payload).status_code == 422
