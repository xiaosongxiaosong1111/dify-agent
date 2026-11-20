"""Independent node-model warnings for current and pre-upgrade configuration proposals."""
import copy
import json

import pytest
import yaml

from test_configuration_proposals import (
    client, prepared, candidate, provider, forbid_configuration_external_calls,
)
from test_question_classifier import plan as classifier_plan
from test_parameter_extractor import plan as extractor_plan
from test_node_models import plan as llm_plan
from app import main
from app.workflow_plan import compile_workflow_plan

INDEPENDENT = {'provider': 'independent/provider', 'name': 'independent-model', 'mode': 'chat',
               'completion_params': {'temperature': 0, 'max_tokens': 256}}
PREFIX = '本配置方案只调整任务默认模型'


def classifier_independent():
    graph = classifier_plan('workflow')
    graph['nodes'][1]['config']['model'] = copy.deepcopy(INDEPENDENT)
    return graph


def classifier_inherited():
    return classifier_plan('workflow')


def extractor_independent():
    graph = extractor_plan('workflow')
    graph['nodes'][1]['config']['model'] = copy.deepcopy(INDEPENDENT)
    return graph


def extractor_inherited():
    return extractor_plan('workflow')


def llm_independent():
    return llm_plan()


def llm_mixed():
    graph = llm_plan()
    graph['nodes'][2]['config'].pop('model')
    return graph


def task_with_plan(client, monkeypatch, graph, configuration=None):
    task = prepared(client, monkeypatch)
    p = provider(client)
    response = client.patch(f"/api/tasks/{task['id']}", json={
        'configuration': {'assistant_provider_id': p['id'], **(configuration or {})}})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/plan",
                           json={'revision': task['revision'], 'plan': graph})
    assert response.status_code == 200, response.text
    return response.json()


def propose(client, monkeypatch, task, **patch):
    value = candidate(**(patch or {'temperature': .3}))

    async def model(*args, **kwargs):
        return json.dumps(value), {'prompt_tokens': 10, 'completion_tokens': 20}

    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f"/api/tasks/{task['id']}/configuration-proposal/generate",
                           json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    return client.get(f"/api/tasks/{task['id']}/configuration-proposal").json()


def independent_ids(state):
    row = next((text for text in state['record']['resource_warnings'] if text.startswith(PREFIX)), None)
    return set(row.split('：')[-1].split('、')) if row else set()


def adopt(client, task, state, acknowledge_unverified=False):
    record = state['record']
    return client.post(f"/api/tasks/{task['id']}/configuration-proposal/adopt", json={
        'revision': task['revision'], 'proposal_id': record['id'],
        'proposal_token': record['proposal_token'], 'acknowledge_changes': True,
        'acknowledge_unverified_resources': acknowledge_unverified})


def compiled_models(task):
    content, _ = compile_workflow_plan(task)
    document = yaml.safe_load(content)
    return {node['id']: node['data'].get('model') for node in document['workflow']['graph']['nodes']}


@pytest.mark.parametrize('builder,expected,excluded', [
    (classifier_independent, {'route'}, set()),
    (classifier_inherited, set(), {'route'}),
    (extractor_independent, {'extract'}, set()),
    (extractor_inherited, set(), {'extract'}),
    (llm_independent, {'classify', 'answer'}, set()),
    (llm_mixed, {'classify'}, {'answer'}),
], ids=['classifier-independent', 'classifier-inherited', 'extractor-independent',
        'extractor-inherited', 'llm-independent', 'llm-mixed'])
def test_independent_scope_covers_supported_node_types(client, monkeypatch,
        forbid_configuration_external_calls, builder, expected, excluded):
    task = task_with_plan(client, monkeypatch, builder())
    state = propose(client, monkeypatch, task, temperature=.3)
    found = independent_ids(state)
    assert expected <= found and not (excluded & found)


@pytest.mark.parametrize('builder,node_ids', [
    (classifier_independent, ['route']),
    (extractor_independent, ['extract']),
    (llm_independent, ['classify', 'answer']),
], ids=['classifier', 'extractor', 'llm'])
def test_compile_keeps_independent_models_after_global_default_change(client, monkeypatch,
        forbid_configuration_external_calls, builder, node_ids):
    task = task_with_plan(client, monkeypatch, builder())
    before = compiled_models(task)
    state = propose(client, monkeypatch, task, temperature=.3)
    assert independent_ids(state)
    response = adopt(client, task, state, acknowledge_unverified=True)
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied['revision'] == task['revision'] + 1
    assert applied['configuration']['temperature'] == .3
    assert applied['requirements_confirmed'] and not applied['configuration_confirmed']
    assert applied['plan_stale'] and applied['workflow_plan'] == task['workflow_plan']
    after = compiled_models(applied)
    assert {node: after[node] for node in node_ids} == {node: before[node] for node in node_ids}
    assert not applied['dify_app_id'] and not applied['runs']


