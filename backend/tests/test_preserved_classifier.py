import copy,json
import pytest,yaml
from test_api import client,approved,create_env
from test_question_classifier import plan
from test_dsl_roundtrip import capture,apply,APP
from app import main
from app.dsl_roundtrip import parse,digest,validate_preserved
from app.case_dsl_semantics import summary
from app.conversation import memory_configuration

def prepared_classifier(client,mode='workflow'):
 env=create_env(client);task=approved(client,app_type=mode,env_id=env['id']);response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan(mode)});assert response.status_code==200,response.text
 task=response.json()
 for kind in ('requirements','configuration'):task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).json()
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200,response.text
 task=response.json();root=parse(main.artifact_path(task).read_text(encoding='utf-8'),mode);task.update(dify_app_id=APP,status='imported');task['runs'].append({'id':'classifier-import','kind':'import','status':'success','revision':task['revision'],'environment_id':env['id'],'result':{'app_id':APP},'dsl_baseline':copy.deepcopy(root)});main.save_task(task);return task,root

def classifier(root):return next(n for n in root['workflow']['graph']['nodes'] if n['id']=='route')

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_actual_classifier_edits_merge_without_recompiling_or_losing_choices(client,mode):
 task,root=prepared_classifier(client,mode);current=copy.deepcopy(root);node=classifier(current);node['data']['classes'].reverse();node['data']['classes'][0]['label']='用户调整售前';node['data']['instruction']='购买信息不足时追问，规则按当前说明。';node['data']['model']['completion_params']['temperature']=.1;node['position']['x']+=20
 if mode=='advanced-chat':node['data']['memory']=memory_configuration(mode,{'conversation_memory':True,'memory_turns':3})
 original=copy.deepcopy(current);assert validate_preserved(current)['valid']
 task=capture(client,task,current);response,_=apply(client,task);assert response.status_code==200,response.text;merged=response.json()
 for kind in ('requirements','configuration'):merged=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':merged['revision'],'kind':kind}).json()
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':merged['revision']});assert response.status_code==200,response.text
 final=parse(main.artifact_path(response.json()).read_text(encoding='utf-8'),mode);assert digest(final)==digest(current) and current==original
 semantic=main.case_proposals.contract(response.json())['source']['semantics'];item=next(n for n in semantic['nodes'] if n['id']=='route')
 assert item['config']['classes']==node['data']['classes'] and item['config']['instruction']==node['data']['instruction']
 assert semantic['classifier_fallbacks'][0]['class_id']=='sales'

@pytest.mark.parametrize('mutation',['vision','vision_null','dynamic','duplicate','missing_branch','memory','instruction_bool'])
def test_unsupported_classifier_features_are_refused_not_discarded(client,mutation):
 task,root=prepared_classifier(client);node=classifier(root)
 if mutation=='vision':node['data']['vision']={'enabled':True}
 elif mutation=='vision_null':node['data']['vision']=None
 elif mutation=='dynamic':node['data']['classes'][0]['name']='{{#sys.query#}}'
 elif mutation=='duplicate':node['data']['classes'][1]['id']='other'
 elif mutation=='missing_branch':root['workflow']['graph']['edges']=[e for e in root['workflow']['graph']['edges'] if e.get('sourceHandle')!='sales']
 elif mutation=='instruction_bool':node['data']['instruction']=False
 else:node['data']['memory']={'window':{'enabled':False}}
 before=copy.deepcopy(root);result=validate_preserved(root);assert not result['valid'] and root==before

def test_semantic_snapshot_contains_actual_classifier_configuration_not_layout(client):
 task,root=prepared_classifier(client);before=copy.deepcopy(root);value=summary(root);node=next(n for n in value['nodes'] if n['id']=='route')
 assert node['config']['classes']==classifier(root)['data']['classes'] and node['config']['query_variable_selector']==['start','query']
 assert 'position' not in json.dumps(node) and root==before
 node['config']['classes'][0]['name']='changed snapshot';assert root==before

def test_scope_five_light_route_is_blocked_until_new_classifier_range_confirmed(client):
 from test_assistant_routing import setup,enable,state
 task,p,light=setup(client);assert enable(client,task,light).status_code==200
 old=main.routing.get(task['id']);old['scope_version']=5;main.store.put('assistant_routing',task['id'],old)
 result=state(client,task);assert result['required_scope_version']==18 and result['blocker'] and '分类' in result['scope_note']
 assert enable(client,task,light,scope_version=5).status_code==409
 assert enable(client,task,light).status_code==200 and not state(client,task)['blocker']
