import copy,json
import pytest
from test_planning import plan,run,USAGE
from test_loop_body_graph import branch_plan
from test_loop import task as loop_task
from test_iteration_branches import branch_plan as iteration_branch
from test_iteration import iteration,task as iteration_task
from app.planning import normalize_draft
from app.workflow_plan import validate_plan

def condition(selector):return {'variable_selector':selector,'comparison_operator':'not empty','value':''}
def route(selector):return {'id':'route_type','type':'if-else','config':{'cases':[{'case_id':'yes','logical_operator':'and','conditions':[condition(selector)]}]}}
def row(node):return node['config']['cases'][0]['conditions'][0]

@pytest.mark.parametrize('kind',['string','number','boolean','object','array[string]','array[number]','array[object]'])
def test_known_code_declaration_fills_only_missing_type(kind):
 p=plan();p['nodes'][1]['config']['outputs']['result']['type']=kind;p['nodes'].insert(2,route(['code','result']));before=copy.deepcopy(p)
 fixed,notes=normalize_draft(p);assert row(fixed['nodes'][2])['varType']==kind and p==before
 del row(fixed['nodes'][2])['varType'];assert fixed==p and notes

@pytest.mark.parametrize('kind',['unknown_type',{},None])
def test_unknown_or_malformed_code_declaration_is_not_guessed(kind):
 p=plan();p['nodes'][1]['config']['outputs']['result']['type']=kind;p['nodes'].insert(2,route(['code','result']))
 fixed,_=normalize_draft(p);assert 'varType' not in row(fixed['nodes'][2])

def test_existing_conflicting_type_is_preserved_for_validator_to_reject():
 p=plan();p['nodes'][1]['config']['outputs']['result']['type']='number';p['nodes'].insert(2,route(['code','result']));row(p['nodes'][2])['varType']='string'
 fixed,notes=normalize_draft(p);assert row(fixed['nodes'][2])['varType']=='string' and not notes

def test_duplicate_source_ids_are_not_reduced_to_last_writer_type():
 p=plan();duplicate=copy.deepcopy(p['nodes'][1]);duplicate['config']['outputs']['result']['type']='number';p['nodes'].append(duplicate);p['nodes'].insert(2,route(['code','result']))
 fixed,_=normalize_draft(p);assert 'varType' not in row(fixed['nodes'][2])

def test_loop_state_type_is_known_without_guessing_value_or_stop_rule():
 p=branch_plan();c=p['nodes'][1]['config'];row(c['nodes'][0]).pop('varType');before=copy.deepcopy(p)
 fixed,notes=normalize_draft(p);actual=row(fixed['nodes'][1]['config']['nodes'][0]);assert actual['varType']=='number' and actual['value']=='1'
 assert validate_plan(loop_task(fixed),fixed)['valid'] and p==before and any('循环内部' in n for n in notes)

def test_iteration_item_and_index_types_are_derived_from_matching_input_declarations():
 p=iteration_branch();c=iteration(p);row(c['nodes'][0]).pop('varType');fixed,notes=normalize_draft(p)
 assert row(iteration(fixed)['nodes'][0])['varType']=='string' and validate_plan(iteration_task(fixed),fixed)['valid']
 row(c['nodes'][0]).update(variable_selector=['batch','index'],comparison_operator='≥',value='0');fixed,_=normalize_draft(p)
 assert row(iteration(fixed)['nodes'][0])['varType']=='number'

def test_conflicting_iterator_element_type_is_not_filled_from_one_side():
 p=iteration_branch();c=iteration(p);c['iterator_input_type']='array[number]';row(c['nodes'][0]).pop('varType')
 fixed,_=normalize_draft(p);assert 'varType' not in row(iteration(fixed)['nodes'][0])

def test_outer_declaration_is_available_in_loop_body_but_dominance_still_checked():
 p=branch_plan();p['nodes'][0]['config']['variables']=[{'variable':'question','type':'paragraph'}];c=p['nodes'][1]['config'];row(c['nodes'][0]).update(variable_selector=['start','question'],comparison_operator='not empty',value='');row(c['nodes'][0]).pop('varType')
 fixed,_=normalize_draft(p);assert row(fixed['nodes'][1]['config']['nodes'][0])['varType']=='string' and validate_plan(loop_task(fixed),fixed)['valid']

def test_sys_query_needs_trusted_app_type_not_a_json_property():
 p=plan();p['nodes'].insert(2,route(['sys','query']));p['_mode']='advanced-chat'
 fixed,_=normalize_draft(p);assert 'varType' not in row(fixed['nodes'][2])
 fixed,_=normalize_draft(p,_mode='advanced-chat');assert row(fixed['nodes'][2])['varType']=='string'

def test_duplicate_loop_labels_are_not_guessed_or_removed():
 p=branch_plan();c=p['nodes'][1]['config'];c['loop_variables'].append(copy.deepcopy(c['loop_variables'][0]));row(c['nodes'][0]).pop('varType')
 fixed,_=normalize_draft(p);assert 'varType' not in row(fixed['nodes'][1]['config']['nodes'][0]) and len(fixed['nodes'][1]['config']['loop_variables'])==2

def test_declared_type_fill_uses_no_second_model_request():
 p=plan();p['nodes'][1]['config']['outputs']['result']['type']='number';p['nodes'].insert(2,route(['code','result']))
 def validate(candidate):return {'valid':row(candidate['nodes'][2]).get('varType')=='number','errors':[] if row(candidate['nodes'][2]).get('varType')=='number' else ['类型缺失']}
 result,op,calls,error=run([(json.dumps(p),USAGE)],validate=validate)
 assert result is not None and error is None and len(calls)==1 and any('varType=number' in n for n in op['attempts'][0]['deterministic_fixes'])

@pytest.mark.parametrize('change',['source_type_list','input_type_list','container_id_missing'])
def test_malformed_metadata_does_not_crash_normalizer_or_invent_a_type(change):
 p=branch_plan();c=p['nodes'][1]['config'];row(c['nodes'][0]).pop('varType')
 if change=='source_type_list':p['nodes'][0]['type']=[]
 elif change=='input_type_list':p['nodes'][0]['config']['variables']=[{'variable':'question','type':[]}];row(c['nodes'][0])['variable_selector']=['start','question']
 else:p['nodes'][1].pop('id')
 before=copy.deepcopy(p);fixed,_=normalize_draft(p);assert p==before
 if change!='source_type_list':assert 'varType' not in row(fixed['nodes'][1]['config']['nodes'][0])
