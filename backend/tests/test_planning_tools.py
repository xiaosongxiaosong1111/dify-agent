"""Synthetic HTTPX responses only: no real model, probe or Dify access."""
import asyncio, copy, hashlib, json
import httpx
import pytest
from test_api import client, approved, create, forbid_api_external_calls
from test_task_budget import provider, policy as budget_policy, ledger, USAGE
from test_planning import plan
from app import main, planning_tools
from app.provider_tool_probe import identity
from app.planning_tool_protocol import NAME, TOOL, arguments, messages_for_wire, pricing_messages, encoded
from app.providers import ProviderError
from app.planning import reserve_cost


def setup(client, app_type='workflow'):
    task=approved(client,app_type=app_type); public=provider(client)
    raw=main.store.get('provider',public['id'])
    raw['capabilities']={**raw.get('capabilities',{}),'tools':'verified'}
    raw['checks']={**raw.get('checks',{}),'tools':{'scope':'single_function_request_only','source_token':identity(raw),'synthetic_fixture':True}}
    main.store.put('provider',raw['id'],raw)
    task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':raw['id']}}).json()
    return task,raw


def state(client, task):return client.get(f"/api/tasks/{task['id']}/planning-tool-policy").json()


def save(client,task,**changes):
    current=state(client,task)
    return client.patch(f"/api/tasks/{task['id']}/planning-tool-policy",json={
        'revision':task['revision'],'policy_revision':current['policy_revision'],'scope_version':current['required_scope_version'],
        'enabled':True,'source_token':current['current_source_token'],'acknowledge_scope':True,
        'note':'明确的合成隔离夹具，不是真实工具能力观察',**changes})


def generate(client,task):return client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})


def reply(text=None,call=None,finish=None,usage=USAGE):
    message={'role':'assistant','content':text}
    if call is not None:message['tool_calls']=[call]
    return {'choices':[{'finish_reason':finish or ('tool_calls' if call else 'stop'),'message':message}],'usage':usage}


def tool(args='{"node_types":["code"]}'):
    return {'id':'rules-1','type':'function','function':{'name':NAME,'arguments':args}}


