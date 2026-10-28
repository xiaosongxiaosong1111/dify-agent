import copy
import pytest
from fastapi import HTTPException
from test_api import client,approved
from test_retained_plan import fixture
from app import main
from app.retained_plan import saved_state


def saved():
    t=fixture();t['revision']=4;t['workflow_plan']=copy.deepcopy(t['planning_runs'][0]['last_candidate']);t['plan_stale']=False
    return t


def test_matches_after_normal_save_without_reclassifying_original_pause():
    t=saved();before=copy.deepcopy(t);r=saved_state(t,'public-run')
    assert r['comparison']=='same' and r['current_revision']==4 and r['input_revision']==3
    assert not r['plan_stale'] and not any(r[k] for k in ('task_changed','network_requested','platform_checked','business_verified'))
    assert t==before and t['planning_runs'][0]['status']=='paused'
    assert 'plan_text' not in r and 'adopted' not in r and r['verification']=='local_saved_plan_comparison'


def test_stale_saved_plan_can_match_without_becoming_current_confirmation():
    t=saved();t['plan_stale']=True;r=saved_state(t,'public-run')
    assert r['comparison']=='same' and r['plan_stale'] is True


def test_no_saved_plan_is_not_inferred_from_retained_candidate():
    t=saved();t['workflow_plan']=None;assert saved_state(t,'public-run')['comparison']=='missing'


@pytest.mark.parametrize('value',[9007199254740992,True,1,'9007199254740993'])
def test_exact_numbers_and_types_cannot_be_rounded_into_matches(value):
    t=saved();t['workflow_plan']['exact']=value;assert saved_state(t,'public-run')['comparison']=='different'


def test_object_key_order_is_not_a_change_but_list_order_is():
    t=saved();t['workflow_plan']={k:t['workflow_plan'][k] for k in reversed(t['workflow_plan'])}
    assert saved_state(t,'public-run')['comparison']=='same'
    t['workflow_plan']['nodes'].append({'id':'another'});assert saved_state(t,'public-run')['comparison']=='different'


@pytest.mark.parametrize('value',[{},[],{'n':float('nan')},{'n':float('inf')},{'text':'\ud800'},{'key':'sk-'+'A'*32},{'text':'x'*2000001}],ids=['empty','list','nan','inf','unicode','secret','size'])
def test_invalid_current_plan_does_not_claim_a_relationship_or_echo(value):
    t=saved();t['workflow_plan']=value
    with pytest.raises(HTTPException) as caught:saved_state(t,'public-run')
    assert caught.value.status_code==422 and 'sk-' not in str(caught.value.detail)


@pytest.mark.parametrize('change',['foreign_run','duplicate_run','running','wrong_kind','no_candidate','agent','bad_stale'])
def test_unsupported_or_ambiguous_sources_refused(change):
    t=saved();run='public-run'
    if change=='foreign_run':run='another-task-run'
    elif change=='duplicate_run':t['planning_runs'].append(copy.deepcopy(t['planning_runs'][0]))
    elif change=='running':t['planning_runs'][0]['status']='running'
    elif change=='wrong_kind':t['planning_runs'][0]['kind']='cases'
    elif change=='no_candidate':t['planning_runs'][0]['last_candidate']=None
    elif change=='agent':t['app_type']='agent'
    else:t['plan_stale']='false'
    with pytest.raises(HTTPException):saved_state(t,run)


def test_saved_state_api_is_local_read_only_and_never_decrypts(client,monkeypatch):
    t=approved(client);t['planning_runs']=fixture()['planning_runs'];t['planning_runs'][0]['revision']=t['revision'];t['workflow_plan']=copy.deepcopy(t['planning_runs'][0]['last_candidate']);main.store.put('task',t['id'],t)
    before=client.get('/api/tasks/'+t['id']).json();budget=copy.deepcopy(main.store.get('task_budget',t['id']))
    def forbid(*a,**kw):pytest.fail('Comparison cannot write, decrypt or call a model')
    monkeypatch.setattr(main.store,'put',forbid);monkeypatch.setattr(main.store,'secret',forbid);monkeypatch.setattr(main,'call_model',forbid)
    r=client.get('/api/tasks/'+t['id']+'/planning/public-run/saved-state')
    assert r.status_code==200 and r.headers['cache-control']=='no-store' and r.json()['comparison']=='same'
    assert client.get('/api/tasks/'+t['id']).json()==before and main.store.get('task_budget',t['id'])==budget
