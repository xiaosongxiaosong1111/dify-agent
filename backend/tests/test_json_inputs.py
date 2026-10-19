import copy,json
import pytest,yaml
from fastapi import HTTPException
from test_api import client,approved
from test_workflow_plan import base_plan,plan_task,task
from app import main
from app.json_inputs import validate_value,validate,schema,MAX_SAFE
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app.start_inputs import form_schema,preflight


def shape():
 return {'type':'object','properties':{'count':{'type':'integer','minimum':0,'maximum':10},'enabled':{'type':'boolean'},'tags':{'type':'array','items':{'type':'string','enum':['a','b']},'maxItems':2}},'required':['count','enabled'],'additionalProperties':False}
def row():return {'variable':'payload','type':'json_object','required':True,'json_schema':shape()}
def plan(mode='workflow'):
 p=base_plan(mode);p['nodes'][0]['config']['variables']=[row()];p['nodes'][1]['config']['user_prompt']='{{#start.payload#}}';return p
def native():
 content,result=compile_workflow_plan(plan_task(plan()));assert result['valid'],result;return yaml.safe_load(content)

@pytest.mark.parametrize('raw',[False,True])
def test_compile_schema_native_final_form_and_manual_preservation(raw):
 p=plan();r=p['nodes'][0]['config']['variables'][0]
 if raw:r['json_schema']=json.dumps(shape(),ensure_ascii=False,indent=2)
 r.update(label='人工对象',description='保持字段',hide=False);content,result=compile_workflow_plan(plan_task(p));assert result['valid'],result
 root=yaml.safe_load(content);emitted=root['workflow']['graph']['nodes'][0]['data']['variables'][0]
 assert emitted['json_schema']==r['json_schema'] and 'max_length' not in emitted and 'options' not in emitted
 before=copy.deepcopy(root);assert validate_preserved(root)['valid'] and root==before
 form=form_schema(root);assert form['fields'][0]['json_schema']==r['json_schema'] and '服务API' in form['note']
 values={'payload':{'count':1,'enabled':False,'tags':['a','a']}};old=copy.deepcopy(values);preflight(root,values);assert values==old

@pytest.mark.parametrize('value',[{}, {'count':True,'enabled':False},{'count':0,'enabled':0},{'count':11,'enabled':False},{'count':1,'enabled':False,'extra':'private-sentinel'},{'count':1,'enabled':False,'tags':['c']},'{}',[],None,False])
def test_invalid_instances_are_rejected_without_coercion_or_private_echo(value):
 before=copy.deepcopy(value)
 with pytest.raises(ValueError) as error:validate_value(shape(),value)
 assert 'private-sentinel' not in str(error.value) and value==before

@pytest.mark.parametrize('patch',[{'required':False},{'required':1},{'hide':True},{'hide':0},{'default':{}},{'options':['x']},{'max_length':1},{'unknown':True},{'label':False},{'json_schema':{'type':'array','items':{'type':'string'}}},{'json_schema':{'type':'object','$ref':'https://example.invalid/private','properties':{},'additionalProperties':False}}])
def test_declaration_unsupported_constraints_are_not_dropped(patch):
 r=row();r.update(patch);assert validate(r)
 p=plan();p['nodes'][0]['config']['variables']=[r];before=copy.deepcopy(p);assert not validate_plan(task(),p)['valid'] and p==before

@pytest.mark.parametrize('value',['{"type":"object","type":"object"}','{"type":NaN}','{','{"type":"object","properties":{},"additionalProperties":false,"default":{}}'])
def test_raw_schema_not_repaired_or_parsed_with_lost_duplicate_keys(value):
 with pytest.raises(ValueError):schema(value)


def test_nested_closed_objects_and_mathematical_integer_keep_original_value():
 s={'type':'object','properties':{'child':shape()},'required':['child'],'additionalProperties':False}
 v={'child':{'count':1.0,'enabled':False,'tags':['b']}};before=copy.deepcopy(v);validate_value(s,v);assert v==before and type(v['child']['count']) is float
 v['child']['extra']=1
 with pytest.raises(ValueError):validate_value(s,v)

@pytest.mark.parametrize('value',[MAX_SAFE+1,float('inf'),float('nan'),'x'*64000],ids=['unsafe-int','infinity','nan','large'])
def test_bounded_finite_json_values(value):
 s={'type':'object','properties':{'value':{'type':'number' if type(value) in (int,float) else 'string'}},'additionalProperties':False}
 with pytest.raises(ValueError):validate_value(s,{'value':value})


def test_no_external_references_or_invalid_schema_network(monkeypatch):
 import socket
 def forbidden(*a,**kw):pytest.fail('离线Schema不能联网')
 monkeypatch.setattr(socket,'socket',forbidden)
 validate_value(shape(),{'count':0,'enabled':True})
 r=shape();r['properties']['count']={'$ref':'https://example.invalid/data'}
 with pytest.raises(ValueError):validate_value(r,{'count':0,'enabled':True})


def test_chatflow_and_agent_not_silently_changed_or_sent_to_model(client):
 p=plan('advanced-chat');assert not validate_plan(task('advanced-chat'),p)['valid']
 root=native();root['app']['mode']='advanced-chat'
 for call in (form_schema,lambda r:preflight(r,{'query':'问题','payload':{'count':0,'enabled':False}})):
  with pytest.raises(ValueError):call(root)
 for mode in ('advanced-chat','agent'):
  t=approved(client);t['app_type']=mode;t['workflow_plan']=plan(mode)
  with pytest.raises(HTTPException):main.case_proposals.contract(t)

