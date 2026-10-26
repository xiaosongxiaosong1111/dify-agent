import copy,json
import pytest,yaml
from test_api import client,approved
from app import main
from app.json_inputs import schema,validate_value
from app.evaluation import evaluate_output,validate_test_cases
from app.workflow_plan import validate_plan
from app.start_inputs import preflight,form_schema
from test_json_inputs import plan,native
from test_workflow_plan import task

def raw(number,keyword='minimum'):
 return '{"type":"object","properties":{"count":{"type":"number","'+keyword+'":'+number+'}},"required":["count"],"additionalProperties":false}'

@pytest.mark.parametrize('number',['1e-999','0.10000000000000001','-0.10000000000000001','1e999'])
def test_raw_schema_cannot_change_constraints_or_become_valid_plan(number):
 text=raw(number);p=plan();p['nodes'][0]['config']['variables'][0]['json_schema']=text;before=copy.deepcopy(p)
 with pytest.raises(ValueError):schema(text)
 with pytest.raises(ValueError):validate_value(text,{'count':0})
 checked=validate_plan(task(),p);assert not checked['valid'] and p==before
 candidate={'id':'one','name':'原规则','input':{'query':'公开'},'required':True,'expectation':{'mode':'json_schema','target':'answer','expected':text}}
 assert not validate_test_cases([candidate])['valid']

@pytest.mark.parametrize('number,expected',[('0.1',0.1),('-2.5',-2.5),('1e2',100),('0e999',0),('1.0',1),('9007199254740993',9007199254740993)])
def test_ordinary_numbers_and_existing_integer_semantics_remain(number,expected):
 text=raw(number);parsed=schema(text);assert parsed['properties']['count']['minimum']==expected
 assert text==raw(number)

@pytest.mark.parametrize('actual',['{"count":0.10000000000000001}','{"count":1e-999}','{"count":1e999}'])
def test_actual_json_text_does_not_pass_by_rounding(actual):
 expected={'type':'object','properties':{'count':{'type':'number','enum':[0.1,0]}},'required':['count'],'additionalProperties':False}
 data={'answer':actual};before=copy.deepcopy(data);result=evaluate_output(data,{'mode':'json_schema','target':'answer','expected':expected})
 assert result['status']=='failed' and data==before and '无损' in result['details']

@pytest.mark.parametrize('actual',['{"count":0.1}','{"count":-2.5}','{"count":1e2}'])
def test_safe_actual_json_rule_still_works(actual):
 result=evaluate_output({'answer':actual},{'mode':'json_schema','target':'answer','expected':json.loads(raw('-10'))})
 assert result['status']=='passed'

def test_final_artifact_schema_and_local_input_api_reject_without_task_changes(client):
 t=approved(client);t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();root=native();root['workflow']['graph']['nodes'][0]['data']['variables'][0]['json_schema']=raw('1e-999')
 before=copy.deepcopy(main.get_task(t['id']));content=yaml.safe_dump(root,allow_unicode=True);main.artifact_path(t).write_text(content,encoding='utf-8')
 with pytest.raises(ValueError):form_schema(root)
 with pytest.raises(ValueError):preflight(root,{'payload':{'count':0}})
 response=client.get(f"/api/tasks/{t['id']}/run-input-schema");assert response.status_code==422,response.text
 assert main.get_task(t['id'])==before and main.artifact_path(t).read_text(encoding='utf-8')==content
