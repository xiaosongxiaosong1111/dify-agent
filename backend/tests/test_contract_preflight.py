import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from test_api import client, approved, planning_provider
from app import main
from app.contract_loading import load_contract, NAMES


@pytest.mark.parametrize('operation,name', [('plan/generate','workflow-plan-contract.md'),('messages','intake-model-contract.md')])
@pytest.mark.parametrize('fault',['missing','empty','bad_utf8','directory'])
def test_missing_model_rules_never_leave_task_busy_or_reserve_a_call(client,monkeypatch,tmp_path,operation,name,fault):
    planning_provider(client)
    task=approved(client)
    before=main.get_task(task['id'])
    root=tmp_path/'broken-install';docs=root/'docs';docs.mkdir(parents=True)
    path=docs/name
    if fault=='empty':path.write_text(' \n\t',encoding='utf-8')
    elif fault=='bad_utf8':path.write_bytes(b'\xff\xfe\x80')
    elif fault=='directory':path.mkdir()
    monkeypatch.setattr(main,'PROJECT_ROOT',root)
    async def forbidden(*args,**kwargs):raise AssertionError('preflight must not call model')
    monkeypatch.setattr(main,'call_model',forbidden)
    payload={'revision':task['revision']} if operation=='plan/generate' else {'content':'开发样例，请继续讨论需求'}
    response=client.post(f"/api/tasks/{task['id']}/{operation}",json=payload)
    assert response.status_code==422,response.text
    assert '规则未就绪' in response.json()['detail']
    assert str(root) not in response.text
    assert main.get_task(task['id'])==before
    assert not client.get(f"/api/tasks/{task['id']}/budget").json()['pending_count']


def test_missing_install_rules_do_not_disable_the_no_provider_local_discussion(client,monkeypatch,tmp_path):
    task=approved(client)
    monkeypatch.setattr(main,'PROJECT_ROOT',tmp_path/'no-rules')
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'先保存我的业务需求'})
    assert response.status_code==200,response.text
    saved=response.json()
    assert saved['messages'][-2]['content']=='先保存我的业务需求'
    assert '当前没有调用 AI' in saved['messages'][-1]['content']
    assert saved['status']==task['status'] and not saved.get('active_interview_id')


def test_interview_sent_rules_match_current_container_capabilities(client,monkeypatch):
    planning_provider(client)
    task=approved(client)
    calls=[]
    async def controlled(provider,key,messages,**kwargs):
        calls.append(messages)
        prompt=messages[0]['content']
        assert '循环内部条件和人工审核仍待适配' not in prompt
        assert '并行项／嵌套保留仍未适配' not in prompt
        marker='当前所选应用的Sierra能力目录（仅compiler_scope，不是资源就绪、运行或业务验收）：\n'
        scope=json.JSONDecoder().raw_decode(prompt.split(marker,1)[1])[0]
        assert scope['app_type']=='workflow' and scope['verification']=='compiler_scope'
        loop=next(row for row in scope['containers'] if row['type']=='loop')
        assert {'if-else','question-classifier','parameter-extractor','variable-aggregator'}<={n['type'] for n in loop['dag_nodes']}
        assert {'code','template-transform','llm','http-request'}<={n['type'] for n in loop['sequence_nodes']}
        assert all(word in loop['note'] for word in ('停止','次数耗尽失败','连续无进展保护'))
        assert any('GET／HEAD' in note and '重复读取' in note for note in scope['notes'])
        context=json.loads(messages[1]['content'].split('当前任务资料：',1)[1])
        question=next(row['question'] for row in context['intake_standard'] if row['id']=='loop_policy')
        assert all(word in question for word in ('初始状态','每轮更新','最大轮次','进度字段','连续无进展'))
        return json.dumps({'message':'当前是开发样例，请确认具体进度字段。','requirements_patch':{}}),{'prompt_tokens':80,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'请讨论受保护循环内部的条件和只读请求'})
    assert response.status_code==200,response.text
    saved=response.json()
    assert len(calls)==1 and not saved.get('active_interview_id')
    assert saved['requirements']==task['requirements']
    assert not saved['artifact'] and not saved['runs']


def test_installed_rule_loader_has_fixed_names_and_keeps_entire_valid_rule(tmp_path):
    docs=tmp_path/'docs';docs.mkdir()
    text=' 当前完整规则\n尾部约束不能被截断。\n'
    for name in NAMES:
        (docs/name).write_text(text,encoding='utf-8')
        assert load_contract(tmp_path,name)==text
    with pytest.raises(HTTPException,match='未适配'):
        load_contract(tmp_path,'../data/.credential-key')
