import copy,json
from decimal import Decimal
import pytest
from test_assistant_routing import client,setup,enable,state,forbid_routing_external_calls
from test_case_proposals import candidate
from test_task_budget import policy
from app import main
from app.providers import ProviderError


USAGE={'prompt_tokens':10,'completion_tokens':20}


def upgrade(client,t,light,**changes):
    current=state(client,t);model=current['upgrade']['main_provider']
    return enable(client,t,light,**{'upgrade_enabled':True,'upgrade_main_provider_id':model['id'] if model else None,'upgrade_main_provider_token':model['provider_token'] if model else None,'acknowledge_upgrade_scope':True,'upgrade_scope_version':current['upgrade']['scope_version'],**changes})


def generate(client,t):return client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']})


def test_upgrade_confirmation_is_local_default_off_and_bound_to_both_models(client,monkeypatch):
    t,p,light=setup(client);before=copy.deepcopy(main.get_task(t['id']));assert not state(client,t)['upgrade']['enabled']
    result=upgrade(client,t,light);assert result.status_code==200,result.text
    assert result.json()['upgrade']['enabled'] and result.json()['upgrade']['max_model_http_requests']==2 and main.get_task(t['id'])==before
    assert client.delete(f"/api/providers/{p['id']}").status_code==409
    assert not main.budgets.get(t['id'])['entries']


def test_known_parse_failure_upgrades_once_and_records_actual_origin_cost_and_original_context(client,monkeypatch):
    t,p,light=setup(client);assert upgrade(client,t,light).status_code==200;assert policy(client,t,'1').status_code==200;calls=[]
    async def model(provider,key,messages,**kwargs):
        calls.append((provider['id'],copy.deepcopy(messages),kwargs))
        return ('NOT JSON PRIVATE-LIGHT-EXCERPT' if len(calls)==1 else json.dumps(candidate())),USAGE
    monkeypatch.setattr(main,'call_model',model)
    response=generate(client,t);assert response.status_code==200,response.text
    saved=response.json();op=saved['planning_runs'][-1]
    assert [c[0] for c in calls]==[light['id'],p['id']] and calls[0][1]==calls[1][1]
    assert all(c[2]['max_tokens']==6000 and 0<c[2]['timeout']<=120 for c in calls)
    assert op['provider_id']==p['id'] and op['model']==p['model'] and op['routing']['upgrade']['triggered'] and op['routing']['final_role']=='main_upgrade'
    assert [a['number'] for a in op['attempts']]==[1,2] and [a['phase'] for a in op['attempts']]==['light','main_upgrade']
    assert op['phases'][0]['attempts'][0]['status']=='invalid' and 'PRIVATE-LIGHT-EXCERPT' in op['phases'][0]['last_response_excerpt']
    ledger=main.budgets.get(t['id']);assert len(ledger['entries'])==2 and all(e['status']=='settled' and e['operation_id']==op['id'] for e in ledger['entries'])
    assert Decimal(str(op['estimated_cost_usd']))==sum(Decimal(e['charged_usd']) for e in ledger['entries'])
    proposal=client.get(f"/api/tasks/{t['id']}/case-proposal").json()['record'];assert proposal['generation_origin']['provider_id']==p['id']
    assert saved['revision']==t['revision'] and not saved['test_cases']


def test_valid_light_candidate_never_calls_main_even_without_final_usage(client,monkeypatch):
    t,p,light=setup(client);upgrade(client,t,light);calls=[]
    async def model(provider,*a,**kw):calls.append(provider['id']);return json.dumps(candidate()),{}
    monkeypatch.setattr(main,'call_model',model);response=generate(client,t)
    assert response.status_code==200 and calls==[light['id']] and not response.json()['planning_runs'][-1]['routing']['upgrade']['triggered']
    assert main.budgets.get(t['id'])['entries'][0]['status']=='unknown'