@pytest.mark.parametrize('value,valid',[({'count':0,'enabled':False},True),({'count':True,'enabled':False},False),('{}',False)])
def test_case_contract_and_candidates_keep_object_schema(client,value,valid):
 from test_case_proposals import candidate
 t=approved(client);t['workflow_plan']=plan();contract=main.case_proposals.contract(t);assert contract['inputs']['payload']['json_schema']==shape()
 c=candidate();c['items'][0]['case']['input']={'payload':value};before=copy.deepcopy(c);assert main.case_proposals.validate(t,c)['valid'] is valid and c==before


def test_workflow_dispatch_keeps_objects_invalid_preflight_before_budget(client,monkeypatch):
 from test_api import create_env
 env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'json-workflow','service_api_key':'fixture-only'})
 t=approved(client,env_id=env['id']);t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();main.artifact_path(t).write_text(yaml.safe_dump(native(),allow_unicode=True),encoding='utf-8');t['dify_app_id']='json-workflow';main.save_task(t);before=copy.deepcopy(main.get_task(t['id']));seen=[]
 async def workflow(self,inputs):seen.append(copy.deepcopy(inputs));return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
 monkeypatch.setattr(main.DifyClient,'run_workflow',workflow)
 with monkeypatch.context() as m:
  def forbidden(*a,**kw):pytest.fail('无效对象不得预留费用')
  m.setattr(main.execution_limits,'require_start',forbidden)
  for values in ({},{'payload':'{}'},{'payload':{'count':True,'enabled':False}}):
   response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':values});assert response.status_code==422 and not seen and main.get_task(t['id'])==before
 value={'payload':{'count':1,'enabled':False,'tags':['a','a']}}
 response=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':value});assert response.status_code==200,response.text
 assert seen==[value] and response.json()['runs'][-1]['input']==value


def test_scope_17_must_reconfirm_before_new_schema_and_case_objects(client,monkeypatch):
 from test_assistant_routing import setup,enable,state
 t,_,light=setup(client);assert enable(client,t,light).status_code==200
 saved=main.routing.get(t['id']);saved['scope_version']=17;main.store.put('assistant_routing',t['id'],saved)
 def forbidden(*a,**kw):pytest.fail('旧范围不能调用模型')
 monkeypatch.setattr(main,'call_model',forbidden)
 current=state(client,t);assert current['required_scope_version']==18 and current['blocker'] and 'JSON对象入口' in current['scope_note']
 assert enable(client,t,light,scope_version=17).status_code==409
 assert client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']}).status_code==422
 assert main.routing.get(t['id'])['scope_version']==17


def test_intake_asks_about_all_entry_enforcement_and_alternatives(client):
 from app.intake import topics
 t=approved(client);t['workflow_plan']=plan();item=next(v for v in topics(t) if v['id']=='json_input_scope')
 assert '所有Dify入口' in item['question'] and '确认' in item['question'] and '敏感数据' in item['question']

@pytest.mark.parametrize('value',[{'value':(1,2)},{'value':{1:'x'}},{'value':'\ud800'},{'value':[0]*20001}],ids=['tuple','nonstring-key','unicode','node-bound'])
def test_non_json_or_oversized_structure_not_converted(value):
 s={'type':'object','properties':{'value':{'type':'array','items':{'type':'integer'}}},'additionalProperties':False}
 with pytest.raises(ValueError):validate_value(s,value)


def test_draft7_boolean_does_not_match_numeric_enum():
 s={'type':'object','properties':{'n':{'type':'integer','enum':[0]}},'required':['n'],'additionalProperties':False}
 validate_value(s,{'n':0})
 with pytest.raises(ValueError):validate_value(s,{'n':False})


def test_manual_schema_layout_capture_merge_reconfirm_build(client):
 from test_dsl_roundtrip import capture,apply,APP
 from app.dsl_roundtrip import parse,digest
 t=approved(client);t['workflow_plan']=plan();main.save_task(t)
 r=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert r.status_code==200,r.text
 t=r.json();root=parse(main.artifact_path(t).read_text(encoding='utf-8'),'workflow');t.update(dify_app_id=APP,status='imported');t['runs'].append({'id':'original-json-import','kind':'import','status':'success','revision':t['revision'],'environment_id':t['environment_id'],'result':{'app_id':APP},'dsl_baseline':copy.deepcopy(root)});main.save_task(t)
 current=copy.deepcopy(root);start=current['workflow']['graph']['nodes'][0];start['position']['x']+=17;r=start['data']['variables'][0];r['json_schema']=json.dumps(shape(),ensure_ascii=False,indent=3);r['label']='人工对象标签';r['description']='人工Schema保留'
 t=capture(client,t,current);response,preview=apply(client,t);assert response.status_code==200,(response.text,preview['validation']);t=response.json();assert not t['configuration_confirmed']
 for kind in ('requirements','configuration'):
  response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert response.status_code==200,response.text;t=response.json()
 response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
 final=parse(main.artifact_path(response.json()).read_text(encoding='utf-8'),'workflow');assert digest(final)==digest(current)


def test_final_schema_read_api_uses_artifact_not_stale_plan(client):
 t=approved(client);t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();root=native();r=root['workflow']['graph']['nodes'][0]['data']['variables'][0];r['json_schema']['properties']['count']['maximum']=3
 main.artifact_path(t).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8');before=copy.deepcopy(main.get_task(t['id']))
 response=client.get(f"/api/tasks/{t['id']}/run-input-schema");assert response.status_code==200,response.text
 assert response.json()['fields'][0]['json_schema']['properties']['count']['maximum']==3 and main.get_task(t['id'])==before
