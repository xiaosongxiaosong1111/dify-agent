import copy,json
import pytest
from test_api import client,approved
from test_task_budget import provider,policy
from test_case_proposals import candidate
from app import main
from app.providers import ProviderError


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
