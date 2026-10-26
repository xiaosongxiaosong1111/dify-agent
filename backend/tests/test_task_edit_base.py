import copy
import pytest
from test_api import client,approved,forbid_api_external_calls
from app import main


def test_old_edit_base_cannot_overwrite_new_requirements_or_advance_state(client):
    old=approved(client)
    newer=client.patch(f"/api/tasks/{old['id']}",json={'requirements':{'goal':'NEWER PUBLIC GOAL'}}).json()
    before=copy.deepcopy(main.store.get('task',old['id']))
    response=client.patch(f"/api/tasks/{old['id']}",json={'expected_revision':old['revision'],'requirements':{'goal':'OLD PUBLIC FORM'}})
    assert response.status_code==409,response.text
    assert main.store.get('task',old['id'])==before and before['revision']==newer['revision']
    assert 'NEWER PUBLIC GOAL' not in response.text and 'OLD PUBLIC FORM' not in response.text


def test_current_base_saves_without_persisting_guard_metadata(client):
    task=approved(client)
    r=client.patch(f"/api/tasks/{task['id']}",json={'expected_revision':task['revision'],'requirements':{'goal':'MATCHED PUBLIC GOAL'}})
    assert r.status_code==200,r.text
    saved=r.json();assert saved['revision']==task['revision']+1 and saved['requirements']['goal']=='MATCHED PUBLIC GOAL'
    assert 'expected_revision' not in saved and 'expected_revision' not in main.store.get('task',task['id'])


@pytest.mark.parametrize('value',[True,False,None,0,-1,1.0,'1',{},[]])
def test_invalid_guard_is_not_coerced_or_treated_as_legacy(client,value):
    task=approved(client);before=copy.deepcopy(main.store.get('task',task['id']))
    r=client.patch(f"/api/tasks/{task['id']}",json={'expected_revision':value,'name':'attempt'})
    assert r.status_code==422 and main.store.get('task',task['id'])==before


def test_legacy_patch_without_guard_keeps_existing_contract(client):
    task=approved(client)
    r=client.patch(f"/api/tasks/{task['id']}",json={'name':'legacy public name'})
    assert r.status_code==200 and r.json()['name']=='legacy public name'
