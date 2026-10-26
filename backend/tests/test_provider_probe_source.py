import copy
import pytest
from test_api import client,forbid_api_external_calls
from test_task_budget import provider
from app import main
from app.providers import ProviderError


@pytest.mark.parametrize('kind,valid',[('test',True),('test-json',True),('test-json',False)])
@pytest.mark.parametrize('action',['edit','delete'])
def test_old_probe_does_not_restore_modified_or_deleted_provider(client,monkeypatch,kind,valid,action):
    p=provider(client);after=[];calls=[]
    async def controlled(*args,**kwargs):
        calls.append(1)
        if action=='edit':main.patch_provider(p['id'],{'name':'NEW PUBLIC NAME','model':'new-public-model','api_key':'new-test-only-key'})
        else:main.delete_provider(p['id'])
        after.append(copy.deepcopy(main.store.get('provider',p['id'])))
        return ('{"ok":true}' if valid else 'invalid public result'),{'total_tokens':9}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/providers/{p['id']}/{kind}",json={'expected_configuration_revision':p['configuration_revision']})
    assert main.store.get('provider',p['id'])==after[0]
    assert response.status_code==200 and response.json()['current_source'] is False and response.json()['result_applied'] is False
    assert response.json()['source_configuration_revision']==p['configuration_revision'] and response.json()['usage']['total_tokens']==9 and len(calls)==1
    assert 'new-test-only-key' not in response.text and 'invalid public result' not in response.text
    if action=='edit':assert main.store.secret(p['id'],'api_key')=='new-test-only-key'


@pytest.mark.parametrize('kind,cap',[('test','text'),('test-json','structured_output')])
def test_probe_merges_current_other_capabilities_instead_of_old_snapshot(client,monkeypatch,kind,cap):
    p=provider(client)
    async def controlled(*args,**kwargs):
        latest=main.store.get('provider',p['id']);latest['capabilities']['vision']='verified';latest.setdefault('checks',{})['vision']={'marker':'PUBLIC-PARALLEL-CHECK'};main.store.put('provider',p['id'],latest)
        return '{"ok":true}',{'total_tokens':9}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/providers/{p['id']}/{kind}")
    saved=main.store.get('provider',p['id'])
    assert saved['capabilities']['vision']=='verified' and saved['checks']['vision']=={'marker':'PUBLIC-PARALLEL-CHECK'}
    assert response.status_code==200 and response.json()['current_source'] is True and response.json()['result_applied'] is True
    assert saved['capabilities'][cap]=='verified' and saved['configuration_revision']==p['configuration_revision']
    assert saved['checks'][cap]['source_configuration_revision']==p['configuration_revision']


@pytest.mark.parametrize('value',[None,True,-1,'1',1.0,{}])
def test_invalid_revision_never_dispatches(client,monkeypatch,value):
    p=provider(client);before=main.store.get('provider',p['id'])
    response=client.post(f"/api/providers/{p['id']}/test",json={'expected_configuration_revision':value})
    assert response.status_code==422 and main.store.get('provider',p['id'])==before


def test_old_frontend_revision_is_rejected_before_call(client):
    p=provider(client);main.patch_provider(p['id'],{'name':'renamed'})
    response=client.post(f"/api/providers/{p['id']}/test-json",json={'expected_configuration_revision':p['configuration_revision']})
    assert response.status_code==409


def test_unknown_body_field_is_rejected_and_legacy_no_body_still_works(client,monkeypatch):
    p=provider(client);calls=[]
    async def controlled(*args,**kwargs):calls.append(1);return '{"ok":true}',{'total_tokens':9}
    monkeypatch.setattr(main,'call_model',controlled)
    assert client.post(f"/api/providers/{p['id']}/test",json={'model':'arbitrary'}).status_code==422 and not calls
    assert client.post(f"/api/providers/{p['id']}/test").status_code==200 and len(calls)==1


def test_text_failure_does_not_rewrite_capabilities_and_json_failure_only_changes_own_check(client,monkeypatch):
    p=provider(client);before=main.store.get('provider',p['id'])
    async def failed(*args,**kwargs):raise ProviderError('公开合成网络失败')
    monkeypatch.setattr(main,'call_model',failed)
    assert client.post(f"/api/providers/{p['id']}/test").status_code==502 and main.store.get('provider',p['id'])==before
    assert client.post(f"/api/providers/{p['id']}/test-json").status_code==502
    saved=main.store.get('provider',p['id']);assert saved['capabilities']['structured_output']=='failed' and saved['configuration_revision']==before['configuration_revision']
    assert saved['capabilities']['text']==before['capabilities']['text']


def test_json_probe_does_not_accept_duplicate_fields_as_exact_fixed_object(client,monkeypatch):
    p=provider(client)
    async def controlled(*a,**kw):return '{"ok":false,"ok":true}',{'total_tokens':9}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/providers/{p['id']}/test-json")
    assert response.status_code==502 and main.store.get('provider',p['id'])['capabilities']['structured_output']=='failed'
