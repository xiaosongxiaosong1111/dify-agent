import copy,hashlib,json,uuid
import pytest
from starlette.datastructures import UploadFile
from test_api import client,create,forbid_api_external_calls
from app import main
from app.case_sets import LIMIT

def case():return {'name':'公开定义','input':{'query':'公开问题'},'required':False,'expectation':{'mode':'equals','target':'answer','expected':{'ok':True,'amount':0.2,'id':'9007199254740993'}}}
def setup(client,kind='advanced-chat'):
    task=create(client,kind);task=main.get_task(task['id']);task['test_cases']=[{'id':'original-case',**case()}];task['runs']=[{'id':'old-remote-run','kind':'run','status':'success','revision':task['revision'],'remote_resource':'DO_NOT_EXPORT_REMOTE'}];main.save_task(task);return main.get_task(task['id'])
def package(kind='advanced-chat',**extra):return {'schema_version':1,'app_type':kind,'cases':[case()],**extra}
def preview(client,task,raw=None,**kwargs):
    return client.post(f"/api/tasks/{task['id']}/test-cases/import-preview",files={'file':('公开样例.json',json.dumps(package(),ensure_ascii=False).encode() if raw is None else raw,'application/json')},data={'revision':str(task['revision']),'request_nonce':str(uuid.uuid4()),**kwargs})

def test_export_and_preview_are_readonly_definitions_not_evidence(client,monkeypatch):
    task=setup(client);before=main.store.get('task',task['id'])
    monkeypatch.setattr(main.store,'put',lambda *a,**k:pytest.fail('定义读取不能写Store'))
    monkeypatch.setattr(main.store,'secret',lambda *a,**k:pytest.fail('定义读取不能解密'))
    response=client.get(f"/api/tasks/{task['id']}/test-cases/export?revision={task['revision']}");assert response.status_code==200,response.text
    value=response.json();assert value==package() and response.headers['cache-control']=='no-store'
    assert response.headers['x-sierra-task-id']==task['id'] and response.headers['x-sierra-definitions-sha256']==hashlib.sha256(response.content).hexdigest()
    assert 'original-case' not in response.text and 'DO_NOT_EXPORT_REMOTE' not in response.text
    read=preview(client,task,response.content);assert read.status_code==200,read.text
    data=read.json();assert data['source']['sha256']==hashlib.sha256(response.content).hexdigest() and data['source']['bytes']==len(response.content)
    assert data['verification']=='case_definitions_only' and all(data[k] is False for k in ['task_changed','network_requested','model_called','run_started','business_verified'])
    assert [{k:v for k,v in c.items() if k!='id'} for c in data['cases']]==value['cases'] and data['cases'][0]['id']!='original-case'
    assert main.store.get('task',task['id'])==before

@pytest.mark.parametrize('kind',['workflow','advanced-chat','agent'])
def test_package_pins_current_type_and_regenerates_all_ids(client,kind):
    task=setup(client,kind);body=package(kind);body['cases'].append({**case(),'name':'另一例'})
    value=preview(client,task,json.dumps(body).encode()).json();assert value['app_type']==kind and len({c['id'] for c in value['cases']})==2
    assert preview(client,task,json.dumps(package('workflow' if kind!='workflow' else 'agent')).encode()).status_code==422

def test_utf8_bom_and_schema_string_keep_original_bytes_and_large_integer_schema(client):
    task=setup(client);body=package();schema='{"type":"object","properties":{"id":{"type":"integer","maximum":900719925474099312345678901}},"additionalProperties":false}'
    body['cases'][0]['expectation']={'mode':'json_schema','target':'answer','expected':schema};raw=b'\xef\xbb\xbf'+json.dumps(body,ensure_ascii=False).encode()
    value=preview(client,task,raw).json();assert value['source']['bytes']==len(raw) and value['source']['sha256']==hashlib.sha256(raw).hexdigest()
    assert value['cases'][0]['expectation']['expected']==schema

@pytest.mark.parametrize('raw',[b'{"schema_version":1,"schema_version":1,"app_type":"advanced-chat","cases":[]}',b'{"value":NaN}',b'\xffbad',b'\xff\xfe{\x00}',b'x'*(LIMIT+1),b'[]'],ids=['duplicate','nonfinite','bad_utf8','utf16','large','array'])
def test_invalid_raw_never_modifies_task(client,raw):
    task=setup(client);before=main.store.get('task',task['id']);assert preview(client,task,raw).status_code in {413,422}
    assert main.store.get('task',task['id'])==before

