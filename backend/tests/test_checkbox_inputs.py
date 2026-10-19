import copy
import pytest,yaml
from test_api import client,approved
from test_workflow_plan import base_plan,plan_task,task
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved
from app.start_inputs import form_schema,preflight,check_values
from app.declared_types import resolve
from app import main

def declaration():return {'variable':'approved','type':'checkbox','required':True,'default':True}

def plan(mode='workflow'):
 p=base_plan(mode);p['nodes'][0]['config']['variables']=[declaration()];p['nodes'][1]['config']['user_prompt']=('问题{{#sys.query#}} ' if mode=='advanced-chat' else '')+'开关{{#start.approved#}}';return p

def native(mode='workflow'):
 content,result=compile_workflow_plan(plan_task(plan(mode),mode));assert result['valid'],result;return yaml.safe_load(content)

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_native_boolean_type_default_schema_and_preservation(mode):
 root=native(mode);rows=root['workflow']['graph']['nodes'][0]['data']['variables'];assert rows[0]['type']=='checkbox' and rows[0]['default'] is True
 nodes={n['id']:n for n in plan(mode)['nodes']};assert resolve(nodes,['start','approved'])=='boolean'
 fields=form_schema(root)['fields'];assert next(r for r in fields if r['variable']=='approved')['default'] is True
 before=copy.deepcopy(root);assert validate_preserved(root)['valid'] and root==before
 values={'approved':False,**({'query':'问题'} if mode=='advanced-chat' else {})};preflight(root,values);assert values['approved'] is False

@pytest.mark.parametrize('patch',[{'default':0},{'default':1},{'default':'false'},{'default':'true'},{'default':None},{'default':[]},{'options':['true','false']},{'minimum':0},{'required':'false'}])
def test_declaration_is_explicit_and_does_not_coerce(patch):
 p=plan();p['nodes'][0]['config']['variables'][0].update(patch);before=copy.deepcopy(p);result=validate_plan(task(),p);assert not result['valid'] and p==before

@pytest.mark.parametrize('value',[0,1,'false','true','yes','',[],{},None])
def test_values_are_real_json_boolean_not_native_coercions(value):
 with pytest.raises(ValueError):preflight(native(),{'approved':value})


def test_required_missing_does_not_use_default_and_optional_default_does_not_change_input():
 root=native();rows=root['workflow']['graph']['nodes'][0]['data']['variables']
 with pytest.raises(ValueError):preflight(root,{})
 rows[0]['required']=False
 for values in ({},{'approved':None},{'approved':False}):
  before=copy.deepcopy(values);preflight(root,values);assert values==before
 rows[0].pop('default');p=plan();p['nodes'][0]['config']['variables']=rows;assert not validate_plan(task(),p)['valid']

@pytest.mark.parametrize('value,valid',[(False,True),(True,True),(0,False),('false',False)])
def test_model_case_contract_accepts_boolean_not_number_or_text(client,value,valid):
 from test_case_proposals import candidate
 t=approved(client);t['workflow_plan']=plan();contract=main.case_proposals.contract(t);assert contract['inputs']['approved']['type']=='boolean'
 c=candidate();c['items'][0]['case']['input']={'approved':value};assert main.case_proposals.validate(t,c)['valid'] is valid


def runtime(client,mode='advanced-chat'):
 from test_chatflow_inputs import runtime as chat_runtime
 t=chat_runtime(client);main.artifact_path(t).write_text(yaml.safe_dump(native(mode),allow_unicode=True),encoding='utf-8');return t


def test_fixed_multi_turn_keeps_false_and_uses_actual_same_conversation(client,monkeypatch):
 from test_chatflow_case_inputs import run
 t=runtime(client);t['test_cases']=[{'id':'stable','name':'布尔固定多轮','required':True,'input':{'query':'首轮','approved':False},'expectation':{'mode':'equals','target':'answer','expected':'ok'},'followups':[{'input':{'query':'追问','approved':False},'expectation':{'mode':'equals','target':'answer','expected':'ok'}}]}];main.save_task(t);seen=[]
 async def chat(self,query,inputs=None,conversation_id=None):seen.append((query,copy.deepcopy(inputs),conversation_id));return {'answer':'ok','conversation_id':conversation_id or 'boolean-fixed'}
 monkeypatch.setattr(main.DifyClient,'run_chatflow',chat);r=run(client,t);assert r.status_code==200,r.text
 assert seen==[('首轮',{'approved':False},None),('追问',{'approved':False},'boolean-fixed')]

