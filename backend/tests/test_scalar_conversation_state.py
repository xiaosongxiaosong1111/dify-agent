import copy,math
import pytest,yaml
from test_api import client
from test_conversation_state import plan,task
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest


def scalar_plan(kind='number',value=0):
    p=plan();p['conversation_variables'][0].update(var_type=kind,initial_value=value)
    p['nodes'][1]['config']['items'][0].update(input_type='constant',value=value)
    return p


@pytest.mark.parametrize('same_target', [False, True])
def test_single_writer_is_per_variable_across_serial_root_assigners(same_target):
    # Public contract illustration: independent state targets may share a path.
    p = scalar_plan('boolean', False)
    p['conversation_variables'][0]['name'] = 'flag_a'
    p['conversation_variables'].append({**p['conversation_variables'][0], 'name': 'flag_b'})
    first = p['nodes'][1]
    first['config']['items'][0]['variable_selector'] = ['conversation', 'flag_a']
    second = copy.deepcopy(first)
    second['id'] = 'write_b'
    second['config']['items'][0].update(variable_selector=['conversation', 'flag_a' if same_target else 'flag_b'], value=True)
    p['nodes'].insert(2, second)
    p['nodes'][-1]['config']['answer'] = '状态：{{#conversation.flag_a#}} / {{#conversation.flag_b#}}'
    p['edges'] = [{'source': a, 'target': b} for a, b in [('start', 'remember'), ('remember', 'write_b'), ('write_b', 'answer')]]
    before = copy.deepcopy(p)
    text, checked = compile_workflow_plan(task(p))
    assert checked['valid'] is not same_target, checked
    assert p == before
    if same_target:
        assert any('多个' in error and '写入' in error for error in checked['errors']), checked
    else:
        native = yaml.safe_load(text)
        assert validate_preserved(native)['valid']
        writers = [n['data']['items'][0]['variable_selector'] for n in native['workflow']['graph']['nodes'] if n['data']['type'] == 'assigner']
        assert writers == [['conversation', 'flag_a'], ['conversation', 'flag_b']]


@pytest.mark.parametrize('kind,value,native_type',[('number',0,'float'),('number',1.5,'float'),('number',-2,'float'),('boolean',False,'boolean'),('boolean',True,'boolean')])
def test_declared_scalar_type_and_false_zero_survive_native_and_manual_preservation(kind,value,native_type):
    p=scalar_plan(kind,value);text,checked=compile_workflow_plan(task(p));assert checked['valid'],checked
    root=yaml.safe_load(text);variable=root['workflow']['conversation_variables'][0]
    assert variable['value_type']==native_type and variable['value']==value
    if kind=='number':assert type(variable['value'])is float
    else:assert type(variable['value'])is bool
    stamp=digest(root);checked=validate_preserved(root);assert checked['valid'],checked
    assert digest(root)==stamp


@pytest.mark.parametrize('kind,value',[('number',True),('number','0'),('number',None),('number',float('nan')),('number',float('inf')),('number',10**13),('boolean',0),('boolean',1),('boolean','false'),('boolean',None)])
def test_scalar_constants_do_not_coerce_strings_truthiness_or_nonfinite_values(kind,value):
    p=scalar_plan(kind,value);checked=validate_plan(task(p),p);assert not checked['valid']


@pytest.mark.parametrize('kind,source_type',[('number','boolean'),('boolean','number'),('number','string'),('boolean','string')])
def test_variable_assignment_source_type_must_match_target(kind,source_type):
    value=False if kind=='boolean' else 0;p=scalar_plan(kind,value);source={'id':'typed-source','type':'code','config':{'code_language':'python3','code':'def main():\n    return {"value": 1}','variables':[],'outputs':{'value':{'type':source_type}}}}
    p['nodes'].insert(1,source);p['edges']=[{'source':'start','target':'typed-source'},{'source':'typed-source','target':'remember'},{'source':'remember','target':'answer'}];p['nodes'][2]['config']['items'][0].update(input_type='variable',value=['typed-source','value'])
    checked=validate_plan(task(p),p);assert not checked['valid'] and any('标量类型' in e for e in checked['errors'])
    source['config']['outputs']['value']['type']=kind;assert validate_plan(task(p),p)['valid']


def test_integer_native_is_not_silently_changed_to_float_and_old_scope12_is_blocked(client):
    from test_assistant_routing import setup,enable,state
    from app import main
    text,checked=compile_workflow_plan(task(scalar_plan()));assert checked['valid'];root=yaml.safe_load(text);root['workflow']['conversation_variables'][0].update(value_type='integer',value=0);stamp=digest(root)
    checked=validate_preserved(root);assert not checked['valid'] and digest(root)==stamp
    t,p,light=setup(client);assert enable(client,t,light).status_code==200;old=main.routing.get(t['id']);old['scope_version']=12;main.store.put('assistant_routing',t['id'],old)
    current=state(client,t);assert current['required_scope_version']==18 and current['blocker'] and '数值' in current['blocker']
    assert enable(client,t,light,scope_version=12).status_code==409
    assert enable(client,t,light,scope_version=18).status_code==200
