import copy
import pytest
from test_api import client, approved
from app import main
from app.execution_costs import summary, amount, reported
from app.dify import DifyClient

APP = 'a161d921-8f76-4a42-ad1e-6150a54cf0d8'
REMOTE = '5b66dc55-cce6-4457-bd4b-8f48ecdfc1bd'
SECOND = '895a778d-e2b2-4c41-9e26-5b08747dd59b'


def run(rid='local1', price='0.001', currency='USD', tokens=20, **changes):
    value = {'id':rid, 'kind':'run', 'revision':1, 'environment_id':'environment1', 'environment_binding':'a'*64,
             'app_id':APP, 'app_type':'advanced-chat', 'status':'success',
             'result':{'workflow_run_id':REMOTE, 'metadata':{'usage':{'total_price':price, 'currency':currency, 'total_tokens':tokens}}}}
    value.update(changes)
    return value


def state(*runs):
    return summary({'revision':3, 'runs':list(runs)})


def test_currencies_are_separate_and_history_failure_unknown_are_included():
    failed = run('failed', '1.25', 'CNY', status='failed', revision=2)
    failed['result']['workflow_run_id'] = SECOND
    missing = run('unknown', None, None, None, status='unknown', result=None)
    result = state(run(), failed, missing)
    assert result['known_amounts_by_currency'] == {'CNY':'1.25', 'USD':'0.001'}
    assert result['execution_count'] == 3 and result['unknown_cost_count'] == 1
    assert result['known_total_tokens'] == 40 and result['unknown_token_count'] == 1
    assert '不实施运行费用硬上限' in result['note']


def test_workflow_tokens_never_invent_a_price_or_use_output_business_values():
    record = run(app_type='workflow', result={'workflow_run_id':REMOTE, 'data':{'id':REMOTE, 'total_tokens':30, 'total_price':'8', 'currency':'USD', 'outputs':{'total_price':'99'}}})
    result = state(record)
    assert result['known_total_tokens'] == 30 and result['unknown_cost_count'] == 1
    assert result['known_amounts_by_currency'] == {}


@pytest.mark.parametrize('shape', ['metadata', 'data'])
def test_legacy_type_missing_reads_saved_fields_without_guessing_task_type(shape):
    record = run(app_type=None)
    if shape == 'data': record['result'] = {'data':{'total_tokens':12}}
    result = state(record)
    row = result['entries'][0]
    assert row['app_type'] is None and 'without_type' in row['basis']
    assert result['known_total_tokens'] == (12 if shape == 'data' else 20)
    assert result['unknown_cost_count'] == (1 if shape == 'data' else 0)


def test_explicit_zero_is_reported_with_free_not_proven_note():
    result = state(run(price='0', tokens=0))
    assert result['unknown_cost_count'] == 0 and result['known_amounts_by_currency'] == {'USD':'0'}
    assert '报价为 0 也不证明免费' in result['note']


@pytest.mark.parametrize('value', [None, True, False, '-1', 'NaN', 'Infinity', '1e999', '1000001', '0.0000000000001', {}, [], 'sk-synthetic-private'])
def test_bad_money_is_unknown_and_raw_secret_never_in_summary(value):
    assert amount(value) is None
    result = state(run(price=value))
    assert result['unknown_cost_count'] == 1 and result['known_amounts_by_currency'] == {}
    assert 'sk-synthetic-private' not in str(result)


@pytest.mark.parametrize('currency', [None, '', 'usd', 'USDT', 'USD\n', 0, True])
def test_missing_or_invalid_currency_never_assumes_usd(currency):
    result = state(run(currency=currency))
    assert result['unknown_cost_count'] == 1 and result['known_amounts_by_currency'] == {}


def test_duplicate_identity_across_revisions_is_counted_once_and_preserves_sources():
    first = run()
    second = run('local2', revision=2)
    result = state(first, second)
    assert result['known_amounts_by_currency'] == {'USD':'0.001'}
    assert result['record_count'] == 2 and result['execution_count'] == 1 and result['duplicate_record_count'] == 1
    assert {s['revision'] for s in result['executions'][0]['sources']} == {1,2}


@pytest.mark.parametrize('change', [{'environment_binding':None}, {'environment_binding':'old'}, {'app_id':None}])
def test_missing_identity_does_not_guess_current_environment_or_deduplicate(change):
    a, b = run(**change), run('local2', **change)
    result = state(a,b)
    assert result['execution_count'] == 2 and result['duplicate_record_count'] == 0
    assert not any(row['identity_verified'] for row in result['entries'])


