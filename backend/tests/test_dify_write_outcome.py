import copy
import httpx
import pytest
from test_api import client,create_env,at22_static_task,forbid_api_external_calls
from app import main


@pytest.mark.parametrize('kind',['import','run'])
@pytest.mark.parametrize('failure',['read','write','remote_protocol','invalid_json'])
def test_dispatched_write_without_trustworthy_response_is_unknown_and_never_replayed(client,monkeypatch,forbid_api_external_calls,kind,failure):
    env=create_env(client);task=at22_static_task(client,env_id=env['id']);tid=task['id'];calls=[]
    if kind=='run':
        async def imported(self,*a):return {'status':'completed','app_id':'at22-synthetic-app'}
        monkeypatch.setattr(main.DifyClient,'import_new',imported)
        response=client.post(f'/api/tasks/{tid}/import',json={'revision':task['revision']});assert response.status_code==200
        task=response.json();assert client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'at22-synthetic-app','service_api_key':'public-fake-only'}).status_code==200
    before=copy.deepcopy(main.get_task(tid));content=main.artifact_path(before).read_bytes()
    async def wire(self,request):
        calls.append((request.method,request.url.path))
        if failure=='invalid_json':return httpx.Response(200,text='<html>PUBLIC NON-JSON</html>',request=request)
        error={'read':httpx.ReadError,'write':httpx.WriteError,'remote_protocol':httpx.RemoteProtocolError}[failure]
        raise error('PRIVATE-SYNTHETIC-TRANSPORT-VALUE',request=request)
    monkeypatch.setattr(main.DifyClient,'request',forbid_api_external_calls)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',wire)
    payload={'revision':task['revision'],**({'case_id':'warranty'} if kind=='run' else {})}
    response=client.post(f'/api/tasks/{tid}/{kind}',json=payload);assert response.status_code==502
    saved=main.get_task(tid);record=saved['runs'][-1]
    assert record['status']=='unknown',record
    assert record['outcome_unknown'] is True and record['error_code'] in {'console_unreachable','console_response_invalid'}
    assert 'PRIVATE-SYNTHETIC' not in response.text and 'PUBLIC NON-JSON' not in response.text
    assert '结果可能未知' in record['error'] and record['completed_at']
    assert saved['revision']==before['revision'] and saved['artifact']==before['artifact'] and saved.get('dify_app_id')==before.get('dify_app_id')
    assert main.artifact_path(saved).read_bytes()==content
    assert 'result' not in record and 'evaluation' not in record
    assert client.post(f'/api/tasks/{tid}/{kind}',json=payload).status_code==409
    assert len(calls)==1


@pytest.mark.parametrize('method',['GET','POST'])
@pytest.mark.parametrize('failure',['connect','read','invalid_json'])
def test_adapter_uncertainty_is_about_dispatched_write_not_display_wording(client,monkeypatch,forbid_api_external_calls,method,failure):
    import asyncio
    env=create_env(client);calls=[]
    async def wire(self,request):
        calls.append(request.method)
        if failure=='invalid_json':return httpx.Response(200,text='PUBLIC INVALID JSON',request=request)
        error=httpx.ConnectError if failure=='connect' else httpx.ReadError
        raise error('PRIVATE-SYNTHETIC-WIRE-ERROR',request=request)
    monkeypatch.setattr(main.DifyClient,'request',forbid_api_external_calls);monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',wire)
    with pytest.raises(main.DifyError) as caught:
        asyncio.run(main.DifyClient(env,main.store).request(method,'/console/api/public-isolated',credential='console_token'))
    assert caught.value.outcome_unknown is (method=='POST' and failure!='connect')
    assert calls==[method] and 'PRIVATE-SYNTHETIC' not in str(caught.value)


def test_typed_unknown_does_not_need_a_specific_error_sentence(client,monkeypatch):
    env=create_env(client);task=at22_static_task(client,env_id=env['id']);calls=[]
    async def wire(self,*a):calls.append(1);raise main.DifyError('公开替代说明',code='public_unknown_test',outcome_unknown=True)
    monkeypatch.setattr(main.DifyClient,'import_new',wire)
    assert client.post(f"/api/tasks/{task['id']}/import",json={'revision':task['revision']}).status_code==502
    record=main.get_task(task['id'])['runs'][-1]
    assert record['status']=='unknown' and record['outcome_unknown'] is True and record['error_code']=='public_unknown_test' and calls==[1]
