import asyncio
import copy
import pytest
import httpx
from test_api import client
from app import main
from app.dify import DifyClient, DifyError
from app.evaluation import validate_test_cases
from app.conversation_cases import execute_conversation, evaluate_conversation
from test_agent_plan import runtime_task
from test_conversation import prepared as chat_task
from app.storage import Store


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('AT-15 隔离检查不得访问真实 HTTP 或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def case():
    return {'id':'memory','name':'正式两轮编号回忆','required':True,'input':{'query':'记住 M-4827'},'expectation':{'mode':'equals','target':'answer','expected':'收到'},
            'followups':[{'input':{'query':'上一轮编号？'},'expectation':{'mode':'equals','target':'answer','expected':'M-4827'}}]}


def prepared(client,mode):
    task=runtime_task(client) if mode=='agent' else chat_task(client)[0]
    task['test_cases']=[case()];main.save_task(task)
    return task


def request(client,task):return client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'case_id':'memory'})


@pytest.mark.parametrize('mode',['agent','advanced-chat'])
def test_chain_starts_fresh_reuses_actual_id_persists_checkpoints_and_counts_one_case(client,monkeypatch,mode):
    task=prepared(client,mode);calls=[]
    async def invoke(self,query,inputs=None,conversation_id=None,**kwargs):
        current=main.get_task(task['id'])['runs'][-1]
        assert current['status']=='pending' and current['result']['pending_turn']['index']==len(calls)+1
        assert len(current['result']['turns'])==len(calls)
        calls.append((query,inputs,conversation_id))
        return {'answer':'收到' if len(calls)==1 else 'M-4827','conversation_id':conversation_id or 'conversation-one','terminal':True,'metadata':{'usage':{'total_tokens':10}}}
    monkeypatch.setattr(DifyClient,'run_agent' if mode=='agent' else 'run_chatflow',invoke)
    response=request(client,task);assert response.status_code==200,response.text
    run=response.json()['runs'][-1]
    assert calls[0][2] is None and calls[1][2]=='conversation-one'
    assert run['evaluation']['status']=='passed' and len(run['result']['turns'])==2 and run['result']['complete']
    assert run['input']==case()['input'] and run['test_case']==case()
    summary=client.get(f"/api/tasks/{task['id']}/acceptance").json()
    assert summary['required']['total']==1 and summary['required']['passed']==1 and summary['all_required_passed']
    # Fixed conversation case is never a source for free runs.
    invalid=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'再追问'},'conversation_from_run_id':run['id']})
    assert invalid.status_code==422 and len(calls)==2


def test_automatic_failure_stops_remaining_turns_and_human_cannot_override(client,monkeypatch):
    task=prepared(client,'agent');calls=[]
    async def invoke(*args,**kwargs):
        calls.append(1);return {'answer':'错误回答','conversation_id':'c','terminal':True}
    monkeypatch.setattr(DifyClient,'run_agent',invoke)
    response=request(client,task);assert response.status_code==200
    run=response.json()['runs'][-1];assert len(calls)==1 and not run['result']['complete'] and run['evaluation']['status']=='failed'
    assert client.get(f"/api/tasks/{task['id']}/acceptance").json()['required']['failed']==1
    review=client.post(f"/api/tasks/{task['id']}/runs/{run['id']}/review",json={'revision':task['revision'],'decision':'passed','reason':'不能覆盖失败'})
    assert review.status_code==422


@pytest.mark.parametrize('mode',['agent','advanced-chat'])
def test_middle_interruption_keeps_finished_and_partial_turn_unknown_blocks_retry(client,monkeypatch,mode):
    task=prepared(client,mode);count=0
    async def invoke(*args,**kwargs):
        nonlocal count;count+=1
        if count==2:raise DifyError('连接中断，结果可能未知。',result={'answer':'部分','conversation_id':'c'})
        return {'answer':'收到','conversation_id':'c','terminal':True}
    monkeypatch.setattr(DifyClient,'run_agent' if mode=='agent' else 'run_chatflow',invoke)
    assert request(client,task).status_code==502
    run=main.get_task(task['id'])['runs'][-1]
    assert run['status']=='unknown' and len(run['result']['turns'])==1 and run['result']['pending_turn']['result']['answer']=='部分'
    assert request(client,task).status_code==409 and count==2