@pytest.mark.parametrize('mutation',['grade','id','unknown','no_required','empty','too_many','big_integer','decimal','underflow','conversation','file','secret','keywords_string','manual_extra','schema_object','name_space'])
def test_no_silent_fields_types_resources_or_rule_conversion(client,mutation):
    task=setup(client);body=package();row=body['cases'][0]
    if mutation=='grade':row['status']='passed'
    elif mutation=='id':row['id']='old-case'
    elif mutation=='unknown':body['PRIVATE_TOP_KEY']='DO_NOT_ECHO'
    elif mutation=='no_required':row.pop('required')
    elif mutation=='empty':body['cases']=[]
    elif mutation=='too_many':body['cases']=[case() for _ in range(21)]
    elif mutation=='big_integer':row['input']['n']=9007199254740993
    elif mutation in {'decimal','underflow'}:row['expectation']['expected']='REPLACE_NUMBER'
    elif mutation=='conversation':row['input']['conversation_id']='old-conversation'
    elif mutation=='file':row['input']['file']={'transfer_method':'local_file','upload_file_id':'old-upload'}
    elif mutation=='secret':row['input']['query']='Bearer PUBLIC_SYNTHETIC_TOKEN_123456'
    elif mutation=='keywords_string':row['expectation']={'mode':'contains','target':'answer','expected':'old string'}
    elif mutation=='manual_extra':row['expectation']={'mode':'manual','description':'人工核对','expected':'would be dropped'}
    elif mutation=='schema_object':row['expectation']={'mode':'json_schema','target':'answer','expected':{'type':'object'}}
    else:row['name']=' name '
    raw=json.dumps(body).replace('"REPLACE_NUMBER"','0.10000000000000001' if mutation=='decimal' else '1e-999').encode();before=main.store.get('task',task['id'])
    response=preview(client,task,raw);assert response.status_code==422,response.text
    assert 'DO_NOT_ECHO' not in response.text and 'PUBLIC_SYNTHETIC_TOKEN' not in response.text and main.store.get('task',task['id'])==before

def test_manual_keywords_multiturn_and_empty_export_boundaries(client):
    task=setup(client);body=package();row=body['cases'][0];row['expectation']={'mode':'manual','description':'核对公开回复'};row['followups']=[{'input':{'query':'追问'},'expectation':{'mode':'contains','target':'answer','expected':['公开','已知']}}]
    response=preview(client,task,json.dumps(body).encode());assert response.status_code==200,response.text
    row['followups'][0]['input']['conversation_id']='not-allowed';assert preview(client,task,json.dumps(body).encode()).status_code==422
    task['test_cases']=[];main.save_task(task);assert client.get(f"/api/tasks/{task['id']}/test-cases/export?revision={task['revision']}").status_code==422

def test_old_export_that_cannot_roundtrip_is_rejected_not_partially_written(client):
    task=setup(client);task['test_cases'][0]['expectation']={'mode':'contains','target':'answer','expected':'legacy text'};main.save_task(task);before=main.store.get('task',task['id'])
    assert client.get(f"/api/tasks/{task['id']}/test-cases/export?revision={task['revision']}").status_code==422
    assert main.store.get('task',task['id'])==before

def test_stale_revision_bad_nonce_and_duplicate_form_are_rejected(client):
    task=setup(client)
    assert preview(client,task,revision=str(task['revision']+1)).status_code==409
    for key,value in [('revision','true'),('revision','PRIVATE_REVISION'),('request_nonce','not-nonce')]:
        response=preview(client,task,**{key:value});assert response.status_code==422 and 'PRIVATE_REVISION' not in response.text
    assert preview(client,task,revision=[str(task['revision']),str(task['revision'])]).status_code==422

def test_revision_change_during_file_read_is_not_a_current_preview(client,monkeypatch):
    task=setup(client);original=UploadFile.read;expected={}
    async def read(self,*args,**kwargs):
        result=await original(self,*args,**kwargs);value=main.get_task(task['id']);value['revision']+=1;main.save_task(value);expected.update(main.store.get('task',task['id']));return result
    monkeypatch.setattr(UploadFile,'read',read);assert preview(client,task).status_code==409
    assert main.store.get('task',task['id'])==expected
