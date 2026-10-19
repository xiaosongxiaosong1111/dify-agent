import copy,json,uuid
import pytest
import httpx
from test_api import client,create
from test_intake import new,review
from test_task_budget import provider
from app.interview_text_preview import MessagePreview,MAX_PREVIEW
from app import main
from app.providers import ProviderError


def test_fragmented_string_escapes_unicode_pair_and_no_other_fields():
    p=MessagePreview()
    for part in ['{"mes','sage": "第一行','\\n第二行','\\uD83D','\\uDE','00','\\"引用','\\""',',"requirements_patch":{"rules":"不应泄漏"},"thought":"不应泄漏"}']:
        p.feed(part)
    assert p.value()=='第一行\n第二行😀"引用"'


@pytest.mark.parametrize('body',['{"nested":{"message":"隐藏"}}','{"analysis":"隐藏","message":"不猜位置"}','```json\n{"message":"围栏"}','{"message":"坏\\q转义"}','{"message":"坏\n裸换行"}','{"message":"\\uDC00"}','{"message":"\\uD800x"}','{"message":"\\uD800\\u0041"}','{"message":"\\u0000"}','{"message":"'+('x'*(MAX_PREVIEW+1))])
def test_unavailable_or_invalid_preview_never_guesses_other_data(body):
    p=MessagePreview();p.feed(body);assert p.value() is None


def test_incomplete_unicode_or_escape_only_shows_valid_prefix():
    p=MessagePreview();p.feed('{"message":"原文\\uD83D');assert p.value()=='原文'
    p.feed('\\uDE00\\');assert p.value()=='原文😀'
    p.feed('n续');assert p.value()=='原文😀\n续'


def begin(client):
    task=create(client);item=str(uuid.uuid4());task['active_interview_id']=item;task['status']='interviewing'
    main.interview_progress.begin(task,{'id':'fixture-provider','model':'fixture-model'},item,True)
    main.interview_progress.received(item,'{"message":"正在形成建议')
    return task,item


def test_current_task_only_volatile_preview_never_stored_or_applied(client):
    task,item=begin(client);before=copy.deepcopy(main.get_task(task['id']))
    response=client.get(f"/api/tasks/{task['id']}/interviews");record=response.json()['operations'][0]
    assert record['message_preview']=='正在形成建议' and record['status']=='running'
    assert 'message_preview' not in main.store.get('interview_operation',item)
    assert main.get_task(task['id'])==before and not main.budgets.get(task['id'])['entries']
    other=create(client);assert client.get(f"/api/tasks/{other['id']}/interviews/{item}").status_code==404


@pytest.mark.parametrize('change',['paused','revision','active','phase','finish','recover'])
def test_stale_paused_terminal_validation_restart_never_expose_preview(client,change):
    task,item=begin(client)
    if change=='phase':main.interview_progress.phase(item,'validating_response')
    elif change=='finish':main.interview_progress.finish(task,item,'failed','技术失败样例')
    elif change=='recover':main.interview_progress.recover()
    else:
        row=main.get_task(task['id'])
        if change=='paused':row['status']='paused'
        elif change=='revision':row['revision']+=1
        else:row['active_interview_id']=str(uuid.uuid4())
        main.store.put('task',task['id'],row)
    record=client.get(f"/api/tasks/{task['id']}/interviews/{item}").json()
    assert 'message_preview' not in record
    if change in {'phase','finish','recover'}:assert item not in main.interview_progress.previews


@pytest.mark.parametrize('failure',[False,True])
def test_actual_stream_interview_previews_then_validates_or_discards_without_new_call(client,monkeypatch,failure):
    task=new(client);provider(client);calls=[];snapshots=[]
    async def model(*args,**kwargs):
        calls.append(1);assert kwargs['stream']
        await kwargs['on_delta']('{"message":"接收中的建议')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://fixture') as reader:
            snapshots.append((await reader.get(f"/api/tasks/{task['id']}/interviews")).json())
        assert main.get_task(task['id'])['requirements']==task['requirements']
        if failure:raise ProviderError('模型流技术失败，没有重试')
        return json.dumps({'message':'完整且待用户确认的建议','requirements_patch':{},'intake_review':review(main.get_task(task['id']))}),{'prompt_tokens':20,'completion_tokens':40}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'检查当前说明','stream_response':True});assert response.status_code==200,response.text
    assert snapshots[0]['operations'][0]['message_preview']=='接收中的建议' and len(calls)==1
    current=response.json();records=client.get(f"/api/tasks/{task['id']}/interviews").json()['operations']
    assert all('message_preview' not in r for r in records)
    assert not current['requirements_confirmed'] and current['requirements']==task['requirements']
    if failure:assert all(m['content']!='接收中的建议' for m in current['messages'])
    else:assert current['messages'][-1]['content']=='完整且待用户确认的建议'
