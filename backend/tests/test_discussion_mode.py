import copy,json
import pytest
from test_api import client,approved
from test_intake import new,manual
from test_task_budget import provider,policy
from app import main
from app.discussion_mode import parse_reply,progress_context
from app.intake import digest as intake_digest,sources as intake_sources,topics as intake_topics
from app.coverage import context as coverage_context,digest
from app.conflicts import context as conflict_context
from app.configuration_proposals import context_stamp

BUSINESS=('revision','app_type','requirements','configuration','requirements_confirmed','configuration_confirmed','workflow_plan','agent_plan','plan_stale','artifact','dify_app_id','environment_id','versions','confirmations','test_cases','intake_review','intake_history','intake_required','plan_review_required','coverage_review','conflict_review')
def business(t):return {k:copy.deepcopy(t.get(k)) for k in BUSINESS}

def protected(client):
    t=new(client);t=manual(client,t).json()
    response=client.post('/api/tasks/'+t['id']+'/confirm',json={'revision':t['revision'],'kind':'requirements'});assert response.status_code==200,response.text;t=response.json()
    t=client.patch('/api/tasks/'+t['id'],json={'configuration':{'dify_model_provider':'fixture/provider','dify_model':'fixture-model','resource_plan':'隔离测试资源说明，未执行真实资源操作。'}}).json()
    # The discussion fixture explicitly chooses its simple graph under the new task policy.
    from app.plan_review import linear_plan
    _,text=linear_plan(t)
    response=client.post('/api/tasks/'+t['id']+'/plan',json={'revision':t['revision'],'plan_text':text});assert response.status_code==200,response.text;t=response.json()
    response=client.post('/api/tasks/'+t['id']+'/confirm',json={'revision':t['revision'],'kind':'configuration'});assert response.status_code==200,response.text
    t=response.json();response=client.post('/api/tasks/'+t['id']+'/build',json={'revision':t['revision']});assert response.status_code==200,response.text
    return response.json()

