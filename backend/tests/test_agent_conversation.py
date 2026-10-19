import asyncio
import pytest
from test_api import client
from test_agent_plan import runtime_task, stream_call
from app import main
from app.dify import DifyClient, DifyError


def source_record(task):
    return {'id':'source','kind':'run','status':'success','revision':task['revision'],'environment_id':task['environment_id'],
            'result':{'answer':'第一轮','conversation_id':'conversation-1','terminal':True}}


def test_native_free_followup_dispatches_saved_conversation_and_keeps_provenance(client, monkeypatch):
    task=runtime_task(client);seen=[]
    async def native(self,query,*,conversation_id=None,**kwargs):
        seen.append((query,conversation_id))
        return {'answer':'回答','conversation_id':conversation_id or 'conversation-1','terminal':True}
    monkeypatch.setattr(DifyClient,'run_agent',native)
    first=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'第一轮'}})
    assert first.status_code==200,first.text
    sid=first.json()['runs'][-1]['id']
    second=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'追问'},'conversation_from_run_id':sid})
    assert second.status_code==200,second.text
    run=second.json()['runs'][-1]
    assert seen==[('第一轮',None),('追问','conversation-1')]
    assert run['input']=={'query':'追问','conversation_id':'conversation-1'}
    assert run['conversation_context']=={'source_run_id':sid,'conversation_id':'conversation-1','revision':task['revision'],'environment_id':task['environment_id']}
    assert not run.get('test_case') and not run.get('evaluation')
    assert client.get(f"/api/tasks/{task['id']}/acceptance").json()['required']['passed']==0


@pytest.mark.parametrize('mismatch',['revision','environment','failed','unknown','foreign_task','fixed_case','bad_id'])
def test_invalid_native_source_never_dispatches(client,monkeypatch,mismatch):
    task=runtime_task(client);record=source_record(task)
    if mismatch=='revision':record['revision']-=1
    if mismatch=='environment':record['environment_id']='elsewhere'
    if mismatch in {'failed','unknown'}:record['status']=mismatch
    if mismatch=='fixed_case':record['test_case']={'id':'fixed'}
    if mismatch=='bad_id':record['result']['conversation_id']='bad/id'
    if mismatch!='foreign_task':task['runs'].append(record)
    main.save_task(task)
    async def forbidden(*args,**kwargs):pytest.fail('Invalid source dispatched')
    monkeypatch.setattr(DifyClient,'run_agent',forbidden)
    response=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'追问'},'conversation_from_run_id':'source'})
    assert response.status_code==422
    assert len(main.get_task(task['id'])['runs'])==len(task['runs'])


@pytest.mark.parametrize('inputs',[{'query':'q','conversation_id':'typed-id'},{'query':'q','files':[]},{'query':''}])
def test_native_unsupported_or_unproven_input_is_rejected_before_dispatch(client,monkeypatch,inputs):
    task=runtime_task(client)
    async def forbidden(*args,**kwargs):pytest.fail('Invalid input dispatched')
    monkeypatch.setattr(DifyClient,'run_agent',forbidden)
    response=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':inputs})
    assert response.status_code==422 and not main.get_task(task['id'])['runs']


def test_native_returned_different_conversation_is_unknown_and_blocks_retry(client,monkeypatch):
    task=runtime_task(client);task['runs'].append(source_record(task));main.save_task(task)
    async def inconsistent(*args,**kwargs):return {'answer':'回答','conversation_id':'different','terminal':True}
    monkeypatch.setattr(DifyClient,'run_agent',inconsistent)
    payload={'revision':task['revision'],'input':{'query':'追问'},'conversation_from_run_id':'source'}
    assert client.post(f"/api/tasks/{task['id']}/run",json=payload).status_code==502
    assert main.get_task(task['id'])['runs'][-1]['status']=='unknown'
    assert client.post(f"/api/tasks/{task['id']}/run",json=payload).status_code==409


def test_native_sse_sends_source_identity_as_top_level_parameter(tmp_path,monkeypatch):
    adapter,seen,_=stream_call(tmp_path,monkeypatch,[{'event':'message','answer':'回答','conversation_id':'conversation-1','task_id':'task-1'},{'event':'message_end'}])
    result=asyncio.run(adapter.run_agent('追问',conversation_id='conversation-1'))
    assert result['terminal'] and result['conversation_id']=='conversation-1'
    assert seen==[('/v1/chat-messages',{'query':'追问','inputs':{},'response_mode':'streaming','user':'flowcraft-local','conversation_id':'conversation-1'})]


def test_native_sse_conflicting_source_attempts_stop_and_preserves_actual_id(tmp_path,monkeypatch):
    adapter,seen,_=stream_call(tmp_path,monkeypatch,[{'event':'message','answer':'回答','conversation_id':'different','task_id':'task-1'},{'event':'message_end'}])
    with pytest.raises(DifyError,match='结果可能未知') as error:
        asyncio.run(adapter.run_agent('追问',conversation_id='conversation-1'))
    assert error.value.result['conversation_id']=='different' and error.value.result['stop_acknowledged']
    assert [path for path,_ in seen]==['/v1/chat-messages','/v1/chat-messages/task-1/stop']


def test_native_adapter_invalid_identity_never_dispatches(tmp_path,monkeypatch):
    adapter,seen,_=stream_call(tmp_path,monkeypatch,[])
    with pytest.raises(DifyError,match='本次未派发'):
        asyncio.run(adapter.run_agent('追问',conversation_id='bad/id'))
    assert not seen