def test_legacy_empty_warnings_is_derived_on_read_without_writing_and_gates_adoption(client,
        monkeypatch, forbid_configuration_external_calls):
    task = task_with_plan(client, monkeypatch, classifier_independent())
    state = propose(client, monkeypatch, task, temperature=.3)
    record_id = state['record']['id']
    legacy = copy.deepcopy(main.store.get('configuration_proposal', record_id))
    legacy['resource_warnings'] = []
    main.store.put('configuration_proposal', record_id, legacy)
    unchanged = copy.deepcopy(main.store.get('configuration_proposal', record_id))

    fresh = client.get(f"/api/tasks/{task['id']}/configuration-proposal").json()
    public = fresh['record']
    assert independent_ids(fresh) == {'route'} and fresh['can_adopt']
    assert public['status'] == 'proposed' and public['resource_warnings'] != unchanged['resource_warnings']
    for key in ('id', 'task_id', 'origin_revision', 'created_at', 'status',
                'context_stamp', 'proposal_token', 'before', 'candidate'):
        assert public[key] == unchanged[key]
    assert [row['reason'] for row in fresh['diffs']] == [row['reason'] for row in unchanged['candidate']['reasons']]
    assert main.store.get('configuration_proposal', record_id) == unchanged

    before_task = copy.deepcopy(main.get_task(task['id']))
    assert adopt(client, task, fresh).status_code == 422
    assert main.get_task(task['id']) == before_task
    assert main.store.get('configuration_proposal', record_id) == unchanged

    response = adopt(client, task, fresh, acknowledge_unverified=True)
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied['configuration']['temperature'] == .3
    assert applied['plan_stale'] and not applied['configuration_confirmed']
    assert applied['workflow_plan'] == task['workflow_plan']
    assert not applied['dify_app_id'] and not applied['runs']
    saved = main.store.get('configuration_proposal', record_id)
    assert saved['status'] == 'adopted' and independent_ids({'record': saved}) == {'route'}
    for key in ('proposal_token', 'before', 'candidate', 'context_stamp'):
        assert saved[key] == unchanged[key]


def test_stale_and_adopted_records_are_not_rewritten(client, monkeypatch,
        forbid_configuration_external_calls):
    task = task_with_plan(client, monkeypatch, classifier_independent())
    state = propose(client, monkeypatch, task, temperature=.3)
    record_id = state['record']['id']
    legacy = copy.deepcopy(main.store.get('configuration_proposal', record_id))
    legacy['resource_warnings'] = []
    main.store.put('configuration_proposal', record_id, legacy)
    changed = client.patch(f"/api/tasks/{task['id']}", json={'requirements': {'goal': '改变目标'}}).json()
    assert changed['revision'] == task['revision'] + 1
    stale_before = copy.deepcopy(main.store.get('configuration_proposal', record_id))
    fresh = client.get(f"/api/tasks/{task['id']}/configuration-proposal").json()
    assert fresh['stale'] and not fresh['can_adopt']
    assert fresh['record']['resource_warnings'] == []
    assert main.store.get('configuration_proposal', record_id) == stale_before

    second = task_with_plan(client, monkeypatch, classifier_independent())
    second_state = propose(client, monkeypatch, second, temperature=.3)
    response = adopt(client, second, second_state, acknowledge_unverified=True)
    assert response.status_code == 200, response.text
    adopted_id = second_state['record']['id']
    adopted = copy.deepcopy(main.store.get('configuration_proposal', adopted_id))
    assert adopted['status'] == 'adopted' and independent_ids({'record': adopted}) == {'route'}
    client.patch(f"/api/tasks/{second['id']}", json={'requirements': {'goal': '再次改变目标'}})
    adopted_before = copy.deepcopy(main.store.get('configuration_proposal', adopted_id))
    fresh = client.get(f"/api/tasks/{second['id']}/configuration-proposal").json()
    assert fresh['record']['status'] == 'adopted'
    assert fresh['record']['resource_warnings'] == adopted_before['resource_warnings']
    assert main.store.get('configuration_proposal', adopted_id) == adopted_before


def test_fresh_derivation_keeps_existing_unverified_resource_warning(client, monkeypatch,
        forbid_configuration_external_calls):
    task = task_with_plan(client, monkeypatch, classifier_independent(),
                          {'dataset_ids': ['legacy_kb']})
    state = propose(client, monkeypatch, task, temperature=.3, dataset_ids=['legacy_kb'])
    assert independent_ids(state) == {'route'}
    assert any('legacy_kb' in text for text in state['record']['resource_warnings'])
    record_id = state['record']['id']
    legacy = copy.deepcopy(main.store.get('configuration_proposal', record_id))
    legacy['resource_warnings'] = [text for text in legacy['resource_warnings'] if 'legacy_kb' in text]
    main.store.put('configuration_proposal', record_id, legacy)
    unchanged = copy.deepcopy(main.store.get('configuration_proposal', record_id))
    fresh = client.get(f"/api/tasks/{task['id']}/configuration-proposal").json()
    stored = set(unchanged['resource_warnings']); current = set(fresh['record']['resource_warnings'])
    assert stored <= current and any(text.startswith(PREFIX) for text in current - stored)
    assert fresh['can_adopt']
    assert main.store.get('configuration_proposal', record_id) == unchanged
    assert adopt(client, task, fresh).status_code == 422
    response = adopt(client, task, fresh, acknowledge_unverified=True)
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied['configuration']['temperature'] == .3
    assert applied['configuration']['dataset_ids'] == ['legacy_kb']
    assert applied['plan_stale'] and not applied['configuration_confirmed']
    assert applied['workflow_plan'] == task['workflow_plan']
