import json
import httpx
import pytest
import yaml
from test_api import client,create_env,approved,forbid_api_external_calls
from app import main
from app.dsl import compile_dsl
from app.workflow_plan import compile_workflow_plan


def plan():return {'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[]}},{'id':'llm','type':'llm','config':{'system_prompt':'只使用当前对话的信息，不编造编号。','user_prompt':'{{#sys.query#}}'}},{'id':'answer','type':'answer','config':{'answer':'{{#llm.text#}}'}}],'edges':[{'source':'start','target':'llm'},{'source':'llm','target':'answer'}]}


@pytest.mark.parametrize('enabled',[True,False])
def test_memory_is_explicit_bounded_and_preserved_by_both_compilers(client,enabled):
    task=approved(client,app_type='advanced-chat');task['configuration'].update(conversation_memory=enabled,memory_turns=3)
    for compiler in (compile_dsl,compile_workflow_plan):
        if compiler is compile_workflow_plan:task['workflow_plan']=plan()
        content,validation=compiler(task);assert validation['valid']
        node=next(n['data'] for n in yaml.safe_load(content)['workflow']['graph']['nodes'] if n['data']['type']=='llm')
        if enabled:assert node['memory']['window']=={'enabled':True,'size':4}
        else:assert 'memory' not in node


def test_workflow_rejects_conversation_memory_instead_of_ignoring_it(client):
    task=approved(client)
    assert client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'conversation_memory':True}}).status_code==422
    for value in (0,51,True,1.5):
        assert client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'memory_turns':value}}).status_code==422


def prepared(client):
    env=create_env(client);task=approved(client,app_type='advanced-chat',env_id=env['id'])
    built=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert built.status_code==200
    task=main.get_task(task['id']);task['dify_app_id']='memory-app';main.save_task(task)
    client.patch('/api/environments/'+env['id'],json={'service_app_id':'memory-app','service_api_key':'unit-key'})
    return task,env


def test_free_conversation_uses_current_successful_source_and_records_actual_context(client,monkeypatch):
    task,env=prepared(client);seen=[]
    async def chat(self,query,inputs=None,conversation_id=None):
        seen.append((query,inputs,conversation_id));return {'answer':'回答','conversation_id':conversation_id or 'conversation-one'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    first=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'第一轮'}});assert first.status_code==200,first.text
    source=first.json()['runs'][-1]['id']
    second=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'追问'},'conversation_from_run_id':source})
    assert second.status_code==200,second.text
    assert seen[1]==('追问',{},'conversation-one')
    run=second.json()['runs'][-1]
    assert run['input']=={'query':'追问','conversation_id':'conversation-one'} and run['conversation_context']['source_run_id']==source
    assert not run.get('test_case') and not run.get('evaluation')
    assert client.get(f"/api/tasks/{task['id']}/acceptance").json()['required']['passed']==0


@pytest.mark.parametrize('mismatch',['revision','environment','failed','foreign_task','app','missing_app'])
def test_unrelated_or_stale_conversation_never_dispatched(client,monkeypatch,mismatch):
    task,env=prepared(client)
    record={'id':'source','kind':'run','status':'success','revision':task['revision'],'environment_id':env['id'],
            'app_id':task['dify_app_id'],'result':{'answer':'回答','conversation_id':'cid'}}
    if mismatch=='revision':record['revision']-=1
    if mismatch=='environment':record['environment_id']='elsewhere'
    if mismatch=='failed':record['status']='failed'
    if mismatch=='app':record['app_id']='different-fixture-app'
    if mismatch=='missing_app':record.pop('app_id')
    if mismatch!='foreign_task':task['runs'].append(record)
    main.save_task(task)
    calls=[]
    async def chat(*args,**kwargs):
        calls.append(1)
        return {'answer':'公开回执','conversation_id':'cid'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',chat)
    result=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'追问'},'conversation_from_run_id':'source'})
    assert result.status_code==422 and not calls
    assert main.get_task(task['id']) == task


def test_saved_conversation_changed_before_admission_never_dispatches_followup(client, monkeypatch):
    task, _ = prepared(client)
    path = f"/api/tasks/{task['id']}/run"
    calls = []

    async def chat(self, query, inputs, conversation_id):
        calls.append(conversation_id)
        return {'answer': '公开回执', 'conversation_id': 'original-cid'}

    monkeypatch.setattr(main.DifyClient, 'run_chatflow', chat)
    payload = {'revision': task['revision'], 'input': {'query': '公开请求'}}
    first = client.post(path, json=payload)
    assert first.status_code == 200, first.text
    source_id = first.json()['runs'][-1]['id']
    external_action = main.external_action

    async def change_source(*args, **kwargs):
        current = main.get_task(task['id'])
        current['runs'][-1]['result']['conversation_id'] = 'changed-cid'
        main.save_task(current)
        return await external_action(*args, **kwargs)

    monkeypatch.setattr(main, 'external_action', change_source)
    response = client.post(path, json={**payload, 'conversation_from_run_id': source_id})
    assert response.status_code == 422 and calls == [None]
    assert len(main.get_task(task['id'])['runs']) == 1


