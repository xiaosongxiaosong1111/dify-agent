import copy
import pytest,yaml
from fastapi import HTTPException
from test_api import client,approved
from test_workflow_plan import task,plan_task
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app.start_inputs import preflight,form_schema,check_values
from app.declared_types import resolve
from app.file_inputs import validate
from app import main

def row(kind='file'):
 return {'variable':'document','type':kind,'label':'资料','required':True,'hide':False,'allowed_file_types':['custom'],'allowed_file_extensions':['.pdf','.txt'],'allowed_file_upload_methods':['local_file'],**({'max_length':5} if kind=='file-list' else {})}

def plan(kind='file'):
 return {'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[row(kind)]}},{'id':'extract','type':'document-extractor','config':{'variable_selector':['start','document'],'input_type':'file' if kind=='file' else 'array[file]','empty_policy':'fail_if_missing' if kind=='file' else 'return_empty_array'}},{'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['extract','text']}]}}],'edges':[{'source':'start','target':'extract'},{'source':'extract','target':'end'}]}

@pytest.mark.parametrize('kind',['file','file-list'])
def test_native_generation_preservation_and_typed_extraction(kind):
 p=plan(kind);before=copy.deepcopy(p);content,result=compile_workflow_plan(plan_task(p));assert result['valid'],result
 root=yaml.safe_load(content);native=root['workflow']['graph']['nodes'][0]['data']['variables'][0]
 assert native==row(kind) and p==before
 assert root['workflow']['graph']['nodes'][1]['data']['is_array_file']==(kind=='file-list')
 assert resolve({n['id']:n for n in p['nodes']},['start','document'])==('file' if kind=='file' else 'array[file]')
 old=copy.deepcopy(root);assert validate_preserved(root)['valid'];assert root==old
 assert not root['workflow']['features']['file_upload']['enabled']
 assert any('上传' in x for x in result['warnings'])

@pytest.mark.parametrize('patch',[
 {'required':None},{'required':1},{'hide':True},{'default':{'upload_file_id':'fake'}},{'default':''},{'options':['a']},{'max_length':5},{'allowed_file_types':[]},{'allowed_file_types':['image']},{'allowed_file_types':['document']},{'allowed_file_extensions':[]},{'allowed_file_extensions':['.PDF']},{'allowed_file_extensions':['.*']},{'allowed_file_extensions':['.pdf','.pdf']},{'allowed_file_upload_methods':[]},{'allowed_file_upload_methods':['tool_file']},{'allowed_file_upload_methods':['local_file','local_file']},{'allowed_file_upload_methods':[{}]},{'allowed_file_extensions':[{}]},{'mystery':True}])
def test_invalid_file_declarations_do_not_change_or_guess(patch):
 r={**row(),**patch};old=copy.deepcopy(r);assert validate(r);assert r==old

@pytest.mark.parametrize('limit',[None,0,21,True,'5'])
def test_list_limit_is_explicit(limit):assert validate({**row('file-list'),'max_length':limit})

def test_document_category_requires_empty_extensions_and_metadata_kept():
 r={**row(),'allowed_file_types':['document'],'allowed_file_extensions':[],'default':None,'max_length':None,'options':[]};assert not validate(r)

@pytest.mark.parametrize('kind',['file','file-list'])
def test_runtime_and_form_refuse_fake_upload_even_with_text_only_legacy(kind):
 root=yaml.safe_load(compile_workflow_plan(plan_task(plan(kind)))[0]);before=copy.deepcopy(root)
 for action in (lambda:preflight(root,{'document':{'upload_file_id':'fake'}}),lambda:form_schema(root),lambda:check_values([row(kind)],{'document':[]})):
  with pytest.raises(ValueError,match='归属'):action()
 assert root==before

