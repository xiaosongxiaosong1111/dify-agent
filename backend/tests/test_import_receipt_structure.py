import copy
import pytest
from test_api import client,create_env,at22_static_task,forbid_api_external_calls
from app import main


@pytest.mark.parametrize('result',[
    None,[],['public'],True,7,'public',{},
    {'status':[],'app_id':'public-app'},
    {'status':{},'app_id':'public-app'},
    {'status':True,'app_id':'public-app'},
    {'status':'completed'},
    {'status':'completed','app_id':[]},
    {'status':'completed','app_id':{'private-synthetic':'not-an-id'}},
    {'status':'completed','app_id':True},
    {'status':'completed','app_id':123},
    {'status':'completed','app_id':''},
    {'status':'completed','app_id':'  public-id  '},
    {'status':'completed-with-warnings','app_id':'public\ninvalid'},
    {'status':'completed','app_id':'x'*201},
    {'status':'completed','app_id':'\ud800'},
],ids=['null','empty_array','array','bool','int','text','empty_object','array_status','object_status','bool_status','missing_id','array_id','object_id','bool_id','int_id','blank_id','padded_id','newline_id','large_id','unicode_id'])
def test_invalid_import_receipt_does_not_bind_app_or_leave_pending(client,monkeypatch,result):
    env=create_env(client);task=at22_static_task(client,env_id=env['id']);tid=task['id'];before=copy.deepcopy(main.get_task(tid));calls=[];content=main.artifact_path(before).read_bytes()
    async def reply(self,*a):calls.append(1);return copy.deepcopy(result)
    monkeypatch.setattr(main.DifyClient,'import_new',reply)
    response=client.post(f'/api/tasks/{tid}/import',json={'revision':task['revision']})
    assert response.status_code==502,response.text
    saved=main.get_task(tid);record=saved['runs'][-1]
    assert record['status']=='unknown' and record['outcome_unknown'] is True and record['error_code']=='import_response_invalid'
    assert record['completed_at'] and record['revision']==task['revision'] and 'result' not in record
    assert 'private-synthetic' not in response.text
    for key in ('revision','artifact','dify_app_id','requirements_confirmed','configuration_confirmed','requirements','configuration'):
        assert saved.get(key)==before.get(key)
    assert main.artifact_path(saved).read_bytes()==content
    assert client.post(f'/api/tasks/{tid}/import',json={'revision':task['revision']}).status_code==409 and calls==[1]


@pytest.mark.parametrize('status',['completed','completed-with-warnings'])
@pytest.mark.parametrize('app_id',['public-legacy-app','12b7a77e-f686-4a23-9843-830c749a13ec'])
def test_existing_valid_import_id_contract_is_preserved(client,monkeypatch,status,app_id):
    env=create_env(client);task=at22_static_task(client,env_id=env['id']);result={'status':status,'app_id':app_id,'warnings':['public']}
    async def reply(self,*a):return result
    monkeypatch.setattr(main.DifyClient,'import_new',reply)
    response=client.post(f"/api/tasks/{task['id']}/import",json={'revision':task['revision']})
    assert response.status_code==200 and response.json()['dify_app_id']==app_id
    assert response.json()['runs'][-1]['result']==result
    assert response.json()['artifact']['verification']=='static_only'


def test_explicit_non_success_receipt_keeps_existing_failure_contract(client,monkeypatch):
    env=create_env(client);task=at22_static_task(client,env_id=env['id'])
    async def reply(self,*a):return {'status':'failed','message':'PRIVATE-SYNTHETIC-REMOTE-DETAIL'}
    monkeypatch.setattr(main.DifyClient,'import_new',reply)
    response=client.post(f"/api/tasks/{task['id']}/import",json={'revision':task['revision']})
    assert response.status_code==502 and 'PRIVATE-SYNTHETIC' not in response.text
    assert main.get_task(task['id'])['runs'][-1]['status']=='failed'


@pytest.mark.parametrize('status',['pending','public-unrecognized-status','','completed '],ids=['pending','unrecognized','blank','padded'])
def test_unconfirmed_status_does_not_prove_import_failure_or_allow_duplicate_creation(client,monkeypatch,status):
    env=create_env(client);task=at22_static_task(client,env_id=env['id']);calls=[]
    async def reply(self,*a):calls.append(1);return {'status':status,'app_id':'public-not-yet-confirmed-app'}
    monkeypatch.setattr(main.DifyClient,'import_new',reply)
    payload={'revision':task['revision']};url=f"/api/tasks/{task['id']}/import"
    assert client.post(url,json=payload).status_code==502
    saved=main.get_task(task['id']);assert not saved.get('dify_app_id') and saved['runs'][-1]['status']=='unknown'
    assert client.post(url,json=payload).status_code==409 and calls==[1]
