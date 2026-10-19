import copy,json
import pytest,yaml
from test_api import client
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,digest


def plan():return {'schema_version':1,'conversation_variables':[{'name':'topic','var_type':'string','initial_value':'','description':'保存本会话最近输入','persistence_policy':'per_conversation','unwritten_policy':'retain_current'}],'nodes':[{'id':'start','type':'start','config':{'variables':[]}},{'id':'remember','type':'assigner','config':{'items':[{'variable_selector':['conversation','topic'],'input_type':'variable','operation':'over-write','value':['sys','query']}]}},{'id':'answer','type':'answer','config':{'answer':'本会话：{{#conversation.topic#}}'}}],'edges':[{'source':'start','target':'remember'},{'source':'remember','target':'answer'}]}
def task(p,mode='advanced-chat'):return {'id':'fixture-task','name':'开发对话状态','app_type':mode,'configuration':{},'workflow_plan':p}


def test_string_conversation_declaration_and_root_v2_assignment_compile_and_preserve():
    p=plan();before=copy.deepcopy(p);text,result=compile_workflow_plan(task(p));assert result['valid'],result
    root=yaml.safe_load(text);var=root['workflow']['conversation_variables'][0];node=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='remember')
    assert var['name']=='topic' and var['value_type']=='string' and var['value']=='' and len(var['id'])==36
    assert node['data']['type']=='assigner' and node['data']['version']=='2' and node['data']['items']==p['nodes'][1]['config']['items']
    assert p==before and yaml.safe_load(compile_workflow_plan(task(p))[0])['workflow']['conversation_variables']==[var]
    node['position']['x']+=10;var['description']='手工来源说明';stamp=digest(root);checked=validate_preserved(root)
    assert checked['valid'],checked
    assert digest(root)==stamp and root['workflow']['conversation_variables'][0]['id']==var['id']


@pytest.mark.parametrize('fault',['workflow','unknown_type','secret_name','duplicate_name','missing_policy','bad_initial','unknown_field','target_sys','unknown_target','number_source','unknown_mode','operation','duplicate_item','duplicate_writer','undeclared_read','reserved_namespace'])
def test_explicit_state_or_assignment_contract_is_not_guessed(fault):
    p=plan();mode='advanced-chat';r=p['conversation_variables'][0];item=p['nodes'][1]['config']['items'][0]
    if fault=='workflow':mode='workflow';p['nodes'][-1].update(type='end',config={'outputs':[]})
    elif fault=='unknown_type':r['var_type']='object'
    elif fault=='secret_name':r['name']='api_key'
    elif fault=='duplicate_name':p['conversation_variables'].append(copy.deepcopy(r))
    elif fault=='missing_policy':r.pop('unwritten_policy')
    elif fault=='bad_initial':r['initial_value']=0
    elif fault=='unknown_field':r['share_across_users']=True
    elif fault=='target_sys':item['variable_selector']=['sys','query']
    elif fault=='unknown_target':item['variable_selector']=['conversation','missing']
    elif fault=='number_source':item['value']=['start','unknown']
    elif fault=='unknown_mode':item['input_type']=False
    elif fault=='operation':item['operation']='append'
    elif fault=='duplicate_item':p['nodes'][1]['config']['items'].append(copy.deepcopy(item))
    elif fault=='duplicate_writer':
        second=copy.deepcopy(p['nodes'][1]);second['id']='remember2';p['nodes'].insert(2,second);p['edges']=[{'source':'start','target':'remember'},{'source':'remember','target':'remember2'},{'source':'remember2','target':'answer'}]
    elif fault=='undeclared_read':p['nodes'][-1]['config']['answer']='{{#conversation.missing#}}'
    else:p['nodes'][0]['id']='conversation';p['edges'][0]['source']='conversation'
    before=copy.deepcopy(p);checked=validate_plan(task(p,mode),p);assert not checked['valid'] and p==before