def wire(monkeypatch,responses,action=None):
    calls=[]
    async def transport(self,request):
        assert str(request.url)=='https://example.com/v1/chat/completions'
        assert request.headers['authorization']=='Bearer not-a-real-key'
        calls.append(json.loads(request.content))
        if action:action(len(calls))
        result=responses[len(calls)-1]
        if isinstance(result,BaseException):raise result
        return httpx.Response(200,json=result,request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',transport)
    return calls


def test_actual_tool_result_is_paired_and_both_requests_share_ledger(client,monkeypatch):
    task,p=setup(client);assert save(client,task).status_code==200
    queries=[];original=planning_tools.execute_query
    monkeypatch.setattr(planning_tools,'execute_query',lambda *a:(queries.append(a),original(*a))[1])
    calls=wire(monkeypatch,[reply(call=tool()),reply(json.dumps(plan()))])
    response=generate(client,task);assert response.status_code==200,response.text
    assert queries==[('workflow',['code'])] and len(calls)==2
    first,second=calls
    assert first['tools']==[TOOL] and first['tool_choice']=='auto' and first['parallel_tool_calls'] is False
    assert 'response_format' not in first and 'tools' not in second
    assert second['response_format']=={'type':'json_object'}
    assert second['messages'][:-2]==first['messages']
    assert second['messages'][-2]=={'role':'assistant','content':None,'tool_calls':[tool()]}
    message=second['messages'][-1];assert message['role']=='tool' and message['tool_call_id']=='rules-1'
    result=json.loads(message['content']);assert result['read_only'] and not result['network_requested'] and not result['resource_permission_granted']
    run=response.json()['planning_runs'][-1];receipt=run['tool_receipts'][0]
    assert receipt['status']=='completed' and receipt['followup_prepared'] and receipt['final_text_received']
    assert receipt['result_sha256']==hashlib.sha256(message['content'].encode()).hexdigest()
    assert receipt['result_bytes']==len(message['content'].encode())<=32768
    assert run['planning_tools']['registered_dispatches_started']==1 and not run['planning_tools']['target_runtime_verified']
    entries=ledger(client,task)['entries'];assert len(entries)==2
    assert {e['operation_id'] for e in entries}=={run['id']}
    assert [e['request_scope'] for e in entries]==['planning_node_rules_select','planning_node_rules_answer']
    assert all(e['kind']=='plan' and e['status']=='settled' for e in entries)
    for stage,call,e in zip(('select','answer'),calls,entries):
        assert e['reserved_usd']==str(reserve_cost(pricing_messages(call['messages'],stage),p['pricing']))


def test_direct_text_has_no_registered_query_or_second_request(client,monkeypatch):
    task,p=setup(client);assert save(client,task).status_code==200
    monkeypatch.setattr(planning_tools,'execute_query',lambda *a:pytest.fail('没有实际工具请求不得执行注册查询'))
    calls=wire(monkeypatch,[reply(json.dumps(plan()))])
    response=generate(client,task);assert response.status_code==200,response.text
    run=response.json()['planning_runs'][-1]
    assert len(calls)==1 and run['tool_receipts']==[] and run['planning_tools']['registered_dispatches_started']==0


@pytest.mark.parametrize('failure',['unknown_name','duplicate_args','extra_arg','multiple','length','role','refusal','unknown_usage','connection','bad_json'])
def test_failed_initial_response_never_dispatches_query_or_repairs(client,monkeypatch,failure):
    task,p=setup(client);assert save(client,task).status_code==200
    value=reply(call=tool())
    if failure=='unknown_name':value['choices'][0]['message']['tool_calls'][0]['function']['name']='read_file'
    if failure=='duplicate_args':value=reply(call=tool('{"node_types":["code"],"node_types":["llm"]}'))
    if failure=='extra_arg':value=reply(call=tool('{"node_types":["code"],"url":"https://example.com"}'))
    if failure=='multiple':value['choices'][0]['message']['tool_calls']*=2
    if failure=='length':value['choices'][0]['finish_reason']='length'
    if failure=='role':value['choices'][0]['message']['role']='user'
    if failure=='refusal':value['choices'][0]['message']['refusal']='no'
    if failure=='unknown_usage':value['usage']={}
    if failure=='connection':value=httpx.ConnectError('synthetic failure')
    if failure=='bad_json':value=reply('not JSON: I already looked up rules')
    calls=wire(monkeypatch,[value])
    monkeypatch.setattr(planning_tools,'execute_query',lambda *a:pytest.fail('失败必须停下'))
    response=generate(client,task);assert response.status_code==422,response.text
    assert len(calls)==1 and not main.get_task(task['id']).get('workflow_plan')
    entries=ledger(client,task)['entries'];assert len(entries)==1
    assert entries[0]['status']==('unknown' if failure in ('unknown_usage','connection') else 'settled')


@pytest.mark.parametrize('change',['pause','revision','provider','policy','time'])
def test_late_source_pause_or_deadline_stops_before_query(client,monkeypatch,change):
    task,p=setup(client);assert save(client,task).status_code==200
    def action(_):
        current=main.get_task(task['id'])
        if change=='pause':main.pause(task['id'])
        if change=='revision':current['revision']+=1;main.save_task(current)
        if change=='provider':p['configuration_revision']=99;main.store.put('provider',p['id'],p)
        if change=='policy':row=main.planning_tool_policy.get(task['id']);row['enabled']=False;main.store.put('planning_tool_policy',task['id'],row)
    if change=='time':
        original=planning_tools.run;clock=[0]
        async def run(*a,**kw):return await original(*a,**kw,clock=lambda:clock[0])
        monkeypatch.setattr(planning_tools,'run',run)
        def action(_):clock[0]=100000
    calls=wire(monkeypatch,[reply(call=tool())],action)
    monkeypatch.setattr(planning_tools,'execute_query',lambda *a:pytest.fail('晚到不得执行查询'))
    assert generate(client,task).status_code==422 and len(calls)==1
    assert ledger(client,task)['entries'][0]['status']=='settled'


def test_second_reservation_uses_same_round_budget(client,monkeypatch):
    task,p=setup(client);assert save(client,task).status_code==200
    settings=main.get_settings();settings['max_cost_usd']=1;main.store.put('settings','execution',settings)
    # First full reserve fits; reported first cost leaves too little for second.
    calls=wire(monkeypatch,[reply(call=tool(),usage={'prompt_tokens':990000,'completion_tokens':1})])
    assert generate(client,task).status_code==422
    run=main.get_task(task['id'])['planning_runs'][-1]
    assert len(calls)==1 and run['stop_reason']=='cost_limit' and run['tool_receipts'][0]['status']=='completed'
    assert len(ledger(client,task)['entries'])==1


def test_cumulative_budget_blocks_second_even_when_round_has_room(client,monkeypatch):
    task,p=setup(client);assert save(client,task).status_code==200
    # Commit an explicit zero limit after first settles, before follow-up reserve.
    original=planning_tools.execute_query
    def query(*args):
        b=main.budgets.get(task['id']);b['limit_usd']='0';main.store.put('task_budget',task['id'],b)
        return original(*args)
    monkeypatch.setattr(planning_tools,'execute_query',query)
    calls=wire(monkeypatch,[reply(call=tool())]);assert generate(client,task).status_code==422
    assert len(calls)==1 and len(ledger(client,task)['entries'])==1


@pytest.mark.parametrize('failure',['tool_again','length','unknown_usage','invalid_plan','connection','cancel'])
def test_second_failure_never_third_request_or_applies_plan(client,monkeypatch,failure):
    task,p=setup(client);assert save(client,task).status_code==200
    second=reply(json.dumps(plan()))
    if failure=='tool_again':second=reply(call=tool())
    if failure=='length':second['choices'][0]['finish_reason']='length'
    if failure=='unknown_usage':second['usage']={}
    if failure=='invalid_plan':second=reply(json.dumps({'schema_version':1,'nodes':[],'edges':[]}))
    if failure=='connection':second=httpx.ConnectError('synthetic')
    if failure=='cancel':second=asyncio.CancelledError()
    calls=wire(monkeypatch,[reply(call=tool()),second])
    try:response=generate(client,task)
    except BaseException:
        assert failure=='cancel'
    else:assert response.status_code==422
    current=main.get_task(task['id']);assert len(calls)==2 and not current.get('workflow_plan')
    assert current['planning_runs'][-1]['tool_receipts'][0]['status']=='completed'
    entries=ledger(client,task)['entries'];assert len(entries)==2
    assert entries[-1]['status']==('unknown' if failure in ('unknown_usage','connection','cancel') else 'settled')


def test_replanning_keeps_existing_plan_and_full_candidate(client,monkeypatch):
    task,p=setup(client);old=plan();r=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':old});assert r.status_code==200
    task=r.json();assert save(client,task).status_code==200
    changed=plan("def main(query):\n    return {'result': query.upper()}\n")
    wire(monkeypatch,[reply(call=tool()),reply(json.dumps(changed))])
    assert generate(client,task).status_code==422
    current=main.get_task(task['id']);assert current['workflow_plan']==old
    assert current['planning_runs'][-1]['last_candidate']==changed
    assert current['planning_runs'][-1]['stop_reason']=='replanning_review'


def test_restart_marks_pending_tool_receipt_unknown_without_replay(client):
    task,p=setup(client)
    task.update(status='planning',planning_runs=[{'id':'crashed','status':'paused','planning_tools':{'max_model_http_requests':2},'tool_receipts':[{'status':'requested'}],'attempts':[{'status':'pending','reserved_cost_usd':.02}]}])
    main.save_task(task);main.recover_planning()
    current=main.get_task(task['id']);run=current['planning_runs'][-1]
    assert current['status']=='paused' and run['status']=='interrupted'
    assert run['tool_receipts'][0]['status']=='interrupted_unknown' and run['attempts'][0]['status']=='unknown_usage'


def test_policy_read_does_not_decrypt_write_or_change_task(client,monkeypatch):
    task,p=setup(client);before=main.get_task(task['id'])
    monkeypatch.setattr(main.store,'secret',lambda *a:pytest.fail('状态读取不得解密'))
    current=state(client,task);assert not current['enabled'] and current['ready']
    assert main.store.get('planning_tool_policy',task['id']) is None and main.get_task(task['id'])==before


@pytest.mark.parametrize('change',['ack','note','scope','task_revision','policy_revision','token','foreign_token','agent','capability','retries_zero','version'])
def test_policy_rejects_ambiguous_or_stale_confirmation(client,change):
    task,p=setup(client);kw={}
    if change=='ack':kw['acknowledge_scope']=False
    if change=='note':kw['note']=' '
    if change=='scope':kw['scope_version']=0
    if change=='task_revision':kw['revision']=task['revision']-1
    if change=='policy_revision':kw['policy_revision']=1
    if change=='token':kw['source_token']='0'*64
    if change=='foreign_token':other,_=setup(client);kw['source_token']=state(client,other)['current_source_token']
    if change=='agent':task=create(client,'agent')
    if change=='capability':p['checks']={};main.store.put('provider',p['id'],p)
    if change=='retries_zero':s=main.get_settings();s['max_retries']=0;main.store.put('settings','execution',s)
    if change=='version':main.store.put('environment','old',{'id':'old','version':'1.0.0'});task['environment_id']='old';main.save_task(task)
    assert save(client,task,**kw).status_code in (409,422)
    assert main.store.get('planning_tool_policy',task['id']) is None


def test_disable_clears_source_but_retains_confirmed_history(client):
    task,p=setup(client);assert save(client,task).status_code==200
    task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'goal':'下一修订'}}).json()
    assert state(client,task)['ready'] # Scope survives business edits, operation still revision-bound.
    assert save(client,task,enabled=False,source_token=None).status_code==200
    current=state(client,task);assert current['source_token'] is None and not current['enabled'] and len(current['history'])==2


