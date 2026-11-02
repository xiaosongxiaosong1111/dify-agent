"""History must not restore malformed collection identities into working tasks."""
import copy
import pytest
from fastapi.testclient import TestClient
from test_api import client
from test_version_restore import seeded,read,forbid_external_calls
from app import main
from app.version_restore import token

BAD_MATERIALS=[None,'PRIVATE-ROW',{}, {'id':None}, {'id':' '},
 {'id':'parsed','status':'parsed','name':'private','text':None},
 {'id':'parsed','status':'parsed','name':None,'text':'private'},
 {'id':'parsed','status':'parsed','name':'private','text':' '},
 {'id':'m','name':['private']}]

@pytest.mark.parametrize('field,bad',[*(('materials',x) for x in BAD_MATERIALS),*(('test_cases',x) for x in (None,1,{}, {'id':None},{'id':' '}))])
def test_malformed_items_rejected_before_preview_or_restore(client,field,bad):
 task,version=seeded(client);task['versions'][0][field]=[bad];version=task['versions'][0];main.store.put('task',task['id'],task)
 before=copy.deepcopy(main.store.get('task',task['id']));ledger=copy.deepcopy(main.store.get('task_budget',task['id']))
 assert read(client,task,version).status_code==422
 payload={'revision':task['revision'],'version_id':version['id'],'review_token':token(task,version),'acknowledge_restore':True}
 response=client.post('/api/tasks/'+task['id']+'/restore',json=payload)
 assert response.status_code==422 and 'PRIVATE' not in response.text and 'private' not in response.text
 assert main.store.get('task',task['id'])==before and main.store.get('task_budget',task['id'])==ledger

@pytest.mark.parametrize('field',['materials','test_cases'])
def test_duplicate_identity_does_not_restore_ambiguous_source(client,field):
 task,version=seeded(client);task['versions'][0][field]=[{'id':'same'},{'id':'same'}];version=task['versions'][0];main.store.put('task',task['id'],task)
 before=copy.deepcopy(main.store.get('task',task['id']))
 assert read(client,task,version).status_code==422
 payload={'revision':task['revision'],'version_id':version['id'],'review_token':token(task,version),'acknowledge_restore':True}
 assert client.post('/api/tasks/'+task['id']+'/restore',json=payload).status_code==422
 assert main.store.get('task',task['id'])==before

def test_null_item_restore_never_poison_intake(client):
 task,version=seeded(client);version=task['versions'][0];version['materials']=[None];main.store.put('task',task['id'],task)
 payload={'revision':task['revision'],'version_id':version['id'],'review_token':token(task,version),'acknowledge_restore':True}
 response=client.post('/api/tasks/'+task['id']+'/restore',json=payload)
 with TestClient(main.app,raise_server_exceptions=False) as safe:
  intake=safe.get('/api/tasks/'+task['id']+'/intake')
 print('RESTORE_STATUS',response.status_code,'INTAKE_STATUS',intake.status_code)
 assert response.status_code==422 and intake.status_code==200

@pytest.mark.parametrize('materials',[[{'id':'old'}],[{'id':'parsed','name':'public.txt','status':'parsed','text':'公开资料','reference_mode':'inspiration','extra_legacy':{'v':1}}],[]])
def test_compatible_rows_keep_exact_metadata_and_restore_normally(client,materials):
 task,version=seeded(client);task['versions'][0]['materials']=copy.deepcopy(materials);version=task['versions'][0];main.store.put('task',task['id'],task)
 preview=read(client,task,version);assert preview.status_code==200
 response=client.post('/api/tasks/'+task['id']+'/restore',json={'revision':task['revision'],'version_id':version['id'],'review_token':preview.json()['review_token'],'acknowledge_restore':True})
 assert response.status_code==200 and response.json()['materials']==materials and response.json()['test_cases']==version['test_cases']
 assert client.get('/api/tasks/'+task['id']+'/intake').status_code==200

def test_missing_legacy_materials_cannot_inherit_bad_current_items(client):
 task,version=seeded(client);task['versions'][0].pop('materials');task['materials']=[None];main.store.put('task',task['id'],task)
 before=copy.deepcopy(main.store.get('task',task['id']))
 assert read(client,task,version).status_code==422
 assert main.store.get('task',task['id'])==before