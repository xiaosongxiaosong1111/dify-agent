import copy,json
import pytest
from test_api import client
from test_intake import new,state,manual,review
from test_task_budget import provider
from test_schedule_trigger import plan
from app.intake import topics,SCHEDULE_TOPICS,validate_review
from app import main


@pytest.mark.parametrize('app_type',['workflow','advanced-chat','agent'])
@pytest.mark.parametrize('text',['每天8点自动发送日报','定时执行客户答复汇总'])
def test_explicit_schedule_raises_separate_policy_topics_preserves_type_no_calls(client,app_type,text):
    task=new(client,app_type);task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':text}}).json()
    rows={r['id']:r for r in topics(task)}
    assert set(SCHEDULE_TOPICS)<=set(rows)
    assert '时区' in rows['schedule_time']['question'] and '短月' in rows['schedule_time']['question']
    assert '幂等' in rows['schedule_delivery']['question'] and '费用' in rows['schedule_operations']['question']
    assert not state(client,task)['can_confirm'] and main.get_task(task['id'])['app_type']==app_type
    assert not main.budgets.get(task['id'])['entries']


def test_ordinary_text_or_webhook_does_not_acquire_schedule_policy(client):
    task=new(client);assert not set(SCHEDULE_TOPICS)&{r['id'] for r in topics(task)}
    task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':'由webhook触发，返回大写文本'}}).json()
    assert 'trigger' in {r['id'] for r in topics(task)} and not set(SCHEDULE_TOPICS)&{r['id'] for r in topics(task)}


def test_draft_schedule_requires_fresh_standard_not_self_approval(client):
    task=new(client);task=manual(client,task).json();assert state(client,task)['can_confirm']
    saved=main.get_task(task['id']);saved['workflow_plan']=plan();main.store.put('task',saved['id'],saved)
    before=copy.deepcopy(saved);value=state(client,saved)
    assert set(SCHEDULE_TOPICS)<={r['id'] for r in value['standard']} and not value['can_confirm'] and value['stale']
    assert main.get_task(task['id'])==before
    incomplete=review(saved);incomplete['checks']=[r for r in incomplete['checks'] if r['topic']!='schedule_operations']
    with pytest.raises(ValueError,match='逐项覆盖'):validate_review(saved,incomplete)


def test_manual_schedule_answers_persist_no_automatic_confirmation_or_platform_calls(client,monkeypatch):
    task=new(client);task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':'定时按UTC每小时第10分钟生成固定文本'}}).json()
    current=state(client,task);answers={r['id']:task['requirements'].get(r['id'],'本项明确不适用：固定文本技术样例没有此依赖。') for r in current['standard']}
    answers.update(schedule_time='UTC每小时第10分钟，不补跑，无月末或夏令时。',schedule_delivery='无外部输入，结果留在运行记录；重复可接受，不要求去重；上次未结束不做跨运行互斥。',schedule_operations='由开发者人工停用，只运行技术验收窗口；无模型费用，不自动重试；失败人工看日志，累计宿主成本人工监控。')
    async def forbidden(*a,**kw):pytest.fail('人工复核不调用平台或模型')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
    response=manual(client,task,answers=answers);assert response.status_code==200,response.text
    updated=response.json();value=state(client,updated)
    assert value['can_confirm'] and not updated['requirements_confirmed'] and not updated['configuration_confirmed']
    assert value['record']['answers']['schedule_operations']==answers['schedule_operations']
    assert not main.budgets.get(task['id'])['entries']


def test_model_interview_schedule_gap_retains_impact_explanation_and_blocks_confirmation(client,monkeypatch):
    task=new(client);task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':'定时执行报表'}}).json();provider(client)
    async def model(*a,**kw):
        request=json.loads(a[2][1]['content'].split('当前任务资料：',1)[-1])
        assert set(SCHEDULE_TOPICS)<={r['id'] for r in request['intake_standard']}
        return json.dumps({'message':'先明确持续费用和停止责任','requirements_patch':{},'intake_review':review(main.get_task(task['id']),gap='schedule_operations')}),{'prompt_tokens':30,'completion_tokens':60}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'帮我检查定时规则'});assert response.status_code==200,response.text
    updated=response.json();value=state(client,updated)
    assert value['reviewed'] and not value['can_confirm'] and not updated['requirements_confirmed']
    assert value['questions'][0]['topic']=='schedule_operations' and all(value['questions'][0][k] for k in ('recommendation','reason','experience','cost','manual_work'))


def test_old_confirmed_task_cannot_bypass_new_schedule_intake_when_enabling(client,monkeypatch):
    from test_schedule_enable import prepared,execute
    task,env,root,p=prepared(client,monkeypatch)
    current=main.get_task(task['id']);current['intake_required']=True;main.store.put('task',current['id'],current)
    async def forbidden(*a,**kw):pytest.fail('未复核专项政策不能读取或启用')
    monkeypatch.setattr(main.DifyClient,'request',forbidden)
    response=execute(client,task,p);assert response.status_code==422 and '需求准入未通过' in response.text
