import copy
import json
import pytest
import httpx
from test_api import client
from test_mock_order_read import saved_after_sales
from test_after_sales_cases import call
from app import main
from app.after_sales_cases import propose
from app.mock_order import PREFIX


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def forbidden(*a, **kw): pytest.fail('Preparing continuation drafts must not run code/models/Dify')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)
    monkeypatch.setattr(main.DifyClient, 'request', forbidden)


def memory_built(client):
    task = saved_after_sales(client)
    task['configuration']['conversation_memory'] = True
    main.store.put('task', task['id'], task)
    assert client.post('/api/tasks/'+task['id']+'/confirm', json={
        'revision':task['revision'], 'kind':'configuration'}).status_code == 200
    assert client.post('/api/tasks/'+task['id']+'/build', json={'revision':task['revision']}).status_code == 200
    return main.get_task(task['id'])


def test_explicit_order_adds_two_turn_draft_without_changing_any_saved_content(client, monkeypatch):
    task = memory_built(client); before = copy.deepcopy(task)
    budget = copy.deepcopy(main.store.get('task_budget', task['id']))
    def forbidden(*a, **kw): pytest.fail('Preview must not write or decrypt')
    monkeypatch.setattr(main.store, 'put', forbidden); monkeypatch.setattr(main.store, 'secret', forbidden)
    response = call(client, task, continuation_order_id='DEMO-001')
    assert response.status_code == 200, response.text
    v = response.json(); rows = v['rows']; assert len(rows) == 4
    row = rows[-1]; assert row['scenario'] == 'missing_then_found:DEMO-001'
    assert row['input'] == rows[-2]['input'] and row['expectation'] == rows[-2]['expectation']
    assert row['followups'] == [{'input':{'query':'DEMO-001'}, 'expectation':{
        'mode':'equals','target':'answer','expected':PREFIX+'合成样例：已发货。'}}]
    assert v['continuation_order_id'] == 'DEMO-001' and '两次Service请求' in v['note']
    assert all(v[k] is False for k in ['task_changed','network_requested','model_called','code_executed','business_verified'])
    assert main.get_task(task['id']) == before and main.store.get('task_budget', task['id']) == budget


def test_without_explicit_selection_old_single_turn_behavior_is_unchanged(client):
    task = memory_built(client); v = call(client, task).json()
    assert len(v['rows']) == 3 and v['continuation_order_id'] is None
    assert all('followups' not in x for x in v['rows'])


@pytest.mark.parametrize('memory', [False, None, 'true', 1])
def test_memory_must_be_explicit_true_not_silently_enabled(client, memory):
    task = memory_built(client); task['configuration']['conversation_memory'] = memory
    main.store.put('task', task['id'], task); before = copy.deepcopy(task)
    r = call(client, task, continuation_order_id='DEMO-001')
    assert r.status_code == 422 and '对话记忆' in r.json()['detail']
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('order', ['UNSAVED-PRIVATE-ORDER', '', True, 123, '../PRIVATE', 'x'*65])
def test_unknown_or_invalid_order_is_never_guessed_or_echoed(client, order):
    task = memory_built(client); before = copy.deepcopy(task)
    r = call(client, task, continuation_order_id=order)
    assert r.status_code == 422 and 'PRIVATE' not in r.text
    assert main.get_task(task['id']) == before


def test_two_turn_row_saves_through_normal_cases_api_with_old_single_turn_kept(client):
    task = memory_built(client); v = call(client, task, continuation_order_id='DEMO-001').json()
    rows = [{k:x for k,x in row.items() if k!='scenario'} | {'id':'case-'+str(i)} for i,row in enumerate(v['rows'])]
    budget = copy.deepcopy(main.store.get('task_budget', task['id']))
    r = client.post('/api/tasks/'+task['id']+'/test-cases', json={'revision':task['revision'],'cases':rows})
    assert r.status_code == 200, r.text
    saved = r.json(); assert len(saved['test_cases']) == 4
    assert len(saved['test_cases'][-1]['followups']) == 1 and not saved['test_cases'][-2].get('followups')
    assert not saved['requirements_confirmed'] and not saved['configuration_confirmed'] and saved['artifact'] is None
    assert saved['runs'] == task['runs'] and main.store.get('task_budget', task['id']) == budget


@pytest.mark.parametrize('change', ['revision', 'artifact', 'plan', 'configuration'])
def test_continuation_keeps_whole_source_and_confirmation_guards(client, change):
    task = memory_built(client)
    if change == 'revision':
        assert call(client, task, continuation_order_id='DEMO-001', revision=task['revision']+1).status_code == 409
        return
    if change == 'artifact': main.artifact_path(task).write_text('changed',encoding='utf-8')
    if change == 'plan': task['workflow_plan']['nodes'][0]['title'] = '人工改动'
    if change == 'configuration': task['configuration_confirmed'] = False
    main.store.put('task', task['id'], task)
    assert call(client, task, continuation_order_id='DEMO-001').status_code == 422


def test_ten_records_plus_one_selected_continuation_is_bounded_to_thirteen_rows(client):
    task = memory_built(client); task['workflow_plan'] = None; task['artifact'] = None
    from test_after_sales_starter import inputs
    from app.after_sales_starter import prepare
    v = inputs(); v['records_text'] = json.dumps({f'DEMO-{i}':f'合成{i}' for i in range(10)})
    text, _ = prepare(task, v); task['workflow_plan'] = json.loads(text)
    rows, _ = propose(task, '订单查询模拟', 'DEMO-9')
    assert len(rows) == 13 and rows[-1]['followups'][0]['input']['query'] == 'DEMO-9'


def test_workflow_is_not_asked_to_enable_unsupported_conversation_memory(client):
    from test_api import approved
    task = approved(client)
    r = client.post('/api/tasks/'+task['id']+'/build', json={'revision':task['revision']})
    assert r.status_code == 200
    task = main.get_task(task['id']); before = copy.deepcopy(task)
    r = call(client, task, continuation_order_id='DEMO-001')
    assert r.status_code == 422 and 'Chatflow' in r.json()['detail']
    assert main.get_task(task['id']) == before
