import copy
from uuid import uuid4
import pytest
import yaml
from test_api import client, approved
from test_structured_guard import prepare, compiled_function
from app.structured_guard import refresh_candidate
from app.workflow_plan import compile_workflow_plan, validate_plan
from app.dsl_roundtrip import validate_preserved
from app import main


def changed():
    task,_,value,guard=prepare();plan=value['plan']
    source=next(n for n in plan['nodes'] if n['id']=='llm')
    source['config']['structured_output']['schema']['properties']['label']['enum']=['客户当前规则']
    guard['title']='保留人工标题'
    return task,plan,guard


def test_explicit_refresh_only_changes_generated_code_preserves_id_title_edges_and_input():
    task,plan,guard=changed();before=copy.deepcopy(plan)
    assert not validate_plan(task,plan)['valid']
    value=refresh_candidate(task,plan,'llm');assert plan==before
    assert value['added_nodes']==value['changed_edges']==0 and value['updated_nodes']==1
    assert value['previous_schema_sha256']!=value['schema_sha256']
    updated=value['plan'];assert updated['edges']==before['edges']
    for old,new in zip(before['nodes'],updated['nodes']):
        if old['id']==guard['id']:
            expected=copy.deepcopy(old);expected['config']['code']=new['config']['code'];assert expected==new
            assert new['title']=='保留人工标题'
        else:assert old==new
    text,checked=compile_workflow_plan({**task,'workflow_plan':updated});assert checked['valid'],checked
    assert validate_preserved(yaml.safe_load(text))['valid']


def test_refreshed_generated_checker_enforces_current_schema_without_coercion():
    task,plan,old=changed();value=refresh_candidate(task,plan,'llm');new=next(n for n in value['plan']['nodes'] if n['id']==old['id'])
    payload={'label':'客户当前规则'}
    with pytest.raises(ValueError):compiled_function(old)(payload)
    assert compiled_function(new)(payload)['result'] is payload
    with pytest.raises(ValueError):compiled_function(new)({'label':'售后'})


@pytest.mark.parametrize('change',[
    lambda p,g:g['config'].update(code=g['config']['code']+'\n# 人工修改必须保留'),
    lambda p,g:g['config']['variables'][0].update(variable='renamed'),
    lambda p,g:p['edges'].append({'source':'llm','target':'end'}),
    lambda p,g:g['config'].update(error_strategy='default-value'),
    lambda p,g:g['config']['outputs'].update(extra={'type':'string'}),
    lambda p,g:g['config'].update(code=g['config']['code'].replace('_SCHEMA = ', '_SCHEMA = execute_untrusted() or ',1)),
])
def test_manual_code_io_or_path_change_not_overwritten_or_executed(change):
    task,plan,guard=changed();change(plan,guard);before=copy.deepcopy(plan)
    with pytest.raises(ValueError):refresh_candidate(task,plan,'llm')
    assert plan==before


def test_unchanged_schema_and_nonworkflow_targets_refused():
    task,_,value,_=prepare()
    with pytest.raises(ValueError,match='未改变'):refresh_candidate(task,value['plan'],'llm')
    task['app_type']='advanced-chat'
    with pytest.raises(ValueError,match='Workflow'):refresh_candidate(task,value['plan'],'llm')
    assert task['app_type']=='advanced-chat'


def test_api_refresh_is_local_revision_ack_and_operation_bound_without_save(client,monkeypatch):
    saved=approved(client);before=copy.deepcopy(main.get_task(saved['id']));_,plan,_=changed()
    def forbidden(*args,**kwargs):pytest.fail('本机更新方案不执行平台或模型')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
    body={'revision':saved['revision'],'plan':plan,'node_id':'llm','acknowledge_fail_workflow':True,'request_nonce':str(uuid4()),'operation':'refresh'}
    path=f"/api/tasks/{saved['id']}/structured-output-guard"
    assert client.post(path,json={**body,'acknowledge_fail_workflow':False}).status_code==422
    assert client.post(path,json={**body,'operation':'overwrite_any_code'}).status_code==422
    assert client.post(path,json={**body,'revision':saved['revision']+1}).status_code==409
    response=client.post(path,json=body);assert response.status_code==200,response.text
    result=response.json();assert result['operation']=='refresh' and result['updated_nodes']==1 and result['added_nodes']==0
    assert result['request_nonce']==body['request_nonce'] and not result['platform_checked']
    assert main.get_task(saved['id'])==before