@pytest.mark.parametrize('raw',['{"node_types":[]}','{"node_types":["code","code"]}','{"node_types":["http-request"]}','{"node_types":["code"],"extra":1}','{"node_types":["code"],"node_types":["llm"]}','{"node_types":[NaN]}'])
def test_argument_registry_closed(raw):
    with pytest.raises(ValueError):arguments(raw)


def test_wire_rejects_unpaired_or_extraneous_result_without_sending():
    assistant={'role':'assistant','content':None,'tool_calls':[tool()]}
    with pytest.raises(ValueError):messages_for_wire([assistant], 'answer')
    with pytest.raises(ValueError):messages_for_wire([assistant,{'role':'tool','content':'x','tool_call_id':'wrong'}],'answer')
    with pytest.raises(ProviderError):pricing_messages([{'role':'user','content':'x'*2_000_001}],'select')


@pytest.mark.parametrize('failure',['lookup_error','oversized','pause_after_query','source_after_query','late_final_source'])
def test_query_or_late_result_failure_keeps_plan_and_no_extra_dispatch(client,monkeypatch,failure):
    task,p=setup(client);assert save(client,task).status_code==200
    original=planning_tools.execute_query;queries=[]
    def query(*args):
        queries.append(args)
        if failure=='lookup_error':raise ValueError('PRIVATE ERROR MUST NOT BE ECHOED')
        if failure=='oversized':return {'huge':'x'*32768}
        result=original(*args)
        if failure=='pause_after_query':main.pause(task['id'])
        if failure=='source_after_query':p['configuration_revision']=123;main.store.put('provider',p['id'],p)
        return result
    monkeypatch.setattr(planning_tools,'execute_query',query)
    def action(number):
        if number==2 and failure=='late_final_source':p['configuration_revision']=123;main.store.put('provider',p['id'],p)
    calls=wire(monkeypatch,[reply(call=tool()),reply(json.dumps(plan()))],action)
    response=generate(client,task);assert response.status_code==422
    assert len(calls)==(2 if failure=='late_final_source' else 1) and len(queries)==1
    current=main.get_task(task['id']);assert not current.get('workflow_plan')
    if failure in ('lookup_error','oversized'):
        assert current['planning_runs'][-1]['tool_receipts'][0]['status']=='failed'
        assert 'PRIVATE ERROR' not in response.text


