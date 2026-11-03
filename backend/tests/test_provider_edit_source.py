import copy
import pytest
from test_api import client,forbid_api_external_calls
from test_task_budget import provider
from app import main


def test_matching_edit_updates_once_and_does_not_persist_source_field(client):
    p=provider(client)
    r=client.patch(f"/api/providers/{p['id']}",json={'name':'公开新名称','expected_configuration_revision':p['configuration_revision']})
    assert r.status_code==200,r.text
    assert r.json()['configuration_revision']==p['configuration_revision']+1 and r.json()['name']=='公开新名称'
    assert 'expected_configuration_revision' not in main.store.get('provider',p['id'])
    assert main.store.secret(p['id'],'api_key')=='not-a-real-key'


def test_old_editor_cannot_overwrite_new_identity_price_or_secret(client,monkeypatch):
    p=provider(client)
    latest=client.patch(f"/api/providers/{p['id']}",json={'model':'current-public-model','api_key':'new-test-only-key','pricing':{'input_per_million_usd':3,'output_per_million_usd':4}})
    assert latest.status_code==200
    before=copy.deepcopy(main.store.get('provider',p['id']))
    def forbidden(*a,**k):pytest.fail('Stale save must stop before credential access or writes')
    with monkeypatch.context() as m:
        m.setattr(main.store,'secret',forbidden);m.setattr(main.store,'set_secret',forbidden);m.setattr(main.store,'put',forbidden)
        r=client.patch(f"/api/providers/{p['id']}",json={'model':p['model'],'api_key':'old-test-only-key','pricing':p['pricing'],'expected_configuration_revision':p['configuration_revision']})
    assert r.status_code==409 and main.store.get('provider',p['id'])==before
    assert main.store.secret(p['id'],'api_key')=='new-test-only-key'
    assert 'test-only-key' not in r.text and 'current-public-model' not in r.text


@pytest.mark.parametrize('revision',[None,True,False,-1,'1',1.0,{},[],9007199254740992],ids=['null','true','false','negative','string','float','object','array','unsafe_integer'])
def test_bad_editor_source_is_rejected_without_store_or_secret_access(client,monkeypatch,revision):
    p=provider(client);before=main.store.get('provider',p['id'])
    def forbidden(*a,**k):pytest.fail('Bad source must stop before credential access or writes')
    with monkeypatch.context() as m:
        m.setattr(main.store,'secret',forbidden);m.setattr(main.store,'set_secret',forbidden);m.setattr(main.store,'put',forbidden)
        r=client.patch(f"/api/providers/{p['id']}",json={'name':'不能保存','expected_configuration_revision':revision})
    assert r.status_code==422 and main.store.get('provider',p['id'])==before


def test_legacy_missing_revision_can_be_explicitly_bound_to_zero(client):
    p=provider(client);stored=main.store.get('provider',p['id']);stored.pop('configuration_revision');main.store.put('provider',p['id'],stored)
    r=client.patch(f"/api/providers/{p['id']}",json={'name':'旧配置明确绑定','expected_configuration_revision':0})
    assert r.status_code==200 and r.json()['configuration_revision']==1


def test_probe_does_not_invalidate_current_configuration_edit_source(client):
    p=provider(client);stored=main.store.get('provider',p['id']);stored['capabilities']['vision']='verified';main.store.put('provider',p['id'],stored)
    r=client.patch(f"/api/providers/{p['id']}",json={'name':'保留并行能力','expected_configuration_revision':p['configuration_revision']})
    assert r.status_code==200 and r.json()['capabilities']['vision']=='verified'


def test_unbound_legacy_api_remains_compatible_and_source_is_not_creation_data(client):
    p=provider(client)
    assert client.patch(f"/api/providers/{p['id']}",json={'name':'旧API兼容'}).status_code==200
    assert client.post('/api/providers',json={'name':'bad','expected_configuration_revision':0}).status_code==422


@pytest.mark.parametrize('stored',[None,True,'1',-1],ids=['null','bool','string','negative'])
def test_invalid_saved_source_never_compares_equal_or_uses_new_default(client,stored):
    p=provider(client);record=main.store.get('provider',p['id']);record['configuration_revision']=stored;main.store.put('provider',p['id'],record);before=main.store.get('provider',p['id'])
    r=client.patch(f"/api/providers/{p['id']}",json={'name':'不能保存','expected_configuration_revision':1})
    assert r.status_code==409 and main.store.get('provider',p['id'])==before