@pytest.mark.parametrize('failure',['provider','timeout','missing_usage','bad_usage','decision','schema','pause','revision'])
def test_nonparse_or_unknown_or_changed_task_never_upgrades(client,monkeypatch,failure):
    t,p,light=setup(client);upgrade(client,t,light);calls=[]
    async def model(provider,*a,**kw):
        calls.append(provider['id'])
        if failure=='provider':raise ProviderError('公开传输失败',usage=USAGE)
        if failure=='timeout':raise TimeoutError()
        if failure in ('pause','revision'):
            task=main.get_task(t['id']);task['status']='paused' if failure=='pause' else task['status'];task['revision']+=int(failure=='revision');main.store.put('task',t['id'],task)
        if failure=='decision':return '{"error":"公开需要决定"}',USAGE
        if failure=='schema':return '{"schema_version":1,"items":[],"open_issues":[],"notes":"invalid"}',USAGE
        return 'NOT JSON',{} if failure=='missing_usage' else {'prompt_tokens':True,'completion_tokens':20} if failure=='bad_usage' else USAGE
    monkeypatch.setattr(main,'call_model',model);response=generate(client,t)
    assert response.status_code==422 and calls==[light['id']] and len(main.budgets.get(t['id'])['entries'])==1


def test_main_invalid_does_not_start_third_call_or_drop_first_failure(client,monkeypatch):
    t,p,light=setup(client);upgrade(client,t,light);calls=[]
    async def model(provider,*a,**kw):calls.append(provider['id']);return 'INVALID JSON',USAGE
    monkeypatch.setattr(main,'call_model',model);response=generate(client,t)
    assert response.status_code==422 and calls==[light['id'],p['id']]
    op=main.get_task(t['id'])['planning_runs'][-1];assert len(op['attempts'])==2 and len(op['phases'])==2 and op['status']=='paused'


@pytest.mark.parametrize('change',['main_key','main_price','main_capability','light_key','zero_retries','stored_scope_version'])
def test_source_or_global_limit_change_blocks_before_any_dispatch(client,monkeypatch,change):
    t,p,light=setup(client);upgrade(client,t,light)
    if change=='main_key':main.patch_provider(p['id'],{'api_key':'rotated-fake-key'})
    elif change=='main_price':main.patch_provider(p['id'],{'pricing':{'input_per_million_usd':2,'output_per_million_usd':3}})
    elif change=='light_key':main.patch_provider(light['id'],{'api_key':'rotated-light-key'})
    elif change=='main_capability':
        stored=main.store.get('provider',p['id']);stored['capabilities']['text']='verified';main.store.put('provider',p['id'],stored)
    elif change=='stored_scope_version':
        record=main.routing.get(t['id']);record['upgrade']['scope_version']=0;main.store.put('assistant_routing',t['id'],record)
    else:
        settings=main.get_settings();settings['max_retries']=0;main.store.put('settings','execution',settings)
    assert generate(client,t).status_code==422 and not main.budgets.get(t['id'])['entries']


@pytest.mark.parametrize('field,value,status',[('acknowledge_upgrade_scope',False,422),('upgrade_main_provider_token','wrong',409),('upgrade_main_provider_id','missing',409),('upgrade_enabled','true',422),('upgrade_scope_version',None,409),('upgrade_scope_version',2,409)])
def test_upgrade_needs_independent_explicit_confirmation_and_current_source(client,field,value,status):
    t,p,light=setup(client);response=upgrade(client,t,light,**{field:value});assert response.status_code==status
    assert not state(client,t)['upgrade']['enabled'] and not main.budgets.get(t['id'])['entries']


@pytest.mark.parametrize('bound',['round','cumulative'])
def test_first_cost_and_main_reservation_share_limits_without_dispatching_main(client,monkeypatch,bound):
    t,p,light=setup(client);upgrade(client,t,light)
    if bound=='round':
        settings=main.get_settings();settings['max_cost_usd']=.003;main.store.put('settings','execution',settings)
    else:assert policy(client,t,'0.003').status_code==200
    calls=[]
    async def model(provider,*a,**kw):calls.append(provider['id']);return 'INVALID JSON',USAGE
    monkeypatch.setattr(main,'call_model',model);response=generate(client,t)
    assert response.status_code==422 and calls==[light['id']]
    entries=main.budgets.get(t['id'])['entries'];assert len(entries)==1 and entries[0]['status']=='settled'
    op=main.get_task(t['id'])['planning_runs'][-1];assert op['stop_reason']==('cost_limit' if bound=='round' else 'task_budget_limit')