def test_oversized_original_context_stops_before_first_reservation(client,monkeypatch):
    task,p=setup(client);assert save(client,task).status_code==200
    task['requirements']['goal']='x'*2_000_001;main.save_task(task)
    calls=wire(monkeypatch,[]);response=generate(client,task)
    assert response.status_code==422 and not calls and not ledger(client,task)['entries']
    assert main.get_task(task['id'])['planning_runs'][-1]['stop_reason']=='invalid_tool_context'


def test_default_disabled_uses_legacy_planner_with_no_tool_scope(client,monkeypatch):
    task,p=setup(client);calls=[]
    async def legacy(*args,**kw):calls.append(kw);return json.dumps(plan()),USAGE
    monkeypatch.setattr(main,'call_model',legacy)
    wire(monkeypatch,[])
    response=generate(client,task);assert response.status_code==200,response.text
    assert len(calls)==1 and 'planning_tool_stage' not in calls[0]
    assert 'planning_tools' not in response.json()['planning_runs'][-1]
    assert 'request_scope' not in ledger(client,task)['entries'][0]


def test_raw_duplicate_policy_rejected_without_echo_or_write(client):
    task,p=setup(client)
    response=client.patch(f"/api/tasks/{task['id']}/planning-tool-policy",content='{"enabled":true,"enabled":false,"private":"HIDDEN_POLICY_INPUT"}',headers={'Content-Type':'application/json'})
    assert response.status_code==422 and 'HIDDEN_POLICY_INPUT' not in response.text
    assert response.headers['cache-control']=='no-store' and main.store.get('planning_tool_policy',task['id']) is None
