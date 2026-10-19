import copy,json
import pytest,yaml
from test_api import client
from test_file_inputs import row,plan
from test_workflow_plan import task,plan_task
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app.file_inputs import validate
from app.optional_file import graph_errors,require_native
from app.file_run_flow import describe
from app.start_inputs import preflight

def optional_plan(op='exists'):
 p=plan();p['nodes'][0]['config']['variables'][0].update(required=False,allowed_file_extensions=['.txt'])
 p['nodes'][0]['config']['variables'].append({'variable':'missing_message','type':'paragraph','required':False,'default':'本次没有提供文件','max_length':2000})
 p['nodes'].insert(1,{'id':'guard','type':'if-else','config':{'cases':[{'case_id':'provided','logical_operator':'and','conditions':[{'variable_selector':['start','document'],'varType':'file','comparison_operator':op,'value':''}]}]}})
 p['nodes'].append({'id':'no_file','type':'end','config':{'outputs':[{'variable':'result','value_selector':['start','missing_message']}]}})
 p['edges']=[{'source':'start','target':'guard'},{'source':'guard','target':'extract','source_handle':'provided' if op=='exists' else 'false'},{'source':'guard','target':'no_file','source_handle':'false' if op=='exists' else 'provided'},{'source':'extract','target':'end'}]
 return p

@pytest.mark.parametrize('op',['exists','not exists'])
def test_guarded_nullable_file_round_trip_and_runtime_scope_are_explicit(op):
 p=optional_plan(op);before=copy.deepcopy(p);text,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked
 root=yaml.safe_load(text);assert p==before and validate_preserved(root)['valid']
 require_native(root);native=root['workflow']['graph']['nodes'][0]['data']['variables'][0];assert native['required'] is False
 flow=describe(root);assert flow['schema_version']==4 and flow['scenario']=='document_optional_extraction'
 assert flow['resolved_branch'] is None and flow['optional_file']['verification']=='exact_presence_branch_static_only'
 with pytest.raises(ValueError,match='归属'):preflight(root,{})
 assert root['workflow']['features']['file_upload']['enabled'] is False

@pytest.mark.parametrize('mutation',['no_guard','wrong_file','empty_operator','wrong_type','wrong_value','missing_branch_to_extract','same_target','bypass','two_cases','and_extra','or_extra','parent'])
def test_optional_extraction_cannot_be_reached_without_necessary_presence_edge(mutation):
 p=optional_plan();guard=p['nodes'][1];case=guard['config']['cases'][0];c=case['conditions'][0]
 if mutation=='no_guard':p['edges']=[{'source':'start','target':'extract'},{'source':'extract','target':'end'},{'source':'start','target':'guard'},{'source':'guard','source_handle':'provided','target':'no_file'},{'source':'guard','source_handle':'false','target':'no_file'}]
 elif mutation=='wrong_file':c['variable_selector']=['start','other']
 elif mutation=='empty_operator':c['comparison_operator']='not empty'
 elif mutation=='wrong_type':c['varType']='string'
 elif mutation=='wrong_value':c['value']='ignored-value'
 elif mutation=='missing_branch_to_extract':p['edges'][1]['source_handle']='false';p['edges'][2]['source_handle']='provided'
 elif mutation=='same_target':p['edges'][2]['target']='extract'
 elif mutation=='bypass':p['edges'].append({'source':'start','target':'extract'})
 elif mutation=='two_cases':guard['config']['cases'].append({**copy.deepcopy(case),'case_id':'another'});p['edges'].append({'source':'guard','source_handle':'another','target':'no_file'})
 elif mutation in {'and_extra','or_extra'}:case['logical_operator']='and' if mutation=='and_extra' else 'or';case['conditions'].append(copy.deepcopy(c))
 elif mutation=='parent':p['nodes'][2]['parentId']='container'
 assert graph_errors(p['nodes'],p['edges']),mutation
 if mutation!='parent':assert not validate_plan(task(),p)['valid']

def test_required_file_presence_condition_is_supported_without_nullable_claims():
 p=optional_plan();p['nodes'][0]['config']['variables'][0]['required']=True
 assert validate_plan(task(),p)['valid']

@pytest.mark.parametrize('kind,required,valid',[('file',False,True),('file',True,True),('file',None,False),('file',0,False),('file','false',False),('file-list',False,False),('file-list',True,True)])
def test_file_required_metadata_and_nullable_list_boundary(kind,required,valid):assert (not validate({**row(kind),'required':required})) is valid

def test_optional_file_cannot_go_straight_to_extractor_or_raw_end():
 p=plan();p['nodes'][0]['config']['variables'][0]['required']=False
 r=validate_plan(task(),p);assert not r['valid'] and '独立exists' in str(r['errors'])
 p['nodes'][-1]['config']['outputs'][0]['value_selector']=['start','document'];assert not validate_plan(task(),p)['valid']

def test_optional_file_declaration_and_present_branch_manual_edits_preserved():
 root=yaml.safe_load(compile_workflow_plan(plan_task(optional_plan()))[0]);root['workflow']['graph']['nodes'][1]['data']['title']='手工改的判断';root['workflow']['graph']['nodes'][0]['data']['variables'][0]['description']='用户原说明'
 old=copy.deepcopy(root);r=validate_preserved(root);assert r['valid'],r;assert root==old
 root['workflow']['graph']['edges'][2]['target']='extract'
 assert not validate_preserved(root)['valid']
 with pytest.raises(ValueError,match='存在|分支'):require_native(root)

@pytest.mark.parametrize('value',[{},[],True,1])
def test_invalid_presence_operators_do_not_throw_internal_errors(value):
 p=optional_plan();p['nodes'][1]['config']['cases'][0]['conditions'][0]['comparison_operator']=value
 assert not validate_plan(task(),p)['valid']

@pytest.mark.parametrize('policy',[{'error_strategy':'default-value'},{'default_value':[{'key':'result','value':'pretend-present'}]},{'retry_config':{'retry_enabled':True,'max_retries':2,'retry_interval':1}}])
def test_native_presence_guards_do_not_drop_error_or_retry_policies(policy):
 root=yaml.safe_load(compile_workflow_plan(plan_task(optional_plan()))[0]);root['workflow']['graph']['nodes'][1]['data'].update(policy)
 assert not validate_preserved(root)['valid']
 with pytest.raises(ValueError):require_native(root)

@pytest.mark.parametrize('index',[0,1,2,3,4])
def test_nullable_native_flow_never_projects_away_unknown_node_versions(index):
 root=yaml.safe_load(compile_workflow_plan(plan_task(optional_plan()))[0]);root['workflow']['graph']['nodes'][index]['data']['version']='unadapted'
 assert not validate_preserved(root)['valid']
 with pytest.raises(ValueError,match='版本1'):require_native(root)

@pytest.mark.parametrize('field',['conditions','logical_operator','unadapted_execution'])
def test_presence_guards_never_drop_extra_native_execution_or_legacy_fields(field):
 root=yaml.safe_load(compile_workflow_plan(plan_task(optional_plan()))[0]);root['workflow']['graph']['nodes'][1]['data'][field]='unknown'
 assert not validate_preserved(root)['valid']
