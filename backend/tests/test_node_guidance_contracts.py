from test_api import client, forbid_api_external_calls
from test_api import approved, planning_provider
from app import main
from app.node_guidance import lookup, for_task
from app.workflow_plan import compile_workflow_plan, validate_plan
from test_workflow_plan import task as compiler_task
import copy,json
import pytest


def test_missing_entry_extractor_and_assigner_contracts_are_available_in_chatflow(client):
    response=client.get('/api/node-guidance',params={'app_type':'advanced-chat','node_types':'start,parameter-extractor,assigner'})
    assert response.status_code==200,response.text
    value=response.json()
    assert [row['node_type'] for row in value['items']]==['start','parameter-extractor','assigner']
    assert value['missing_node_types']==[] and value['runtime_verified'] is False


def example(mode,kind):
    row=lookup(mode,[kind])['items'][0]
    return {**compiler_task(mode),'configuration':row['example_configuration'],'workflow_plan':row['example_plan']}


def test_workflow_and_agent_never_receive_chatflow_root_assigner_examples(client):
    value=client.get('/api/node-guidance',params={'app_type':'workflow','node_types':'assigner'}).json()
    assert value['app_type']=='workflow' and value['items']==[] and value['missing_node_types']==['assigner']
    assert any('Chatflow根层' in text for text in value['notes'])
    assert 'assigner' not in value['available_node_types']
    agent=lookup('agent',['start','parameter-extractor','assigner'])
    assert not agent['items'] and not agent['available_node_types']


@pytest.mark.parametrize('kind',['start','parameter-extractor','assigner'])
def test_new_examples_reject_the_actual_399_wrong_field_patterns_without_normalization(kind):
    task=example('advanced-chat',kind);before=copy.deepcopy(task['workflow_plan'])
    assert compile_workflow_plan(task)[1]['valid']
    if kind=='start':task['workflow_plan']['nodes'][0]['config']['variables']=[{'variable':'query','type':'text-input','required':True}]
    elif kind=='parameter-extractor':
        node=next(n for n in task['workflow_plan']['nodes'] if n['type']==kind)
        node['config']['query_variable_selector']=node['config'].pop('query')
    else:
        node=next(n for n in task['workflow_plan']['nodes'] if n['type']==kind)
        item=node['config']['items'][0];item['value_selector']=item.pop('value')
    changed=copy.deepcopy(task['workflow_plan']);checked=validate_plan(task,changed)
    assert not checked['valid'] and task['workflow_plan']==changed and changed!=before


@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_extractor_example_has_strict_number_success_gate_and_no_failed_field_read(mode):
    task=example(mode,'parameter-extractor');plan=task['workflow_plan']
    extractor=next(n for n in plan['nodes'] if n['type']=='parameter-extractor')
    assert extractor['config']['query']==(['sys','query'] if mode=='advanced-chat' else ['start','query'])
    gate=next(n for n in plan['nodes'] if n['id']==extractor['config']['failure_policy']['guard_node_id'])
    assert gate['config']['cases'][0]['conditions']==[{'variable_selector':['extract','__is_success'],'varType':'number','comparison_operator':'=','value':'1'}]
    assert compile_workflow_plan(task)[1]['valid']
    failure=next(n for n in plan['nodes'] if n['id']=='failure')
    failure['config']['variables']=[{'variable':'unsafe','value_selector':['extract','order_no']}]
    assert not validate_plan(task,plan)['valid']


def test_selection_uses_saved_requirements_and_scope_without_data_inference():
    task={'app_type':'advanced-chat','requirements':{'input':'每次一个query文字','rules':'提取明确订单号；两个每会话标记'},'configuration':{'dataset_ids':['PRIVATE-DATASET']},'messages':[{'content':'PRIVATE-MESSAGE'}]}
    before=copy.deepcopy(task);value=for_task(task)
    assert {'start','parameter-extractor','assigner'} <= {row['node_type'] for row in value['items']}
    assert 'PRIVATE' not in json.dumps(value) and task==before
    workflow=for_task({**task,'app_type':'workflow','workflow_plan':{'nodes':[{'type':'assigner'}]}})
    assert 'assigner' not in {row['node_type'] for row in workflow['items']} and 'assigner' in workflow['missing_node_types']


def test_normal_planning_payload_and_saved_provenance_include_new_contracts(client,monkeypatch):
    planning_provider(client);t=approved(client,app_type='advanced-chat');url='/api/tasks/'+t['id']
    requirements={**t['requirements'],'input':'每次一个query文字','rules':'提取明确订单号；两个每会话标记'}
    response=client.patch(url,json={'requirements':requirements});assert response.status_code==200
    t=response.json();response=client.post(url+'/confirm',json={'revision':t['revision'],'kind':'requirements'});assert response.status_code==200,response.text
    t=response.json();seen=[]
    async def model(*args,**kwargs):
        context=json.loads(args[2][1]['content']);guide=context['node_guidance'];seen.append(guide)
        kinds={row['node_type'] for row in guide['items']};assert {'start','parameter-extractor','assigner'}<=kinds
        for row in guide['items']:
            content,checked=compile_workflow_plan({**compiler_task('advanced-chat'),'configuration':row['example_configuration'],'workflow_plan':row['example_plan']})
            assert checked['valid'],checked
        return json.dumps(lookup('advanced-chat',['parameter-extractor'])['items'][0]['example_plan']),{'prompt_tokens':100,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(url+'/plan/generate',json={'revision':t['revision']});assert response.status_code==200,response.text
    assert len(seen)==1
    saved=response.json()['planning_runs'][-1]['node_guidance']
    assert saved['items']==[{'id':row['id'],'content_sha256':row['content_sha256']} for row in seen[0]['items']]
    assert 'example_plan' not in json.dumps(saved)


def test_registered_tool_advertises_new_contracts_but_keeps_four_type_and_byte_limits():
    from app.planning_tool_protocol import TOOL,arguments,NODE_TYPES,MAX_RESULT_BYTES,encoded
    assert {'start','parameter-extractor','assigner'}<=set(NODE_TYPES)
    assert TOOL['function']['parameters']['properties']['node_types']['maxItems']==4 and MAX_RESULT_BYTES==32768
    assert arguments('{"node_types":["start","parameter-extractor","assigner"]}')['node_types']==['start','parameter-extractor','assigner']
    with pytest.raises(ValueError):arguments(json.dumps({'node_types':list(NODE_TYPES[:5])}))
    assert len(encoded(lookup('advanced-chat',['start','parameter-extractor','assigner'])))<=MAX_RESULT_BYTES


def test_old_tool_scope_does_not_silently_expand_or_dispatch(client,monkeypatch):
    from test_planning_tools import setup,save,state,generate
    task,provider=setup(client);assert save(client,task).status_code==200
    row=main.store.get('planning_tool_policy',task['id']);row['scope_version']=1
    main.store.put('planning_tool_policy',task['id'],row);before=copy.deepcopy(row);calls=[]
    async def forbidden(*args,**kwargs):calls.append(args);raise AssertionError('Old tool scope must not dispatch')
    monkeypatch.setattr(main,'call_model',forbidden)
    current=state(client,task)
    assert current['required_scope_version']==2 and not current['ready'] and current['blocker']
    assert generate(client,task).status_code==422 and not calls
    assert main.store.get('planning_tool_policy',task['id'])==before
