import json
import httpx
import pytest
from test_assistant_routing import client,setup,forbid_routing_external_calls
from test_lightweight_upgrade import upgrade,generate,USAGE
from test_case_proposals import candidate
from app import main
from app.providers import call_model


@pytest.mark.parametrize('valid_json',[False,True])
def test_declared_length_with_nonempty_content_stops_before_upgrade_or_candidate_application(client,monkeypatch,valid_json):
    task,primary,light=setup(client);assert upgrade(client,task,light).status_code==200;calls=[]
    async def wire(self,request):
        calls.append(request)
        content=json.dumps(candidate()) if valid_json or len(calls)>1 else 'TRUNCATED NONEMPTY JSON {'
        return httpx.Response(200,json={'choices':[{'finish_reason':'length' if len(calls)==1 else 'stop','message':{'role':'assistant','content':content}}],'usage':USAGE},request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',wire);monkeypatch.setattr(main,'call_model',call_model)
    response=generate(client,task)
    assert response.status_code==422 and len(calls)==1 and not main.store.list('case_proposal')
    op=main.get_task(task['id'])['planning_runs'][-1]
    assert op['attempts'][0]['finish_reason']=='length' and not op['routing']['upgrade']['triggered']
    assert len(main.budgets.get(task['id'])['entries'])==1 and main.budgets.get(task['id'])['entries'][0]['status']=='settled'


@pytest.mark.parametrize('kind',['content_filter','tool_calls','missing','wrong_role','refusal','stop_with_tool_payload'])
def test_nonfinal_or_refused_wire_never_becomes_a_format_upgrade(client,monkeypatch,kind):
    task,primary,light=setup(client);upgrade(client,task,light);calls=[]
    async def wire(self,request):
        calls.append(request);message={'role':'assistant','content':'NOT JSON'};reason=kind if kind in ('content_filter','tool_calls') else None if kind=='missing' else 'stop'
        if kind=='wrong_role':message['role']='user'
        if kind=='refusal':message['refusal']='PRIVATE REFUSAL'
        if kind=='stop_with_tool_payload':message['tool_calls']=[{'PRIVATE':'PAYLOAD'}]
        return httpx.Response(200,json={'choices':[{'finish_reason':reason,'message':message}],'usage':USAGE},request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',wire);monkeypatch.setattr(main,'call_model',call_model)
    assert generate(client,task).status_code==422 and len(calls)==1 and not main.store.list('case_proposal')


def test_legacy_plain_text_transport_without_strict_flag_keeps_old_contract(monkeypatch):
    import asyncio
    async def wire(self,request):return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'legacy nonempty'}}],'usage':USAGE},request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',wire)
    text,usage=asyncio.run(call_model({'protocol':'openai-compatible','base_url':'https://legacy.example.test/v1','model':'fake','provider':'custom'},'fake-only',[{'role':'user','content':'public'}]))
    assert text=='legacy nonempty' and usage==USAGE


@pytest.mark.parametrize('reason',['max_tokens','tool_use','stop_sequence',None,'end_turn'])
def test_strict_anthropic_terminal_state_preserves_usage(monkeypatch,reason):
    import asyncio
    from app.providers import ProviderError
    async def wire(self,request):return httpx.Response(200,json={'role':'assistant','content':[{'type':'text','text':'complete text'}],'stop_reason':reason,'usage':{'input_tokens':10,'output_tokens':20}},request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',wire)
    async def invoke():return await call_model({'protocol':'anthropic','base_url':'https://synthetic.example.test/v1','model':'fake','provider':'custom'},'fake-only',[{'role':'user','content':'public'}],require_final_text=True)
    if reason=='end_turn':assert asyncio.run(invoke())[0]=='complete text'
    else:
        with pytest.raises(ProviderError) as error:asyncio.run(invoke())
        assert error.value.usage=={'input_tokens':10,'output_tokens':20}
