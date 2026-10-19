import copy
import pytest
import yaml
from test_workflow_plan import task,start,end
from app.condition_settings import validate,value_refs
from app.workflow_plan import validate_plan,compile_workflow_plan

def plan(kind='string',value='订单',op='contains'):
 return {'schema_version':1,'nodes':[start(),{'id':'route','type':'if-else','config':{'cases':[{'case_id':'match','logical_operator':'and','conditions':[{'variable_selector':['start','query'],'varType':kind,'comparison_operator':op,'value':value}]}]}},{'id':'yes','type':'template-transform','config':{'template':'命中','variables':[]}},{'id':'no','type':'template-transform','config':{'template':'未命中','variables':[]}},end(selector=['yes','output']),end('end_no',['no','output'])],
 'edges':[{'source':'start','target':'route'},{'source':'route','source_handle':'match','target':'yes'},{'source':'route','source_handle':'false','target':'no'},{'source':'yes','target':'end'},{'source':'no','target':'end_no'}]}

def cfg(p):return p['nodes'][1]['config']
def cond(p):return cfg(p)['cases'][0]['conditions'][0]

@pytest.mark.parametrize('field,value',[('sub_variable_condition',{'logical_operator':'and','conditions':[]}),('key','name'),('numberVarType','variable'),('unexpected',True)])
def test_unemitted_condition_semantics_are_rejected_not_dropped(field,value):
 p=plan();cond(p)[field]=value
 result=validate_plan(task(),p)
 assert not result['valid'] and any('不会丢弃后生成' in e for e in result['errors'])
 content,result=compile_workflow_plan({**task(),'workflow_plan':p})
 assert not content and not result['valid']

@pytest.mark.parametrize('location',['config','case'])
def test_unemitted_outer_fields_are_rejected(location):
 p=plan();(cfg(p) if location=='config' else cfg(p)['cases'][0])['conditions_policy']='override'
 assert not validate_plan(task(),p)['valid']

@pytest.mark.parametrize('op',['is null','is not null'])
def test_frontend_only_null_spellings_are_not_native_operators(op):
 p=plan(op=op);result=validate_plan(task(),p)
 assert not result['valid'] and any('null／not null' in e for e in result['errors'])

@pytest.mark.parametrize('op',['null','not null'])
def test_native_null_operators_are_emitted_without_conversion(op):
 p=plan(value=None,op=op);assert validate_plan(task(),p)['valid']
 content,result=compile_workflow_plan({**task(),'workflow_plan':p});assert result['valid']
 document=yaml.safe_load(content)
 actual=next(n for n in document['workflow']['graph']['nodes'] if n['id']=='route')['data']['cases'][0]['conditions'][0]
 assert actual['comparison_operator']==op and actual['value'] is None

@pytest.mark.parametrize('value',[0,1,3.5,{'a':1},[1,2],[True]])
def test_native_union_cannot_coerce_numeric_or_unrepresentable_rhs(value):
 p=plan(value=value);result=validate_plan(task(),p)
 assert not result['valid'] and any('数值比较填写数值文本' in e for e in result['errors'])

@pytest.mark.parametrize('value',['NaN','inf','1e9999','','not-a-number','a{{#start.query#}}'])
def test_number_comparison_refuses_nonfinite_or_unparsable_text(value):
 p=plan('number',value,'>');assert any('数值' in e for e in validate(cfg(p)))

@pytest.mark.parametrize('value',['0','-1.25','1e4','{{#counter.count#}}'])
def test_valid_numeric_text_is_checked_not_rewritten(value):
 p=plan('number',value,'>');before=copy.deepcopy(p)
 assert not validate(cfg(p)) and p==before

@pytest.mark.parametrize('value',[True,False,'{{#counter.done#}}'])
def test_explicit_boolean_or_symbolic_rhs_stays_unchanged(value):
 p=plan('boolean',value,'is');before=copy.deepcopy(p)
 assert not validate(cfg(p)) and p==before

