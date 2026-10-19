import copy
import pytest,yaml
from test_api import client
from test_scalar_conversation_state import scalar_plan
from test_conversation_state import task
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest


def arithmetic(operation='+=',value=1):
    p=scalar_plan('number',0)
    p['nodes'][1]['config']['items'][0].update(operation=operation,value=value)
    return p


@pytest.mark.parametrize('operation,value',[('+=',1),('-=',-2),('*=',0),('/=',.5),('+=',10**12),('/=',-3)])
def test_numeric_constant_operation_survives_compile_preservation_and_semantic_summary(operation,value):
    from app.case_dsl_semantics import summary
    p=arithmetic(operation,value);before=copy.deepcopy(p)
    text,result=compile_workflow_plan(task(p));assert result['valid'],result
    root=yaml.safe_load(text);node=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='remember')
    assert node['data']['version']=='2' and node['data']['items']==p['nodes'][1]['config']['items']
    root['workflow']['conversation_variables'][0]['description']='手改计数说明';node['position']['x']+=13
    stamp=digest(root);checked=validate_preserved(root);assert checked['valid'],checked
    assert digest(root)==stamp and p==before
    assert next(n for n in summary(root)['nodes'] if n['id']=='remember')['config']['items'][0]['operation']==operation


@pytest.mark.parametrize('operation,value',[('/=',0),('/=',-0.0),('+=',True),('-=',False),('*=','2'),('/=',None),('+=',float('inf')),('+=',float('nan')),('+=',10**13),('+=',[]),('set',1),('**=',2),([],1)])
def test_bad_numeric_operation_never_coerces_or_drops_ir(operation,value):
    p=arithmetic(operation,value);checked=validate_plan(task(p),p)
    assert not checked['valid'] and p['nodes'][1]['config']['items'][0]['operation']==operation


@pytest.mark.parametrize('kind,value',[('boolean',False),('string','2')])
def test_arithmetic_requires_numeric_target(kind,value):
    p=scalar_plan(kind,value);p['nodes'][1]['config']['items'][0].update(operation='+=',value=1)
    checked=validate_plan(task(p),p);assert not checked['valid'] and any('number状态' in e for e in checked['errors'])


@pytest.mark.parametrize('operation',['+=','-=','*=','/='])
def test_native_numeric_variable_arithmetic_not_supported_even_when_selector_is_typed(operation):
    p=arithmetic(operation);p['conversation_variables'].append({**p['conversation_variables'][0],'name':'source'})
    p['nodes'][1]['config']['items'][0].update(input_type='variable',value=['conversation','source'])
    checked=validate_plan(task(p),p);assert not checked['valid'] and any('只支持明确数值常量' in e for e in checked['errors'])


def test_arithmetic_does_not_claim_runtime_result_range_or_change_initial_value():
    p=arithmetic('*=',10**12);p['conversation_variables'][0]['initial_value']=10**12
    text,result=compile_workflow_plan(task(p));assert result['valid'],result
    root=yaml.safe_load(text);assert root['workflow']['conversation_variables'][0]['value']==10**12
    assert next(n for n in root['workflow']['graph']['nodes'] if n['id']=='remember')['data']['items'][0]['value']==10**12


def test_arithmetic_retains_single_writer_and_no_implicit_parallel_guards():
    p=arithmetic();other=copy.deepcopy(p['nodes'][1]);other['id']='again';p['nodes'].insert(2,other)
    p['edges']=[{'source':'start','target':'remember'},{'source':'remember','target':'again'},{'source':'again','target':'answer'}]
    checked=validate_plan(task(p),p);assert not checked['valid'] and any('写节点' in e or '赋值节点' in e for e in checked['errors'])


def test_invalid_native_division_is_not_preserved_by_omitting_the_operation():
    root=yaml.safe_load(compile_workflow_plan(task(arithmetic('/=',2)))[0])
    next(n for n in root['workflow']['graph']['nodes'] if n['id']=='remember')['data']['items'][0]['value']=0
    stamp=digest(root);checked=validate_preserved(root)
    assert not checked['valid'] and digest(root)==stamp and any('不能为零' in e for e in checked['errors'])


def test_scope13_requires_new_arithmetic_scope_confirmation(client):
    from test_assistant_routing import setup,enable,state
    from app import main
    t,_,light=setup(client);assert enable(client,t,light).status_code==200
    old=main.routing.get(t['id']);old['scope_version']=13;main.store.put('assistant_routing',t['id'],old)
    current=state(client,t);assert current['required_scope_version']==18 and '加减乘除' in current['blocker']
    assert '加减乘除' in current['scope_note'] and enable(client,t,light,scope_version=13).status_code==409
    assert enable(client,t,light,scope_version=18).status_code==200