def test_same_remote_id_in_different_instances_is_not_a_duplicate():
    result = state(run(), run('local2', environment_binding='b'*64))
    assert result['execution_count'] == 2 and result['known_amounts_by_currency'] == {'USD':'0.002'}


def test_disagreeing_prices_are_visible_and_excluded_from_known_sum():
    result = state(run(), run('local2', '0.002'))
    assert result['cost_conflict_count'] == 1 and result['unknown_cost_count'] == 1
    assert result['known_amounts_by_currency'] == {}
    assert len(result['executions'][0]['sources']) == 2


def test_disagreeing_token_counts_are_not_arbitrarily_chosen():
    result = state(run(tokens=20), run('local2', tokens=30))
    assert result['known_total_tokens'] == 0 and result['unknown_token_count'] == 1
    assert result['executions'][0]['token_conflict']
    assert reported({'metadata':{'usage':{'total_tokens':20, 'prompt_tokens':5, 'completion_tokens':6}}}, 'advanced-chat')['token_conflict']


@pytest.mark.parametrize('value', [True, '20', -1, 1.5, float('nan'), 10**13])
def test_invalid_tokens_not_treated_as_zero(value):
    result = state(run(tokens=value))
    assert result['known_total_tokens'] == 0 and result['unknown_token_count'] == 1


def test_multiturn_success_and_pending_failure_costs_are_all_retained():
    first, second = run(), run('two','0.002')
    second['result']['workflow_run_id'] = SECOND
    record = run(result={'conversation_case':True, 'turns':[{'index':1, 'result':first['result']}, {'index':2, 'result':second['result']}], 'pending_turn':{'index':3, 'result':None}}, status='unknown')
    result = state(record)
    assert result['record_count'] == 3 and result['execution_count'] == 3 and result['unknown_cost_count'] == 1
    assert {row['turn'] for row in result['entries']} == {1,2,3}
    assert result['known_amounts_by_currency'] == {'USD':'0.003'}


def test_native_agent_message_usage_and_valid_message_identity():
    a = run(app_type='agent')
    a['result'].pop('workflow_run_id')
    a['result']['message_id'] = REMOTE
    b = copy.deepcopy(a)
    b['id'] = 'local2'
    result = state(a,b)
    assert result['execution_count'] == 1 and result['known_total_tokens'] == 20


def test_empty_or_malformed_conversation_has_unknown_record():
    for value in ({'conversation_case':True,'turns':[]}, {'conversation_case':True,'turns':'bad'}):
        assert state(run(result=value))['unknown_cost_count'] == 1


def test_malformed_turn_indices_are_not_invented():
    result = state(run(result={'conversation_case':True, 'turns':[{'index':True, 'result':run()['result']}], 'pending_turn':{'index':'2'}}))
    assert all(row['turn'] is None for row in result['entries'])


def test_import_and_diagnostic_node_prices_are_not_double_counted():
    record = run()
    record['diagnostics'] = [{'nodes':[{'total_price':'100','currency':'USD'}]}]
    result = state(record, {'kind':'import', 'result':record['result']})
    assert result['record_count'] == 1 and result['known_amounts_by_currency'] == {'USD':'0.001'}


def test_limit_is_explicit_not_claimed_complete(monkeypatch):
    import app.execution_costs as module
    monkeypatch.setattr(module, 'MAX_ENTRIES', 2)
    result = state(run(), run('local2',environment_binding=None),run('local3',environment_binding=None))
    assert result['truncated'] and result['record_count'] == 2 and '不能称为完整累计' in result['note']


def test_api_and_report_are_readonly_without_model_or_dify_calls(client, monkeypatch):
    t = approved(client)
    t['runs'] = [run(), run('pending', result=None, status='unknown')]
    main.save_task(t)
    before = copy.deepcopy(main.get_task(t['id']))
    budget_before = copy.deepcopy(main.store.list('task_budget'))
    async def forbidden(*a,**kw): pytest.fail('费用汇总不得调用模型或 Dify')
    monkeypatch.setattr(DifyClient, 'request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)
    response = client.get(f"/api/tasks/{t['id']}/execution-costs")
    assert response.status_code == 200 and response.json()['unknown_cost_count'] == 1
    report = client.get(f"/api/tasks/{t['id']}/report")
    assert report.status_code == 200 and 'Dify 试跑用量与报告金额' in report.text
    assert main.get_task(t['id']) == before and main.store.list('task_budget') == budget_before
    assert client.get('/api/tasks/not-owned/execution-costs').status_code == 404
