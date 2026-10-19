import copy,json
import pytest
from test_api import client,approved,create_env
from test_json_inputs import shape
from app import main
from app.evaluation import evaluate_output


def rule():return {'mode':'json_schema','target':'result','expected':shape()}

@pytest.mark.parametrize('value,pointer',[
 ({'count':'private-value-sentinel','enabled':False},'/properties/count/type'),
 ({'count':11,'enabled':False},'/properties/count/maximum'),
 ({'count':0},'/required'),
 ({'count':0,'enabled':False,'private-extra-sentinel':'private-value-sentinel'},'/additionalProperties'),
 ({'count':0,'enabled':False,'tags':['private-value-sentinel']},'/properties/tags/items/enum'),
])
def test_failure_explains_schema_rule_without_original_field_values(value,pointer):
 before=copy.deepcopy(value);r=evaluate_output({'result':value},rule())
 assert r['status']=='failed' and pointer in r['details'] and '仅本机结果检查' in r['details']
 assert 'private-value-sentinel' not in r['details'] and 'private-extra-sentinel' not in r['details'] and value==before

@pytest.mark.parametrize('value',['{"count":0,"count":1,"enabled":false}','{"count":NaN,"enabled":false}','```json\n{}\n```','[1,2]','private-text-sentinel'])
def test_text_failure_describes_unparsed_json_without_guessing_or_echo(value):
 r=evaluate_output({'result':value},rule());assert r['status']=='failed' and '唯一键且有限' in r['details'] and '不去Markdown' in r['details'] and 'private-text-sentinel' not in r['details']


def test_rule_pointer_escapes_schema_keys():
 s={'type':'object','properties':{'a/b~c':{'type':'boolean'}},'additionalProperties':False}
 r=evaluate_output({'result':{'a/b~c':0}},{'mode':'json_schema','target':'result','expected':s})
 assert '/properties/a~1b~0c/type' in r['details']


def test_long_json_text_and_invalid_encoding_have_distinct_static_reason():
 r=evaluate_output({'result':'x'*64001},rule());assert r['status']=='failed' and '64000字节' in r['details']
 r=evaluate_output({'result':'\ud800'},rule());assert r['status']=='failed' and '编码无效' in r['details']


def test_run_record_and_acceptance_keep_rule_failure_without_retry(client,monkeypatch):
 env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'schema-diagnostic-app','service_api_key':'fixture-only'})
 t=approved(client,env_id=env['id']);c={'id':'diagnostic','name':'核对对象类型','required':True,'input':{'query':'结构'},'expectation':rule()}
 t=client.post(f"/api/tasks/{t['id']}/test-cases",json={'revision':t['revision'],'cases':[c]}).json()
 for kind in ('requirements','configuration'):t=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind}).json()
 t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();t['dify_app_id']='schema-diagnostic-app';main.save_task(t);calls=[]
 async def workflow(self,inputs):calls.append(True);return {'data':{'status':'succeeded','outputs':{'result':{'count':'private-value-sentinel','enabled':False}}}}
 monkeypatch.setattr(main.DifyClient,'run_workflow',workflow)
 r=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'case_id':'diagnostic'});assert r.status_code==200,r.text
 evaluation=r.json()['runs'][-1]['evaluation'];assert evaluation['status']=='failed' and '/properties/count/type' in evaluation['details'] and 'private-value-sentinel' not in evaluation['details'] and len(calls)==1
 summary=client.get(f"/api/tasks/{t['id']}/acceptance").json();assert summary['required']['failed']==1 and not summary['all_required_passed']