@pytest.mark.parametrize('consumer',['llm','end','template-transform'])
def test_raw_files_do_not_become_text_or_bypass_extractor(consumer):
 p=plan();node=p['nodes'][1];node['type']=consumer
 node['config']={'user_prompt':'{{#start.document#}}'} if consumer=='llm' else {'template':'{{#start.document#}}','variables':[]} if consumer=='template-transform' else {'outputs':[{'variable':'raw','value_selector':['start','document']}]}
 result=validate_plan(task(),p);assert not result['valid'] and '须先经根文档提取' in str(result['errors'])

def test_chatflow_is_not_silently_switched():
 p=plan();p['nodes'][-1].update(type='answer',config={'answer':'{{#extract.text#}}'});result=validate_plan(task('advanced-chat'),p)
 assert not result['valid'] and '根Workflow' in str(result['errors'])

def test_wrong_single_array_marker_preserved_refused():
 root=yaml.safe_load(compile_workflow_plan(plan_task(plan()))[0]);root['workflow']['graph']['nodes'][1]['data']['is_array_file']=True
 assert not validate_preserved(root)['valid']

def test_intake_and_case_contract_do_not_invent_file_samples(client):
 t=approved(client);t['workflow_plan']=plan();old=copy.deepcopy(t)
 from app.intake import topics
 assert any(x['id']=='document_processing' for x in topics(t))
 with pytest.raises(HTTPException,match='自动样例生成已暂停'):main.case_proposals.contract(t)
 assert t==old


def test_final_artifact_run_gate_precedes_records_budget_secret_and_network(client,monkeypatch):
 from test_api import create_env
 env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'file-test-app','service_api_key':'fixture-only'})
 t=approved(client,env_id=env['id']);t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json()
 main.artifact_path(t).write_text(compile_workflow_plan(plan_task(plan()))[0],encoding='utf-8');t['dify_app_id']='file-test-app';main.save_task(t)
 before=copy.deepcopy(main.get_task(t['id']));calls=[]
 async def remote(*args,**kwargs):calls.append(True);raise AssertionError('must not dispatch')
 monkeypatch.setattr(main.DifyClient,'run_workflow',remote)
 for inputs in ({},{'document':{'upload_file_id':'fake'}},{'document':'https://invalid.example/a.pdf'}):
  response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':inputs})
  assert response.status_code==422 and '归属' in response.text,response.text
  assert main.get_task(t['id'])==before and not calls


@pytest.mark.parametrize('kind',['file','file-list'])
def test_actual_file_input_changes_survive_capture_merge_reconfirm_build(client,kind):
 from test_api import create_env
 from test_dsl_roundtrip import capture,apply,APP
 from app.dsl_roundtrip import parse,digest
 env=create_env(client);t=approved(client,env_id=env['id'])
 response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':plan(kind)});assert response.status_code==200,response.text;t=response.json()
 for approval in ('requirements','configuration'):t=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':approval}).json()
 response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text;t=response.json()
 root=parse(main.artifact_path(t).read_text(encoding='utf-8'),'workflow');t.update(dify_app_id=APP,status='imported')
 t['runs'].append({'id':'file-import-fixture','kind':'import','status':'success','revision':t['revision'],'environment_id':env['id'],'result':{'app_id':APP},'dsl_baseline':copy.deepcopy(root)});main.save_task(t)
 current=copy.deepcopy(root);start=current['workflow']['graph']['nodes'][0];start['position']['x']+=15;v=start['data']['variables'][0]
 v.update(label='人工标签',description='人工确认',allowed_file_extensions=['.txt','.pdf'],allowed_file_upload_methods=['remote_url','local_file'])
 if kind=='file-list':v['max_length']=7
 assert validate_preserved(current)['valid']
 t=capture(client,t,current);response,_=apply(client,t);assert response.status_code==200,response.text;t=response.json()
 for approval in ('requirements','configuration'):t=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':approval}).json()
 response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
 final=parse(main.artifact_path(response.json()).read_text(encoding='utf-8'),'workflow');assert digest(final)==digest(current)
