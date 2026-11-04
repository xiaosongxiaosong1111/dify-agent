import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from test_api import client, create, forbid_api_external_calls
from test_task_budget import provider
from app import main


def delete(client,p,source):
    return client.request('DELETE',f"/api/providers/{p['id']}",json={'expected_configuration_revision':source})


def test_stale_delete_preserves_latest_configuration_and_secret(client):
    p=provider(client)
    latest=client.patch(f"/api/providers/{p['id']}",json={'name':'最新公开配置','api_key':'new-test-only-key'}).json()
    before=copy.deepcopy(main.store.get('provider',p['id']))
    r=delete(client,p,p['configuration_revision'])
    assert r.status_code==409,r.text
    assert main.store.get('provider',p['id'])==before
    assert main.store.secret(p['id'],'api_key')=='new-test-only-key'
    assert latest['name'] not in r.text and 'test-only-key' not in r.text


def test_matching_delete_removes_only_selected_configuration_and_secret(client):
    p=provider(client);other=provider(client)
    before=copy.deepcopy(main.store.get('provider',other['id']))
    r=delete(client,p,p['configuration_revision'])
    assert r.status_code==200 and r.json()=={'ok':True,'deleted_id':p['id'],'configuration_revision':p['configuration_revision']}
    assert main.store.get('provider',p['id']) is None and main.store.secret(p['id'],'api_key')==''
    assert main.store.get('provider',other['id'])==before and main.store.secret(other['id'],'api_key')=='not-a-real-key'


@pytest.mark.parametrize('source',[None,True,False,-1,'1',1.0,{},[],9007199254740992],ids=['null','true','false','negative','string','float','object','array','unsafe'])
def test_bad_delete_source_stops_before_deletion_or_secret_access(client,monkeypatch,source):
    p=provider(client);before=copy.deepcopy(main.store.get('provider',p['id']))
    def forbidden(*a,**k):pytest.fail('Invalid source must not delete or inspect secrets')
    with monkeypatch.context() as m:
        m.setattr(main.store,'delete',forbidden);m.setattr(main.store,'secret',forbidden)
        r=delete(client,p,source)
    assert r.status_code==422 and main.store.get('provider',p['id'])==before


@pytest.mark.parametrize('payload',[{}, {'unexpected':'public'}, {'expected_configuration_revision':1,'api_key':'public-test-only'}])
def test_unknown_or_empty_delete_body_is_not_an_unbound_legacy_request(client,payload):
    p=provider(client);r=client.request('DELETE',f"/api/providers/{p['id']}",json=payload)
    assert r.status_code==422 and main.store.get('provider',p['id']) is not None
    assert 'public-test-only' not in r.text


def test_bound_missing_model_is_not_reported_as_newly_deleted(client):
    p=provider(client);main.store.delete('provider',p['id'])
    assert delete(client,p,p['configuration_revision']).status_code==404
    assert client.delete(f"/api/providers/{p['id']}").json()=={'ok':True}


def test_legacy_record_can_bind_zero_and_unbound_api_remains_compatible(client):
    p=provider(client);stored=main.store.get('provider',p['id']);stored.pop('configuration_revision');main.store.put('provider',p['id'],stored)
    assert delete(client,p,0).status_code==200
    p=provider(client)
    assert client.delete(f"/api/providers/{p['id']}").json()=={'ok':True}


@pytest.mark.parametrize('source',[None,True,'1',-1],ids=['null','bool','string','negative'])
def test_bad_stored_version_never_authorizes_bound_delete(client,source):
    p=provider(client);stored=main.store.get('provider',p['id']);stored['configuration_revision']=source;main.store.put('provider',p['id'],stored)
    assert delete(client,p,1).status_code==409 and main.store.get('provider',p['id'])==stored


def test_matching_source_keeps_task_reference_guard(client):
    p=provider(client);t=create(client);t['configuration']['assistant_provider_id']=p['id'];main.store.put('task',t['id'],t)
    before=copy.deepcopy(main.store.get('task',t['id']))
    assert delete(client,p,p['configuration_revision']).status_code==409
    assert main.store.get('provider',p['id']) is not None and main.store.get('task',t['id'])==before


def test_edit_and_delete_use_same_lock_and_only_one_original_intent_wins(client):
    p=provider(client);barrier=Barrier(2)
    def edit():
        barrier.wait();return client.patch(f"/api/providers/{p['id']}",json={'name':'并发公开配置','expected_configuration_revision':p['configuration_revision']}).status_code
    def remove():
        barrier.wait();return delete(client,p,p['configuration_revision']).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(edit);b=pool.submit(remove);pair=(a.result(),b.result())
    assert pair in {(200,409),(404,200)}
    if pair[0]==200:
        assert main.store.get('provider',p['id'])['name']=='并发公开配置' and main.store.secret(p['id'],'api_key')=='not-a-real-key'
    else:assert main.store.get('provider',p['id']) is None and main.store.secret(p['id'],'api_key')==''
