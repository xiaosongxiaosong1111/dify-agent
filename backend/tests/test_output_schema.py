import copy,json
import pytest
from test_api import client,approved,create_env
from test_json_inputs import shape
from app import main
from app.evaluation import evaluate_output,validate_test_cases


def expectation(schema=None):return {'mode':'json_schema','target':'result','expected':shape() if schema is None else schema}
def case(schema=None):return {'id':'schema-case','name':'明确输出结构','required':True,'input':{'query':'检查结构'},'expectation':expectation(schema)}

@pytest.mark.parametrize('text',[False,True])
def test_output_object_or_strict_json_text_without_mutation(text):
 value={'count':0,'enabled':False,'tags':['a','a']};actual={'result':json.dumps(value) if text else value};before=copy.deepcopy(actual)
 r=evaluate_output(actual,expectation());assert r['status']=='passed' and '不代表完整业务正确性' in r['details'] and actual==before

@pytest.mark.parametrize('value',[{'count':True,'enabled':False},{'count':1,'enabled':0},{'count':11,'enabled':True},{'count':1,'enabled':False,'extra':'private-sentinel'}, {},[],None,'{"count":1,"count":2,"enabled":true}','{"count":NaN,"enabled":true}','```json\n{}\n```','[1,2]','{"count":1}garbage'])
def test_full_schema_rejects_bad_output_types_or_repairs(value):
 r=evaluate_output({'result':value},expectation());assert r['status']=='failed' and 'private-sentinel' not in r['details']

@pytest.mark.parametrize('schema',[{'type':'array','items':{'type':'string'}},{'type':'object','$ref':'https://example.invalid/private','properties':{},'additionalProperties':False},'{','{"type":"object","type":"object"}'])
def test_invalid_rule_refused_before_saved_or_run(schema):
 c=case(schema);assert not validate_test_cases([c],'workflow')['valid']
 assert evaluate_output({'result':{}},expectation(schema))['status']=='failed'


def test_json_keys_does_not_falsely_imply_full_schema():
 actual={'result':{'count':True,'enabled':0}}
 assert evaluate_output(actual,{'mode':'json_keys','target':'result','expected':['count','enabled']})['status']=='passed'
 assert evaluate_output(actual,expectation())['status']=='failed'


def test_raw_schema_preserves_intact_text_and_duplicate_keys_not_overwritten(client):
 t=approved(client);raw=json.dumps(shape(),ensure_ascii=False,indent=3);c=case(raw)
 r=client.post(f"/api/tasks/{t['id']}/test-cases",json={'revision':t['revision'],'cases':[c]});assert r.status_code==200,r.text
 t=r.json();assert t['test_cases'][0]['expectation']['expected']==raw;before=copy.deepcopy(main.get_task(t['id']))
 c['expectation']['expected']='{"type":"object","type":"object"}'
 r=client.post(f"/api/tasks/{t['id']}/test-cases",json={'revision':t['revision'],'cases':[c]});assert r.status_code==422 and main.get_task(t['id'])==before


def test_strict_json_output_size_bound_and_no_partial_pass():
 s={'type':'object','properties':{'x':{'type':'string'}},'additionalProperties':False}
 r=evaluate_output({'result':json.dumps({'x':'a'*64000})},expectation(s));assert r['status']=='failed'

@pytest.mark.parametrize('valid',[False,True])
def test_model_candidate_supports_full_schema_without_real_model(client,valid):
 from test_case_proposals import candidate
 t=approved(client);c=candidate();c['items'][0]['case']['expectation']=expectation(shape() if valid else '{')
 assert main.case_proposals.validate(t,c)['valid'] is valid


def test_mock_workflow_run_uses_schema_then_acceptance_summary(client,monkeypatch):
 env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'schema-result-app','service_api_key':'fixture-only'})
 t=approved(client,env_id=env['id']);t=client.post(f"/api/tasks/{t['id']}/test-cases",json={'revision':t['revision'],'cases':[case()]}).json()
 for kind in ('requirements','configuration'):
  r=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert r.status_code==200,r.text;t=r.json()
 t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();t['dify_app_id']='schema-result-app';main.save_task(t);calls=[]
 async def workflow(self,inputs):calls.append(copy.deepcopy(inputs));return {'data':{'status':'succeeded','outputs':{'result':{'count':1,'enabled':False}}}}
 monkeypatch.setattr(main.DifyClient,'run_workflow',workflow)
 r=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'case_id':t['test_cases'][0]['id']});assert r.status_code==200,r.text
 result=r.json();assert result['runs'][-1]['evaluation']['status']=='passed' and calls==[{'query':'检查结构'}]
 from app.acceptance import summarize_acceptance
 assert summarize_acceptance(result)['all_required_passed']


@pytest.mark.parametrize('good',[False,True])
def test_fixed_conversation_each_turn_schema_with_same_actual_conversation(good):
 from app.conversation_cases import evaluate_conversation
 e=expectation();e['target']='answer';c={'input':{'query':'首轮'},'expectation':e,'followups':[{'input':{'query':'追问'},'expectation':e}]}
 turns=[]
 for index,turn in enumerate([c,*c['followups']]):
  output={'count':index,'enabled':False if good or index==0 else 0}
  turns.append({'index':index+1,'input':copy.deepcopy(turn['input']),'expectation':copy.deepcopy(e),'status':'success','source_conversation_id':None if index==0 else 'fixed-schema','result':{'answer':json.dumps(output),'conversation_id':'fixed-schema'}})
 result={'conversation_case':True,'complete':True,'conversation_id':'fixed-schema','turns':turns}
 assert evaluate_conversation(c,result)['status']==('passed' if good else 'failed')
