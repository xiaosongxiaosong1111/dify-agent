import copy
import pytest,yaml
from fastapi import HTTPException
from test_api import client,approved
from test_workflow_plan import base_plan,plan_task,task
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app.start_inputs import preflight,check_values
from app import main

@pytest.mark.parametrize('patch',[{'max_length':-1},{'max_length':True},{'max_length':'10'},{'max_length':''},{'max_length':1.5},{'max_length':9007199254740992},{'options':['a','b']},{'minimum':1},{'pattern':'.+'},{'label':False},{'description':[]},{'hide':'false'}])
def test_bad_text_metadata_not_ignored_in_plan_native_or_legacy_dispatch(patch):
 p=base_plan();p['nodes'][0]['config']['variables'][0].update(patch);before=copy.deepcopy(p);result=validate_plan(task(),p);assert not result['valid'] and p==before
 root=yaml.safe_load(compile_workflow_plan(plan_task(base_plan()))[0]);root['workflow']['graph']['nodes'][0]['data']['variables'][0].update(patch);old=copy.deepcopy(root)
 assert not validate_preserved(root)['valid'] and root==old
 with pytest.raises(ValueError):preflight(root,{'query':'正常'})
 assert root==old

@pytest.mark.parametrize('limit',[None,0,1,10])
def test_text_limit_sentinels_and_codepoint_boundary_not_coerced(limit):
 p=base_plan();p['nodes'][0]['config']['variables'][0]['max_length']=limit;content,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked
 root=yaml.safe_load(content);rows=root['workflow']['graph']['nodes'][0]['data']['variables'];assert rows[0]['max_length']==limit and type(rows[0]['max_length']) is type(limit)
 before=copy.deepcopy(root);assert validate_preserved(root)['valid'] and root==before
 check_values(rows,{'query':'😀'})
 if limit==1:
  with pytest.raises(ValueError):check_values(rows,{'query':'😀a'})
 else:check_values(rows,{'query':'😀a'})


def test_legacy_pure_text_values_and_default_semantics_are_not_changed():
 root=yaml.safe_load(compile_workflow_plan(plan_task(base_plan()))[0]);values={'legacy_extra':'保持既有纯文字路径','query':None};before=copy.deepcopy(values)
 preflight(root,values);assert values==before

@pytest.mark.parametrize('inputs,valid',[({'query':'abc'},True),({'query':'abcd'},False)])
def test_auto_case_checks_explicit_text_max_without_truncating(client,inputs,valid):
 from test_case_proposals import candidate
 t=approved(client);p=base_plan();p['nodes'][0]['config']['variables'][0]['max_length']=3;t['workflow_plan']=p
 value=candidate();value['items'][0]['case']['input']=inputs;before=copy.deepcopy(value);checked=main.case_proposals.validate(t,value)
 assert checked['valid'] is valid and value==before


def test_select_does_not_gain_text_maxlength_semantics_in_case_suggestions(client):
 from test_case_proposals import candidate
 t=approved(client);p=base_plan();p['nodes'][0]['config']['variables']=[{'variable':'query','type':'select','required':True,'options':['long-option'],'max_length':1}];t['workflow_plan']=p
 value=candidate();value['items'][0]['case']['input']={'query':'long-option'};assert main.case_proposals.validate(t,value)['valid']


def test_case_contract_refuses_bad_entry_before_model_generation(client):
 t=approved(client);p=base_plan();p['nodes'][0]['config']['variables'][0]['pattern']='secret-input-sentinel';t['workflow_plan']=p
 with pytest.raises(HTTPException) as error:main.case_proposals.contract(t)
 assert error.value.status_code==422 and 'secret-input-sentinel' not in str(error.value)

@pytest.mark.parametrize('variables',[None,[{'variable':'query','type':[]}],[{'variable':'query'},{'variable':'query'}]])
def test_legacy_final_start_shape_invalid_is_a_clear_error(variables):
 root=yaml.safe_load(compile_workflow_plan(plan_task(base_plan()))[0]);root['workflow']['graph']['nodes'][0]['data']['variables']=variables
 with pytest.raises(ValueError):preflight(root,{'query':'x'})
