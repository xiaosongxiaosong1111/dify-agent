import copy
import json
import pytest
from test_api import client
from test_chatflow_inputs import runtime
from app import main
from app.conversation_inputs import KIND


def request(client,task,values,source=None):
    return client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':values,**({'conversation_from_run_id':source} if source else {})})


def first(client,monkeypatch):
    task=runtime(client);seen=[]
    async def chat(self,query,inputs=None,conversation_id=None):
        seen.append((query,copy.deepcopy(inputs),conversation_id));return {'answer':'回答','conversation_id':conversation_id or 'stable-free'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=request(client,task,{'query':'首轮','budget':0});assert response.status_code==200,response.text
    task=response.json();return task,task['runs'][-1]['id'],seen


def test_custom_free_conversation_same_parameters_uses_original_cid_private_proof_and_no_default(client,monkeypatch):
    task,source,seen=first(client,monkeypatch);proof=main.store.get(KIND,source)
    assert proof['conversation_id']=='stable-free' and proof['app_id']==task['dify_app_id']
    assert proof['credential_stamp'] not in json.dumps(task) and 'unit-key' not in json.dumps(proof)
    response=request(client,task,{'query':'追问','budget':0},source);assert response.status_code==200,response.text
    assert seen==[('首轮',{'budget':0},None),('追问',{'budget':0},'stable-free')]
    record=response.json()['runs'][-1]
    assert record['conversation_context']['source_run_id']==source and not record.get('test_case') and not record.get('evaluation')
    assert main.store.get(KIND,record['id'])['conversation_id']=='stable-free'


@pytest.mark.parametrize('values',[
    {'query':'追问'}, {'query':'追问','budget':1}, {'query':'追问','budget':'0'},
    {'query':'追问','budget':0,'region':None}, {'query':'追问','budget':0,'extra':'PRIVATE-VALUE'},
])
def test_changed_or_missing_custom_parameters_fail_before_pending_budget_or_call(client,monkeypatch,values):
    task,source,seen=first(client,monkeypatch);before=copy.deepcopy(main.get_task(task['id']))
    def forbidden(*a,**kw):pytest.fail('参数不一致前不能登记运行预算')
    monkeypatch.setattr(main.execution_limits,'require_start',forbidden)
    response=request(client,task,values,source);assert response.status_code==422,response.text
    assert len(seen)==1 and main.get_task(task['id'])==before and 'PRIVATE-VALUE' not in response.text


@pytest.mark.parametrize('change',['credential','app','address','artifact','missing_proof','record_input','record_cid','proof_type'])
def test_source_target_credentials_artifact_and_receipt_binding_cannot_be_reused_after_change(client,monkeypatch,change):
    task,source,seen=first(client,monkeypatch)
    if change=='credential':main.store.set_secret(task['environment_id'],'service_api_key','new-unit-key')
    elif change=='address':
        env=main.store.get('environment',task['environment_id']);env['base_url']='http://127.0.0.1:9999';main.store.put('environment',env['id'],env)
    elif change=='artifact':
        path=main.artifact_path(task);path.write_text(path.read_text(encoding='utf-8')+'\n',encoding='utf-8')
    elif change=='missing_proof':main.store.delete(KIND,source)
    elif change=='proof_type':
        proof=main.store.get(KIND,source);proof['schema_version']=True;main.store.put(KIND,source,proof)
    else:
        current=main.get_task(task['id']);record=current['runs'][-1]
        if change=='app':record['app_id']='other-app'
        if change=='record_input':record['input']['budget']=1
        if change=='record_cid':record['result']['conversation_id']='changed-cid'
        main.save_task(current)
    before=copy.deepcopy(main.get_task(task['id']))
    def forbidden(*a,**kw):pytest.fail('来源不可信前不能登记预算或派发')
    monkeypatch.setattr(main.execution_limits,'require_start',forbidden)
    response=request(client,task,{'query':'追问','budget':0},source);assert response.status_code==422,response.text
    assert len(seen)==1 and main.get_task(task['id'])==before


def test_actual_client_uses_frozen_service_key_if_saved_key_changes_during_call(client,monkeypatch):
    task=runtime(client);seen=[]
    async def chat(self,query,inputs=None,conversation_id=None):
        original=self.store.secret(self.env['id'],'service_api_key');seen.append(original)
        main.store.set_secret(self.env['id'],'service_api_key','rotated-unit-key')
        assert self.store.secret(self.env['id'],'service_api_key')==original
        return {'answer':'回答','conversation_id':'frozen-key'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=request(client,task,{'query':'首轮','budget':0});assert response.status_code==200,response.text
    task=response.json();source=task['runs'][-1]['id'];assert seen==['unit-key']
    response=request(client,task,{'query':'追问','budget':0},source)
    assert response.status_code==422 and len(seen)==1


def test_success_and_private_binding_commit_together_without_credential_into_task(client,monkeypatch):
    task=runtime(client);original=main.store.put_many;commits=[]
    def commit(rows):commits.append(copy.deepcopy(rows));return original(rows)
    monkeypatch.setattr(main.store,'put_many',commit)
    async def chat(*a,**kw):return {'answer':'回答','conversation_id':'atomic-chat'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=request(client,task,{'query':'首轮','budget':0});assert response.status_code==200,response.text
    assert len(commits)==1 and [r[0] for r in commits[0]]==['task',KIND]
    task_value=commits[0][0][2];proof=commits[0][1][2]
    assert task_value['runs'][-1]['status']=='success' and proof['run_id']==task_value['runs'][-1]['id']
    assert 'credential_stamp' not in json.dumps(task_value) and 'unit-key' not in json.dumps(commits)


def test_chatflow_returning_different_conversation_is_unknown_not_original_success(client,monkeypatch):
    task,source,seen=first(client,monkeypatch)
    async def wrong(*a,**kw):seen.append('wrong');return {'answer':'回答','conversation_id':'other-chat'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',wrong)
    response=request(client,task,{'query':'追问','budget':0},source);assert response.status_code==502,response.text
    saved=main.get_task(task['id']);record=saved['runs'][-1]
    assert record['status']=='unknown' and main.store.get(KIND,record['id']) is None
    assert request(client,saved,{'query':'再次','budget':0},source).status_code==409 and len(seen)==2


def test_fixed_custom_case_keeps_same_captured_key_across_turns_without_free_source_proof(client,monkeypatch):
    from test_chatflow_case_inputs import prepared,run
    task=prepared(client);seen=[]
    async def chat(self,query,inputs=None,conversation_id=None):
        seen.append(self.store.secret(self.env['id'],'service_api_key'))
        if len(seen)==1:main.store.set_secret(self.env['id'],'service_api_key','new-during-case')
        return {'answer':'第一轮' if len(seen)==1 else '第二轮','conversation_id':conversation_id or 'case-frozen'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=run(client,task);assert response.status_code==200,response.text
    assert seen==['unit-key','unit-key'] and main.store.list(KIND)==[]


def test_custom_runtime_only_decrypts_service_key_not_console_or_dataset_credentials(client,monkeypatch):
    import hashlib
    from app.conversation_inputs import credential_stamp
    task=runtime(client);original=main.store.cipher.decrypt;seen=[];expected=credential_stamp(main.store,task['environment_id'])
    def decrypt(blob,*args,**kwargs):seen.append(hashlib.sha256(blob).hexdigest());return original(blob,*args,**kwargs)
    monkeypatch.setattr(main.store.cipher,'decrypt',decrypt)
    async def chat(*a,**kw):return {'answer':'回答','conversation_id':'service-only'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    response=request(client,task,{'query':'首轮','budget':0});assert response.status_code==200,response.text
    assert seen==[expected]


def test_private_binding_read_failure_is_explicit_no_budget_or_dispatch(client,monkeypatch):
    import sqlite3
    task,source,seen=first(client,monkeypatch);before=copy.deepcopy(main.get_task(task['id']));original=main.store.get
    def get(kind,item):
        if kind==KIND:raise sqlite3.OperationalError('PRIVATE DATABASE DETAILS')
        return original(kind,item)
    monkeypatch.setattr(main.store,'get',get)
    def forbidden(*a,**kw):pytest.fail('来源不可读取时不能登记预算')
    monkeypatch.setattr(main.execution_limits,'require_start',forbidden)
    response=request(client,task,{'query':'追问','budget':0},source)
    assert response.status_code==503 and 'PRIVATE DATABASE DETAILS' not in response.text
    assert len(seen)==1 and main.get_task(task['id'])==before