def test_two_phases_share_original_deadline_and_do_not_apply_late_main_candidate(client,monkeypatch):
    from app import lightweight_upgrade
    t,p,light=setup(client);upgrade(client,t,light);settings=main.get_settings();settings['max_minutes']=1;main.store.put('settings','execution',settings)
    original=lightweight_upgrade.run;now=[0.0];calls=[]
    async def driver(*a,**kw):return await original(*a,**kw,clock=lambda:now[0])
    async def model(provider,*a,**kw):
        calls.append(provider['id']);now[0]+=50 if len(calls)==1 else 20
        return 'INVALID JSON' if len(calls)==1 else json.dumps(candidate()),USAGE
    monkeypatch.setattr(lightweight_upgrade,'run',driver);monkeypatch.setattr(main,'call_model',model)
    assert generate(client,t).status_code==422 and calls==[light['id'],p['id']]
    assert main.get_task(t['id'])['planning_runs'][-1]['stop_reason']=='time_limit' and not main.store.list('case_proposal')
    assert len(main.budgets.get(t['id'])['entries'])==2


@pytest.mark.parametrize('phase',[1,2])
def test_model_source_change_during_either_phase_keeps_results_and_stops_application(client,monkeypatch,phase):
    t,p,light=setup(client);upgrade(client,t,light);calls=[]
    async def model(provider,*a,**kw):
        calls.append(provider['id'])
        if len(calls)==phase:main.patch_provider(p['id'] if phase==1 else light['id'],{'name':'changed PUBLIC NAME'})
        return 'INVALID JSON' if len(calls)==1 else json.dumps(candidate()),USAGE
    monkeypatch.setattr(main,'call_model',model)
    assert generate(client,t).status_code==422 and len(calls)==phase and not main.store.list('case_proposal')
    assert main.get_task(t['id'])['planning_runs'][-1]['stop_reason']=='routing_changed'


def test_old_unknown_entry_is_not_released_or_borrowed_for_new_two_stage_operation(client):
    t,p,light=setup(client);upgrade(client,t,light)
    ledger=main.budgets.get(t['id'],create=True);entry={'id':'old-held','operation_id':'old-consumed','status':'unknown','reserved_usd':'.02','charged_usd':None,'provider_id':light['id']};ledger['entries'].append(entry);main.store.put('task_budget',t['id'],ledger)
    assert generate(client,t).status_code==422 and main.budgets.get(t['id'])['entries']==[entry]


@pytest.mark.parametrize('error',['provider','timeout','cancel'])
def test_main_phase_failure_keeps_two_receipts_and_never_starts_a_third_call(client,monkeypatch,error):
    import asyncio
    from concurrent.futures import CancelledError as FutureCancelled
    t,p,light=setup(client);upgrade(client,t,light);calls=[]
    async def model(provider,*a,**kw):
        calls.append(provider['id'])
        if len(calls)==1:return 'INVALID JSON',USAGE
        if error=='provider':raise ProviderError('公开主阶段失败')
        if error=='timeout':raise TimeoutError()
        raise asyncio.CancelledError()
    monkeypatch.setattr(main,'call_model',model)
    if error=='cancel':
        with pytest.raises((asyncio.CancelledError,FutureCancelled)):generate(client,t)
    else:assert generate(client,t).status_code==422
    assert calls==[light['id'],p['id']]
    entries=main.budgets.get(t['id'])['entries'];assert len(entries)==2 and entries[0]['status']=='settled' and entries[1]['status']=='unknown'
    op=main.get_task(t['id'])['planning_runs'][-1];assert len(op['attempts'])==2 and op['phases'][-1]['status'] in {'paused','interrupted'}
    assert not main.store.list('case_proposal')


