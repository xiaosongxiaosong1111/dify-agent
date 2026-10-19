import copy,json,yaml
import pytest
from test_api import client,approved,create_env
from test_preservation_extensions import http_plan
from test_dsl_roundtrip import capture,apply,APP
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import parse,digest,validate_preserved
from app.declared_types import resolve
from app.iteration import output_type
from app import main

def plan(mode='workflow'):
 p=http_plan();p['nodes'].insert(2,{'id':'documents','type':'document-extractor','config':{'variable_selector':['http','files'],'input_type':'array[file]','empty_policy':'return_empty_array'}})
 p['nodes'][-1].update(type='end' if mode=='workflow' else 'answer',config={'outputs':[{'variable':'text','value_selector':['documents','text']}]} if mode=='workflow' else {'answer':'{{#documents.text#}}'})
 p['edges']=[{'source':'start','target':'http'},{'source':'http','target':'documents'},{'source':'documents','target':p['nodes'][-1]['id']}]
 if mode=='advanced-chat':
  p['nodes'][0]['config']['variables']=[]
  p['nodes'][1]['config']=json.loads(json.dumps(p['nodes'][1]['config']).replace('{{#start.query#}}','{{#sys.query#}}'))
 return p

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_files_compile_native_selector_and_array_output_not_fake_text(client,mode):
 task=approved(client,app_type=mode);p=plan(mode);task['workflow_plan']=p;before=copy.deepcopy(p)
 content,result=compile_workflow_plan(task);assert result['valid'],result
 root=yaml.safe_load(content);data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='documents')
 assert data['variable_selector']==['http','files'] and data['is_array_file'] is True and 'input_type' not in data and 'empty_policy' not in data and p==before
 nodes={n['id']:n for n in p['nodes']};assert resolve(nodes,['documents','text'])=='array[string]' and output_type(nodes,['documents','text'])=='array[string]'
 assert not root['workflow']['features']['file_upload']['enabled'] and any('空输入返回空数组' in w for w in result['warnings'])

@pytest.mark.parametrize('mutation',['missing_source','self','body_string','code_file','single_file','unknown_type','empty_default','ocr','parser_key','sibling_source','scalar_query'])
def test_sources_and_unsupported_choices_are_not_guessed_or_coerced(client,mutation):
 task=approved(client);p=plan();cfg=p['nodes'][2]['config']
 if mutation=='missing_source':cfg['variable_selector']=['missing','files']
 elif mutation=='self':cfg['variable_selector']=['documents','text']
 elif mutation=='body_string':cfg['variable_selector']=['http','body']
 elif mutation=='code_file':p['nodes'][1]={'id':'http','type':'code','config':{'code_language':'python3','code':'def main():\n    return {"files": []}','variables':[],'outputs':{'files':{'type':'array[file]'}}}}
 elif mutation in {'single_file','unknown_type'}:cfg['input_type']='file' if mutation=='single_file' else 'unknown'
 elif mutation=='empty_default':cfg.pop('empty_policy')
 elif mutation=='ocr':cfg['ocr']=True
 elif mutation=='parser_key':cfg['api_key']='not-a-real-key'
 elif mutation=='sibling_source':p['edges']=[{'source':'start','target':'documents'},{'source':'documents','target':'http'},{'source':'http','target':p['nodes'][-1]['id']}]
 else:
  p['nodes'][-1]={'id':'end','type':'question-classifier','config':{'classes':[{'id':'a','name':'A'},{'id':'b','name':'B'}],'query_variable_selector':['documents','text'],'unmatched_policy':{'behavior':'first_class','class_id':'a'}}}
 result=validate_plan(task,p);assert not result['valid'] and result['errors']

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_actual_document_selector_layout_survive_capture_merge_and_build(client,mode):
 env=create_env(client);task=approved(client,app_type=mode,env_id=env['id']);response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan(mode)});assert response.status_code==200,response.text;task=response.json()
 for kind in ('requirements','configuration'):task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).json()
 task=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']}).json();root=parse(main.artifact_path(task).read_text(encoding='utf-8'),mode)
 task.update(dify_app_id=APP,status='imported');task['runs'].append({'id':'doc-import','kind':'import','status':'success','revision':task['revision'],'environment_id':env['id'],'result':{'app_id':APP},'dsl_baseline':copy.deepcopy(root)});main.save_task(task)
 current=copy.deepcopy(root);node=next(n for n in current['workflow']['graph']['nodes'] if n['id']=='documents');node['position']['x']+=13;node['data']['desc']='用户保留说明';before=copy.deepcopy(current)
 assert validate_preserved(current)['valid'] and current==before
 task=capture(client,task,current);response,_=apply(client,task);assert response.status_code==200,response.text;task=response.json()
 for kind in ('requirements','configuration'):task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).json()
 built=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert built.status_code==200,built.text
 final=parse(main.artifact_path(built.json()).read_text(encoding='utf-8'),mode);assert digest(final)==digest(current)
 semantics=main.case_proposals.contract(built.json())['source']['semantics'];actual=next(n for n in semantics['nodes'] if n['id']=='documents');assert actual['config']['variable_selector']==['http','files']

def test_scope_eight_requires_confirming_document_bindings_before_light_calls(client):
 from test_assistant_routing import setup,enable,state
 task,p,light=setup(client);assert enable(client,task,light).status_code==200
 old=main.routing.get(task['id']);old['scope_version']=8;main.store.put('assistant_routing',task['id'],old)
 current=state(client,task);assert current['required_scope_version']==18 and current['blocker'] and '文档提取' in current['scope_note']
 assert enable(client,task,light,scope_version=8).status_code==409

def test_document_plan_activates_parser_and_outbound_conditions_standard(client):
 from app.intake import topics
 task=approved(client);task['workflow_plan']=plan();item=next(t for t in topics(task) if t['id']=='document_processing')
 assert '外部解析服务' in item['question'] and '文件出站' in item['question'] and '额外费用' in item['question']

@pytest.mark.parametrize('error,category',[('Unstructured API URL is not configured for DOC file processing.','document_parser_service'),('Unsupported Extension Type: .png','document_format'),('Failed to download file: unavailable','document_download')])
def test_document_diagnostics_do_not_redirect_parser_credentials_to_model(error,category):
 from app.run_diagnostics import classify
 assert classify(error,'document-extractor')['category']==category
 assert classify(error,'code')['category']!=category

@pytest.mark.parametrize('marker',[None,False,1])
def test_actual_ui_array_flag_mismatch_is_not_silently_preserved_or_corrected(client,marker):
 task=approved(client);task['workflow_plan']=plan();content,result=compile_workflow_plan(task);assert result['valid']
 root=yaml.safe_load(content);data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='documents')
 if marker is None:data.pop('is_array_file')
 else:data['is_array_file']=marker
 before=copy.deepcopy(root);result=validate_preserved(root);assert not result['valid'] and 'is_array_file' in str(result['errors']) and root==before
