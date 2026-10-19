import copy
from uuid import uuid4
import pytest
import yaml
from test_api import client, approved
from test_structured_output import configured, schema
from app import main
from app.structured_guard import candidate, MARKER
from app.workflow_plan import validate_plan, compile_workflow_plan
from app.dsl_roundtrip import validate_preserved


def prepare():
    task=configured();original=copy.deepcopy(task['workflow_plan'])
    value=candidate(task,original,'llm')
    guard=next(n for n in value['plan']['nodes'] if n['id']==value['guard_node_id'])
    return task,original,value,guard


def compiled_function(guard):
    # Execute only Sierra's fixed generated checker plus repr() schema literal.
    # No customer-provided code body is executed by this test helper or service.
    scope={};exec(compile(guard['config']['code'],'<sierra-generated-schema-guard>','exec'),scope)
    return scope['main']


def test_candidate_adds_one_guard_and_routes_all_successors_without_touching_original():
    task,original,value,guard=prepare()
    assert original==task['workflow_plan'] and guard['config']['code'].startswith(MARKER)
    assert value['added_nodes']==1 and value['changed_edges']==1
    assert value['failure_behavior']=='fail_workflow_no_defaults_no_retry'
    assert not value['platform_checked'] and not value['business_verified']
    plan=value['plan'];assert plan['nodes'][0]==original['nodes'][0] and plan['nodes'][1]==original['nodes'][1] and plan['nodes'][-1]==original['nodes'][-1]
    assert [e['target'] for e in plan['edges'] if e['source']=='llm']==[guard['id']]
    text,checked=compile_workflow_plan({**task,'workflow_plan':plan});assert checked['valid'],checked
    assert validate_preserved(yaml.safe_load(text))['valid']
    assert guard['config']['variables']==[{'variable':'data','value_selector':['llm','structured_output']}]


@pytest.mark.parametrize('value',[
    {'label':'售后'}, {'label':'其它','scores':[0,0.3,1],'approved':False},
])
def test_generated_checker_passes_valid_data_without_coercion_or_defaults(value):
    _,_,_,guard=prepare();before=copy.deepcopy(value);result=compiled_function(guard)(value)
    assert result=={'result':before} and result['result'] is value and value==before


@pytest.mark.parametrize('value',[
    {}, {'label':None}, {'label':'无此枚举'}, {'label':True},
    {'label':'售后','extra':'PRIVATE-VALUE'}, {'label':'售后','scores':['0.2']},
    {'label':'售后','scores':[True]}, {'label':'售后','scores':[float('inf')]},
    {'label':'售后','scores':[1.1]}, {'label':'售后','scores':[0,0,0,0]},
    {'label':'售后','approved':'false'}, [], 'PRIVATE-VALUE',
])
def test_generated_checker_rejects_bad_objects_without_echo_or_repair(value):
    _,_,_,guard=prepare();before=copy.deepcopy(value)
    with pytest.raises(ValueError) as failure:compiled_function(guard)(value)
    assert 'PRIVATE-VALUE' not in str(failure.value) and '失败' in str(failure.value)
    assert value==before


@pytest.mark.parametrize('change',[
    lambda p:p['nodes'][1]['config']['structured_output']['schema']['properties']['label'].update(enum=['新规则']),
    lambda p:p['nodes'][2]['config'].update(code=p['nodes'][2]['config']['code']+'\n# 手改'),
    lambda p:p['edges'].append({'source':'llm','target':'end'}),
    lambda p:p['nodes'][2]['config']['variables'][0].update(value_selector=['llm','text']),
])
def test_stale_schema_changed_code_binding_or_bypass_cannot_claim_original_guard(change):
    task,_,value,_=prepare();plan=value['plan'];change(plan);before=copy.deepcopy(plan)
    result=validate_plan(task,plan);assert not result['valid'] and plan==before
    assert any('校验' in e for e in result['errors'])


def test_duplicate_generation_refused_and_id_collision_does_not_overwrite():
    task,original,value,_=prepare()
    with pytest.raises(ValueError,match='已有'):candidate(task,value['plan'],'llm')
    task['workflow_plan']['nodes'].insert(2,{'id':'llm__schema_check','type':'template-transform','config':{'template':'保留','variables':[]}})
    task['workflow_plan']['edges']=[{'source':'start','target':'llm'},{'source':'llm','target':'llm__schema_check'},{'source':'llm__schema_check','target':'end'}]
    value=candidate(task,task['workflow_plan'],'llm')
    assert value['guard_node_id']=='llm__schema_check2'
    assert next(n for n in value['plan']['nodes'] if n['id']=='llm__schema_check')['config']['template']=='保留'


def test_chatflow_and_container_target_refused_without_changing_type():
    task,original,_,_=prepare();task['app_type']='advanced-chat'
    with pytest.raises(ValueError,match='流式'):candidate(task,original,'llm')
    assert task['app_type']=='advanced-chat'
    task['app_type']='workflow'
    with pytest.raises(ValueError,match='根大模型'):candidate(task,original,'not-root')


def test_schema_literal_cannot_inject_python_and_json_integer_float_value_remains_original():
    task=configured();rule=task['workflow_plan']['nodes'][1]['config']['structured_output']['schema']
    literal="x');raise RuntimeError('injection')#"
    rule['properties']={'literal':{'type':'string','enum':[literal]},'count':{'type':'integer','minimum':1,'maximum':2}}
    rule['required']=['literal','count']
    value=candidate(task,task['workflow_plan'],'llm');guard=next(n for n in value['plan']['nodes'] if n['id']==value['guard_node_id'])
    payload={'literal':literal,'count':1.0};assert compiled_function(guard)(payload)['result'] is payload
    with pytest.raises(ValueError):compiled_function(guard)({'literal':literal,'count':1.5})


def test_local_preview_api_requires_ack_revision_nonce_and_does_not_save_or_call(client,monkeypatch):
    t=approved(client);before=copy.deepcopy(main.get_task(t['id']));_,plan,_,_=prepare()
    def forbidden(*args,**kwargs):pytest.fail('纯本机方案不能调用平台／模型')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
    body={'revision':t['revision'],'plan':plan,'node_id':'llm','acknowledge_fail_workflow':True,'request_nonce':str(uuid4())}
    path=f"/api/tasks/{t['id']}/structured-output-guard"
    assert client.post(path,json={**body,'acknowledge_fail_workflow':False}).status_code==422
    assert client.post(path,json={**body,'acknowledge_fail_workflow':'true'}).status_code==422
    assert client.post(path,json={**body,'revision':t['revision']+1}).status_code==409
    assert client.post(path,json={**body,'request_nonce':'wrong'}).status_code==422
    response=client.post(path,json=body);assert response.status_code==200,response.text
    assert response.json()['task_id']==t['id'] and response.json()['request_nonce']==body['request_nonce']
    assert main.get_task(t['id'])==before


@pytest.mark.parametrize('settings',[
    {'error_strategy':'default-value','default_value':[{'key':'result','value':{}}]},
    {'retry_config':{'retry_enabled':True,'max_retries':2,'retry_interval':1000}},
    {'version':'unknown'}, {'unknown_execution_setting':True},
])
def test_actual_guard_retry_error_default_and_unknown_behavior_not_silently_preserved(settings):
    task,_,value,_=prepare();text,checked=compile_workflow_plan({**task,'workflow_plan':value['plan']});assert checked['valid']
    native=yaml.safe_load(text);node=next(n['data'] for n in native['workflow']['graph']['nodes'] if n['id']==value['guard_node_id']);node.update(settings)
    before=copy.deepcopy(native);assert not validate_preserved(native)['valid'] and native==before