def test_disabling_new_policy_clears_upgrade_pointer_and_keeps_confirmation_history(client):
    t,p,light=setup(client);upgrade(client,t,light)
    result=enable(client,t,light);assert result.status_code==200 and not result.json()['upgrade']['enabled']
    saved=main.routing.get(t['id']);assert saved['upgrade']=={'enabled':False,'main_provider_id':None,'main_provider_token':None}
    assert len(saved['history'])==2 and saved['history'][0]['after']['upgrade']['enabled'] and saved['history'][1]['before']['upgrade']['enabled']


@pytest.mark.parametrize('missing',['price','provider','key','separate_role'])
def test_unavailable_main_conditions_do_not_enable_or_dispatch_upgrade(client,missing):
    t,p,light=setup(client)
    if missing=='price':main.patch_provider(p['id'],{'pricing':None})
    elif missing=='provider':main.store.delete('provider',p['id'])
    elif missing=='key':
        empty=client.post('/api/providers',json={'name':'公开无密钥主模型','provider':'custom','base_url':'https://empty.example.test/v1','model':'main-empty','role':'main','pricing':{'input_per_million_usd':1,'output_per_million_usd':1}}).json()
        t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'assistant_provider_id':empty['id']}}).json()
    else:t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'assistant_provider_id':light['id']}}).json()
    assert upgrade(client,t,light).status_code==422 and not main.routing.get(t['id']).get('upgrade') and not main.budgets.get(t['id'])['entries']


@pytest.mark.parametrize('main_started',[False,True])
def test_restart_at_upgrade_boundary_or_main_pending_never_replays_and_keeps_known_and_held_usage(client,main_started):
    t,p,light=setup(client);upgrade(client,t,light)
    first={'number':1,'status':'invalid','estimated_cost_usd':.000005,'usage':USAGE,'cost_basis':'reported_usage'}
    pending={'number':2,'status':'pending','reserved_cost_usd':.02,'usage':None}
    phases=[{'phase':'light','status':'paused','provider_id':light['id'],'model':light['model'],'attempts':[copy.deepcopy(first)],'last_response_excerpt':'KEPT INVALID JSON'}]
    if main_started:phases.append({'phase':'main_upgrade','status':'running','provider_id':p['id'],'model':p['model'],'attempts':[copy.deepcopy(pending)]})
    op={'id':'restart-operation','kind':'cases','status':'running' if main_started else 'paused','revision':t['revision'],'attempts':[first]+([pending] if main_started else []),'phases':phases,'routing':{'upgrade':{'max_model_http_requests':2,'triggered':main_started}}}
    current=main.get_task(t['id']);current['status']='planning';current['planning_runs'].append(op);main.store.put('task',t['id'],current)
    ledger=main.budgets.get(t['id'],create=True);known={'id':'first-entry','operation_id':op['id'],'provider_id':light['id'],'status':'settled','charged_usd':'.000005','reserved_usd':'.001','usage':USAGE}
    ledger['entries']=[copy.deepcopy(known)]
    if main_started:ledger['entries'].append({'id':'main-entry','operation_id':op['id'],'provider_id':p['id'],'status':'reserved','charged_usd':None,'reserved_usd':'.02','usage':None})
    main.store.put('task_budget',t['id'],ledger);main.budgets.recover();main.recover_planning()
    restored=main.get_task(t['id']);result=restored['planning_runs'][-1];entries=main.budgets.get(t['id'])['entries']
    assert restored['status']=='paused' and result['status']=='interrupted' and result['stop_reason']=='server_restart' and entries[0]==known
    assert result['phases'][0]['attempts'][0]==first and result['phases'][0]['last_response_excerpt']=='KEPT INVALID JSON'
    if main_started:
        assert entries[1]['status']=='unknown' and entries[1]['reserved_usd']=='.02' and entries[1]['charged_usd'] is None
        assert result['phases'][1]['status']=='interrupted' and result['phases'][1]['attempts'][0]['status']=='unknown_usage'
    main.budgets.recover();main.recover_planning();assert main.get_task(t['id'])==restored and main.budgets.get(t['id'])['entries']==entries
