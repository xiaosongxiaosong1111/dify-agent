import copy
import pytest
from starlette.datastructures import UploadFile
from test_api import client,create,forbid_api_external_calls
from app import main

def setup(client):
    task=create(client);main.save_task(main.get_task(task['id']));return main.get_task(task['id'])

def upload(client,task,revision):
    return client.post(f"/api/tasks/{task['id']}/materials",files={'file':('公开.txt',b'public source','text/plain')},data={} if revision is None else {'expected_revision':str(revision)})

def files(task):return set((main.DATA_ROOT/task['id']/'materials').glob('*'))

@pytest.mark.parametrize('value',['true','0','-1','1.0','1e0',' 1 ','PRIVATE_VALUE','9007199254740992'])
def test_invalid_revision_never_saves_or_echoes(client,value):
    task=setup(client);before=main.store.get('task',task['id']);old=files(task);response=upload(client,task,value)
    assert response.status_code==422 and 'PRIVATE_VALUE' not in response.text and files(task)==old and main.store.get('task',task['id'])==before

def test_optional_old_api_and_new_exact_revision_keep_uploaded_bytes_and_history(client):
    task=setup(client)
    for revision in [None,task['revision']+1]:
        before=copy.deepcopy(main.get_task(task['id']));response=upload(client,task,revision);assert response.status_code==200,response.text
        value=response.json();assert value['revision']==before['revision']+1 and value['versions'][-1]['materials']==before['materials']
        material=value['materials'][-1];assert material['text']=='public source' and material['status']=='parsed'
        assert (main.DATA_ROOT/task['id']/'materials'/(material['id']+'.txt')).read_bytes()==b'public source'
    before=main.store.get('task',task['id']);old=files(task);assert upload(client,task,task['revision']).status_code==409
    assert main.store.get('task',task['id'])==before and files(task)==old

@pytest.mark.parametrize('change',['revision','busy'])
def test_commit_preconditions_rechecked_and_unregistered_file_removed(client,monkeypatch,change):
    task=setup(client);old=files(task);original=UploadFile.read;expected={}
    async def read(self,*args,**kwargs):
        value=await original(self,*args,**kwargs);changed=main.get_task(task['id'])
        if change=='revision':changed['revision']+=1;changed['requirements']['goal']='同时保存的新目标'
        else:changed['status']='planning'
        main.save_task(changed);expected.update(main.store.get('task',task['id']));return value
    monkeypatch.setattr(UploadFile,'read',read);response=upload(client,task,task['revision'])
    assert response.status_code==409 and files(task)==old and main.store.get('task',task['id'])==expected
