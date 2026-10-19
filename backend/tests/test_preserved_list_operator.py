import copy
import pytest
from test_api import client,approved,create_env
from test_list_operator import plan
from test_dsl_roundtrip import capture,apply,APP
from app import main
from app.dsl_roundtrip import parse,digest,validate_preserved

def prepared(client,mode='workflow'):
 env=create_env(client);task=approved(client,app_type=mode,env_id=env['id']);response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan(mode)});assert response.status_code==200,response.text;task=response.json()
 for kind in ('requirements','configuration'):task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).json()
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200,response.text;task=response.json();root=parse(main.artifact_path(task).read_text(encoding='utf-8'),mode)
 task.update(dify_app_id=APP,status='imported');task['runs'].append({'id':'list-import','kind':'import','status':'success','revision':task['revision'],'environment_id':env['id'],'result':{'app_id':APP},'dsl_baseline':copy.deepcopy(root)});main.save_task(task);return task,root
def node(root,key):return next(n for n in root['workflow']['graph']['nodes'] if n['id']==key)

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_actual_filters_sorting_limits_and_layout_survive_full_roundtrip(client,mode):
 task,root=prepared(client,mode);current=copy.deepcopy(root);data=node(current,'list')['data'];data['filter_by']['conditions'][0]['value']='10';data['order_by']['value']='asc';data['limit']['size']=2;data['extract_by']={'enabled':True,'serial':'2'};node(current,'list')['position']['x']+=23
 before=copy.deepcopy(current);assert validate_preserved(current)['valid'] and current==before
 task=capture(client,task,current);response,_=apply(client,task);assert response.status_code==200,response.text;task=response.json()
 for kind in ('requirements','configuration'):task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).json()
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200,response.text;final=parse(main.artifact_path(response.json()).read_text(encoding='utf-8'),mode)
 assert digest(final)==digest(current)
 snapshot=main.case_proposals.contract(response.json())['source']['semantics'];actual=next(n for n in snapshot['nodes'] if n['id']=='list')
 assert actual['config']['filter_by']==data['filter_by'] and actual['config']['extract_by']==data['extract_by'] and actual['config']['limit']['size']==2

def test_reversed_native_node_array_still_infers_chained_list_types_without_writing_file(client):
 task,root=prepared(client);first=node(root,'list');second=copy.deepcopy(first);second['id']='list2';second['data']['variable']=['list','result'];node(root,'end')['data']['outputs'][0]['value_selector']=['list2','result'];root['workflow']['graph']['nodes'].insert(0,second);root['workflow']['graph']['edges']=[e for e in root['workflow']['graph']['edges'] if e['source']!='list'];root['workflow']['graph']['edges'] += [{'source':'list','target':'list2'},{'source':'list2','target':'end'}]
 before=copy.deepcopy(root);result=validate_preserved(root);assert result['valid'],result;assert root==before

@pytest.mark.parametrize('mutation',['source_type','source_unknown','dynamic','object_path','enabled_negative','first_record','container'])
def test_unsupported_manual_behavior_is_not_deleted_or_normalized(client,mutation):
 task,root=prepared(client);data=node(root,'list')['data']
 if mutation=='source_type':node(root,'source')['data']['outputs']['items']['type']='array[object]'
 elif mutation=='source_unknown':node(root,'source')['data']['outputs']['items']={}
 elif mutation=='dynamic':data['filter_by']['conditions'][0]['value']='{{#source.items#}}'
 elif mutation=='object_path':data['filter_by']['conditions'][0]['key']='price'
 elif mutation=='enabled_negative':data['limit']['size']=-1
 elif mutation=='first_record':node(root,'end')['data']['outputs'][0]['value_selector']=['list','first_record']
 else:node(root,'list')['parentId']='source'
 before=copy.deepcopy(root);assert not validate_preserved(root)['valid'] and root==before

def test_disabled_native_negative_sentinel_is_kept_without_enabling_or_rewriting(client):
 task,root=prepared(client);node(root,'list')['data']['limit']={'enabled':False,'size':-1};before=copy.deepcopy(root)
 assert validate_preserved(root)['valid'] and root==before

def test_scope_seven_requires_new_array_fields_confirmation(client):
 from test_assistant_routing import setup,enable,state
 task,p,light=setup(client);assert enable(client,task,light).status_code==200;old=main.routing.get(task['id']);old['scope_version']=7;main.store.put('assistant_routing',task['id'],old)
 current=state(client,task);assert current['required_scope_version']==18 and current['blocker'] and '数组处理' in current['scope_note']
 assert enable(client,task,light,scope_version=7).status_code==409
