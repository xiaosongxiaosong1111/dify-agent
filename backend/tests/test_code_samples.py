import copy,importlib,json,sys,uuid
from pathlib import Path
import pytest
from app.code_sample_policy import validate_code,parse_inputs,output_matches
from app import code_sample_docker as docker

@pytest.mark.parametrize('code',[
 'def main(x):\n return {"v":x+1}',
 'import math\ndef main(x):\n return {"v":math.sqrt(x)}',
 'from json import loads\ndef main(x):\n return {"v":loads(x)}',
 'RATE=0.2\ndef main(x):\n return {"v":x*RATE}',
 'def helper(x):\n return x.upper()\ndef main(x):\n return {"v":helper(x)}',
])
def test_policy_accepts_pure_code(code):validate_code(code)

@pytest.mark.parametrize('body',[
 'import os','import sys','import socket','import subprocess','from pathlib import Path','from json import JSONDecoder','from math import *',
 'return x.__class__','return getattr(x,"a")','return eval("1")','return globals()','return locals()','return open("x")','return type(x)','return vars(x)',
 'class X: pass','global x','nonlocal x','with x: pass','return await x','yield x',
 'try: return x\n except: return 0','try: return x\n except BaseException: return 0','return x._private','x.attr=1','return \"{0.__globals__}\".format(x)','return x.format_map({})','return Exception.mro()','return (v for v in []).gi_frame',
])
def test_policy_rejects_unsafe_or_unsupported(body):
 code=body if body.startswith(('import ','from ')) else 'def main(x):\n '+body.replace('\n','\n ')
 with pytest.raises(ValueError):validate_code(code)

@pytest.mark.parametrize('text',['[]','{"a":1,"a":2}','{"a":1,"\\u0061":2}','{"a":NaN}','{"a":Infinity}','{"a":1e-999}','{"a":0.10000000000000001}','{"a":'])
def test_input_rejects_ambiguous_json(text):
 with pytest.raises(ValueError):parse_inputs(text)

def test_inputs_preserve_large_integer_and_types():
 value=parse_inputs('{"x":9007199254740993,"ok":true,"v":[null,"",0.2]}');assert value['x']==9007199254740993 and value['ok'] is True and value['v']==[None,'',0.2]

def test_input_limits_and_depth():
 for text in ['{"x":"'+'a'*65536+'"}','{"x":'+'['*34+'0'+']'*34+'}']:
  with pytest.raises(ValueError):parse_inputs(text)

@pytest.mark.parametrize('value,kind,expected',[(True,'number',False),(1,'boolean',False),('', 'string',True),([], 'array[string]',True),([1,False],'array[number]',False),({},'object',True),([{}],'array[object]',True)])
def test_output_contract_distinguishes_types(value,kind,expected):assert output_matches({'v':value},{'v':{'type':kind}}) is expected

def test_output_contract_requires_all_exact_fields():assert not output_matches({'x':1,'other':0},{'x':{'type':'number'}})

@pytest.fixture
def api(tmp_path,monkeypatch):
 monkeypatch.setenv('FLOWCRAFT_DATA_DIR',str(tmp_path/'data'))
 import app.main as main
 main=importlib.reload(main)
 import httpx
 def forbidden(*a,**kw):raise AssertionError('Physical upstream forbidden')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden);monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 calls=[]
 monkeypatch.setattr(docker.LocalDocker,'__enter__',lambda self:self);monkeypatch.setattr(docker.LocalDocker,'__exit__',lambda *args:None)
 monkeypatch.setattr(docker.LocalDocker,'ready',lambda self:{'image_id':docker.IMAGE,'profile':docker.PROFILE,'limits':copy.deepcopy(docker.LIMITS)})
 def fake(code,inputs,operation,progress):
  calls.append(operation);progress(phase='executing',create_dispatches=1,start_dispatches=1,profile_verified=True)
  return {'status':'returned','output_json':'{"result":"A"}','cleanup_verified':True}
 monkeypatch.setattr(docker,'execute',fake)
 from fastapi.testclient import TestClient
 with TestClient(main.app) as client:yield client,main,calls

