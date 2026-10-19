import copy,json,uuid
import pytest,yaml
from test_api import client
from test_runtime_files import ready,prepare as upload_plan,execute as upload_execute,receipt,REMOTE
from test_file_run import remote,run,PUBLISHED,RUN
from test_optional_file import optional_plan
from test_workflow_plan import plan_task
from app.workflow_plan import compile_workflow_plan
from app import main
from app.file_run import KIND,plan_token

def optional_ready(client,op='exists'):
 t,env=ready(client);text,checked=compile_workflow_plan(plan_task(optional_plan(op)));assert checked['valid']
 main.artifact_path(t).write_text(text,encoding='utf-8');main.store.set_secret(env['id'],'console_token','fixture-console-token');return t,env
def prepare(client,t,values,**patch):return client.post(f"/api/tasks/{t['id']}/file-runs/prepare",json={'revision':t['revision'],'input_text':json.dumps(values),**patch})
def upload(client,monkeypatch,t):
 async def send(*a):return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',send);p=upload_plan(client,t).json();assert upload_execute(client,t,p).status_code==200;return p
def returned(text):return {'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'succeeded','outputs':{'result':text}}}

@pytest.mark.parametrize('values,state',[({},'omitted'),({'document':None},'explicit_null'),({'missing_message':None},'omitted'),({'document':None,'missing_message':'自定义没有文件时的说明'},'explicit_null'),({'missing_message':''},'omitted')])
def test_missing_file_is_local_frozen_and_native_omission_null_are_preserved(client,monkeypatch,values,state):
 t,env=optional_ready(client);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('准备分支方案不能解密、上传、查询平台或调用模型')
 with monkeypatch.context() as m:
  m.setattr(main.store,'secret',forbidden);m.setattr(main.DifyClient,'request',forbidden)
  r=prepare(client,t,values);assert r.status_code==200,r.text
 q=r.json();flow=q['data_flow'];assert q['plan_schema_version']==5 and flow['schema_version']==4 and flow['scenario']=='document_optional_extraction'
 assert q['input']==values and q['files']==[] and flow['extraction']['files']==[] and flow['resolved_branch']['file_input_state']==state
 message=values.get('missing_message');message='本次没有提供文件' if message is None else message
 assert flow['resolved_branch']['expected_outputs']=={'result':message} and flow['resolved_branch']['expected_path']=='file_missing'
 assert flow['resolved_branch']['skipped_node_ids']==['extract','end'] and flow['resolved_branch']['actual_path_verified'] is False
 assert not flow['model_egress'] and q['workflow_runs']==1 and main.get_task(t['id'])==before
 calls,_=remote(monkeypatch,t,env,result=returned(message));assert run(client,t,q).status_code==422 and not calls
 r=run(client,t,q,acknowledge_optional_branch=True);assert r.status_code==200,r.text
 assert r.json()['plan']['optional_branch_approved'] and not r.json()['plan']['business_verified'] and calls[-1]==('run',values)
 assert [c[0] for c in calls]==['keys','published','run'] and 'upload_file_id' not in json.dumps(calls)
 assert run(client,t,q,acknowledge_optional_branch=True).status_code==409 and len(calls)==3

@pytest.mark.parametrize('op',['exists','not exists'])
def test_present_file_uses_trusted_upload_and_keeps_unselected_missing_path(client,monkeypatch,op):
 t,env=optional_ready(client,op);p=upload(client,monkeypatch,t);values={'document':{'sierra_file_id':p['id']}};r=prepare(client,t,values);assert r.status_code==200,r.text;q=r.json()
 flow=q['data_flow'];assert len(q['files'])==1 and flow['resolved_branch']['file_input_state']=='uploaded_file' and flow['resolved_branch']['expected_end_node_id']=='end'
 assert flow['resolved_branch']['skipped_node_ids']==['no_file'] and flow['resolved_branch']['expected_outputs'] is None
 assert flow['optional_file']['present_handle']==('provided' if op=='exists' else 'false')
 calls,workflow=remote(monkeypatch,t,env);before=copy.deepcopy(workflow);r=run(client,t,q,acknowledge_optional_branch=True);assert r.status_code==200,r.text
 assert calls[-1][1]=={'document':{'type':'document','transfer_method':'local_file','upload_file_id':REMOTE}} and workflow==before
 assert len(workflow['graph']['nodes'])==5 and 'upload_file_id' not in json.dumps(r.json())

@pytest.mark.parametrize('value',['',{},[],False,0,{'upload_file_id':REMOTE},{'sierra_file_id':str(uuid.uuid4())}])
def test_bad_present_file_is_not_treated_as_omitted_or_fallback(client,monkeypatch,value):
 t,env=optional_ready(client);r=prepare(client,t,{'document':value});assert r.status_code in (409,422),r.text;assert not main.store.list(KIND) and not main.get_task(t['id'])['runs']

@pytest.mark.parametrize('value',[[],{},False,1,'x'*2001,'bad\x00text','\ud800'])
def test_fallback_is_not_coerced_truncated_or_implicitly_sanitized(client,value):
 t,env=optional_ready(client);r=prepare(client,t,{'missing_message':value});assert r.status_code==422,r.text;assert not main.store.list(KIND)

def test_wrong_missing_message_receipt_is_unknown_not_success_or_auto_retry(client,monkeypatch):
 t,env=optional_ready(client);q=prepare(client,t,{}).json();calls,_=remote(monkeypatch,t,env,result=returned('意外的其他路径输出'))
 r=run(client,t,q,acknowledge_optional_branch=True);assert r.status_code==502 and main.get_task(t['id'])['runs'][-1]['status']=='unknown'
 assert main.store.get(KIND,q['id'])['state']=='unknown' and run(client,t,q,acknowledge_optional_branch=True).status_code==409 and len(calls)==3

@pytest.mark.parametrize('branch',['present','missing'])
def test_actual_published_unselected_path_is_still_frozen(client,monkeypatch,branch):
 t,env=optional_ready(client);q=prepare(client,t,{}).json();calls,workflow=remote(monkeypatch,t,env)
 target='extract' if branch=='present' else 'no_file';next(n for n in workflow['graph']['nodes'] if n['id']==target)['data']['desc']='changed unselected path'
 assert run(client,t,q,acknowledge_optional_branch=True).status_code==502 and [c[0] for c in calls]==['keys','published'] and not main.get_task(t['id'])['runs']

def test_conditional_approval_cannot_be_downgraded_to_old_linear_plan(client,monkeypatch):
 t,env=optional_ready(client);q=prepare(client,t,{}).json();row=main.store.get(KIND,q['id']);row['plan_schema_version']=4;row['resource_token']=plan_token(row);main.store.put(KIND,row['id'],row)
 calls,_=remote(monkeypatch,t,env);assert run(client,t,row).status_code==409 and not calls

@pytest.mark.parametrize('ack',[False,1,'true'])
def test_optional_branch_ack_is_independent_strict_and_never_reuses_general_approval(client,monkeypatch,ack):
 t,env=optional_ready(client);q=prepare(client,t,{}).json();calls,_=remote(monkeypatch,t,env)
 assert run(client,t,q,acknowledge_optional_branch=ack).status_code==422 and not calls and main.store.get(KIND,q['id'])['attempts']==0

def test_no_file_fixed_cases_keep_omission_and_null_distinct_and_map_without_upload(client,monkeypatch):
 t,env=optional_ready(client)
 def capture(values,revision):return client.post(f"/api/tasks/{t['id']}/file-cases/capture",json={'revision':t['revision'],'catalog_revision':revision,'input_text':json.dumps(values),'name':'缺文件路径','expectation':{'mode':'equals','target':'result','expected':'本次没有提供文件'}})
 c=capture({},0);assert c.status_code==200,c.text;first=c.json();assert first['cases'][0]['input']=={}
 c=capture({'document':None},1);assert c.status_code==200,c.text;second=c.json();assert len(second['cases'])==2 and not second['stale'] and second['cases'][1]['input']=={'document':None}
 assert main.store.get('runtime_file_cases',t['id'])['history'][0]['binding_digest']==main.store.get('runtime_file_cases',t['id'])['binding_digest']
 for case in second['cases']:
  mapped=client.post(f"/api/tasks/{t['id']}/file-cases/{case['id']}/match",json={'revision':t['revision'],'catalog_revision':2});assert mapped.status_code==200,mapped.text
  assert mapped.json()['state']=='ready' and mapped.json()['slots']==[] and json.loads(mapped.json()['input_text'])==case['input']
 wrong=prepare(client,t,{'document':None},case_id=second['cases'][0]['id'],case_catalog_revision=2);assert wrong.status_code==422
 q=prepare(client,t,{},case_id=second['cases'][0]['id'],case_catalog_revision=2);assert q.status_code==200,q.text;remote(monkeypatch,t,env,result=returned('本次没有提供文件'))
 assert run(client,t,q.json(),acknowledge_optional_branch=True).status_code==200
 assert client.get(f"/api/tasks/{t['id']}/acceptance").json()['required']['passed']==1

def test_normal_run_cannot_bypass_new_optional_plan_even_for_empty_input(client,monkeypatch):
 t,env=optional_ready(client);calls,_=remote(monkeypatch,t,env)
 assert client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':{}}).status_code==422 and not calls

@pytest.mark.parametrize('mutation',['case_extra','case_conflict','bad_logic','bad_operator','extra_node','extra_edge','other_output','no_default','bad_length','unknown_version'])
def test_optional_runtime_scope_never_drops_unknown_or_additional_behavior(client,mutation):
 from app.file_run_flow import describe
 t,env=optional_ready(client);root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'))
 nodes=root['workflow']['graph']['nodes'];guard=next(n for n in nodes if n['id']=='guard');case=guard['data']['cases'][0];fallback=nodes[0]['data']['variables'][1]
 if mutation=='case_extra':case['future_execution']='unknown'
 elif mutation=='case_conflict':case['id']='another-id'
 elif mutation=='bad_logic':case['logical_operator']=[]
 elif mutation=='bad_operator':case['conditions'][0]['comparison_operator']=[]
 elif mutation=='extra_node':nodes.append({'id':'other','data':{'type':'llm'}})
 elif mutation=='extra_edge':root['workflow']['graph']['edges'].append(copy.deepcopy(root['workflow']['graph']['edges'][0]))
 elif mutation=='other_output':next(n for n in nodes if n['id']=='no_file')['data']['outputs'][0]['variable']='other'
 elif mutation=='no_default':fallback.pop('default')
 elif mutation=='bad_length':fallback['max_length']=True
 elif mutation=='unknown_version':guard['data']['version']='2'
 with pytest.raises(ValueError):describe(root)