def test_pause_between_turns_keeps_known_first_result_without_dispatching_next(client,monkeypatch):
    task=prepared(client,'agent');calls=[]
    async def invoke(*args,**kwargs):
        calls.append(1);current=main.get_task(task['id']);current['status']='paused';main.save_task(current)
        return {'answer':'收到','conversation_id':'c','terminal':True}
    monkeypatch.setattr(DifyClient,'run_agent',invoke)
    assert request(client,task).status_code==502
    current=main.get_task(task['id']);run=current['runs'][-1]
    assert current['status']=='paused' and len(calls)==1 and len(run['result']['turns'])==1 and run['result']['stop_reason']=='paused'
    assert not run['result'].get('pending_turn') and run['status']=='failed'


def test_changed_conversation_is_unknown_not_passed(client,monkeypatch):
    task=prepared(client,'advanced-chat');calls=[]
    async def invoke(*args,**kwargs):
        calls.append(1);return {'answer':'收到' if len(calls)==1 else 'M-4827','conversation_id':'c' if len(calls)==1 else 'wrong'}
    monkeypatch.setattr(DifyClient,'run_chatflow',invoke)
    assert request(client,task).status_code==502
    assert main.get_task(task['id'])['runs'][-1]['status']=='unknown'


def test_mixed_manual_turn_requires_explicit_overall_review_after_automatic_rules(client,monkeypatch):
    task=prepared(client,'agent');task['test_cases'][0]['followups'][0]['expectation']={'mode':'manual','description':'核对回忆来源，只使用第一轮提供的编号。'};main.save_task(task)
    calls=[]
    async def invoke(*args,**kwargs):
        calls.append(1);return {'answer':'收到' if len(calls)==1 else 'M-4827','conversation_id':'c','terminal':True}
    monkeypatch.setattr(DifyClient,'run_agent',invoke)
    response=request(client,task);assert response.status_code==200
    run=response.json()['runs'][-1];assert run['evaluation']['mode']=='manual'
    assert client.get(f"/api/tasks/{task['id']}/acceptance").json()['required']['needs_review']==1
    review=client.post(f"/api/tasks/{task['id']}/runs/{run['id']}/review",json={'revision':task['revision'],'decision':'passed','reason':'两轮已核对，编号来自首轮；自动规则通过。'})
    assert review.status_code==200,review.text
    summary=client.get(f"/api/tasks/{task['id']}/acceptance").json();assert summary['required']['passed']==1 and summary['cases'][0]['method']=='human'


@pytest.mark.parametrize('mutation',['first','followup','expectation','missing','identity'])
def test_changed_snapshots_or_incomplete_trace_cannot_count_as_passed(client,monkeypatch,mutation):
    task=prepared(client,'agent');calls=[]
    async def invoke(*args,**kwargs):
        calls.append(1);return {'answer':'收到' if len(calls)==1 else 'M-4827','conversation_id':'c','terminal':True}
    monkeypatch.setattr(DifyClient,'run_agent',invoke);assert request(client,task).status_code==200
    current=main.get_task(task['id']);run=current['runs'][-1]
    if mutation=='first':run['input']['query']='变了'
    if mutation=='followup':run['test_case']['followups'][0]['input']['query']='变了'
    if mutation=='expectation':run['result']['turns'][1]['expectation']['expected']='变了'
    if mutation=='missing':run['result']['turns'].pop()
    if mutation=='identity':run['result']['turns'][1]['result']['conversation_id']='wrong'
    main.save_task(current)
    summary=client.get(f"/api/tasks/{task['id']}/acceptance").json();assert summary['required']['passed']==0 and not summary['all_required_passed']


