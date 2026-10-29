import copy,json
import pytest
from test_api import client,forbid_api_external_calls
from test_mock_order_read import saved_after_sales
from test_after_sales_starter import review_saved_state
from test_delivery_bundle import bundle,unpack,built
from app import main
from app.dsl_roundtrip import parse


def task_with_mock(client):
    task=saved_after_sales(client);path='/api/tasks/'+task['id']
    response=client.patch(path,json={'configuration':{'mock_dependency_bindings':[{'dependency':'订单查询模拟','node_id':'order_lookup','replacement_todo':'待补接口地址、认证变量、字段和失败规则，另行确认接入。'}]}})
    assert response.status_code==200,response.text
    task=review_saved_state(client,response.json())
    response=client.post(path+'/confirm',json={'revision':task['revision'],'kind':'configuration'});assert response.status_code==200,response.text
    response=client.post(path+'/build',json={'revision':task['revision']});assert response.status_code==200,response.text
    return main.get_task(task['id'])


def test_bundle_contains_actionable_node_contract_and_hash_without_mutation(client,monkeypatch):
    task=task_with_mock(client);before=copy.deepcopy(task);budget=main.store.get('task_budget',task['id']);artifact=main.artifact_path(task).read_bytes();report=bytes(main.report(task['id']).body)
    from fastapi.responses import Response
    # Existing reports include elapsed-time metrics. Pin the returned bytes to
    # verify that packaging the guide never rewrites the report itself.
    monkeypatch.setattr(main,'report',lambda item_id:Response(report,media_type='text/markdown'))
    def forbidden(*args,**kwargs):pytest.fail('Guide export must not mutate/decrypt/dispatch')
    monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.store,'secret',forbidden)
    files,manifest=unpack(bundle(client,task));assert 'integration-guide.md' in files
    text=files['integration-guide.md'].decode();assert all(word in text for word in ('order_lookup','order_id','extract_order.order_no','result','string','status','order_answer','接入资料','认证','超时','重新确认','缺号','未验证'))
    assert '合成样例：已发货。' not in text and 'def main' not in text and 'DEMO-001' not in text
    assert files[f"dify-advanced-chat-r{task['revision']}.yaml"]==artifact and files[f"report-r{task['revision']}.md"]==report
    assert all(manifest[k] is False for k in ('task_changed','network_requested','platform_checked','business_verified'))
    assert main.get_task(task['id'])==before and main.store.get('task_budget',task['id'])==budget


def test_no_mock_dependencies_keeps_original_four_file_bundle(client):
    files,_=unpack(bundle(client,built(client)));assert len(files)==4 and 'integration-guide.md' not in files


@pytest.mark.parametrize('binding',[[],[{'dependency':'订单查询模拟','node_id':'missing','replacement_todo':'先确认位置。'}]])
def test_unbound_or_missing_native_node_is_explicit_not_guessed(binding):
    from app.mock_integration_guide import render
    task={'revision':3,'configuration':{'mock_dependencies':['订单查询模拟'],'mock_dependency_bindings':binding}}
    text=render(task,{'workflow':{'graph':{'nodes':[],'edges':[]}}})
    assert '待补' in text and '未定位' in text and '不自动' in text


def native_fixture():
    return {'workflow':{'graph':{'nodes':[
        {'id':'mock','data':{'type':'code','variables':[{'variable':'order','value_selector':['source','id']}],'outputs':{'result':{'type':'string','children':None}},'code':'PRIVATE_TABLE_DO_NOT_COPY'}},
        {'id':'reply','data':{'type':'answer','answer':'{{#mock.result#}}'}},
        {'id':'consumer','data':{'type':'code','variables':[{'variable':'value','value_selector':['mock','result']}],'code':'# {{#mock.comment_only#}}'}}], 'edges':[{'source':'mock','target':'reply'}]}}}


def test_guide_uses_native_artifact_contract_and_references_without_code_or_literals():
    from app.mock_integration_guide import render
    native=native_fixture();before=copy.deepcopy(native)
    task={'revision':5,'workflow_plan':{'nodes':[{'id':'wrong'}]},'configuration':{'mock_dependencies':['公开模拟'],'mock_dependency_bindings':[{'dependency':'公开模拟','node_id':'mock','replacement_todo':'需提供正式接口约定。'}]}}
    text=render(task,native)
    assert 'source.id' in text and 'mock.result' in text and 'reply' in text and 'consumer' in text
    assert 'PRIVATE_TABLE' not in text and 'comment_only' not in text and 'wrong' not in text and native==before


def test_guide_does_not_invent_unknown_output_types_or_actual_api():
    from app.mock_integration_guide import render
    native=native_fixture();native['workflow']['graph']['nodes'][0]['data'].pop('outputs')
    text=render({'revision':1,'configuration':{'mock_dependencies':['公开模拟'],'mock_dependency_bindings':[{'dependency':'公开模拟','node_id':'mock','replacement_todo':'未知接口。'}]}},native)
    assert '未声明' in text and 'https://' not in text and 'curl ' not in text


@pytest.mark.parametrize('where',['dependency','todo','node_id'])
def test_guide_credentials_fail_entire_bundle_without_echo(client,where):
    task=task_with_mock(client);secret='app-PRIVATE-SYNTHETIC-NEVER-EXPORT'
    if where=='dependency':task['configuration']['mock_dependencies']=[secret]
    else:task['configuration']['mock_dependency_bindings'][0]['replacement_todo' if where=='todo' else 'node_id']=secret
    main.store.put('task',task['id'],task);response=bundle(client,task)
    assert response.status_code==422 and 'PRIVATE-SYNTHETIC' not in response.text


def test_changed_saved_fact_during_guide_refuses_mixed_bundle(client,monkeypatch):
    from app import delivery_bundle
    task=task_with_mock(client);original=delivery_bundle.integration_guide
    def changed(*args):
        text=original(*args);current=main.get_task(task['id']);current['status']='paused';main.store.put('task',task['id'],current);return text
    monkeypatch.setattr(delivery_bundle,'integration_guide',changed)
    assert bundle(client,task).status_code==409
