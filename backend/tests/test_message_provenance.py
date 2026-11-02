import copy,json
import pytest
from test_api import client,create,approved,forbid_api_external_calls
from test_task_budget import provider
from test_material_parsing import upload
from test_planning import plan
from app import main
from app.discussion_mode import history_content
from app.intake import sources
from app.providers import ProviderError


def configured(client):
    task=create(client);p=provider(client)
    return client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json(),p


@pytest.mark.parametrize('mode',['review','discussion'])
@pytest.mark.parametrize('stream',[False,True])
def test_same_named_material_bodies_have_direct_identifiers_and_task_isolation(client,monkeypatch,mode,stream):
    task,p=configured(client);task,a=upload(client,task,'rules.txt',b'FIRST-PUBLIC-RULE');task,b=upload(client,task,'rules.txt',b'SECOND-PUBLIC-RULE')
    other=create(client);client.patch(f"/api/tasks/{other['id']}",json={'requirements':{'goal':'OTHER-TASK-PRIVATE-MARKER'}})
    before=copy.deepcopy(task['messages']);seen=[]
    async def fake(*args,**kwargs):
        messages=args[2];ctx=json.loads(messages[1]['content'].split('当前任务资料：',1)[1]);materials=ctx['materials']
        assert [(m['id'],m['source_sha256'],m['text']) for m in materials]==[(a['id'],a['sha256'],a['text']),(b['id'],b['sha256'],b['text'])]
        assert 'OTHER-TASK-PRIVATE-MARKER' not in json.dumps(messages) and 'not-a-real-key' not in json.dumps(messages)
        assert '当前修订' in messages[-1]['content']
        reply=json.dumps({'message':'公开隔离回复'} if mode=='discussion' else {'message':'公开隔离回复','requirements_patch':{}},ensure_ascii=False)
        if stream:await kwargs['on_delta'](reply)
        seen.append(ctx);return reply,{'prompt_tokens':10,'completion_tokens':2}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'核对两份同名资料，不代我裁定','mode':mode,'stream_response':stream})
    assert response.status_code==200,response.text
    saved=response.json();assert len(seen)==1 and saved['messages'][:len(before)]==before
    user,assistant=saved['messages'][-2:]
    assert user['context_revision']==assistant['context_revision']==task['revision'] and assistant['result_revision']==saved['revision']
    assert assistant.get('purpose')==('discussion' if mode=='discussion' else None)


@pytest.mark.parametrize('message,expected',[
    ({'role':'user','content':'原话'},'修订未记录'),
    ({'role':'user','content':'原话','context_revision':3},'历史消息'),
    ({'role':'user','content':'原话','context_revision':5},'当前修订'),
    ({'role':'assistant','content':'原话','context_revision':4,'result_revision':5},'当前修订'),
    ({'role':'assistant','content':'原话','context_revision':3,'result_revision':4},'历史消息'),
    ({'role':'user','content':'原话','context_revision':True,'result_revision':False},'修订未记录'),
])
def test_history_labels_do_not_modify_original_messages_or_guess_unknown_revisions(message,expected):
    before=copy.deepcopy(message);text=history_content(message,current_revision=5)
    assert expected in text and text.endswith('原话') and message==before
    assert 'vTrue' not in text and 'vFalse' not in text


def test_discussion_marker_and_legacy_helper_behavior_are_preserved():
    message={'role':'user','content':'原讨论','purpose':'discussion','context_revision':2}
    assert history_content(message)=='【只读讨论记录，未作为需求或批准】\n原讨论'
    text=history_content(message,current_revision=5)
    assert text.startswith('【只读讨论记录，未作为需求或批准】') and '历史消息' in text and text.endswith('原讨论')


