from concurrent.futures import ThreadPoolExecutor
import copy,re
import pytest
from test_api import client,forbid_api_external_calls
from app import main

HEADER='X-Sierra-Settings-Source'
def token(client):return client.get('/api/settings').headers.get(HEADER,'0'*64)


def test_read_source_is_stable_plain_body_compatible_and_read_only(client):
    before=main.store.get('settings','execution');r=client.get('/api/settings')
    assert set(r.json())=={'max_retries','max_minutes','max_cost_usd'} and re.fullmatch('[a-f0-9]{64}',r.headers.get(HEADER,''))
    assert r.headers['Cache-Control']=='no-store' and client.get('/api/settings').headers[HEADER]==r.headers[HEADER] and main.store.get('settings','execution')==before


def test_current_source_saves_and_returns_new_source_without_persisting_token(client):
    source=token(client);r=client.patch('/api/settings',json={'expected_source_token':source,'max_cost_usd':.25})
    assert r.status_code==200 and r.json()['max_cost_usd']==.25 and r.headers[HEADER]!=source
    assert r.headers[HEADER]==token(client) and set(main.store.get('settings','execution'))=={'max_retries','max_minutes','max_cost_usd'}


def test_stale_editor_cannot_raise_newly_lowered_cost_or_duration(client,monkeypatch):
    source=token(client);assert client.patch('/api/settings',json={'max_cost_usd':.1,'max_minutes':2}).status_code==200
    before=copy.deepcopy(main.store.get('settings','execution'))
    def forbidden(*a,**k):pytest.fail('Rejected settings must not write')
    monkeypatch.setattr(main.store,'put',forbidden)
    r=client.patch('/api/settings',json={'expected_source_token':source,'max_cost_usd':10,'max_minutes':30})
    assert r.status_code==409 and main.store.get('settings','execution')==before


@pytest.mark.parametrize('source',[None,True,1,{},[],'','x'*64,'A'*64,'0'*65],ids=['null','bool','number','object','array','empty','not_hash','uppercase','long'])
def test_invalid_source_is_rejected_without_writes(client,monkeypatch,source):
    before=main.store.get('settings','execution')
    monkeypatch.setattr(main.store,'put',lambda *a,**k:pytest.fail('Bad source must not write'))
    r=client.patch('/api/settings',json={'expected_source_token':source,'max_retries':0})
    assert r.status_code==422 and main.store.get('settings','execution')==before


@pytest.mark.parametrize('key,value',[('max_retries',True),('max_retries',1.0),('max_retries',11),('max_minutes',0),('max_cost_usd',-1),('max_minutes',10**400)],ids=['bool','float_retry','too_many','zero','negative','huge_int'])
def test_bound_invalid_value_does_not_partially_save(client,key,value):
    source=token(client);before=main.store.get('settings','execution')
    r=client.patch('/api/settings',json={'expected_source_token':source,'max_cost_usd':.25,key:value})
    assert r.status_code==422 and main.store.get('settings','execution')==before


def test_same_source_concurrent_saves_only_one_commits(client):
    source=token(client)
    def update(value):return client.patch('/api/settings',json={'expected_source_token':source,'max_cost_usd':value}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(update,[.2,.3]))
    assert sorted(responses)==[200,409]


def test_legacy_partial_api_and_internal_read_contract_remain_compatible(client):
    assert client.patch('/api/settings',json={'max_retries':0}).status_code==200
    assert set(main.get_settings())=={'max_retries','max_minutes','max_cost_usd'} and main.get_settings()['max_retries']==0
    assert client.patch('/api/settings',json={'unknown':2}).status_code==422


def test_development_origin_can_read_source_header(client):
    r=client.get('/api/settings',headers={'Origin':'http://127.0.0.1:5173'})
    assert HEADER.lower() in r.headers.get('Access-Control-Expose-Headers','').lower()


def test_legacy_huge_numeric_limit_is_safely_rejected_before_write(client):
    before=main.store.get('settings','execution')
    r=client.patch('/api/settings',json={'max_minutes':10**400})
    assert r.status_code==422 and main.store.get('settings','execution')==before