@pytest.mark.parametrize('mutation',['empty','too_many','bad_shape','no_query','literal_id','wrong_expectation','workflow','agent_files'])
def test_invalid_chain_is_rejected(mutation):
    c=case();mode='agent'
    if mutation=='empty':c['followups']=[]
    if mutation=='too_many':c['followups']*=10
    if mutation=='bad_shape':c['followups'][0]['tools']=[]
    if mutation=='no_query':c['input']={'query':''}
    if mutation=='literal_id':c['followups'][0]['input']['conversation_id']='literal'
    if mutation=='wrong_expectation':c['followups'][0]['expectation']={'mode':'manual'}
    if mutation=='workflow':mode='workflow'
    if mutation=='agent_files':c['followups'][0]['input']['files']=[]
    assert not validate_test_cases([c],mode)['valid']


def test_saving_chain_advances_revision_invalidates_confirmations_and_preserves_turns(client):
    task=runtime_task(client)
    response=client.post(f"/api/tasks/{task['id']}/test-cases",json={'revision':task['revision'],'cases':[case()]})
    assert response.status_code==200,response.text
    new=response.json();assert new['revision']>task['revision'] and not new['requirements_confirmed'] and not new['configuration_confirmed'] and new['plan_stale']
    assert new['test_cases'][0]['followups']==case()['followups']
    assert request(client,task).status_code in {409,422}
    assert not main.get_task(task['id'])['runs']


def test_chain_timeout_preserves_unknown_checkpoint_without_retry():
    async def invoke(*args):await asyncio.sleep(.05)
    snapshots=[]
    with pytest.raises(DifyError,match='结果可能未知') as error:
        asyncio.run(execute_conversation(case(),invoke,snapshots.append,lambda:False,seconds=.001))
    assert len(snapshots)==1 and error.value.result['pending_turn']['index']==1 and not error.value.result['turns']


@pytest.mark.parametrize('kind,status',[('run','running'),('import','importing'),('run','paused')])
def test_restart_preserves_checkpoint_marks_pending_unknown_and_never_reissues(client,kind,status):
    task=runtime_task(client);checkpoint={'conversation_case':True,'turns':[],'pending_turn':{'index':1}}
    task['status']=status;task['runs']=[{'id':'pending','kind':kind,'revision':task['revision'],'status':'pending','result':copy.deepcopy(checkpoint)}];main.save_task(task)
    main.recover_external_actions();current=main.get_task(task['id'])
    assert current['runs'][0]['status']=='unknown' and current['runs'][0]['result']==checkpoint
    assert current['status']==('paused' if status=='paused' else 'error')
    assert '不自动重复派发' in current['runs'][0]['error']
    snapshot=copy.deepcopy(current);main.recover_external_actions();assert main.get_task(task['id'])==snapshot


