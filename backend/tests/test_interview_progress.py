import asyncio,copy,json
import pytest,httpx
from test_api import client,create
from test_task_budget import provider,policy
from app import main
from app.providers import ProviderError


def configured(client):
    task=create(client);p=provider(client)
    task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json()
    return task,p


def test_streamed_interview_counts_only_before_complete_validated_commit(client,monkeypatch):
    t,p=configured(client);seen=[]
    async def controlled(*a,**kw):
        assert kw['stream'] is True
        current=main.get_task(t['id']);assert current['revision']==t['revision'] and current['requirements']==t['requirements']
        assert current['active_interview_id']
        for delta in ('private-chunk','第二段','结尾'):await kw['on_delta'](delta)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as api:
            read=(await api.get(f"/api/tasks/{t['id']}/interviews")).json()
        record=read['operations'][0]
        assert record['phase']=='receiving_response' and record['received_characters']>0 and record['delta_count']>=1
        assert 'private-chunk' not in json.dumps(read) and 'not-a-real-key' not in json.dumps(read)
        seen.append(record['id'])
        return json.dumps({'message':'请确认用户范围','requirements_patch':{'goal':'明确的新目标'}},ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'开发样例','stream_response':True})
    assert response.status_code==200,response.text
    saved=response.json();assert saved['requirements']['goal']=='明确的新目标' and saved['revision']==t['revision']+1 and not saved['requirements_confirmed']
    read=client.get(f"/api/tasks/{t['id']}/interviews").json();r=read['operations'][0]
    assert read['active_operation_id'] is None and r['status']=='applied' and r['phase']=='completed' and r['applied']
    assert r['received_characters']==len('private-chunk第二段结尾') and r['delta_count']==3 and r['result_revision']==saved['revision']
    assert client.get(f"/api/tasks/{t['id']}/interviews/{seen[0]}").json()==r
    other=create(client);assert client.get(f"/api/tasks/{other['id']}/interviews/{seen[0]}").status_code==404


@pytest.mark.parametrize('mode',['bad_json','user_pause','stream_error','cancel'])
def test_streamed_interview_failure_pause_and_interrupt_never_apply_partial_state(client,monkeypatch,mode):
    t,p=configured(client);assert policy(client,t,'1').status_code==200
    async def controlled(*a,**kw):
        await kw['on_delta']('private-partial')
        if mode=='user_pause':
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as api:await api.post(f"/api/tasks/{t['id']}/pause")
        if mode=='stream_error':raise ProviderError('流中断',usage={},partial_usage={'prompt_tokens':100,'completion_tokens':3})
        if mode=='cancel':raise asyncio.CancelledError()
        return ('bad' if mode=='bad_json' else json.dumps({'message':'迟到候选','requirements_patch':{'goal':'不能采用'}})),{'prompt_tokens':100,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    if mode=='cancel':
        with pytest.raises(BaseException):client.post(f"/api/tasks/{t['id']}/messages",json={'content':'测试','stream_response':True})
    else:assert client.post(f"/api/tasks/{t['id']}/messages",json={'content':'测试','stream_response':True}).status_code==200
    current=main.get_task(t['id']);assert current['requirements']==t['requirements'] and current['revision']==t['revision'] and not current.get('active_interview_id')
    record=client.get(f"/api/tasks/{t['id']}/interviews").json()['operations'][0]
    assert record['status']=={'bad_json':'failed','user_pause':'paused','stream_error':'paused','cancel':'interrupted'}[mode] and not record['applied']
    assert 'private-partial' not in json.dumps(record)


def test_stream_preflight_missing_model_and_nonboolean_does_not_save_user_message(client):
    t=create(client);before=main.get_task(t['id'])
    assert client.post(f"/api/tasks/{t['id']}/messages",json={'content':'测试','stream_response':True}).status_code==422
    assert client.post(f"/api/tasks/{t['id']}/messages",json={'content':'测试','stream_response':'true'}).status_code==422
    assert main.get_task(t['id'])==before and not main.store.list('interview_operation')


def test_nonstream_interview_keeps_old_provider_call_and_records_phase(client,monkeypatch):
    t,p=configured(client)
    async def controlled(*a,**kw):
        assert 'stream' not in kw and 'on_delta' not in kw
        return json.dumps({'message':'正常回复','requirements_patch':{}}),{'prompt_tokens':10,'completion_tokens':3}
    monkeypatch.setattr(main,'call_model',controlled)
    assert client.post(f"/api/tasks/{t['id']}/messages",json={'content':'测试'}).status_code==200
    r=client.get(f"/api/tasks/{t['id']}/interviews").json()['operations'][0]
    assert not r['stream_requested'] and r['received_characters']==0 and r['status']=='applied'


def test_restart_marks_unfinished_checkpoint_and_never_replays(client,monkeypatch):
    t,p=configured(client);op='controlled-operation';t['status']='interviewing';t['active_interview_id']=op;main.interview_progress.begin(t,p,op,True)
    main.interview_progress.received(op,'partial');main.budgets.recover();main.interview_progress.recover()
    r=client.get(f"/api/tasks/{t['id']}/interviews/{op}").json();current=main.get_task(t['id'])
    assert r['status']=='interrupted' and not r['applied'] and current['status']=='paused' and not current.get('active_interview_id')
    assert current['requirements']==t['requirements'] and not main.budgets.get(t['id'])['entries']
