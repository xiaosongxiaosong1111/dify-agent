import copy
import pytest
import yaml
from test_iteration import batch_plan,task,iteration
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app.planning import normalize_draft,preserves_scope
from test_api import client,approved


def branch_plan():
    p=batch_plan();cfg=iteration(p)
    cfg.update(entry_node_id='route_item',output_selector=['merged_item','output'],nodes=[
        {'id':'route_item','type':'if-else','config':{'cases':[{'case_id':'present','logical_operator':'and','conditions':[{'variable_selector':['batch','item'],'varType':'string','comparison_operator':'not empty','value':''}]}]}},
        {'id':'clean','type':'code','config':copy.deepcopy(batch_plan()['nodes'][2]['config']['nodes'][0]['config'])},
        {'id':'empty_item','type':'template-transform','config':{'template':'空项：{{ index }}','variables':[{'variable':'index','value_selector':['batch','index'],'value_type':'number'}]}},
        {'id':'merged_item','type':'variable-aggregator','config':{'variables':[['clean','result'],['empty_item','output']],'output_type':'string','selection_mode':'first_available'}}
    ],edges=[{'source':'route_item','target':'clean','source_handle':'present'}, {'source':'route_item','target':'empty_item','source_handle':'false'}, {'source':'clean','target':'merged_item'},{'source':'empty_item','target':'merged_item'}])
    return p


def test_per_item_branches_compile_real_inner_edges_and_scopes_not_a_sequence():
    p=branch_plan();before=copy.deepcopy(p)
    text,checked=compile_workflow_plan(task(p));assert checked['valid'],checked['errors']
    graph=yaml.safe_load(text)['workflow']['graph'];nodes={n['id']:n for n in graph['nodes']}
    edges=[(e['source'],e['target'],e['sourceHandle']) for e in graph['edges'] if e['data'].get('iteration_id')=='batch']
    assert set(edges)=={('batch__iteration_start','route_item','source'),('route_item','clean','present'),('route_item','empty_item','false'),('clean','merged_item','source'),('empty_item','merged_item','source')}
    assert nodes['route_item']['data']['cases'][0]['conditions'][0]['variable_selector']==['batch','item']
    assert nodes['merged_item']['data']['variables']==[['clean','result'],['empty_item','output']]
    assert nodes['clean']['position']['x']==nodes['empty_item']['position']['x'] and nodes['clean']['position']['y']!=nodes['empty_item']['position']['y']
    assert 'edges' not in nodes['batch']['data'] and 'entry_node_id' not in nodes['batch']['data'] and p==before
    assert validate_preserved(yaml.safe_load(text))['valid']


def test_body_array_order_is_not_execution_order_for_declared_dag():
    p=branch_plan();iteration(p)['nodes'].reverse()
    text,result=compile_workflow_plan(task(p));assert text and result['valid'],result['errors']


def test_parallel_branch_body_keeps_independence_declaration_and_ordered_output():
    p=branch_plan();iteration(p).update(is_parallel=True,parallel_nums=3,parallel_safe=True,parallel_reason='每项只做自身文本转换，没有共享写入或其他项依赖。')
    text,result=compile_workflow_plan(task(p));assert result['valid'],result['errors']
    data=next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='batch')
    assert data['is_parallel'] and data['parallel_nums']==3


@pytest.mark.parametrize('mutation',['missing_entry','bad_entry','incoming_entry','missing_edges','no_false','unknown_handle','external_edge','reserved_start','cycle','duplicate_edge','not_common_output','missing_candidate','candidate_type','external_aggregate','item_aggregate','unknown_body','extra_field','leaked_item','sibling_read'])
def test_invalid_branch_scope_and_incomplete_results_are_rejected(mutation):
    p=branch_plan();cfg=iteration(p);nodes={n['id']:n for n in cfg['nodes']}
    if mutation=='missing_entry':cfg.pop('entry_node_id')
    elif mutation=='bad_entry':cfg['entry_node_id']='unknown'
    elif mutation=='incoming_entry':cfg['edges'].append({'source':'clean','target':'route_item'})
    elif mutation=='missing_edges':cfg.pop('edges')
    elif mutation=='no_false':cfg['edges'].pop(1)
    elif mutation=='unknown_handle':cfg['edges'][0]['source_handle']='other'
    elif mutation=='external_edge':cfg['edges'][0]['target']='end'
    elif mutation=='reserved_start':cfg['edges'][0]['source']='batch__iteration_start'
    elif mutation=='cycle':cfg['edges'].append({'source':'merged_item','target':'clean'})
    elif mutation=='duplicate_edge':cfg['edges'].append(copy.deepcopy(cfg['edges'][0]))
    elif mutation=='not_common_output':cfg['output_selector']=['clean','result']
    elif mutation=='missing_candidate':nodes['merged_item']['config']['variables']=[['clean','result']]
    elif mutation=='candidate_type':nodes['merged_item']['config']['output_type']='number'
    elif mutation=='external_aggregate':nodes['merged_item']['config']['variables']=[['start','items_json']]
    elif mutation=='item_aggregate':nodes['merged_item']['config']['variables']=[['batch','item']]
    elif mutation=='unknown_body':nodes['empty_item']['type']='http-request'
    elif mutation=='extra_field':nodes['route_item']['config']['memory']={}
    elif mutation=='leaked_item':p['nodes'][-1]['config']['outputs'][0]['value_selector']=['merged_item','output']
    else:nodes['empty_item']['config']['variables'].append({'variable':'sibling','value_selector':['clean','result']})
    result=validate_plan(task(p),p);assert not result['valid'] and not compile_workflow_plan(task(p))[0]


@pytest.mark.parametrize('value',[None,{},'bad',[],[None],[{'source':'route_item','target':[]}],[{'source':'route_item','target':'clean','extra':True}]])
def test_bad_internal_edge_shape_never_crashes(value):
    p=branch_plan();iteration(p)['edges']=value
    assert not validate_plan(task(p),p)['valid']


def test_structural_repair_cannot_change_confirmed_branch_or_model_choice():
    p=branch_plan();updated,fixes=normalize_draft(p)
    assert updated==p and not fixes and preserves_scope(p,updated)
    repaired=copy.deepcopy(p);iteration(repaired)['edges'][0]['source_handle']='false'
    assert not preserves_scope(p,repaired)


def test_existing_sequential_body_is_compatible_and_does_not_need_edges():
    p=batch_plan();text,checked=compile_workflow_plan(task(p));assert text and checked['valid']
    assert validate_preserved(yaml.safe_load(text))['valid']


def test_api_save_retains_body_dag_and_requires_new_configuration_confirmation(client):
    t=approved(client);p=branch_plan()
    response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':p})
    assert response.status_code==200,response.text
    t=response.json()
    assert iteration(t['workflow_plan'])['edges']==iteration(p)['edges'] and not t['configuration_confirmed']
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind})
        assert response.status_code==200,response.text;t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']})
    assert response.status_code==200,response.text
    assert not response.json()['dify_app_id']
