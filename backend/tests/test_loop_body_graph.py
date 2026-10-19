import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,yaml
from test_loop import loop_plan,task
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import parse,validate_preserved
from app.loop_body_graph import shape
from test_preserved_loop import review


def branch_plan():
    p=loop_plan();cfg=p['nodes'][1]['config']
    cfg['nodes']=[
        {'id':'route','type':'if-else','config':{'cases':[{'case_id':'early','logical_operator':'and','conditions':[{'variable_selector':['repeat','count'],'varType':'number','comparison_operator':'<','value':'1'}]}]}},
        {'id':'small','type':'code','config':{'code_language':'python3','code':'def main(count: float) -> dict:\n    return {"next_count": count + 1}\n','variables':[{'variable':'count','value_selector':['repeat','count']}],'outputs':{'next_count':{'type':'number'}}}},
        {'id':'large','type':'code','config':{'code_language':'python3','code':'def main(count: float) -> dict:\n    return {"next_count": count + 2}\n','variables':[{'variable':'count','value_selector':['repeat','count']}],'outputs':{'next_count':{'type':'number'}}}},
        {'id':'merged','type':'variable-aggregator','config':{'variables':[['small','next_count'],['large','next_count']],'output_type':'number','selection_mode':'first_available'}}]
    cfg.update(entry_node_id='route',edges=[{'source':'route','source_handle':'early','target':'small'},{'source':'route','source_handle':'false','target':'large'},{'source':'small','target':'merged'},{'source':'large','target':'merged'}],updates=[{'variable':'count','value_selector':['merged','output']}])
    return p


def native(p=None):
    content,result=compile_workflow_plan(task(p or branch_plan()));assert result['valid'],result['errors']
    return parse(content,'workflow')


def test_conditional_loop_compiles_actual_handles_and_keeps_protection():
    p=branch_plan();before=copy.deepcopy(p);root=native(p);graph=root['workflow']['graph'];nodes={n['id']:n for n in graph['nodes']}
    links={(e['source'],e['sourceHandle'],e['target']) for e in graph['edges']}
    assert ('route','early','small') in links and ('route','false','large') in links
    assert ('repeat__loop_input','source','route') in links and ('merged','source','repeat__loop_progress') in links
    assert ('repeat__loop_progress','source','repeat__loop_update') in links
    assert ('repeat','source','end') not in links and ('repeat__loop_limit','source','end') in links
    assert nodes['repeat__loop_update']['data']['items'][0]['value']==['merged','output']
    assert nodes['small']['position']['y']!=nodes['large']['position']['y'] and nodes['repeat']['height']>250
    assert all(nodes[key]['parentId']=='repeat' and nodes[key]['data']['loop_id']=='repeat' for key in ('route','small','large','merged'))
    assert p==before


def test_node_list_order_is_not_execution_order_for_explicit_graph():
    p=branch_plan();p['nodes'][1]['config']['nodes'].reverse();root=native(p)
    nodes={n['id']:n for n in root['workflow']['graph']['nodes']}
    assert nodes['route']['position']['x']<nodes['small']['position']['x']<nodes['merged']['position']['x']
    assert shape(p['nodes'][1]['config'])['terminal']=='merged'


