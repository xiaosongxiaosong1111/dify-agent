import copy,json
import pytest
from test_api import client,approved,code_only_plan
from app import main
from app.version_restore import node_changes,preview
from app.version_node_changes import GROUPS

def plan(nodes=None,edges=None):return {'schema_version':1,'nodes':nodes or [],'edges':edges or []}
def code(identity='c',text='before'):return {'id':identity,'type':'code','title':'PRIVATE-TITLE','config':{'code':text,'code_language':'python3'}}

def test_code_changes_show_locations_and_fixed_fields_without_customer_content():
 before=plan([code('PRIVATE-ID','PRIVATE-CODE-BEFORE')]);after=copy.deepcopy(before);after['nodes'][0]['config']['code']='PRIVATE-CODE-AFTER'
 result=node_changes(before,after);row=result['details']['items'][0]
 assert result['changed']==1 and result['moved']==0
 assert row=={'change':'changed','current_path':[1],'historical_path':[1],'before_type':'代码','after_type':'代码','fields':['代码或语言']}
 assert 'PRIVATE' not in json.dumps(result,ensure_ascii=False)
 assert before['nodes'][0]['config']['code']=='PRIVATE-CODE-BEFORE'

def test_nested_positions_match_identity_and_keep_only_the_changed_child():
 before=plan([{'id':'PRIVATE-PARENT','type':'iteration','config':{'nodes':[code('PRIVATE-CHILD')]}}]);after=copy.deepcopy(before);after['nodes'][0]['config']['nodes'][0]['config']['code']='after'
 result=node_changes(before,after)
 assert result['changed']==1 and result['details']['items'][0]['current_path']==[1,1]
 assert 'PRIVATE' not in json.dumps(result)

def test_reordering_is_distinct_from_content_change_and_edges():
 before=plan([code('a'),code('b')]);after=copy.deepcopy(before);after['nodes'].reverse()
 result=node_changes(before,after)
 assert result['changed']==0 and result['moved']==2 and result['root_order_changed'] and not result['connections_changed']
 assert result['details']['items'][0]['historical_path']==[2]
 assert all(row['fields']==['节点顺序'] for row in result['details']['items'])

def test_moved_and_changed_node_is_counted_once_and_renamed_as_remove_add():
 before=plan([code('a'),code('b')]);after=copy.deepcopy(before);after['nodes'].reverse();after['nodes'][1]['title']='PRIVATE-NEW'
 result=node_changes(before,after)
 assert result['changed']==1 and result['moved']==1 and result['details']['total']==2
 row=next(r for r in result['details']['items'] if r['change']=='changed');assert row['fields']==['标题','节点顺序']
 renamed=copy.deepcopy(before);renamed['nodes'][0]['id']='new'
 result=node_changes(before,renamed)
 assert result['added']==result['removed']==1 and result['changed']==result['moved']==0

def test_container_rename_does_not_guess_its_children_are_the_same_entities():
 before=plan([{'id':'a','type':'iteration','config':{'nodes':[code('child')]}}]);after=copy.deepcopy(before);after['nodes'][0]['id']='b'
 result=node_changes(before,after);assert result['removed']==result['added']==2
 assert result['details']['total']==4

def test_unknown_type_keys_and_values_do_not_escape_as_labels():
 before=plan([{'id':'PRIVATE-ID','type':'PRIVATE-KIND','PRIVATE-ATTR':'before','config':{'PRIVATE-KEY':'before'}}]);after=copy.deepcopy(before);after['nodes'][0]['PRIVATE-ATTR']='PRIVATE-VALUE';after['nodes'][0]['config']['PRIVATE-KEY']='PRIVATE-SECRET'
 result=node_changes(before,after);row=result['details']['items'][0]
 assert row['before_type']==row['after_type']=='其它类型'
 assert row['fields']==['其它节点字段','其它配置字段']
 assert 'PRIVATE' not in json.dumps(result)

def test_customer_child_order_field_cannot_collide_with_internal_comparison_metadata():
 before=plan([{'id':'a','type':'iteration','child_order':'PRIVATE-BEFORE','config':{'nodes':[]}}]);after=copy.deepcopy(before);after['nodes'][0]['child_order']='PRIVATE-AFTER'
 result=node_changes(before,after);assert result['changed']==1
 assert result['details']['items'][0]['fields']==['其它节点字段']

