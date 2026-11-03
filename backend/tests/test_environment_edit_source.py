import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_api import client,create,forbid_api_external_calls
from test_login import env
from app import main


def sealed():
    with main.store.connect() as conn:
        return conn.execute('SELECT id,value FROM secrets ORDER BY id').fetchall()


def test_current_environment_source_saved_and_not_persisted(client):
    e=env(client,service_api_key='not-a-real-key');t=create(client,env_id=e['id']);before=main.store.get('task',t['id'])
    r=client.patch(f"/api/environments/{e['id']}",json={'name':'公开新名','expected_connection_revision':e['connection_revision']})
    assert r.status_code==200,r.text
    assert r.json()['connection_revision']!=e['connection_revision'] and r.json()['name']=='公开新名'
    assert 'expected_connection_revision' not in main.store.get('environment',e['id']) and main.store.get('task',t['id'])==before
    assert main.store.secret(e['id'],'service_api_key')=='not-a-real-key'


def test_stale_environment_form_cannot_write_key_or_invalidate_task(client,monkeypatch):
    e=env(client,service_api_key='not-a-real-key');t=create(client,env_id=e['id'])
    assert client.patch(f"/api/environments/{e['id']}",json={'base_url':'https://new.example.com','service_api_key':'new-test-only-key'}).status_code==200
    before=main.store.get('environment',e['id']);task=main.store.get('task',t['id']);cipher=sealed()
    def forbidden(*a,**k):pytest.fail('Stale edit must stop before credentials, store writes or task invalidation')
    with monkeypatch.context() as m:
        for name in ['secret','put','put_with_secrets']:m.setattr(main.store,name,forbidden)
        m.setattr(main,'invalidate',forbidden)
        r=client.patch(f"/api/environments/{e['id']}",json={'base_url':e['base_url'],'service_api_key':'old-test-only-key','expected_connection_revision':e['connection_revision']})
    assert r.status_code==409 and main.store.get('environment',e['id'])==before and main.store.get('task',t['id'])==task and sealed()==cipher
    assert 'test-only-key' not in r.text and 'new.example' not in r.text


@pytest.mark.parametrize('source',[True,False,1,1.0,{},[],'',' ','x'*201],ids=['true','false','int','float','object','array','empty','blank','long'])
def test_bad_environment_edit_source_never_writes(client,source):
    e=env(client,service_api_key='not-a-real-key');before=main.store.get('environment',e['id']);cipher=sealed()
    r=client.patch(f"/api/environments/{e['id']}",json={'name':'不能保存','expected_connection_revision':source})
    assert r.status_code==422 and main.store.get('environment',e['id'])==before and sealed()==cipher


def test_explicit_null_only_binds_genuinely_unversioned_environment(client):
    e=env(client);r=client.patch(f"/api/environments/{e['id']}",json={'name':'不能绕过','expected_connection_revision':None});assert r.status_code==409
    old=main.store.get('environment',e['id']);old.pop('connection_revision');main.store.put('environment',e['id'],old)
    r=client.patch(f"/api/environments/{e['id']}",json={'name':'旧环境明确来源','expected_connection_revision':None})
    assert r.status_code==200 and r.json()['connection_revision']


@pytest.mark.parametrize('source',[None,True,{},''],ids=['null','bool','object','empty'])
def test_invalid_saved_environment_source_does_not_fall_back(client,source):
    e=env(client);old=main.store.get('environment',e['id']);old['connection_revision']=source;main.store.put('environment',e['id'],old)
    r=client.patch(f"/api/environments/{e['id']}",json={'name':'不能保存','expected_connection_revision':e['connection_revision']})
    assert r.status_code==409 and main.store.get('environment',e['id'])==old


def test_current_identity_change_preserves_old_task_version_and_needs_recheck(client):
    e=env(client);t=create(client,env_id=e['id'])
    r=client.patch(f"/api/environments/{e['id']}",json={'base_url':'https://new.example.com','expected_connection_revision':e['connection_revision']})
    saved=main.store.get('task',t['id'])
    assert r.status_code==200 and saved['revision']==t['revision']+1 and len(saved['versions'])==len(t['versions'])+1
    assert saved['versions'][-1]['revision']==t['revision'] and not saved['configuration_confirmed'] and saved['environment_id']==e['id']


def test_same_source_concurrent_edits_cannot_both_commit(client):
    e=env(client)
    def update(name):return client.patch(f"/api/environments/{e['id']}",json={'name':name,'expected_connection_revision':e['connection_revision']}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(update,['并发A','并发B']))
    assert sorted(results)==[200,409]


def test_unbound_legacy_api_and_create_boundary(client):
    e=env(client)
    assert client.patch(f"/api/environments/{e['id']}",json={'name':'旧API兼容'}).status_code==200
    assert client.post('/api/environments',json={'name':'bad','expected_connection_revision':None}).status_code==422
