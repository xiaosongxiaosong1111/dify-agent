import copy,hashlib,json
import pytest,yaml
from test_api import client,create
from test_workflow_plan import plan_task
from test_file_structured_run import shape
from app import main
from app.file_structured_template import template
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app.file_run_flow import describe

def post(client,t,text=None,**patch):return client.post(f"/api/tasks/{t['id']}/file-structured-template",content=json.dumps({'revision':t['revision'],'schema_text':json.dumps(shape(),ensure_ascii=False) if text is None else text,'extensions':['.txt'],**patch},ensure_ascii=True),headers={'content-type':'application/json'})

def test_complete_explicit_schema_prepares_only_local_unsaved_text_without_choosing_model(client,monkeypatch):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']));s=shape();s['properties']['amount']['maximum']=900719925474099312345678901;text=json.dumps(s,ensure_ascii=False,indent=2)
 def forbidden(*args,**kwargs):pytest.fail('起步模板不能保存／解密／联网／选择或调用模型')
 monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 r=post(client,t,text,extensions=['.json','.md']);assert r.status_code==200,r.text;v=r.json();p=json.loads(v['plan_text'])
 assert v['source_schema_sha256']==hashlib.sha256(text.encode()).hexdigest() and v['plan_sha256']==hashlib.sha256(v['plan_text'].encode()).hexdigest()
 assert v['extensions']==['.json','.md'] and v['verification']=='local_structured_file_draft_only' and all(v[k] is False for k in ('network_requested','model_called','task_changed','run_authorized'))
 assert p['nodes'][2]['config']['structured_output']['schema']==s and '900719925474099312345678901' in v['plan_text'] and 'model' not in p['nodes'][2]['config']
 assert [n['type'] for n in p['nodes']]==['start','document-extractor','llm','end'] and p['nodes'][-1]['config']['outputs'][0]['value_selector']==['answer_llm','structured_output']
 assert main.get_task(t['id'])==before and not t['requirements_confirmed'] and not t['configuration_confirmed']

@pytest.mark.parametrize('extensions',[['.txt'],['.md','.csv','.json','.yaml','.yml']])
def test_template_compiles_to_native_preserved_object_flow_and_does_not_change_source(extensions):
 p=template(json.dumps(shape()),extensions);before=copy.deepcopy(p);text,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked
 root=yaml.safe_load(text);assert validate_preserved(root)['valid'] and p==before
 f=describe(root);assert f['schema_version']==5 and f['scenario']=='document_model_object' and f['structured_output']['schema']==shape()
 assert root['workflow']['graph']['nodes'][0]['data']['variables'][0]['allowed_file_extensions']==extensions

@pytest.mark.parametrize('text',['','{}','[]','null','{"type":"object","type":"array"}', '{"type":"object","properties":{},"additionalProperties":false,"maximum":1e999}',json.dumps({'type':'object','properties':{},'additionalProperties':True}),json.dumps({'type':'object','properties':{'x':{'$ref':'https://invalid.example/'}},'additionalProperties':False}),json.dumps({'type':'array','items':{'type':'string'}}),'x'*64001,'\ud800'],ids=['blank','object_missing_rules','array','null','duplicate','nonfinite','open_object','reference','array_schema','oversize','surrogate'])
def test_bad_schema_is_rejected_without_echo_repair_or_task_change(client,text):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']));r=post(client,t,text);assert r.status_code==422,r.text
 assert 'invalid.example' not in r.text and main.get_task(t['id'])==before

@pytest.mark.parametrize('extensions',[[],['.pdf'],['.txt','.txt'],['.TXT'],['.txt','.docx']])
def test_format_scope_never_widens_or_converts_unsupported_files(client,extensions):
 t=create(client);assert post(client,t,extensions=extensions).status_code==422

@pytest.mark.parametrize('key',['workflow_plan','artifact','dify_app_id','dsl_reference'])
def test_existing_content_is_never_replaced(client,key):
 t=create(client);saved=main.get_task(t['id']);saved[key]={'id':'existing'} if key!='dify_app_id' else 'existing';main.save_task(saved);before=copy.deepcopy(main.get_task(t['id']))
 assert post(client,t).status_code==409 and main.get_task(t['id'])==before

def test_wrong_app_revision_unknown_field_and_outer_duplicate_are_not_ignored(client):
 t=create(client);assert post(client,t,revision=t['revision']+1).status_code==409
 assert post(client,t,automatic_confirm=True).status_code==422
 raw='{"revision":1,"revision":2,"schema_text":"private-payload","extensions":[".txt"]}'
 r=client.post(f"/api/tasks/{t['id']}/file-structured-template",content=raw,headers={'content-type':'application/json'});assert r.status_code==422 and 'private-payload' not in r.text
 t=create(client,app_type='advanced-chat');assert post(client,t).status_code==422

def test_request_size_bound_is_explicit_and_not_silently_truncated(client):
 t=create(client);r=client.post(f"/api/tasks/{t['id']}/file-structured-template",content=b'x'*256001,headers={'content-type':'application/json'});assert r.status_code==413