def test_root_edges_and_metadata_are_reported_without_fake_node_differences():
 before=plan([code()]);after=copy.deepcopy(before);after['edges']=[{'source':'PRIVATE-A','target':'PRIVATE-B'}];after['PRIVATE-FIELD']='PRIVATE-VALUE'
 result=node_changes(before,after)
 assert result['connections_changed'] and result['other_plan_fields_changed']
 assert result['details']['total']==0 and not result['root_order_changed']
 assert 'PRIVATE' not in json.dumps(result)

def test_all_field_groups_are_bounded_and_grouped_without_raw_keys():
 a=code();b=code();a['title']='A';b['title']='B';b['type']='llm'
 for _,keys in GROUPS:
  for key in keys:a['config'][key]=0;b['config'][key]=1
 a['config']['PRIVATE-X']=0;b['config']['PRIVATE-X']=1;a['PRIVATE-OTHER']=0;b['PRIVATE-OTHER']=1
 result=node_changes(plan([a]),plan([b]));fields=result['details']['items'][0]['fields']
 assert 1<=len(fields)<=20 and len(set(fields))==len(fields)
 assert all(len(field)<=60 for field in fields)
 assert 'PRIVATE' not in json.dumps(result)

def test_first_thirty_details_are_explicitly_truncated_but_all_changes_counted():
 before=plan([code(str(i)) for i in range(45)]);after=copy.deepcopy(before)
 for node in after['nodes']:node['config']['code']='after'
 result=node_changes(before,after);details=result['details']
 assert result['changed']==45 and len(details['items'])==30 and details['total']==45 and details['omitted']==15 and details['limit']==30
 assert details['items'][-1]['current_path']==[30]

def test_two_thousand_nodes_each_side_are_counted_without_unbounded_detail_output():
 before=plan([code('a'+str(i)) for i in range(2000)]);after=plan([code('b'+str(i)) for i in range(2000)])
 result=node_changes(before,after)
 assert result['added']==result['removed']==2000 and result['details']['total']==4000
 assert len(result['details']['items'])==30 and result['details']['omitted']==3970

@pytest.mark.parametrize('bad',[{'nodes':[None]},{'nodes':[code('same'),code('same')]},{'nodes':'PRIVATE'},{'nodes':[code(str(i)) for i in range(2001)]}])
def test_unavailable_structure_never_returns_a_partial_detail_table(bad):
 result=node_changes(bad,plan([code()]));assert result['available'] is False and 'details' not in result
 assert 'PRIVATE' not in json.dumps(result)

def nest(depth):
 node=code('leaf')
 for i in range(depth-1):node={'id':str(i),'type':'iteration','config':{'nodes':[node]}}
 return plan([node])

def test_position_depth_limit_is_exact_and_does_not_drop_the_tail():
 before=nest(21);after=copy.deepcopy(before);node=after['nodes'][0]
 for _ in range(20):node=node['config']['nodes'][0]
 node['config']['code']='after';result=node_changes(before,after)
 assert result['available'] and len(result['details']['items'][0]['historical_path'])==21
 assert node_changes(nest(22),nest(22))['available'] is False

def test_api_preview_keeps_original_task_token_and_budget_without_customer_values(client):
 task=approved(client);task['workflow_plan']=code_only_plan();main.snapshot(task,'PRIVATE-LABEL');version=copy.deepcopy(task['versions'][-1]);task['workflow_plan']['nodes'][1]['config']['code']+='\n# PRIVATE-CODE';main.store.put('task',task['id'],task)
 before=copy.deepcopy(main.store.get('task',task['id']));ledger=copy.deepcopy(main.store.get('task_budget',task['id']))
 response=client.get(f"/api/tasks/{task['id']}/versions/{version['id']}/restore-preview",params={'revision':task['revision']})
 assert response.status_code==200,response.text
 expected=preview(task,version);assert response.json()==expected
 row=next(s for s in expected['sections'] if s['key']=='workflow_plan');assert row['nodes']['details']['items'][0]['current_path']==[2]
 assert 'PRIVATE' not in response.text
 assert main.store.get('task',task['id'])==before and main.store.get('task_budget',task['id'])==ledger
