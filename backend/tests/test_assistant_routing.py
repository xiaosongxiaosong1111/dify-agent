import copy,json
from decimal import Decimal
import httpx
import pytest
from test_api import client,approved
from test_task_budget import provider,policy
from test_case_proposals import candidate
from app import main
from app.providers import ProviderError
from app.storage import Store


@pytest.fixture(autouse=True)
def forbid_routing_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('AT-25 隔离检查不得访问真实 HTTP、Dify 或付费模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main.DifyClient, 'request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def setup(client):
    t=approved(client);p=provider(client)
    t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json()
    light=client.post('/api/providers',json={'name':'轻量用途技术模型','provider':'custom','base_url':'https://light.example.com/v1','model':'light-model','role':'light','api_key':'fake-light-key','pricing':{'input_per_million_usd':.1,'output_per_million_usd':.2}}).json()
    return t,p,light


def state(client,t):return client.get(f"/api/tasks/{t['id']}/assistant-routing").json()
def enable(client,t,light,**patch):
    s=state(client,t);choice=next((p for p in s['eligible'] if p['id']==light['id']),None)
    return client.patch(f"/api/tasks/{t['id']}/assistant-routing",json={'revision':t['revision'],'policy_revision':s['policy_revision'],'enabled':True,'light_provider_id':light['id'],'provider_token':choice['provider_token'] if choice else 'not-observed','scope_version':18,'acknowledge_scope':True,'note':'明确验收建议数据及费用使用轻量服务，不自动换主模型。',**patch})


def test_route_read_and_confirm_are_local_do_not_change_task_or_confirmations(client,monkeypatch):
    t,p,light=setup(client);before=copy.deepcopy(main.get_task(t['id']));calls=[]
    async def model(*a,**kw):calls.append(a);pytest.fail('设置路由不得调用模型')
    monkeypatch.setattr(main,'call_model',model)
    initial=state(client,t);assert not initial['enabled'] and not initial['blocker']
    response=enable(client,t,light);assert response.status_code==200,response.text
    result=response.json();assert result['enabled'] and len(result['history'])==1 and result['policy_revision']==1
    assert main.get_task(t['id'])==before and not calls
    assert 'fake-light-key' not in response.text and 'not-a-real-key' not in response.text
    assert 'tokens 更少' in result['scope_note']


def test_only_case_proposal_routes_to_light_and_shared_ledger_records_actual_provider(client,monkeypatch):
    t,p,light=setup(client);assert enable(client,t,light).status_code==200
    assert main.routing.provider(t,'cases')['id']==light['id']
    for kind in ('configuration','conflicts','coverage','interview','plan'):
        assert main.routing.provider(t,kind)['id']==p['id']
    assert policy(client,t,'1').status_code==200
    seen=[]
    async def model(provider,key,messages,**kw):
        seen.append((provider['id'],key,json.loads(messages[1]['content'])))
        return json.dumps(candidate()),{'prompt_tokens':10,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']});assert response.status_code==200,response.text
    saved=response.json();op=saved['planning_runs'][-1]
    assert seen[0][0]==light['id'] and seen[0][1]=='fake-light-key'
    assert op['routing']=={'operation':'cases','selected_role':'light','policy_revision':1}
    ledger=main.budgets.get(t['id']);assert ledger['entries'][-1]['provider_id']==light['id'] and ledger['entries'][-1]['charged_usd'] is not None
    assert not saved['test_cases'] and saved['revision']==t['revision']
    assert 'api_key' not in json.dumps(seen[0][2])
    preview=client.get(f"/api/tasks/{t['id']}/case-proposal").json()
    assert preview['generation_route']['provider']['id']==light['id'] and preview['generation_route']['role']=='light'
    assert preview['record']['generation_origin']['id']==op['id'] and preview['record']['generation_origin']['model']=='light-model'
    assert preview['record']['generation_origin']['routing']['policy_revision']==1


@pytest.mark.parametrize('mutation',['model','price','role','key','probe'])
def test_changed_provider_configuration_or_capability_blocks_before_dispatch(client,monkeypatch,mutation):
    t,p,light=setup(client);enable(client,t,light)
    if mutation=='model':patch={'model':'new-model'}
    elif mutation=='price':patch={'pricing':{'input_per_million_usd':.9,'output_per_million_usd':1}}
    elif mutation=='role':patch={'role':'main'}
    elif mutation=='key':patch={'api_key':'new-fake-light-key'}
    else:
        record=main.store.get('provider',light['id']);record['capabilities']['text']='verified';main.store.put('provider',light['id'],record);patch=None
    if patch:assert client.patch(f"/api/providers/{light['id']}",json=patch).status_code==200
    async def forbidden(*a,**kw):pytest.fail('来源改变后不能派发或自动换主模型')
    monkeypatch.setattr(main,'call_model',forbidden)
    assert state(client,t)['blocker']
    response=client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']});assert response.status_code==422
    assert not main.get_task(t['id'])['planning_runs']


def test_stale_revision_missing_ack_foreign_role_and_inactive_selection_rejected(client):
    t,p,light=setup(client)
    assert enable(client,t,light,revision=t['revision']-1).status_code==409
    assert enable(client,t,light,provider_token='old').status_code==409
    assert enable(client,t,light,policy_revision=9).status_code==409
    assert enable(client,t,light,acknowledge_scope=False).status_code==422
    assert enable(client,t,light,note='').status_code==422
    assert enable(client,t,p).status_code==422
    assert enable(client,t,light,enabled=False).status_code==422


def test_missing_key_and_deleted_selected_service_never_fallback(client):
    t,p,light=setup(client);enable(client,t,light)
    main.store.delete('provider',light['id'])
    assert state(client,t)['blocker']
    with pytest.raises(main.HTTPException):main.routing.provider(t,'cases')
    assert main.routing.provider(t,'plan')['id']==p['id']


def test_provider_failure_does_not_try_primary_even_when_available(client,monkeypatch):
    t,p,light=setup(client);enable(client,t,light)
    seen=[]
    async def failed(provider,*a,**kw):seen.append(provider['id']);raise ProviderError('技术模型返回失败。')
    monkeypatch.setattr(main,'call_model',failed)
    response=client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']})
    assert response.status_code==422 and seen==[light['id']]
    assert main.get_task(t['id'])['status']=='paused'


def test_close_route_keeps_history_and_then_provider_can_be_deleted(client):
    t,p,light=setup(client);enable(client,t,light)
    assert client.delete(f"/api/providers/{light['id']}").status_code==409
    s=state(client,t);response=client.patch(f"/api/tasks/{t['id']}/assistant-routing",json={'revision':t['revision'],'policy_revision':s['policy_revision'],'enabled':False,'light_provider_id':None,'provider_token':None,'scope_version':18,'acknowledge_scope':True,'note':'明确恢复默认主模型，保留旧调用用量。'})
    assert response.status_code==200 and not response.json()['enabled'] and len(response.json()['history'])==2
    assert main.routing.provider(t,'cases')['id']==p['id']
    assert client.delete(f"/api/providers/{light['id']}").status_code==200


def test_reserved_calls_protect_provider_edits_even_after_pause(client):
    t,p,light=setup(client)
    main.store.put('task_budget',t['id'],{'id':t['id'],'entries':[{'id':'pending','status':'reserved','provider_id':light['id']}]})
    assert client.patch(f"/api/providers/{light['id']}",json={'model':'changed'}).status_code==409
    assert client.delete(f"/api/providers/{light['id']}").status_code==409


def test_report_includes_route_scope_history_and_no_keys(client):
    t,p,light=setup(client);enable(client,t,light)
    response=client.get(f"/api/tasks/{t['id']}/report")
    assert response.status_code==200 and '轻量建议模型路由' in response.text and 'fake-light-key' not in response.text


def test_route_change_changes_next_preview_not_existing_candidate_source_or_validity(client,monkeypatch):
    t,p,light=setup(client);enable(client,t,light)
    async def model(*a,**kw):return json.dumps(candidate()),{'prompt_tokens':10,'completion_tokens':10}
    monkeypatch.setattr(main,'call_model',model)
    assert client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']}).status_code==200
    before=client.get(f"/api/tasks/{t['id']}/case-proposal").json();assert before['can_adopt']
    assert client.patch(f"/api/tasks/{t['id']}/assistant-routing",json={'revision':t['revision'],'policy_revision':1,'enabled':False,'scope_version':18,'acknowledge_scope':True,'note':'恢复默认，仅影响以后主动生成建议。'}).status_code==200
    after=client.get(f"/api/tasks/{t['id']}/case-proposal").json()
    assert after['generation_route']['provider']['id']==p['id'] and after['generation_route']['role']=='main'
    assert after['record']==before['record'] and after['can_adopt'] and not after['stale']


@pytest.mark.parametrize('old_scope', [1, 17])
def test_old_scope_blocks_without_decryption_or_charge_until_explicit_reconfirmation(client, monkeypatch, old_scope):
    t, p, light = setup(client)
    assert enable(client, t, light).status_code == 200
    saved = main.routing.get(t['id'])
    saved['scope_version'] = old_scope
    main.store.put('assistant_routing', t['id'], saved)
    before = copy.deepcopy(main.get_task(t['id']))
    ledger = copy.deepcopy(main.budgets.get(t['id']))
    with monkeypatch.context() as guard:
        def forbidden(*args, **kwargs):
            pytest.fail('过期范围确认不得解密凭据或派发')
        guard.setattr(main.store, 'secret', forbidden)
        assert state(client, t)['blocker']
        response = client.post(f"/api/tasks/{t['id']}/case-proposal/generate", json={'revision': t['revision']})
        assert response.status_code == 422 and '重新核对' in response.json()['detail']
        assert enable(client, t, light, scope_version=old_scope).status_code == 409
    assert main.get_task(t['id']) == before
    assert main.budgets.get(t['id']) == ledger
    assert main.routing.get(t['id']) == saved
    result = enable(client, t, light)
    assert result.status_code == 200, result.text
    assert not result.json()['blocker'] and result.json()['policy_revision'] == 2
    assert result.json()['history'][-1]['before']['scope_version'] == old_scope


def test_route_policy_is_task_local_and_survives_store_reopen(client, monkeypatch):
    t, p, light = setup(client)
    other, other_main, _ = setup(client)
    before = copy.deepcopy(main.get_task(t['id']))
    other_before = copy.deepcopy(main.get_task(other['id']))
    assert enable(client, t, light).status_code == 200
    saved = state(client, t)
    monkeypatch.setattr(main, 'store', Store(main.store.root))
    assert state(client, t) == saved
    assert main.routing.provider(t, 'cases')['id'] == light['id']
    assert not state(client, other)['enabled'] and not state(client, other)['history']
    assert main.routing.provider(other, 'cases')['id'] == other_main['id']
    assert main.get_task(t['id']) == before and main.get_task(other['id']) == other_before
    assert not main.budgets.get(t['id'])['entries'] and not main.budgets.get(other['id'])['entries']


def test_removed_light_key_blocks_dispatch_without_main_fallback_or_charge(client):
    t, p, light = setup(client)
    assert enable(client, t, light).status_code == 200
    record = main.store.get('provider', light['id'])
    main.store.put_with_secrets('provider', light['id'], record, {'api_key': ''})
    before = copy.deepcopy(main.get_task(t['id']))
    assert '无密钥' in state(client, t)['blocker']
    response = client.post(f"/api/tasks/{t['id']}/case-proposal/generate", json={'revision': t['revision']})
    assert response.status_code == 422 and '不会换到主模型' in response.json()['detail']
    assert main.get_task(t['id']) == before and not main.budgets.get(t['id'])['entries']


@pytest.mark.parametrize('outcome', ['repaired', 'invalid_again', 'provider_failure'])
def test_light_json_retry_accounts_every_attempt_without_fallback_or_business_success(client, monkeypatch, outcome):
    t, p, light = setup(client)
    assert enable(client, t, light).status_code == 200
    assert policy(client, t, '1').status_code == 200
    monkeypatch.setattr(main, 'get_settings', lambda: {'max_retries': 2, 'max_minutes': 1, 'max_cost_usd': 1})
    seen = []
    usage = {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}
    async def model(selected, key, messages, **kwargs):
        seen.append((selected['id'], key, copy.deepcopy(messages)))
        if len(seen) == 1:
            return '这不是 JSON', usage
        if outcome == 'provider_failure':
            raise ProviderError('固定测试失败', usage=usage)
        return (json.dumps(candidate()) if outcome == 'repaired' else '仍不是 JSON'), usage
    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f"/api/tasks/{t['id']}/case-proposal/generate", json={'revision': t['revision']})
    assert response.status_code == (200 if outcome == 'repaired' else 422), response.text
    assert [(pid, key) for pid, key, _ in seen] == [(light['id'], 'fake-light-key')] * 2
    assert len(seen[1][2]) == len(seen[0][2]) + 2
    assert '只修复 JSON 格式' in seen[1][2][-1]['content']
    saved = main.get_task(t['id'])
    op = saved['planning_runs'][-1]
    assert op['routing'] == {'operation': 'cases', 'selected_role': 'light', 'policy_revision': 1}
    assert len(op['attempts']) == 2 and op['attempts'][0]['status'] == 'invalid'
    assert op['status'] == ('succeeded' if outcome == 'repaired' else 'paused')
    if outcome != 'repaired':
        assert op['stop_reason'] == ('no_progress' if outcome == 'invalid_again' else 'provider_error')
    entries = main.budgets.get(t['id'])['entries']
    assert len(entries) == 2 and {entry['operation_id'] for entry in entries} == {op['id']}
    assert all(entry['provider_id'] == light['id'] and entry['status'] == 'settled' for entry in entries)
    assert sum(Decimal(entry['charged_usd']) for entry in entries) == Decimal('0.000024')
    summary = client.get(f"/api/tasks/{t['id']}/budget/usage-summary", params={'revision': t['revision']}).json()
    assert summary['state'] == 'ready' and summary['totals']['calls'] == 2
    assert summary['totals']['returned'] == (1 if outcome == 'provider_failure' else 2)
    assert summary['totals']['failed_or_interrupted'] == (1 if outcome == 'provider_failure' else 0)
    assert summary['totals']['tokens']['total'] == {'known': 220, 'missing': 0}
    assert Decimal(summary['totals']['estimated_usd']) == Decimal('0.000024')
    assert not summary['business_quality_verified'] and not summary['savings_verified']
    proposal = client.get(f"/api/tasks/{t['id']}/case-proposal").json()
    assert bool(proposal['record']) == (outcome == 'repaired')
    assert saved['revision'] == t['revision'] and not saved['test_cases'] and not saved['runs'] and not saved['dify_app_id']
    assert 'fake-light-key' not in json.dumps([saved, entries, summary, proposal])
