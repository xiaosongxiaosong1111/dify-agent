import copy,json
import pytest
from test_api import client
from test_file_structured_run import ready,result,execute,shape
from test_file_run import plan,remote,RUN
from test_file_model_run import inputs
from app import main
from app.file_run import KIND
from app.json_inputs import validate_value
from app.file_output_reason import make,valid

@pytest.mark.parametrize('output,category,pointer',[
 ('private-original-output','object_required',None),
 ({'customer':'private-value'},'schema_rule','/required'),
 ({'customer':'甲','approved':1},'schema_rule','/properties/approved/type'),
 ({'customer':'甲','approved':True,'private-extra':'private-value'},'schema_rule','/additionalProperties'),
 ({'customer':'','approved':True},'schema_rule','/properties/customer/minLength'),
 ({'customer':'甲','approved':True,'amount':-1},'schema_rule','/properties/amount/minimum'),
 ({'customer':'甲','approved':True,'amount':9007199254740992},'integer_range',None),
 ({'customer':'甲','approved':True,'tags':['1','2','3','4']},'schema_rule','/properties/tags/maxItems'),
 ({'customer':'x'*64001,'approved':True},'size_limit',None),
 ({'customer':'\ud800','approved':True},'json_value_invalid',None),
],ids=['text','required','type','extra','length','minimum','unsafe-integer','array-count','bytes','encoding'])
def test_reason_uses_confirmed_rule_only_without_values_unknown_field_names_or_coercion(output,category,pointer):
 s=shape();text=json.dumps(s,ensure_ascii=False)
 with pytest.raises(ValueError) as error:validate_value(s,output)
 r=make(s,text,error.value);assert r['category']==category and r['schema_pointer']==pointer and valid(r,s,text)
 assert r['output_retained'] is False and r['automatic_retry'] is False and r['business_verified'] is False
 assert 'private-' not in json.dumps(r,ensure_ascii=False)

def test_unknown_exception_body_and_unconfirmed_pointer_are_not_echoed():
 s=shape();text=json.dumps(s)
 for error in [ValueError('password=private-secret'),ValueError('JSON对象输入不符合已确认Schema，规则位置/private-schema-key；不回显字段值、不补默认或删除额外字段。')]:
  r=make(s,text,error);assert r['category']=='unknown' and r['schema_pointer'] is None and 'private-' not in json.dumps(r)

def test_pointer_escaping_and_nonprintable_or_oversize_confirmed_names():
 for key,expected in [('a/b~c','/properties/a~1b~0c/type'),('a\u200bb',None)]:
  s={'type':'object','properties':{key:{'type':'boolean'}},'additionalProperties':False};text=json.dumps(s)
  with pytest.raises(ValueError) as error:validate_value(s,{key:1})
  r=make(s,text,error.value);assert r['category']=='schema_rule' and r['schema_pointer']==expected and valid(r,s,text)
  if expected is None:assert key not in r['message']
 s={'type':'boolean'};value=1
 for i in range(8):
  key='x'*120+str(i);s={'type':'object','properties':{key:s},'additionalProperties':False};value={key:value}
 with pytest.raises(ValueError) as error:validate_value(s,value)
 r=make(s,json.dumps(s),error.value);assert r['category']=='schema_rule' and r['schema_pointer'] is None and valid(r,s,json.dumps(s))

@pytest.mark.parametrize('mutation',['hash','pointer','message','version_bool','false_flag','unknown_code'])
def test_reason_validation_rejects_modified_source_or_extra_claims(mutation):
 s=shape();text=json.dumps(s);r=make(s,text,'output_fields')
 if mutation=='hash':r['schema_text_sha256']='0'*64
 elif mutation=='pointer':r['category']='schema_rule';r['schema_pointer']='/private-field';r['message']='private-value'
 elif mutation=='message':r['message']='private-value'
 elif mutation=='version_bool':r['schema_version']=True
 elif mutation=='false_flag':r['output_retained']=0
 else:r['category']=[]
 assert not valid(r,s,text)

@pytest.mark.parametrize('case',['wrong_type','missing_output','extra_key','unknown_error'])
def test_failed_object_run_returns_safe_actionable_reason_and_history_without_extra_model_or_platform_calls(client,monkeypatch,case):
 t,env,u,_=ready(client,monkeypatch);q=plan(client,t,u,inputs(u)).json();receipt=result({'customer':'甲','approved':1})
 if case=='missing_output':receipt['data']['outputs']={}
 elif case=='extra_key':receipt['data']['outputs']['result']={'customer':'甲','approved':True,'private-extra':'private-value'}
 elif case=='unknown_error':
  from app import json_inputs
  def rejected(*args):raise ValueError('password=private-secret')
  monkeypatch.setattr(json_inputs,'validate_value',rejected)
 calls,_=remote(monkeypatch,t,env,result=receipt);r=execute(client,t,q);assert r.status_code==502 and len(calls)==3 and 'private-' not in r.text
 row=main.store.get(KIND,q['id']);reason=row['output_contract_reason'];assert valid(reason,row['data_flow']['structured_output']['schema'],row['data_flow']['structured_output']['schema_text'])
 assert reason['category']==({'wrong_type':'schema_rule','missing_output':'output_fields','extra_key':'schema_rule','unknown_error':'unknown'}[case])
 assert reason['message'] in r.json()['detail'] and row['state']=='unknown' and row['output_contract_rejected'] is True
 record=main.get_task(t['id'])['runs'][-1];assert record['status']=='unknown' and record['result']['data']['id']==RUN and 'outputs' not in record['result']['data'] and 'private-' not in json.dumps(record)
 history=client.get(f"/api/tasks/{t['id']}/file-runs");assert history.status_code==200 and history.json()['records'][0]['output_contract_reason']==reason and len(calls)==3
 assert reason['message'] in record['error'] and execute(client,t,q).status_code==409 and len(calls)==3
