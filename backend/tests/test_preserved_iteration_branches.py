import copy
import pytest
import yaml
from test_api import client
from test_iteration_branches import branch_plan
from test_iteration import task
from test_dsl_roundtrip import prepared,capture,apply
from app import main
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,merge,digest


def native():
    text,result=compile_workflow_plan(task(branch_plan()));assert result['valid'],result['errors']
    return yaml.safe_load(text)


def parts(root):
    graph=root['workflow']['graph'];return graph,{n['id']:n for n in graph['nodes']}


def test_native_condition_graph_reordering_and_manual_config_remain_exact():
    root=native();graph,nodes=parts(root)
    nodes['route_item']['data']['cases'][0]['conditions'][0]['comparison_operator']='empty'
    nodes['empty_item']['data']['template']='手工规则 {{ index }}'
    nodes['merged_item']['data']['variables'].reverse()
    nodes['route_item']['position']['x']+=23
    graph['nodes'].reverse();graph['edges'].reverse()
    before=copy.deepcopy(root);result=validate_preserved(root)
    assert result['valid'],result['errors']
    assert root==before and any('内部链或条件／聚合 DAG' in w for w in result['warnings'])


def test_swapped_actual_branch_targets_are_preserved_with_original_ids():
    root=native();graph,nodes=parts(root)
    for edge in graph['edges']:
        if edge['source']=='route_item':
            edge['target']='empty_item' if edge['sourceHandle']=='present' else 'clean'
            edge['data']['targetType']=nodes[edge['target']]['data']['type']
    before=copy.deepcopy(root);checked=validate_preserved(root)
    assert checked['valid'],checked['errors'];assert root==before


def test_missing_dify_type_metadata_is_inferred_only_from_explicit_source_declarations():
    root=native();_,nodes=parts(root);nodes['batch']['data'].pop('iterator_input_type');nodes['batch']['data'].pop('output_type')
    before=copy.deepcopy(root);result=validate_preserved(root)
    assert result['valid'],result['errors'];assert root==before and any('仅依据源 DSL' in w for w in result['warnings'])


@pytest.mark.parametrize('mutation',['unknown_input','explicit_null','contradiction'])
def test_missing_type_inference_never_overrides_unknown_or_contradicting_declarations(mutation):
    root=native();_,nodes=parts(root);data=nodes['batch']['data']
    data.pop('iterator_input_type')
    if mutation=='unknown_input':data['iterator_selector']=['start','items_json']
    elif mutation=='explicit_null':data['iterator_input_type']=None
    else:data['iterator_input_type']='array[number]'
    assert not validate_preserved(root)['valid']


def test_condition_edit_conflicts_require_explicit_current_or_generated_choice():
    base=native();current,generated=copy.deepcopy(base),copy.deepcopy(base)
    parts(current)[1]['route_item']['data']['cases'][0]['conditions'][0]['comparison_operator']='empty'
    parts(generated)[1]['route_item']['data']['cases'][0]['conditions'][0]['value']='new-prefix'
    result=merge(base,current,generated);assert result['unresolved']==1
    path=result['conflicts'][0]['path'];assert path.endswith('/@route_item/data/cases')
    for choice,expected in [('current',current),('generated',generated)]:
        selected=merge(base,current,generated,{path:choice});assert not selected['unresolved'] and selected['root']==expected and validate_preserved(selected['root'])['valid']


@pytest.mark.parametrize('change',['no_default','unknown_case','bad_target_handle','duplicate_start','start_branch','duplicate_edge','cross_scope','loop','wrong_scope','wrong_output','missing_candidate','candidate_type','sibling_read','item_aggregate','inner_http','parallel','skip_failure','flatten','memory'])
def test_unadapted_or_invalid_native_condition_graph_stays_intact_but_blocks_adoption(change):
    root=native();graph,nodes=parts(root);route=nodes['route_item']['data'];parent=nodes['batch']['data']
    false=next(e for e in graph['edges'] if e['source']=='route_item' and e['sourceHandle']=='false')
    start=next(e for e in graph['edges'] if e['source']=='batch__iteration_start')
    if change=='no_default':graph['edges'].remove(false)
    elif change=='unknown_case':false['sourceHandle']='unknown'
    elif change=='bad_target_handle':false['targetHandle']='other'
    elif change=='duplicate_start':graph['edges'].append(copy.deepcopy(start))
    elif change=='start_branch':start['sourceHandle']='false'
    elif change=='duplicate_edge':graph['edges'].append(copy.deepcopy(false))
    elif change=='cross_scope':false['target']='end'
    elif change=='loop':graph['edges'].append({'source':'merged_item','target':'route_item','sourceHandle':'source','targetHandle':'target','data':{'iteration_id':'batch'}})
    elif change=='wrong_scope':false['data']['iteration_id']='other'
    elif change=='wrong_output':parent['output_selector']=['clean','result']
    elif change=='missing_candidate':nodes['merged_item']['data']['variables']=[['clean','result']]
    elif change=='candidate_type':nodes['merged_item']['data']['output_type']='number'
    elif change=='sibling_read':nodes['empty_item']['data']['variables'].append({'variable':'sibling','value_selector':['clean','result']})
    elif change=='item_aggregate':nodes['merged_item']['data']['variables']=[['batch','item']]
    elif change=='inner_http':nodes['clean']['data']['type']='http-request'
    elif change=='parallel':parent.update(is_parallel=True,parallel_nums=2)
    elif change=='skip_failure':parent['error_handle_mode']='remove-abnormal-output'
    elif change=='flatten':parent['flatten_output']=True
    else:route['memory']={}
    before=copy.deepcopy(root);result=validate_preserved(root)
    assert not result['valid'] and root==before


def test_real_api_merge_and_final_file_keep_branch_rules_and_candidate_priority(client):
    t,_=prepared(client);p=branch_plan()
    response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':p});assert response.status_code==200,response.text;t=response.json()
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert response.status_code==200,response.text;t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text;t=response.json()
    root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'));graph,nodes=parts(root)
    nodes['route_item']['data']['cases'][0]['conditions'][0]['comparison_operator']='empty'
    nodes['merged_item']['data']['variables'].reverse();nodes['clean']['position']['x']+=15
    t=capture(client,t,root);response,preview=apply(client,t);assert response.status_code==200,(response.text,preview['validation']);t=response.json()
    assert not t['configuration_confirmed']
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert response.status_code==200,response.text;t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    final=yaml.safe_load(main.artifact_path(response.json()).read_text(encoding='utf-8'));assert digest(final)==digest(root) and not response.json()['dify_app_id']