def test_constant_empty_reset_is_explicit_and_unknown_array_state_never_silently_dropped():
    p=plan();item=p['nodes'][1]['config']['items'][0];item.update(input_type='constant',value='')
    text,result=compile_workflow_plan(task(p));assert result['valid'],result
    root=yaml.safe_load(text);root['workflow']['conversation_variables'][0]['value_type']='array[string]';root['workflow']['conversation_variables'][0]['value']=[];stamp=digest(root)
    checked=validate_preserved(root);assert not checked['valid'] and digest(root)==stamp



def test_state_semantics_and_old_light_scope_are_explicit_not_silently_reused(client):
    from app.case_dsl_semantics import summary
    from test_assistant_routing import setup,enable,state
    from app import main
    text,checked=compile_workflow_plan(task(plan()));assert checked['valid']
    root=yaml.safe_load(text);actual=summary(root)
    assert actual['conversation_variables'][0]['name']=='topic' and actual['conversation_variables'][0]['value']==''
    assert '运行中的对话状态' in actual['conversation_state_note']
    t,p,light=setup(client);assert enable(client,t,light).status_code==200
    old=main.routing.get(t['id']);old['scope_version']=11;main.store.put('assistant_routing',t['id'],old)
    current=state(client,t);assert current['required_scope_version']==18 and current['blocker'] and '对话状态声明' in current['blocker'] or '标量状态' in current['blocker']
    assert enable(client,t,light,scope_version=11).status_code==409
    assert enable(client,t,light,scope_version=18).status_code==200



def test_same_node_current_write_dependencies_and_implicit_parallel_are_not_guessed():
    p=plan();p['nodes'][1]['config']['items'][0]['value']=['conversation','topic'];checked=validate_plan(task(p),p);assert not checked['valid'] and any('读后写' in e for e in checked['errors'])
    p=plan();p['nodes'].insert(1,{'id':'branch','type':'template-transform','config':{'template':'{{#sys.query#}}','variables':[]}});p['edges'].append({'source':'start','target':'branch'});p['edges'].append({'source':'branch','target':'answer'})
    checked=validate_plan(task(p),p);assert not checked['valid'] and any('隐式并行' in e for e in checked['errors'])


def test_conditional_unwritten_branch_retains_declared_current_state():
    p=plan();gate={'id':'choose','type':'if-else','config':{'cases':[{'case_id':'update','logical_operator':'and','conditions':[{'variable_selector':['sys','query'],'varType':'string','comparison_operator':'contains','value':'更新'}]}]}};keep={'id':'keep','type':'answer','config':{'answer':'保持：{{#conversation.topic#}}'}}
    p['nodes'].insert(1,gate);p['nodes'].append(keep);p['edges']=[{'source':'start','target':'choose'},{'source':'choose','target':'remember','source_handle':'update'},{'source':'choose','target':'keep','source_handle':'false'},{'source':'remember','target':'answer'}]
    content,checked=compile_workflow_plan(task(p));assert checked['valid'],checked
    assert yaml.safe_load(content)['workflow']['conversation_variables'][0]['value']==''



def test_unknown_native_assignment_error_policy_is_not_ignored_in_preservation():
    text,checked=compile_workflow_plan(task(plan()));assert checked['valid'];root=yaml.safe_load(text)
    next(n for n in root['workflow']['graph']['nodes'] if n['id']=='remember')['data']['error_strategy']='default-value'
    stamp=digest(root);checked=validate_preserved(root);assert not checked['valid'] and digest(root)==stamp and any('错误' in e for e in checked['errors'])



def test_existing_node_named_conversation_is_not_shadowed_when_no_state_declared():
    p={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[]}},{'id':'conversation','type':'template-transform','config':{'template':'原节点文字','variables':[]}},{'id':'answer','type':'answer','config':{'answer':'{{#conversation.output#}}'}}],'edges':[{'source':'start','target':'conversation'},{'source':'conversation','target':'answer'}]}
    assert compile_workflow_plan(task(p))[1]['valid']
    p['conversation_variables']=plan()['conversation_variables'];checked=validate_plan(task(p),p);assert not checked['valid'] and any('命名空间' in e for e in checked['errors'])