def task(api,code='def main(x):\n return {"result":x.strip().upper()}',outputs=None):
 client,main,_=api;t=client.post('/api/tasks',json={'name':'public sample','app_type':'workflow'}).json()
 plan={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[{'variable':'x','type':'text-input','required':True}]}},{'id':'code','type':'code','config':{'code_language':'python3','code':code,'variables':[{'variable':'x','value_selector':['start','x']}],'outputs':outputs or {'result':{'type':'string','children':None}}}},{'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['code','result']}]}}],'edges':[{'source':'start','target':'code'},{'source':'code','target':'end'}]}
 response=client.post('/api/tasks/'+t['id']+'/plan',json={'revision':t['revision'],'plan_text':json.dumps(plan)});assert response.status_code==200,response.text
 return response.json()

def prepare(api,t,text='{"x":" a "}'):
 return api[0].post('/api/tasks/'+t['id']+'/code-samples/prepare',json={'revision':t['revision'],'node_id':'code','input_text':text})
def execute(api,t,row,text='{"x":" a "}',**changes):
 return api[0].post('/api/tasks/'+t['id']+'/code-samples/execute',json={'revision':t['revision'],'proposal_id':row['id'],'review_token':row['review_token'],'input_text':text,'acknowledge_limits':True}|changes)

def test_prepare_and_single_execute_preserve_task_and_confirmations(api):
 t=task(api);before=copy.deepcopy(api[1].store.get('task',t['id']));row=prepare(api,t).json();assert row['state']=='prepared' and row['business_verified'] is False and row['dify_sandbox_verified'] is False and not api[2]
 result=execute(api,t,row);assert result.status_code==200,result.text
 assert result.json()['state']=='passed' and result.json()['source_current_at_return'] is True
 assert api[1].store.get('task',t['id'])==before and len(api[2])==1
 assert execute(api,t,row).status_code==409 and len(api[2])==1
 stored=api[1].store.get('code_sample',row['id']);assert 'input_text' not in stored and 'code' not in stored
 assert api[0].get('/api/tasks/'+t['id']+'/code-samples').json()['records'][0]['id']==row['id']

@pytest.mark.parametrize('change',[{'acknowledge_limits':False},{'acknowledge_limits':1},{'review_token':'wrong'},{'input_text':'{ "x":" a "}'}])
def test_scope_or_confirmation_change_never_executes(api,change):
 t=task(api);row=prepare(api,t).json();assert execute(api,t,row,**change).status_code in (409,422) and not api[2]

def test_revision_change_invalidates_prepared_sample(api):
 t=task(api);row=prepare(api,t).json();api[0].patch('/api/tasks/'+t['id'],json={'expected_revision':t['revision'],'requirements':{'goal':'changed'}});assert execute(api,t,row).status_code==409 and not api[2]

def test_wrong_task_and_expired_proposal(api):
 t=task(api);row=prepare(api,t).json();other=task(api);assert execute(api,other,row).status_code==409
 saved=api[1].store.get('code_sample',row['id']);saved['expires_at']=0;api[1].store.put('code_sample',row['id'],saved);assert execute(api,t,row).status_code==409 and not api[2]

@pytest.mark.parametrize('text',['{}','{"x":"a","y":"b"}','{"x":1,"x":2}','{"x":1e-999}'])
def test_bad_input_refused_before_container(api,text):
 t=task(api);assert prepare(api,t,text).status_code==422 and not api[2]

def test_bad_code_and_nested_schema_refused(api):
 t=task(api,'import os\ndef main(x):\n return {"result":x}')
 assert prepare(api,t).status_code==422
 t2=task(api,outputs={'result':{'type':'object','children':{'v':{'type':'string'}}}})
 assert prepare(api,t2).status_code==422 and not api[2]

def test_result_mismatch_not_passed_or_task_changed(api,monkeypatch):
 t=task(api);before=copy.deepcopy(api[1].store.get('task',t['id']));row=prepare(api,t).json()
 monkeypatch.setattr(docker,'execute',lambda *a,**kw:{'status':'returned','output_json':'{"result":true}','cleanup_verified':True})
 r=execute(api,t,row);assert r.json()['state']=='failed' and r.json()['result']['status']=='output_mismatch' and api[1].store.get('task',t['id'])==before

@pytest.mark.parametrize('status',['timeout','code_error','output_limit','unknown'])
def test_execution_error_states_do_not_retry(api,monkeypatch,status):
 t=task(api);row=prepare(api,t).json();calls=[]
 def fake(*a):calls.append(True);return {'status':status,'error_category':'PUBLIC_ERROR','cleanup_verified':status!='unknown'}
 monkeypatch.setattr(docker,'execute',fake);r=execute(api,t,row);assert r.status_code==200 and r.json()['state']==('unknown' if status=='unknown' else 'failed')
 assert execute(api,t,row).status_code==409 and len(calls)==1

def test_busy_blocks_other_write_and_recover_does_not_execute(api):
 t=task(api);row=prepare(api,t).json();saved=api[1].store.get('code_sample',row['id']);saved['state']='executing';api[1].store.put('code_sample',row['id'],saved)
 assert api[0].patch('/api/tasks/'+t['id'],json={'expected_revision':t['revision'],'requirements':{'goal':'changed'}}).status_code==409
 api[1].code_samples_recover();assert api[1].store.get('code_sample',row['id'])['state']=='unknown' and not api[2]

def test_missing_docker_refuses_without_host_fallback(api,monkeypatch):
 t=task(api)
 def missing(*a):raise docker.DockerProblem('docker_unavailable')
 monkeypatch.setattr(docker.LocalDocker,'ready',missing);assert prepare(api,t).status_code==503 and not api[2]

def test_duplicate_body_and_invalid_revision_do_not_echo(api):
 t=task(api);r=api[0].post('/api/tasks/'+t['id']+'/code-samples/prepare',content='{"revision":1,"revision":2,"node_id":"PRIVATE_NO_ECHO","input_text":"{}"}',headers={'content-type':'application/json'});assert r.status_code==422 and 'PRIVATE_NO_ECHO' not in r.text
 r=api[0].post('/api/tasks/'+t['id']+'/code-samples/prepare',json={'revision':True,'node_id':'code','input_text':'{}'});assert r.status_code==422

def test_pattern_matching_is_not_an_introspection_backdoor():
 with pytest.raises(ValueError):validate_code('def main(x):\n match x:\n  case {"a": a}: return {"v": a}\n return {"v": None}')

def test_request_size_is_bounded_before_reading_the_rest():
 import asyncio
 from fastapi import HTTPException
 from app.code_samples import body
 class Request:
  headers={'content-type':'application/json'}
  async def stream(self):
   yield b'a'*100000
   yield b'b'*50000
   raise AssertionError('Must stop before reading the remaining body')
 with pytest.raises(HTTPException) as problem:asyncio.run(body(Request(),('revision','node_id','input_text')))
 assert problem.value.status_code==422