@pytest.mark.parametrize('change',['missing_entry','missing_edges','bad_entry','cross_edge','duplicate_edge','unknown_handle','missing_false','multiple_sinks','cycle','disconnected','implicit_fork','branch_update','wrong_state_type','foreign_aggregation','unknown_child','nested'])
def test_invalid_conditional_graph_scope_or_update_is_rejected(change):
    p=branch_plan();cfg=p['nodes'][1]['config']
    if change=='missing_entry':cfg.pop('entry_node_id')
    elif change=='missing_edges':cfg.pop('edges')
    elif change=='bad_entry':cfg['entry_node_id']='small'
    elif change=='cross_edge':cfg['edges'][0]['target']='start'
    elif change=='duplicate_edge':cfg['edges'].append(copy.deepcopy(cfg['edges'][0]))
    elif change=='unknown_handle':cfg['edges'][0]['source_handle']='unconfirmed-case'
    elif change=='missing_false':cfg['edges'].pop(1)
    elif change=='multiple_sinks':cfg['edges'].pop()
    elif change=='cycle':cfg['edges'].append({'source':'merged','target':'route'})
    elif change=='disconnected':cfg['nodes'].append({'id':'unused','type':'template-transform','config':{'template':'literal','variables':[]}})
    elif change=='implicit_fork':cfg['edges'].append({'source':'small','target':'large'})
    elif change=='branch_update':cfg['updates'][0]['value_selector']=['small','next_count']
    elif change=='wrong_state_type':cfg['nodes'][0]['config']['cases'][0]['conditions'][0]['varType']='string'
    elif change=='foreign_aggregation':cfg['nodes'][3]['config']['variables'][0]=['repeat','count']
    elif change=='unknown_child':cfg['nodes'][1]['config']['error_strategy']='default-value'
    elif change=='nested':cfg['nodes'][1]['type']='loop'
    result=validate_plan(task(p),p);assert not result['valid'],change
    assert not compile_workflow_plan(task(p))[0]


def test_chatflow_body_conditional_can_read_explicit_system_query_without_history():
    p=branch_plan();cfg=p['nodes'][1]['config'];cfg['nodes'][0]['config']['cases'][0]['conditions'][0]={'variable_selector':['sys','query'],'varType':'string','comparison_operator':'contains','value':'early'}
    p['nodes'][-1]={'id':'end','type':'answer','config':{'answer':'{{#repeat.count#}}'}}
    t=task(p);t['app_type']='advanced-chat';result=validate_plan(t,p);assert result['valid'],result['errors']


def test_preserved_conditional_loop_keeps_manual_code_branch_order_and_layout():
    root=native();nodes={n['id']:n for n in root['workflow']['graph']['nodes']}
    nodes['small']['data']['code']='def main(count: float) -> dict:\n    return {"next_count": count + 2}\n'
    nodes['merged']['data']['variables'].reverse();nodes['large']['position']['y']+=51
    root['workflow']['graph']['nodes'].reverse();root['workflow']['graph']['edges'].reverse();before=copy.deepcopy(root)
    result=validate_preserved(root,loop_reviews=review(root));assert result['valid'],result['errors'];assert root==before


@pytest.mark.parametrize('change',['missing_false','progress_bypass','update_bypass','disconnected_branch','loopback','bad_handle','outside_state','branch_update','grouped_aggregation'])
def test_preserved_loop_branch_cannot_drop_behavior_or_skip_guards(change):
    root=native();graph=root['workflow']['graph'];nodes={n['id']:n for n in graph['nodes']}
    if change=='missing_false':graph['edges']=[e for e in graph['edges'] if not(e['source']=='route' and e['sourceHandle']=='false')]
    elif change=='progress_bypass':next(e for e in graph['edges'] if e['source']=='merged')['target']='repeat__loop_update'
    elif change=='update_bypass':next(e for e in graph['edges'] if e['source']=='repeat__loop_progress')['target']='route'
    elif change=='disconnected_branch':graph['edges']=[e for e in graph['edges'] if e['target']!='large']
    elif change=='loopback':next(e for e in graph['edges'] if e['source']=='large')['target']='route'
    elif change=='bad_handle':next(e for e in graph['edges'] if e['source']=='route')['sourceHandle']='unknown'
    elif change=='outside_state':nodes['route']['data']['cases'][0]['conditions'][0]['variable_selector']=['other-loop','count']
    elif change=='branch_update':nodes['repeat__loop_update']['data']['items'][0]['value']=['small','next_count']
    elif change=='grouped_aggregation':nodes['merged']['data']['advanced_settings']['group_enabled']=True
    before=copy.deepcopy(root);result=validate_preserved(root,loop_reviews=review(root));assert not result['valid'] and root==before,change