def test_chain_time_limit_cancels_native_stream_attempts_remote_stop_and_keeps_partial(tmp_path,monkeypatch):
    from app.storage import Store
    from app import agent_stream
    import json
    store=Store(tmp_path);store.set_secret('env','service_api_key','unit-key')
    adapter=DifyClient({'id':'env','base_url':'http://127.0.0.1:8080'},store);paths=[];original=httpx.AsyncClient
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ('data: '+json.dumps({'event':'agent_message','answer':'部分','conversation_id':'c','task_id':'t'})+'\n\n').encode()
            await asyncio.sleep(1)
    def handler(req):
        paths.append(req.url.path)
        if req.url.path.endswith('/stop'):return httpx.Response(200,json={'result':'success'})
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=SlowStream())
    monkeypatch.setattr(agent_stream.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    async def send(values,cid,remaining):return await adapter.run_agent(values['query'],conversation_id=cid,seconds=remaining+1)
    with pytest.raises(DifyError,match='结果可能未知') as error:
        asyncio.run(execute_conversation(case(),send,lambda result:None,lambda:False,seconds=.02))
    assert paths==['/v1/chat-messages','/v1/chat-messages/t/stop']
    assert error.value.result['pending_turn']['result']['answer']=='部分' and error.value.result['pending_turn']['result']['stop_acknowledged']


def clarification_case():
    # Fixed answers exercise declared rules, not real model clarification quality.
    return {
        'id': 'memory', 'name': '缺失工单信息逐步追问', 'required': True,
        'input': {'query': '查询工单进度'},
        'expectation': {'mode': 'equals', 'target': 'answer', 'expected': '请提供工单编号。'},
        'followups': [
            {'input': {'query': 'S-4827'}, 'expectation': {
                'mode': 'equals', 'target': 'answer', 'expected': '请提供手机号尾号。'}},
            {'input': {'query': '7316'}, 'expectation': {
                'mode': 'equals', 'target': 'answer', 'expected': '已收集工单 S-4827 和尾号 7316，等待查询。'}},
        ],
    }


def clarification_task(client, mode):
    task = prepared(client, mode)
    task['test_cases'] = [clarification_case()]
    main.save_task(task)
    return task


@pytest.mark.parametrize('mode', ['agent', 'advanced-chat'])
def test_at15_clarification_preserves_context_and_rerun_starts_fresh(client, monkeypatch, tmp_path, mode):
    task = clarification_task(client, mode)
    declared = clarification_case()
    turns = [{'input': declared['input'], 'expectation': declared['expectation']}, *declared['followups']]
    calls = []

    async def invoke(self, query, inputs=None, conversation_id=None, **kwargs):
        attempt, index = divmod(len(calls), 3)
        cid = f'isolated-clarification-{attempt}'
        assert query == turns[index]['input']['query']
        assert inputs in (None, {})
        assert conversation_id == (cid if index else None)
        current = main.get_task(task['id'])['runs'][-1]['result']
        assert current['pending_turn']['input'] == turns[index]['input']
        assert current['pending_turn']['source_conversation_id'] == conversation_id
        calls.append((query, conversation_id))
        return {'answer': turns[index]['expectation']['expected'], 'conversation_id': cid, 'terminal': True}

    monkeypatch.setattr(DifyClient, 'run_agent' if mode == 'agent' else 'run_chatflow', invoke)
    for attempt in range(2):
        response = request(client, task)
        assert response.status_code == 200, response.text
        run = response.json()['runs'][-1]
        assert run['evaluation']['status'] == 'passed' and run['result']['complete']
        assert [step['input'] for step in run['result']['turns']] == [turn['input'] for turn in turns]
        assert [step['result']['answer'] for step in run['result']['turns']] == [turn['expectation']['expected'] for turn in turns]
        assert run['test_case'] == declared and len(run['result']['turns']) == 3
        assert len(calls) == 3 * (attempt + 1)
    persisted = main.get_task(task['id'])
    monkeypatch.setattr(main, 'store', Store(tmp_path))
    assert main.get_task(task['id']) == persisted
    summary = client.get(f"/api/tasks/{task['id']}/acceptance").json()
    assert summary['required']['total'] == summary['required']['passed'] == 1
    assert summary['cases'][0]['run_id'] == persisted['runs'][-1]['id']
    assert summary['verification'] == 'declared_checks_only'
    assert any('完整业务覆盖仍需人工确认' in text for text in summary['blockers'])
    assert main.get_task(task['id']) == persisted


@pytest.mark.parametrize('mode', ['agent', 'advanced-chat'])
def test_at15_skipping_required_followup_fails_even_with_successful_transport(client, monkeypatch, mode):
    task = clarification_task(client, mode)
    calls = []

    async def invoke(*args, **kwargs):
        calls.append(1)
        return {'answer': '请提供工单编号。' if len(calls) == 1 else '工单已完成。',
                'conversation_id': 'isolated-c', 'terminal': True}

    monkeypatch.setattr(DifyClient, 'run_agent' if mode == 'agent' else 'run_chatflow', invoke)
    response = request(client, task)
    assert response.status_code == 200, response.text
    run = response.json()['runs'][-1]
    assert len(calls) == 2 and run['status'] == 'success'
    assert run['evaluation']['status'] == 'failed'
    assert run['result']['stop_reason'] == 'rule_failed' and not run['result']['complete']
    assert run['result']['turns'][1]['result']['answer'] == '工单已完成。'
    summary = client.get(f"/api/tasks/{task['id']}/acceptance").json()
    assert summary['required']['failed'] == 1 and not summary['all_required_passed']
    review = client.post(f"/api/tasks/{task['id']}/runs/{run['id']}/review", json={
        'revision': task['revision'], 'decision': 'passed', 'reason': '不能以请求成功代替必要追问'})
    assert review.status_code == 422 and len(calls) == 2


@pytest.mark.parametrize('mode', ['agent', 'advanced-chat'])
@pytest.mark.parametrize('missing', ['answer', 'conversation_id', 'changed_id'])
def test_at15_incomplete_second_turn_keeps_checkpoint_and_blocks_acceptance(client, monkeypatch, mode, missing):
    task = clarification_task(client, mode)
    calls = []
    partial = {'answer': '请提供手机号尾号。', 'conversation_id': 'isolated-c', 'terminal': True}
    if missing == 'changed_id':
        partial['conversation_id'] = 'another-c'
    else:
        partial.pop(missing)

    async def invoke(*args, **kwargs):
        calls.append(1)
        return {'answer': '请提供工单编号。', 'conversation_id': 'isolated-c', 'terminal': True} if len(calls) == 1 else partial

    monkeypatch.setattr(DifyClient, 'run_agent' if mode == 'agent' else 'run_chatflow', invoke)
    assert request(client, task).status_code == 502
    run = main.get_task(task['id'])['runs'][-1]
    assert run['status'] == 'unknown' and len(run['result']['turns']) == 1
    assert not run['result']['complete']
    assert run['result']['pending_turn'] == {
        'index': 2, 'input': {'query': 'S-4827'}, 'source_conversation_id': 'isolated-c', 'result': partial}
    summary = client.get(f"/api/tasks/{task['id']}/acceptance").json()
    assert summary['required']['unknown'] == 1 and not summary['all_required_passed']
    assert request(client, task).status_code == 409 and len(calls) == 2


@pytest.mark.parametrize('mutation', ['answer', 'source_id', 'index', 'complete', 'revision', 'environment'])
def test_at15_saved_pass_cannot_hide_invalid_context_or_stale_revision(client, monkeypatch, mutation):
    task = clarification_task(client, 'agent')
    expected = ['请提供工单编号。', '请提供手机号尾号。', '已收集工单 S-4827 和尾号 7316，等待查询。']
    calls = []

    async def invoke(*args, **kwargs):
        answer = expected[len(calls)]
        calls.append(1)
        return {'answer': answer, 'conversation_id': 'isolated-c', 'terminal': True}

    monkeypatch.setattr(DifyClient, 'run_agent', invoke)
    assert request(client, task).status_code == 200
    current = main.get_task(task['id'])
    run = current['runs'][-1]
    assert run['evaluation']['status'] == 'passed'
    if mutation == 'answer': run['result']['turns'][2]['result']['answer'] = '忘记了工单编号'
    if mutation == 'source_id': run['result']['turns'][2]['source_conversation_id'] = 'another-c'
    if mutation == 'index': run['result']['turns'][2]['index'] = 2
    if mutation == 'complete': run['result']['complete'] = False
    if mutation == 'revision': run['revision'] -= 1
    if mutation == 'environment': run['environment_id'] = 'another-env'
    main.save_task(current)
    summary = client.get(f"/api/tasks/{task['id']}/acceptance").json()
    status = 'failed' if mutation == 'answer' else 'not_run' if mutation in {'revision', 'environment'} else 'needs_review'
    assert summary['cases'][0]['status'] == status
    assert summary['required']['passed'] == 0 and not summary['all_required_passed']
    assert main.get_task(task['id']) == current and len(calls) == 3