def test_bool_text_is_not_silently_converted():
 assert any('不自动把文字变布尔值' in e for e in validate(cfg(plan('boolean','false','is'))))

def test_known_source_type_mismatch_is_rejected():
 result=validate_plan(task(),plan('boolean',False,'is'))
 assert not result['valid'] and any('已声明来源类型' in e for e in result['errors'])

@pytest.mark.parametrize('value',['{{#missing.value#}}','{{#yes.output#}}','{{#start.query#broken'])
def test_rhs_template_references_must_be_real_and_dominate(value):
 result=validate_plan(task(),plan(value=value))
 assert not result['valid'] and any('value' in e for e in result['errors'])

def test_rhs_existing_reference_and_list_refs_use_existing_ref_rules():
 p=plan(value='{{#start.query#}}');assert validate_plan(task(),p)['valid']
 cond(p).update(comparison_operator='in',value=['{{#start.query#}}','订单'])
 assert validate_plan(task(),p)['valid']
 assert list(value_refs(cond(p)['value']))==[['start','query']]

def test_bounded_cases_and_conditions_are_not_truncated():
 p=plan();row=copy.deepcopy(cond(p));cfg(p)['cases'][0]['conditions']=[copy.deepcopy(row) for _ in range(65)]
 assert any('64' in e for e in validate(cfg(p)))
 cfg(p)['cases']=[copy.deepcopy(cfg(p)['cases'][0]) for _ in range(33)]
 assert any('32' in e for e in validate(cfg(p)))

def test_bad_unhashable_fields_return_validation_errors():
 p=plan();cond(p).update(varType=[],comparison_operator={})
 assert validate(cfg(p)) and not validate_plan(task(),p)['valid']

def test_loop_symbolic_rhs_is_projected_for_validation_but_native_source_is_preserved():
 from test_loop_body_graph import branch_plan
 from test_loop import task as loop_task
 p=branch_plan();row=p['nodes'][1]['config']['nodes'][0]['config']['cases'][0]['conditions'][0]
 row['value']='{{#repeat.count#}}';before=copy.deepcopy(p)
 text,result=compile_workflow_plan(loop_task(p));assert result['valid'],result['errors']
 native=yaml.safe_load(text)['workflow']['graph']['nodes']
 condition=next(n for n in native if n['id']=='route')['data']['cases'][0]['conditions'][0]
 assert condition['value']=='{{#repeat.count#}}' and p==before

def test_numeric_iteration_scope_keeps_actual_item_type_and_rhs_reference():
 from test_iteration_branches import branch_plan
 from test_iteration import task as batch_task,iteration
 p=branch_plan();c=iteration(p)
 p['nodes'][1]['config']['outputs']['items']['type']='array[number]'
 p['nodes'][1]['config']['code']='import json\ndef main(items_json: str) -> dict:\n    return {"items": json.loads(items_json)}\n'
 c['iterator_input_type']='array[number]'
 row=c['nodes'][0]['config']['cases'][0]['conditions'][0]
 row.update(varType='number',comparison_operator='≥',value='{{#batch.index#}}')
 c['nodes'][1]['config']['code']='def main(item: float, index: int) -> dict:\n    return {"result": str(item)}\n'
 before=copy.deepcopy(p);text,result=compile_workflow_plan(batch_task(p));assert result['valid'],result['errors']
 native=yaml.safe_load(text)['workflow']['graph']['nodes']
 emitted=next(n for n in native if n['id']=='route_item')['data']['cases'][0]['conditions'][0]
 assert emitted['varType']=='number' and emitted['value']=='{{#batch.index#}}' and p==before
 row['varType']='string'
 assert not validate_plan(batch_task(p),p)['valid']

def test_json_property_cannot_override_internal_scope_type_checks():
 p=plan('boolean',False,'is');p['_scope_types']={'start.query':'boolean'}
 assert not validate_plan(task(),p)['valid']
