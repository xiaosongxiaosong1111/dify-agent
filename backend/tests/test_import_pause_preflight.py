"""暂停跨过已开始导入的来源读取：只在写入前拦截本操作，不锁新的人工请求。"""
import asyncio,copy,sys
from pathlib import Path
import httpx,pytest,yaml

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_api import client,create_env,approved  # noqa: F401  正常API替身夹具
from test_dsl_roundtrip import prepared,changed,apply,confirm_and_build
from app import main
from app.dify import DifyClient

NEW_APP='11111111-1111-4111-8111-111111111111'


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('导入暂停隔离检查不得访问真实 HTTP、Dify 请求或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(DifyClient, 'request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def live_reference(client, monkeypatch):
    """正常API：导入来源任务 → 在线读取dify_draft → 合并/应用 → 确认+构建。"""
    task,root=prepared(client)
    current=changed(root)
    async def exported(*args):return yaml.safe_dump(current)
    monkeypatch.setattr(DifyClient,'export_dsl',exported)
    response=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision']})
    assert response.status_code==200,response.text
    task=response.json()['task']
    result,_=apply(client,task)
    assert result.status_code==200,result.text
    task=confirm_and_build(client,result.json())
    assert main.store.get('dsl_reference',task['dsl_reference']['id'])['source']=='dify_draft'
    return task,current


def test_pause_during_source_export_blocks_import_before_dispatch(client,monkeypatch):
    task,current=live_reference(client,monkeypatch);tid=task['id'];calls=[]
    async def export_then_pause(self,app_id):
        response=await asyncio.to_thread(client.post,f"/api/tasks/{tid}/pause")
        assert response.status_code==200,response.text
        return yaml.safe_dump(current)
    async def imported(*args,**kwargs):
        calls.append(1);return {'app_id':NEW_APP,'status':'completed'}
    monkeypatch.setattr(DifyClient,'export_dsl',export_then_pause)
    monkeypatch.setattr(DifyClient,'import_new',imported)
    before=copy.deepcopy(main.get_task(tid))
    response=client.post(f"/api/tasks/{tid}/import",json={'revision':task['revision']})
    assert response.status_code==409,response.text
    assert calls==[]
    saved=main.get_task(tid);run=saved['runs'][-1]
    assert saved['status']=='paused' and saved['dify_app_id'] is None
    assert saved['revision']==before['revision'] and saved['artifact']==before['artifact']
    assert saved['dsl_reference']==before['dsl_reference']
    assert saved['runs'][:-1]==before['runs']
    assert run['status']=='failed' and run.get('outcome_unknown') is False
    assert run.get('error_code')=='import_paused_before_dispatch' and '未创建' in run['error']


def test_generation_change_during_export_blocks_import_even_if_status_unpaused(client,monkeypatch):
    task,current=live_reference(client,monkeypatch);tid=task['id'];calls=[]
    async def export_bump(self,app_id):
        def bump():
            with main.store.lock:
                row=main.get_task(tid);row['pause_generation']=row.get('pause_generation',0)+1;row['status']='draft_ready';main.save_task(row)
        await asyncio.to_thread(bump)
        return yaml.safe_dump(current)
    async def imported(*args,**kwargs):
        calls.append(1);return {'app_id':NEW_APP,'status':'completed'}
    monkeypatch.setattr(DifyClient,'export_dsl',export_bump)
    monkeypatch.setattr(DifyClient,'import_new',imported)
    response=client.post(f"/api/tasks/{tid}/import",json={'revision':task['revision']})
    assert response.status_code==409,response.text
    assert calls==[]
    saved=main.get_task(tid);run=saved['runs'][-1]
    assert saved['dify_app_id'] is None and run['status']=='failed'
    assert run.get('outcome_unknown') is False and run.get('error_code')=='import_paused_before_dispatch'


def test_fresh_import_request_after_pause_is_explicit_continue(client,monkeypatch):
    task,current=live_reference(client,monkeypatch);tid=task['id'];calls=[]
    assert client.post(f"/api/tasks/{tid}/pause").status_code==200
    assert main.get_task(tid)['status']=='paused'
    async def exported(*args):return yaml.safe_dump(current)
    async def imported(*args,**kwargs):
        calls.append(1);return {'app_id':NEW_APP,'status':'completed'}
    monkeypatch.setattr(DifyClient,'export_dsl',exported)
    monkeypatch.setattr(DifyClient,'import_new',imported)
    response=client.post(f"/api/tasks/{tid}/import",json={'revision':task['revision']})
    assert response.status_code==200,response.text
    assert calls==[1]
    saved=main.get_task(tid)
    assert saved['dify_app_id']==NEW_APP and saved['status']=='imported'
    assert saved['runs'][-1]['status']=='success'


def test_pause_after_import_post_keeps_known_success_and_app_binding(client,monkeypatch):
    task,current=live_reference(client,monkeypatch);tid=task['id'];calls=[]
    async def exported(*args):return yaml.safe_dump(current)
    async def import_then_pause(self,content,name):
        calls.append(1)
        response=await asyncio.to_thread(client.post,f"/api/tasks/{tid}/pause")
        assert response.status_code==200,response.text
        return {'app_id':NEW_APP,'status':'completed'}
    monkeypatch.setattr(DifyClient,'export_dsl',exported)
    monkeypatch.setattr(DifyClient,'import_new',import_then_pause)
    response=client.post(f"/api/tasks/{tid}/import",json={'revision':task['revision']})
    assert response.status_code==200,response.text
    assert calls==[1]
    saved=main.get_task(tid);run=saved['runs'][-1]
    assert saved['dify_app_id']==NEW_APP and saved['status']=='paused'
    assert run['status']=='success' and run.get('outcome_unknown') is not True
