import json
import pytest
import yaml
from test_api import client,create_env,approved
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


@pytest.mark.parametrize('mismatch',['revision','environment','failed','foreign_task'])
def test_unrelated_or_stale_conversation_never_dispatched(client,monkeypatch,mismatch):
    task,env=prepared(client)
    record={'id':'source','kind':'run','status':'success','revision':task['revision'],'environment_id':env['id'],'result':{'answer':'回答','conversation_id':'cid'}}
    if mismatch=='revision':record['revision']-=1
    if mismatch=='environment':record['environment_id']='elsewhere'
    if mismatch=='failed':record['status']='failed'
    if mismatch!='foreign_task':task['runs'].append(record)
    main.save_task(task)
    async def forbidden(*args,**kwargs):pytest.fail('Invalid context must not dispatch')
    monkeypatch.setattr(main.DifyClient,'run_chatflow',forbidden)
    result=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'追问'},'conversation_from_run_id':'source'})
    assert result.status_code==422


def test_conversation_source_cannot_mix_with_fixed_case_or_other_id(client):
    task,env=prepared(client)
    for payload in ({'case_id':'case'},{'input':{'query':'q','conversation_id':'other'}}):
        result=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'conversation_from_run_id':'source',**payload})
        assert result.status_code==422


def test_missing_conversation_result_is_unknown_not_success(client,monkeypatch):
    task,env=prepared(client)
    async def malformed(*args,**kwargs):return {'answer':'部分输出'}
    monkeypatch.setattr(main.DifyClient,'run_chatflow',malformed)
    result=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'q'}})
    assert result.status_code==502
    current=main.get_task(task['id']);assert current['runs'][-1]['status']=='unknown' and current['runs'][-1]['result']=={'answer':'部分输出'}
    assert client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'q'}}).status_code==409
