import copy
import pytest
from test_api import client,approved,create_env
from test_parameter_extractor import plan
from test_dsl_roundtrip import capture,apply,APP
from app import main
from app.dsl_roundtrip import parse,digest,validate_preserved
from app.conversation import memory_configuration

def prepared(client,mode='workflow'):
 env=create_env(client);task=approved(client,app_type=mode,env_id=env['id']);response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan(mode)});assert response.status_code==200,response.text;task=response.json()
 for kind in ('requirements','configuration'):task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).json()
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200,response.text;task=response.json();root=parse(main.artifact_path(task).read_text(encoding='utf-8'),mode)
 task.update(dify_app_id=APP,status='imported');task['runs'].append({'id':'extract-import','kind':'import','status':'success','revision':task['revision'],'environment_id':env['id'],'result':{'app_id':APP},'dsl_baseline':copy.deepcopy(root)});main.save_task(task);return task,root

def node(root,key):return next(n for n in root['workflow']['graph']['nodes'] if n['id']==key)

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_user_extraction_rules_and_gate_survive_capture_merge_reconfirm_build(client,mode):
 task,root=prepared(client,mode);current=copy.deepcopy(root);data=node(current,'extract')['data'];data['parameters'][0]['description']='订单号必须用户给出，信息不足追问。';data['parameters'][0]['options']=['order_a','order_b'];data['instruction']='保留真实提取规则，不编造信息。';data['model']['completion_params']['temperature']=.1;node(current,'extract')['position']['x']+=17
 if mode=='advanced-chat':data['memory']=memory_configuration(mode,{'conversation_memory':True,'memory_turns':4})
 before=copy.deepcopy(current);checked=validate_preserved(current);assert checked['valid'],checked
 task=capture(client,task,current);response,_=apply(client,task);assert response.status_code==200,response.text;task=response.json()
 for kind in ('requirements','configuration'):task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).json()
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200,response.text;final=parse(main.artifact_path(response.json()).read_text(encoding='utf-8'),mode)
 assert digest(final)==digest(current) and current==before
 snapshot=main.case_proposals.contract(response.json())['source']['semantics'];actual=next(n for n in snapshot['nodes'] if n['id']=='extract')
 assert actual['config']['parameters']==data['parameters'] and actual['config']['instruction']==data['instruction']

@pytest.mark.parametrize('mutation',['bypass','wrong_flag','business_failure','common_parameter','function_call','vision','dynamic','missing_required','no_guard'])
def test_unsafe_manual_default_usage_or_missing_protection_is_not_silently_fixed(client,mutation):
 task,root=prepared(client);data=node(root,'extract')['data']
 if mutation=='bypass':next(e for e in root['workflow']['graph']['edges'] if e['source']=='extract')['target']='success'
 elif mutation=='wrong_flag':node(root,'check')['data']['cases'][0]['conditions'][0]['value']='0'
 elif mutation=='business_failure':node(root,'failure')['data']['variables']=[{'variable':'order','value_selector':['extract','order_no']}]
 elif mutation=='common_parameter':node(root,'end')['data']['outputs'][0]['value_selector']=['extract','order_no']
 elif mutation=='function_call':data['reasoning_mode']='function_call'
 elif mutation=='vision':data['vision']['enabled']=True
 elif mutation=='dynamic':data['parameters'][0]['description']='{{#sys.query#}}'
 elif mutation=='missing_required':data['parameters'][0].pop('required')
 else:root['workflow']['graph']['edges']=[e for e in root['workflow']['graph']['edges'] if e['source']!='extract']
 before=copy.deepcopy(root);assert not validate_preserved(root)['valid'] and root==before

def test_scope_six_must_reconfirm_extraction_fields_before_light_model_use(client):
 from test_assistant_routing import setup,enable,state
 task,p,light=setup(client);assert enable(client,task,light).status_code==200
 old=main.routing.get(task['id']);old['scope_version']=6;main.store.put('assistant_routing',task['id'],old)
 current=state(client,task);assert current['required_scope_version']==18 and current['blocker'] and '参数提取' in current['scope_note']
 assert enable(client,task,light,scope_version=6).status_code==409
 assert enable(client,task,light).status_code==200 and not state(client,task)['blocker']
