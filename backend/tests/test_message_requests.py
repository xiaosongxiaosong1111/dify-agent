import asyncio,copy,json,uuid
import httpx,pytest
from test_api import client,create,forbid_api_external_calls
from test_interview_progress import configured
from app import main
from app.providers import ProviderError


def body(task,**kwargs):
    return {'request_id':str(uuid.uuid4()),'revision':task['revision'],'content':'公开只读讨论','mode':'discussion',**kwargs}


def test_duplicate_discussion_records_and_bills_only_one_model_call(client,monkeypatch):
    task,_=configured(client);calls=[];payload=body(task)
    async def model(*args,**kwargs):calls.append(True);return json.dumps({'message':'只读回复'}),{'prompt_tokens':10,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{task['id']}/messages",json=payload);assert response.status_code==200,response.text
    first=copy.deepcopy(main.get_task(task['id']))
    repeated=client.post(f"/api/tasks/{task['id']}/messages",json=payload)
    assert repeated.status_code==200 and repeated.json()==first and len(calls)==1
    assert main.get_task(task['id'])==first
    assert len(main.budgets.get(task['id'])['entries'])==1
    receipt=client.get(f"/api/tasks/{task['id']}/message-requests/{payload['request_id']}").json()
    assert receipt['state']=='applied' and receipt['operation_id']
    assert '公开只读讨论' not in json.dumps(receipt,ensure_ascii=False)


def test_review_retry_after_result_revision_change_returns_current_state_not_new_request(client,monkeypatch):
    task,_=configured(client);calls=[];payload=body(task,mode='review')
    async def model(*args,**kwargs):calls.append(True);return json.dumps({'message':'新草案','requirements_patch':{'goal':'公开新目标'}}),{'prompt_tokens':10,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',model)
    first=client.post(f"/api/tasks/{task['id']}/messages",json=payload);assert first.status_code==200,first.text
    assert first.json()['revision']>payload['revision']
    retry=client.post(f"/api/tasks/{task['id']}/messages",json=payload)
    assert retry.status_code==200 and retry.json()==first.json() and len(calls)==1


@pytest.mark.parametrize('change',[{'content':'other'},{'mode':'review'},{'stream_response':True},{'revision':999}])
def test_same_id_different_payload_is_rejected_without_call_or_mutation(client,monkeypatch,change):
    task,_=configured(client);payload=body(task);calls=[]
    async def model(*args,**kwargs):calls.append(True);return json.dumps({'message':'回复'}),{'prompt_tokens':10,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',model)
    assert client.post(f"/api/tasks/{task['id']}/messages",json=payload).status_code==200
    before=copy.deepcopy(main.get_task(task['id']))
    assert client.post(f"/api/tasks/{task['id']}/messages",json={**payload,**change}).status_code==409
    assert main.get_task(task['id'])==before and len(calls)==1


def test_parallel_same_id_is_blocked_while_original_is_running(client,monkeypatch):
    task,_=configured(client);payload=body(task);calls=[]
    async def model(*args,**kwargs):
        calls.append(True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as api:
            repeated=await api.post(f"/api/tasks/{task['id']}/messages",json=payload)
            assert repeated.status_code==409
        return json.dumps({'message':'唯一回复'}),{'prompt_tokens':10,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{task['id']}/messages",json=payload)
    assert response.status_code==200,response.text
    assert len(calls)==1 and len([m for m in response.json()['messages'] if m['role']=='user'])==1


def test_failure_remains_consumed_and_readonly_receipt_does_not_retry(client,monkeypatch):
    task,_=configured(client);payload=body(task);calls=[]
    async def failed(*args,**kwargs):calls.append(True);raise ProviderError('isolated provider failure')
    monkeypatch.setattr(main,'call_model',failed)
    response=client.post(f"/api/tasks/{task['id']}/messages",json=payload);assert response.status_code==200
    before=copy.deepcopy(main.get_task(task['id']))
    assert client.post(f"/api/tasks/{task['id']}/messages",json=payload).json()==before
    receipt=client.get(f"/api/tasks/{task['id']}/message-requests/{payload['request_id']}").json()
    assert receipt['state']=='failed' and len(calls)==1 and main.get_task(task['id'])==before


def test_no_provider_request_and_cross_task_receipt_are_isolated(client):
    task=create(client);payload=body(task)
    first=client.post(f"/api/tasks/{task['id']}/messages",json=payload);assert first.status_code==200,first.text
    assert client.post(f"/api/tasks/{task['id']}/messages",json=payload).json()==first.json()
    other=create(client)
    assert client.get(f"/api/tasks/{other['id']}/message-requests/{payload['request_id']}").status_code==404
    assert client.get(f"/api/tasks/{task['id']}/message-requests/{payload['request_id']}").json()['state']=='no_provider'


def test_stale_first_request_is_rejected_before_recording(client):
    task=create(client);payload=body(task,revision=task['revision']-1);before=copy.deepcopy(main.store.get('task',task['id']))
    assert client.post(f"/api/tasks/{task['id']}/messages",json=payload).status_code==409
    assert main.store.get('task',task['id'])==before
    assert client.get(f"/api/tasks/{task['id']}/message-requests/{payload['request_id']}").status_code==404


@pytest.mark.parametrize('bad',['not-uuid','../path',123,True])
def test_invalid_identity_rejected_without_echo_or_record(client,bad):
    task=create(client);response=client.post(f"/api/tasks/{task['id']}/messages",json=body(task,request_id=bad))
    assert response.status_code==422 and '公开只读讨论' not in response.text


def test_old_clients_without_request_identity_keep_existing_behavior(client):
    task=create(client)
    assert client.post(f"/api/tasks/{task['id']}/messages",json={'content':'旧客户端公开文字'}).status_code==200


def test_registered_interview_survives_restart_and_remains_consumed(client,monkeypatch,tmp_path):
    from app.message_requests import record
    from app.storage import Store
    task,provider=configured(client);payload=body(task);op=str(uuid.uuid4())
    request=record(main,task,main.Message(**payload),op)
    task['status']='interviewing';task['active_interview_id']=op
    main.interview_progress.begin(task,provider,op,False,'discussion',request_record=request)
    monkeypatch.setattr(main,'store',Store(tmp_path))
    main.budgets.recover();main.interview_progress.recover()
    receipt=client.get(f"/api/tasks/{task['id']}/message-requests/{payload['request_id']}").json()
    assert receipt['state']=='interrupted'
    before=copy.deepcopy(main.get_task(task['id']))
    assert client.post(f"/api/tasks/{task['id']}/messages",json=payload).json()==before
    assert main.get_task(task['id'])==before


def test_unknown_registered_request_is_not_redispatched(client):
    from app.message_requests import record
    task=create(client);payload=body(task);value=record(main,task,main.Message(**payload),None)
    main.store.put('message_request',value['id'],value)
    before=copy.deepcopy(main.store.get('task',task['id']))
    assert client.post(f"/api/tasks/{task['id']}/messages",json=payload).status_code==409
    assert main.store.get('task',task['id'])==before


def test_tracking_identity_requires_explicit_revision(client):
    task=create(client);value=body(task);value.pop('revision')
    assert client.post(f"/api/tasks/{task['id']}/messages",json=value).status_code==422


def test_identity_must_be_durable_before_any_model_dispatch(client,monkeypatch):
    task,_=configured(client);value=body(task);before=copy.deepcopy(main.store.get('task',task['id']))
    original=main.store.put_many
    def blocked(records):
        if any(row[0]=='message_request' for row in records):raise RuntimeError('isolated durable registration failure')
        return original(records)
    monkeypatch.setattr(main.store,'put_many',blocked)
    with pytest.raises(RuntimeError,match='durable registration'):
        client.post(f"/api/tasks/{task['id']}/messages",json=value)
    assert main.store.get('task',task['id'])==before
    assert not main.store.list('message_request') and not main.store.list('interview_operation')


def test_late_result_after_revision_change_keeps_consumed_request_identity(client,monkeypatch):
    task,_=configured(client);value=body(task);calls=[]
    async def model(*args,**kwargs):
        calls.append(True);current=main.get_task(task['id']);current['revision']+=1;main.save_task(current)
        return json.dumps({'message':'迟到只读回复'}),{'prompt_tokens':10,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',model)
    first=client.post(f"/api/tasks/{task['id']}/messages",json=value);assert first.status_code==409
    receipt=client.get(f"/api/tasks/{task['id']}/message-requests/{value['request_id']}").json()
    assert receipt['state']=='stale'
    before=copy.deepcopy(main.get_task(task['id']))
    assert client.post(f"/api/tasks/{task['id']}/messages",json=value).json()==before
    assert len(calls)==1
