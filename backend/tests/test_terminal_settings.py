import copy
import pytest,yaml
from test_workflow_plan import task,base_plan
from app.workflow_plan import validate_plan,compile_workflow_plan

def terminal(p):return p['nodes'][-1]['config']

def test_duplicate_output_names_are_refused_without_mutation():
 p=base_plan();row=copy.deepcopy(terminal(p)['outputs'][0]);terminal(p)['outputs'].append(row);before=copy.deepcopy(p)
 text,result=compile_workflow_plan({**task(),'workflow_plan':p});assert not text and not result['valid'] and any('覆盖同名结果' in e for e in result['errors']);assert p==before

@pytest.mark.parametrize('value_type',['string','number','integer','boolean','object','file','array','array[string]','array[number]','array[object]','array[boolean]','array[file]','any','array[any]','Array[String]'])
def test_native_value_type_enum_is_emitted_without_rewriting(value_type):
 p=base_plan();terminal(p)['outputs'][0]['value_type']=value_type;before=copy.deepcopy(p)
 text,result=compile_workflow_plan({**task(),'workflow_plan':p});assert result['valid'],result['errors']
 assert yaml.safe_load(text)['workflow']['graph']['nodes'][-1]['data']['outputs'][0]['value_type']==value_type and p==before

def test_secret_value_type_is_not_treated_as_redaction():
 p=base_plan();terminal(p)['outputs'][0]['value_type']='secret';result=validate_plan(task(),p)
 assert result['valid'] and any('不自动脱敏' in w for w in result['warnings'])

@pytest.mark.parametrize('value',['unsupported',None,True,{},'Array[unsupported]'])
def test_invalid_output_type_is_rejected_without_coercion(value):
 p=base_plan();terminal(p)['outputs'][0]['value_type']=value;assert not validate_plan(task(),p)['valid']

@pytest.mark.parametrize('name',['','  ','x'*129])
def test_output_field_name_bounds_are_not_fixed_by_renaming(name):
 p=base_plan();terminal(p)['outputs'][0]['variable']=name;before=copy.deepcopy(p)
 assert not validate_plan(task(),p)['valid'] and p==before

def test_output_count_is_not_silently_truncated():
 p=base_plan();terminal(p)['outputs']=[{'variable':f'field_{i}','value_selector':['llm','text']} for i in range(65)]
 result=validate_plan(task(),p);assert not result['valid'] and any('64' in e for e in result['errors'])

@pytest.mark.parametrize('place',['end_config','end_output','answer_config'])
def test_unadapted_terminal_fields_cannot_be_ignored(place):
 p=base_plan('advanced-chat' if place=='answer_config' else 'workflow')
 if place=='end_output':terminal(p)['outputs'][0]['value']='constant-not-adapted'
 else:terminal(p)['unexpected_mode']='custom'
 result=validate_plan(task('advanced-chat' if place=='answer_config' else 'workflow'),p)
 assert not result['valid'] and any('未适配字段' in e for e in result['errors'])

def test_known_falsey_output_names_and_distinct_return_fields_are_kept():
 p=base_plan();terminal(p)['outputs']=[{'variable':'0','value_selector':['llm','text']},{'variable':'用户回答','value_selector':['llm','text']}]
 assert validate_plan(task(),p)['valid']