@pytest.mark.parametrize('stream',[False,True])
def test_discussion_saves_one_reply_and_usage_without_invalidating_business(client,monkeypatch,stream):
    t=protected(client);provider(client);before=business(t);intake_before=intake_digest(t);sources_before=intake_sources(t);topics_before=intake_topics(t);coverage_before=digest(coverage_context(t));conflict_before=digest(conflict_context(t));config_before=context_stamp(main,t);calls=[]
    async def fake(*args,**kwargs):
        calls.append(args[2]);system=args[2][0]['content'];ctx=json.loads(args[2][1]['content'].split('当前任务资料：',1)[1])
        assert '本轮是用户明确选择的“只读讨论”' in system
        assert '仅有message一个字段' in system and '本次访谈同时执行 Sierra 需求准入检查' not in system
        assert ctx['task_progress']['state']=='offline' and ctx['task_progress']['business_verified'] is False
        assert not {'task_id','snapshot_token','dify_app_id','environment_id'}&set(ctx['task_progress'])
        assert args[2][-1]['content'].startswith('【只读讨论记录，未作为需求或批准】')
        assert bool(kwargs.get('stream')) is stream
        if stream:await kwargs['on_delta']('{"message":"可以先下载待验证DSL。"}')
        return '{"message":"可以先下载待验证DSL，也可以补齐环境后单独确认导入。没有执行或改变方案。"}',{'prompt_tokens':100,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post('/api/tasks/'+t['id']+'/messages',json={'content':'我只是讨论，不采用新规则；批量HTTP定时人工审核为什么会有费用？','mode':'discussion','stream_response':stream})
    assert response.status_code==200,response.text;saved=response.json()
    assert business(saved)==before and saved['status']==t['status'] and len(calls)==1
    assert intake_digest(saved)==intake_before and intake_sources(saved)==sources_before and intake_topics(saved)==topics_before
    assert digest(coverage_context(saved))==coverage_before and digest(conflict_context(saved))==conflict_before and context_stamp(main,saved)==config_before
    assert saved['messages'][-2]['purpose']==saved['messages'][-1]['purpose']=='discussion'
    assert len(main.budgets.get(t['id'])['entries'])==1
    record=client.get('/api/tasks/'+t['id']+'/interviews').json()['operations'][0]
    assert record['mode']=='discussion' and record['status']=='applied' and '需求、配置、流程、确认和成果未修改' in record['note']

@pytest.mark.parametrize('reply',[ '{"message":"private", "requirements_patch":{"goal":"not applied"}}','{"message":"private","intake_review":{}}','{"message":"private","configuration":{}}','{"message":"first","message":"private"}','{"message":"private","x":NaN}','```json\n{"message":"private"}\n```','{"message":""}','{"message":42}','["private"]'])
def test_forbidden_or_malformed_model_reply_is_not_partly_adopted(client,monkeypatch,reply):
    t=approved(client);provider(client);before=business(t);before_digest=intake_digest(t)
    async def fake(*args,**kwargs):return reply,{'prompt_tokens':5,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post('/api/tasks/'+t['id']+'/messages',json={'content':'只讨论，不修改','mode':'discussion'});assert response.status_code==200,response.text
    saved=response.json();assert business(saved)==before and intake_digest(saved)==before_digest
    assert saved['status']==t['status'] and saved['messages'][-1]['source']=='system'
    assert saved['interview_attempts'][-1]['applied'] is False and len(main.budgets.get(t['id'])['entries'])==1

def test_no_provider_discussion_preserves_approval_and_intake(client):
    t=protected(client);before=business(t);token=intake_digest(t)
    response=client.post('/api/tasks/'+t['id']+'/messages',json={'content':'解释下一步','mode':'discussion'});assert response.status_code==200,response.text
    saved=response.json();assert business(saved)==before and intake_digest(saved)==token
    assert '尚未配置' in saved['messages'][-1]['content'] and main.budgets.get(t['id'])['entries']==[]

def test_discussion_cannot_be_cited_as_requirement_evidence_or_activate_topics(client):
    t=new(client);before=intake_sources(t);standard=intake_topics(t);token=intake_digest(t)
    t['messages'].append({'role':'user','purpose':'discussion','content':'仅讨论循环、批量、定时、JSON对象、会话状态，不采用。'})
    assert intake_sources(t)==before and intake_topics(t)==standard and intake_digest(t)==token
    t['messages'][-1].pop('purpose')
    assert intake_digest(t)!=token and len(intake_topics(t))>len(standard)

@pytest.mark.parametrize('body',[{'mode':'private'}, {'mode':True}, {'mode':'discussion','unknown':'private'},{'mode':'discussion','stream_response':1},{'mode':'discussion','content':{ 'private':'payload'}},{'mode':'discussion','content':'   '},{'mode':'discussion','content':'\ud800'}])
def test_invalid_mode_or_body_rejected_before_recording_without_echo(client,body):
    t=new(client);before=client.get('/api/tasks/'+t['id']).json()
    response=client.post('/api/tasks/'+t['id']+'/messages',content=json.dumps({'content':'private-content',**body}),headers={'Content-Type':'application/json'})
    assert response.status_code==422,response.text
    assert 'private' not in response.text and client.get('/api/tasks/'+t['id']).json()==before

def test_read_only_progress_context_is_minimal_and_does_not_leak_ids(client):
    t=approved(client);t.update(environment_id='private-env',dify_app_id='private-app')
    ctx=progress_context(t)
    assert 'private' not in json.dumps(ctx) and not {'task_id','revision','snapshot_token'}&set(ctx)

def test_legacy_review_mode_still_applies_explicit_requirement_updates(client,monkeypatch):
    t=approved(client);provider(client)
    async def fake(*args,**kwargs):
        assert '本轮是用户明确选择的“只读讨论”' not in args[2][0]['content']
        return json.dumps({'message':'新目标需重新确认','requirements_patch':{'goal':'明确的新业务目标'}}),{'prompt_tokens':5,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post('/api/tasks/'+t['id']+'/messages',json={'content':'修改我的业务目标'});assert response.status_code==200,response.text
    saved=response.json();assert saved['revision']==t['revision']+1 and saved['requirements']['goal']=='明确的新业务目标' and saved['requirements_confirmed'] is False


def test_paused_discussion_does_not_apply_late_reply_or_business_changes(client,monkeypatch):
    t=protected(client);provider(client);before=business(t);token=intake_digest(t)
    async def fake(*args,**kwargs):
        current=main.get_task(t['id']);current['status']='paused';main.save_task(current)
        return '{"message":"late reply not adopted"}',{'prompt_tokens':5,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post('/api/tasks/'+t['id']+'/messages',json={'content':'只讨论并暂停','mode':'discussion'});assert response.status_code==200,response.text
    saved=response.json();assert saved['status']=='paused' and business(saved)==before and intake_digest(saved)==token
    assert saved['messages'][-1].get('purpose')!='discussion'
    assert saved['interview_attempts'][-1]['applied'] is False


def test_zero_budget_blocks_discussion_without_model_dispatch_or_business_edit(client,monkeypatch):
    t=protected(client);provider(client);policy(client,t,'0');before=business(t);calls=[]
    async def forbidden(*args,**kwargs):calls.append(1);raise AssertionError('Zero budget must stop before model dispatch')
    monkeypatch.setattr(main,'call_model',forbidden)
    response=client.post('/api/tasks/'+t['id']+'/messages',json={'content':'费用上限为0，不可派发','mode':'discussion'});assert response.status_code==200,response.text
    saved=response.json();assert business(saved)==before and calls==[] and saved['status']=='paused'


def test_revision_change_never_restores_old_approvals_or_applies_discussion(client,monkeypatch):
    t=protected(client);provider(client);expected=[]
    async def fake(*args,**kwargs):
        current=main.get_task(t['id']);main.invalidate(current,'开发隔离新修订');current['requirements']['goal']='用户已修改的新目标';main.save_task(current);expected.append(business(current))
        return '{"message":"stale reply"}',{'prompt_tokens':5,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post('/api/tasks/'+t['id']+'/messages',json={'content':'讨论中修订变化','mode':'discussion'});assert response.status_code==409,response.text
    assert business(client.get('/api/tasks/'+t['id']).json())==expected[0]
