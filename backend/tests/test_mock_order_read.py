import copy
import hashlib
import json
from uuid import uuid4

import pytest

from test_api import client, forbid_api_external_calls
from test_mock_order import context, proposal, RECORDS
from test_extracted_mock_order import context as extracted_context, source as extracted_source, proposal as extracted_proposal
from test_after_sales_starter import prepared as blank_after_sales, inputs as starter_inputs
from app import main, mock_order
from app.after_sales_starter import prepare as starter
from app.plan_text_codec import parse, render


@pytest.mark.parametrize('mode,selector',[('workflow',['entry','order_id']),('advanced-chat',['entry','order_id']),('advanced-chat',['sys','query'])])
def test_original_template_table_and_binding_recovered_without_plan_changes(mode,selector):
    task=context(mode);text=proposal(task,selector=selector)['plan_text'];original=copy.deepcopy(task)
    value=mock_order.read_existing(task,text,'lookup','订单查询模拟')
    assert json.loads(value['records_text'])==RECORDS and value['input_selector']==selector
    assert value['record_count']==2 and task==original
    assert value['source_text_sha256']==hashlib.sha256(text.encode()).hexdigest()
    assert value['records_text_sha256']==hashlib.sha256(value['records_text'].encode()).hexdigest()
    assert all(value[k] is False for k in ['task_changed','network_requested','code_executed','platform_checked','business_verified'])


def test_extracted_order_source_keeps_success_protection_and_rejects_bypass():
    task=extracted_context();text=extracted_proposal(task,extracted_source())['plan_text']
    value=mock_order.read_existing(task,text,'success','订单查询模拟')
    assert value['input_selector']==['extract','order_no']
    graph=parse(text);next(e for e in graph['edges'] if e['source']=='extract')['target']='success'
    with pytest.raises(ValueError):mock_order.read_existing(task,render(graph),'success','订单查询模拟')


@pytest.mark.parametrize('change',['business','comment','outputs','binding','language'])
def test_manual_code_or_declaration_changes_are_not_assumed_to_be_the_original(change):
    task=context();graph=parse(proposal(task)['plan_text']);cfg=graph['nodes'][1]['config']
    if change=='business':cfg['code']=cfg['code'].replace('key = order_id.strip()','key = order_id.lower().strip()')
    if change=='comment':cfg['code']+='\n# 用户保留的备注\n'
    if change=='outputs':cfg['outputs'].pop('status')
    if change=='binding':cfg['variables'][0]['variable']='custom_order'
    if change=='language':cfg['code_language']='javascript'
    original=copy.deepcopy(graph)
    with pytest.raises(ValueError):mock_order.read_existing(task,render(graph),'lookup','订单查询模拟')
    assert graph==original


@pytest.mark.parametrize('table',["{'A': 'one', 'A': 'two'}","{'A': str(123)}","dict(A='one')","{**{'A':'one'}}","{1:'one'}"])
def test_duplicate_keys_expressions_unpacking_and_non_text_literals_are_not_evaluated(table):
    task=context();graph=parse(proposal(task)['plan_text']);cfg=graph['nodes'][1]['config']
    original=cfg['code'];line=next(s for s in original.splitlines() if s.startswith('    orders = '))
    cfg['code']=original.replace(line,'    orders = '+table)
    with pytest.raises(ValueError):mock_order.read_existing(task,render(graph),'lookup','订单查询模拟')


def test_no_python_is_executed_and_large_source_is_bounded(tmp_path):
    task=context();graph=parse(proposal(task)['plan_text']);sentinel=tmp_path/'must-not-exist.txt';cfg=graph['nodes'][1]['config']
    cfg['code']+=f"\nopen({str(sentinel)!r},'w').write('executed')\n"
    with pytest.raises(ValueError):mock_order.read_existing(task,render(graph),'lookup','订单查询模拟')
    assert not sentinel.exists()
    cfg['code']=' '*64001
    with pytest.raises(ValueError):mock_order.read_existing(task,render(graph),'lookup','订单查询模拟')