@pytest.mark.parametrize('value',[True,0,'false',None])
def test_changed_boolean_fixed_turn_refused_before_any_budget_or_dispatch(client,monkeypatch,value):
 from test_chatflow_case_inputs import run
 t=runtime(client);t['test_cases']=[{'id':'stable','name':'布尔不一致','required':True,'input':{'query':'首轮','approved':False},'expectation':{'mode':'manual','description':'检查回答'},'followups':[{'input':{'query':'追问','approved':value},'expectation':{'mode':'manual','description':'检查回答'}}]}];main.save_task(t);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('invalid inputs must not reserve or dispatch')
 monkeypatch.setattr(main.execution_limits,'require_start',forbidden);monkeypatch.setattr(main.DifyClient,'run_chatflow',forbidden)
 response=run(client,t);assert response.status_code==422 and main.get_task(t['id'])==before


def test_trusted_free_source_preserves_false_and_rejects_zero_or_changed_flag(client,monkeypatch):
 from test_conversation_inputs import request
 t=runtime(client);seen=[]
 async def chat(self,query,inputs=None,conversation_id=None):seen.append((copy.deepcopy(inputs),conversation_id));return {'answer':'ok','conversation_id':conversation_id or 'boolean-free'}
 monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
 response=request(client,t,{'query':'首轮','approved':False});assert response.status_code==200,response.text;t=response.json();source=t['runs'][-1]['id']
 response=request(client,t,{'query':'继续','approved':False},source);assert response.status_code==200,response.text;t=response.json()
 assert seen==[({'approved':False},None),({'approved':False},'boolean-free')]
 before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('changed boolean must not reserve budget')
 monkeypatch.setattr(main.execution_limits,'require_start',forbidden)
 for values in ({'query':'变更','approved':True},{'query':'变更','approved':0},{'query':'变更','approved':'false'},{'query':'变更'},{'query':'变更','approved':None}):
  response=request(client,t,values,source);assert response.status_code==422 and main.get_task(t['id'])==before and len(seen)==2



def test_workflow_sends_false_as_boolean_and_invalid_values_do_not_dispatch(client,monkeypatch):
 from test_api import create_env
 env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'bool-workflow','service_api_key':'fixture-only'})
 t=approved(client,env_id=env['id']);t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();main.artifact_path(t).write_text(yaml.safe_dump(native(),allow_unicode=True),encoding='utf-8');t['dify_app_id']='bool-workflow';main.save_task(t);before=copy.deepcopy(main.get_task(t['id']));seen=[]
 async def workflow(self,inputs):seen.append(copy.deepcopy(inputs));return {'data':{'status':'succeeded','outputs':{'result':inputs['approved']}}}
 monkeypatch.setattr(main.DifyClient,'run_workflow',workflow)
 for values in ({},{'approved':0},{'approved':'false'}):
  response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':values});assert response.status_code==422 and not seen and main.get_task(t['id'])==before
 response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':{'approved':False}});assert response.status_code==200,response.text
 assert seen[0]['approved'] is False and response.json()['runs'][-1]['input']['approved'] is False


def test_manual_false_default_and_metadata_retained_in_native_source():
 root=native();row=root['workflow']['graph']['nodes'][0]['data']['variables'][0];row.update(default=False,label='人工开关',description='保留false',max_length=None,required=False)
 before=copy.deepcopy(root);assert validate_preserved(root)['valid'] and root==before


def test_boolean_input_drives_boolean_condition_without_string_conversion():
 from test_condition_settings import plan as conditions
 p=conditions(kind='boolean',value=False,op='is');p['nodes'][0]['config']['variables']=[declaration()];p['nodes'][1]['config']['cases'][0]['conditions'][0]['variable_selector']=['start','approved']
 content,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked
 root=yaml.safe_load(content);c=root['workflow']['graph']['nodes'][1]['data']['cases'][0]['conditions'][0]
 assert c['varType']=='boolean' and c['value'] is False and validate_preserved(root)['valid']