def test_current_revision_wins_in_context_but_raw_user_evidence_and_old_records_remain(client,monkeypatch):
    task,p=configured(client);old={'role':'user','content':'旧版原话','context_revision':task['revision']};task['messages'].append(old);main.store.put('task',task['id'],task)
    task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'goal':'当前保存的业务目标'}}).json();before=copy.deepcopy(task['messages'])
    async def fake(*args,**kwargs):
        ctx=json.loads(args[2][1]['content'].split('当前任务资料：',1)[1]);assert ctx['requirements']['goal']=='当前保存的业务目标' and ctx['revision']==task['revision']
        assert any('历史消息' in m['content'] and m['content'].endswith('旧版原话') for m in args[2])
        return '{"message":"本轮公开回复","requirements_patch":{"goal":"本轮提出的新目标"}}',{'prompt_tokens':10,'completion_tokens':2}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'本轮原话'});assert response.status_code==200
    saved=response.json();assert saved['messages'][:len(before)]==before and saved['revision']>task['revision']
    assert saved['messages'][-1]['context_revision']==task['revision'] and saved['messages'][-1]['result_revision']==saved['revision']
    assert sources(saved)[('message',str(len(saved['messages'])-2))]=='本轮原话'
    assert not saved['requirements_confirmed']


@pytest.mark.parametrize('failure',['provider','shape'])
def test_failed_reply_records_actual_input_and_result_revision_without_retry(client,monkeypatch,failure):
    task,p=configured(client);calls=[]
    async def fake(*a,**kw):
        calls.append(1)
        if failure=='provider':raise ProviderError('隔离供应商错误')
        return 'bad-json',{}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'公开问题'})
    assert response.status_code==200 and calls==[1]
    saved=response.json();assert saved['messages'][-1]['context_revision']==task['revision'] and saved['messages'][-1]['result_revision']==saved['revision']


def test_no_provider_does_not_guess_a_reply_revision_or_dispatch(client):
    task=create(client);response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'公开问题'})
    assert response.status_code==200
    saved=response.json();assert saved['messages'][-2]['context_revision']==task['revision']
    assert saved['messages'][-1]['context_revision']==task['revision']==saved['messages'][-1]['result_revision']


def test_planning_snippets_also_directly_bind_identifiers_and_hashes(client,monkeypatch):
    task=approved(client);p=provider(client);task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json()
    ids=[]
    for text in (b'FIRST',b'SECOND'):
        task,m=upload(client,task,'same.txt',text);ids.append(m['id'])
        task=client.patch(f"/api/tasks/{task['id']}/materials/{m['id']}",json={'revision':task['revision'],'reference_mode':'borrow'}).json()
    async def fake(*args,**kwargs):
        ctx=json.loads(args[2][1]['content']);assert [m['id'] for m in ctx['reference_materials']]==ids
        assert all(len(m['source_sha256'])==64 for m in ctx['reference_materials'])
        return json.dumps(plan()),{'prompt_tokens':10,'completion_tokens':2}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert response.status_code==200,response.text


def test_excerpt_limits_keep_direct_identity_and_mark_unseen_parts(client,monkeypatch):
    task,p=configured(client);materials=[]
    for number in range(3):
        task,m=upload(client,task,'same.txt',(str(number)*13000).encode());materials.append(m)
    async def fake(*args,**kwargs):
        ctx=json.loads(args[2][1]['content'].split('当前任务资料：',1)[1]);rows=ctx['materials']
        assert [r['id'] for r in rows]==[m['id'] for m in materials]
        assert [len(r['text']) for r in rows]==[12000,12000,0] and all(r['excerpt_truncated'] for r in rows)
        assert all(r['full_text_length']==13000 and r['source_sha256']==m['sha256'] for r,m in zip(rows,materials))
        return '{"message":"公开讨论回复"}',{'prompt_tokens':10,'completion_tokens':2}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'讨论范围，不改需求','mode':'discussion'})
    assert response.status_code==200,response.text


def test_paused_reply_keeps_input_revision_and_never_presents_a_candidate_as_applied(client,monkeypatch):
    import asyncio
    task,p=configured(client)
    async def fake(*args,**kwargs):
        assert (await asyncio.to_thread(client.post,f"/api/tasks/{task['id']}/pause")).status_code==200
        return '{"message":"迟到回复","requirements_patch":{"goal":"不应采用"}}',{'prompt_tokens':10,'completion_tokens':2}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'公开问题'})
    assert response.status_code==200
    saved=response.json();assert saved['status']=='paused' and saved['requirements']==task['requirements']
    assert saved['messages'][-1]['context_revision']==task['revision']==saved['messages'][-1]['result_revision']