def test_literal_unicode_escapes_line_endings_and_boundaries_are_lossless():
    task=context();records={'DEMO-001':'😀'*500,'DEMO-002':'引号"与换行\n以及反斜线\\'}
    graph=parse(proposal(task,records=records)['plan_text']);graph['nodes'][1]['config']['code']=graph['nodes'][1]['config']['code'].replace('\n','\r\n')
    value=mock_order.read_existing(task,render(graph),'lookup','订单查询模拟')
    assert json.loads(value['records_text'])==records


def test_missing_dependency_foreign_binding_and_wrong_node_are_refused():
    task=context();text=proposal(task)['plan_text']
    with pytest.raises(ValueError):mock_order.read_existing(task,text,'finish','订单查询模拟')
    with pytest.raises(ValueError):mock_order.read_existing(task,text,'lookup','未声明依赖')
    task['configuration']['mock_dependency_bindings']=[{'dependency':'订单查询模拟','node_id':'other','replacement_todo':'真实接入'}]
    with pytest.raises(ValueError):mock_order.read_existing(task,text,'lookup','订单查询模拟')


def saved_after_sales(client):
    task=blank_after_sales(client);text,_=starter(task,starter_inputs())
    response=client.post('/api/tasks/'+task['id']+'/plan',json={'revision':task['revision'],'plan_text':text})
    assert response.status_code==200,response.text
    from test_after_sales_starter import review_saved_state
    review_saved_state(client,response.json())
    return main.get_task(task['id'])


def payload(task):return {'revision':task['revision'],'plan_text':render(task['workflow_plan']),'node_id':'order_lookup','dependency':'订单查询模拟','request_nonce':str(uuid4())}


def test_actual_read_route_is_readonly_no_decrypt_and_returns_bound_source(client,monkeypatch):
    task=saved_after_sales(client);before=copy.deepcopy(task);budget=main.store.get('task_budget',task['id']);body=payload(task)
    def forbid(*args,**kwargs):pytest.fail('Reading existing template must not write or decrypt')
    monkeypatch.setattr(main.store,'put',forbid);monkeypatch.setattr(main.store,'secret',forbid)
    response=client.post('/api/tasks/'+task['id']+'/mock-order-template/read',json=body)
    assert response.status_code==200,response.text
    value=response.json();assert value['request_nonce']==body['request_nonce'] and value['revision']==task['revision']
    assert value['input_selector']==['extract_order','order_no'] and json.loads(value['records_text'])=={'DEMO-001':'合成样例：已发货。'}
    assert main.get_task(task['id'])==before and main.store.get('task_budget',task['id'])==budget


def test_read_rechecks_revision_after_background_parsing(client,monkeypatch):
    task=saved_after_sales(client);original=mock_order.read_existing
    def changed(*args):
        value=original(*args);current=main.get_task(task['id']);current['revision']+=1;main.store.put('task',task['id'],current);return value
    monkeypatch.setattr(mock_order,'read_existing',changed)
    response=client.post('/api/tasks/'+task['id']+'/mock-order-template/read',json=payload(task))
    assert response.status_code==409 and main.get_task(task['id'])['revision']==task['revision']+1


def test_api_rejects_stale_duplicate_keys_and_credentials_without_echo(client):
    task=saved_after_sales(client);body=payload(task);path='/api/tasks/'+task['id']+'/mock-order-template/read'
    assert client.post(path,json={**body,'revision':task['revision']+1}).status_code==409
    assert client.post(path,json={**body,'revision':True}).status_code==422
    raw=json.dumps(body)[:-1]+',"node_id":"order_lookup"}'
    assert client.post(path,content=raw,headers={'Content-Type':'application/json'}).status_code==422
    graph=parse(body['plan_text']);next(n for n in graph['nodes'] if n['id']=='order_lookup')['config']['code']+='\n# app-SYNTHETICPRIVATEVALUE12345\n'
    response=client.post(path,json={**body,'plan_text':render(graph)})
    assert response.status_code==422 and 'SYNTHETICPRIVATEVALUE' not in response.text and main.get_task(task['id'])==task