def test_conversation_source_cannot_mix_with_fixed_case_or_other_id(client):
    task,env=prepared(client)
    task['test_cases']=[{'id':'case','name':'隔离样例','input':{'query':'q'},
                        'expectation':{'mode':'equals','target':'answer','expected':'公开回执'}}]
    main.save_task(task)
    for payload in ({'case_id':'case'},{'input':{'query':'q','conversation_id':'other'}}):
        result=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'conversation_from_run_id':'source',**payload})
        assert result.status_code==422


@pytest.mark.parametrize('entry', ['save', 'run', 'acceptance', 'legacy_empty_followups'])
def test_single_turn_chatflow_case_cannot_reuse_existing_conversation(client, monkeypatch, entry):
    task, _ = prepared(client)
    path = f"/api/tasks/{task['id']}"
    case = {
        'id': 'isolated-case', 'name': '单轮公开样例',
        'input': {'query': '公开问题', 'conversation_id': 'previous-synthetic-conversation'},
        'expectation': {'mode': 'manual', 'description': '核对公开回答'},
    }
    payload = {'revision': task['revision']}
    calls = []

    async def local_chat(self, query, inputs, conversation_id):
        calls.append(conversation_id)
        return {'answer': '公开回答', 'conversation_id': conversation_id or 'fresh-conversation'}

    monkeypatch.setattr(main.DifyClient, 'run_chatflow', local_chat)
    if entry == 'save':
        before = main.get_task(task['id'])
        response = client.post(f'{path}/test-cases', json={**payload, 'cases': [case]})
        assert response.status_code == 422 and '会话' in response.json()['detail']
    else:
        task['test_cases'] = [case]
        if entry == 'legacy_empty_followups':
            case['followups'] = []
        if entry in {'acceptance', 'legacy_empty_followups'}:
            task['runs'] = [{
                'id': 'recorded-run', 'kind': 'run', 'status': 'success', 'revision': task['revision'],
                'environment_id': task['environment_id'], 'app_id': task['dify_app_id'],
                'input': case['input'], 'test_case': case, 'evaluation': {'mode': 'manual', 'status': 'needs_review'},
                'manual_review': {'source': 'user', 'decision': 'passed', 'reason': '历史复核'},
                'result': {'answer': '公开回答', 'conversation_id': 'previous-synthetic-conversation'},
            }]
        main.save_task(task)
        before = main.get_task(task['id'])
        if entry == 'run':
            assert client.post(f'{path}/run', json={**payload, 'case_id': case['id']}).status_code == 422
        else:
            summary = client.get(f'{path}/acceptance').json()
            assert summary['required']['needs_review'] == 1 and not summary['all_required_passed']
            assert summary['cases'][0]['run_id'] == 'recorded-run'
            assert '会话' in summary['cases'][0]['details']
            report = client.get(f'{path}/report')
            assert report.status_code == 200 and '## 当前 Chatflow 样例实际回复' not in report.text
            review = client.post(f'{path}/runs/recorded-run/review',
                                 json={**payload, 'decision': 'passed', 'reason': '重新审核'})
            assert review.status_code == 422 and '会话' in review.json()['detail']
    assert not calls and main.get_task(task['id']) == before


def test_missing_conversation_result_is_unknown_not_success(client,monkeypatch):
    task,env=prepared(client)
    async def malformed(*args,**kwargs):return {'answer':'部分输出'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',malformed)
    result=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'q'}})
    assert result.status_code==502
    current=main.get_task(task['id']);assert current['runs'][-1]['status']=='unknown' and current['runs'][-1]['result']=={'answer':'部分输出'}
    assert client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'q'}}).status_code==409


def test_rebinding_runtime_key_before_locked_admission_never_dispatches(client, monkeypatch):
    task, env = prepared(client)
    path = f"/api/tasks/{task['id']}/run"
    payload = {'revision': task['revision'], 'input': {'query': '查订单'}}
    external_action = main.external_action
    dispatched = []

    async def rebind_before_admission(*args, **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as api:
            response = await api.patch(f"/api/environments/{env['id']}", json={
                'service_app_id': 'different-fixture-app', 'service_api_key': 'different-fixture-key',
            })
        assert response.status_code == 200, response.text
        return await external_action(*args, **kwargs)

    async def chat(self, query, inputs, conversation_id):
        dispatched.append(self.env['service_app_id'])
        return {'answer': '隔离试跑', 'conversation_id': 'fixture-conversation'}

    monkeypatch.setattr(main, 'external_action', rebind_before_admission)
    monkeypatch.setattr(main.DifyClient, 'run_chatflow', chat)
    response = client.post(path, json=payload)
    assert response.status_code == 422 and not dispatched
    assert main.get_task(task['id']) == task

    monkeypatch.setattr(main, 'external_action', external_action)
    assert client.patch(f"/api/environments/{env['id']}", json={
        'service_app_id': task['dify_app_id'], 'service_api_key': 'unit-key',
    }).status_code == 200
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    assert dispatched == [task['dify_app_id']]
    assert response.json()['runs'][-1]['app_id'] == task['dify_app_id']
