import copy,json
import pytest
from test_api import client,create
from app import main
from app.assistant_usage_groups import summarize


def row(identity='a',**patch):
    return {'id':identity,'provider_id':'fixture-service','model':'fixture-model','kind':'cases','modality':'text',
            'pricing':{'input_per_million_usd':1,'output_per_million_usd':2},'status':'settled','call_status':'returned',
            'charged_usd':'0.1','reserved_usd':'0.3','cost_basis':'reported_usage',
            'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12},'elapsed_seconds':0.1,**patch}


def test_all_attempt_outcomes_and_unknowns_count_without_mixing_bills_reserves_or_partial_usage():
    ledger={'entries':[
        row('a',charged_usd='1E-18'),row('b',charged_usd='0.2',call_status='failed_or_interrupted'),
        row('c',status='reserved',charged_usd=None,usage=None,elapsed_seconds=None),
        row('d',status='unknown',charged_usd=None,reserved_usd=None,call_status='interrupted_by_restart',usage=None,elapsed_seconds=None,partial_reported_usage={'prompt_tokens':999},private_error='private-sentinel'),
        row('e',status='reconciled',charged_usd='0.4',cost_basis='user_declared_bill',call_status='failed_or_interrupted',usage=None,elapsed_seconds=0.5,reconciliation={'note':'private-bill-note'})]}
    before=copy.deepcopy(ledger);v=summarize(ledger);assert v['state']=='ready' and v['record_count']==5 and len(v['groups'])==1
    m=v['totals'];assert (m['calls'],m['returned'],m['failed_or_interrupted'],m['pending'],m['outcome_unknown'])==(5,1,3,1,0)
    assert m['estimated_usd']=='0.200000000000000001' and m['declared_bill_usd']=='0.4' and m['held_usd']=='0.3'
    assert m['known_cost_count']==3 and m['unknown_cost_count']==2 and m['held_unknown_count']==1
    assert m['tokens']=={'input':{'known':20,'missing':3},'output':{'known':4,'missing':3},'total':{'known':24,'missing':3}}
    assert m['elapsed_seconds']=='0.7' and m['elapsed_missing']==2
    assert v['groups'][0]['metrics']==m and ledger==before and 'private-' not in json.dumps(v)
    assert all(v[key] is False for key in ('business_quality_verified','savings_verified','network_requested','ledger_changed','automatic_retry'))


@pytest.mark.parametrize('patch',[{'provider_id':'another'},{'model':'another'},{'kind':'plan'},{'modality':'image'},
    {'modality':None},{'pricing':None},{'pricing':{'input_per_million_usd':3,'output_per_million_usd':2}}])
def test_saved_context_and_old_price_changes_split_groups_without_current_provider_lookup(patch):
    v=summarize({'entries':[row('a'),row('b',**patch)]});assert v['state']=='ready' and len(v['groups'])==2
    assert v['totals']['calls']==2 and len({g['id'] for g in v['groups']})==2


def test_equivalent_numeric_price_snapshots_share_group_without_repricing_records():
    v=summarize({'entries':[row('a'),row('b',pricing={'output_per_million_usd':2.0,'input_per_million_usd':1.0},charged_usd='7')]})
    assert v['state']=='ready' and len(v['groups'])==1 and v['totals']['estimated_usd']=='7.1'


@pytest.mark.parametrize('patch',[{'id':None},{'provider_id':''},{'model':'\ud800'},{'kind':'private\nkind'},
    {'status':'future-private-status'},{'charged_usd':'private-amount'},{'charged_usd':'-1'},
    {'charged_usd':'NaN'},{'charged_usd':'1E-31'},{'cost_basis':'future-private-basis'},
    {'pricing':{'private-sentinel':'unknown'}},{'charged_usd':None},{'modality':'video'}])
def test_incomplete_record_never_returns_partial_totals_or_echoes_unknown_values(patch):
    ledger={'entries':[row('valid'),row('bad',**patch)]};before=copy.deepcopy(ledger);v=summarize(ledger)
    assert v['state']=='unavailable' and v['groups']==[] and v['totals'] is None and ledger==before
    assert 'private-' not in json.dumps(v)


def test_duplicate_record_id_is_not_silently_deduplicated_or_charged_twice():
    v=summarize({'entries':[row(),row()]});assert v['state']=='unavailable' and v['totals'] is None


def test_full_bounds_do_not_return_only_a_convenient_subset(monkeypatch):
    from app import assistant_usage_groups as module
    monkeypatch.setattr(module,'MAX_RECORDS',1);assert summarize({'entries':[row('a'),row('b')]})['state']=='unavailable'
    monkeypatch.setattr(module,'MAX_RECORDS',3);monkeypatch.setattr(module,'MAX_GROUPS',1)
    v=summarize({'entries':[row('a'),row('b',model='other')]});assert v['state']=='unavailable' and not v['groups'] and v['totals'] is None


def test_token_aliases_are_not_double_counted_or_reconstructed_and_missing_differs_from_zero():
    v=summarize({'entries':[row('a',usage={'prompt_tokens':10,'input_tokens':10,'completion_tokens':0,'output_tokens':0,'total_tokens':0}),
        row('b',usage={'prompt_tokens':1,'input_tokens':2,'output_tokens':True,'total_tokens':-1}),
        row('c',usage={'input_tokens':3,'output_tokens':4})]})
    assert v['state']=='ready';t=v['totals']['tokens']
    assert t=={'input':{'known':13,'missing':1},'output':{'known':4,'missing':1},'total':{'known':0,'missing':2}}


def test_decimal_sum_preserves_tiny_amount_next_to_large_saved_amount():
    v=summarize({'entries':[row('a',charged_usd='1E+60'),row('b',charged_usd='1E-30')]})
    assert v['state']=='ready'
    assert v['totals']['estimated_usd']=='1'+'0'*60+'.'+'0'*29+'1'


def test_usage_endpoint_is_revision_bound_read_only_and_task_isolated(client,monkeypatch):
    t=create(client);other=create(client);ledger=main.budgets.get(t['id']);ledger['entries']=[row()];main.store.put('task_budget',t['id'],ledger)
    before=copy.deepcopy(main.get_task(t['id']));old=copy.deepcopy(main.budgets.get(t['id']))
    def forbidden(*args,**kw):pytest.fail('历史分组不能解密、调用模型或Dify')
    monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
    url=f"/api/tasks/{t['id']}/budget/usage-summary";r=client.get(url,params={'revision':t['revision']});assert r.status_code==200,r.text
    v=r.json();assert v['task_id']==t['id'] and v['task_revision']==t['revision'] and v['state']=='ready' and v['totals']['calls']==1
    assert client.get(url,params={'revision':t['revision']+1}).status_code==409
    empty=client.get(f"/api/tasks/{other['id']}/budget/usage-summary",params={'revision':other['revision']}).json();assert empty['state']=='ready' and empty['record_count']==0 and empty['groups']==[]
    assert main.get_task(t['id'])==before and main.budgets.get(t['id'])==old
