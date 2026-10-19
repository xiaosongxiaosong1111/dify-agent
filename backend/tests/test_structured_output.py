import copy
import pytest
import yaml
from test_api import client
from test_workflow_plan import base_plan, task
from app.structured_output import validate, native, schema_errors, output_type
from app.workflow_plan import compile_workflow_plan, validate_plan
from app.dsl import validate_dsl
from app.dsl_roundtrip import validate_preserved
from app.declared_types import resolve
from app.iteration import output_type as iteration_type


def schema():
    return {'type':'object','properties':{
        'label':{'type':'string','enum':['售后','其它'],'maxLength':20},
        'scores':{'type':'array','items':{'type':'number','minimum':0,'maximum':1},'maxItems':3},
        'approved':{'type':'boolean'},
    },'required':['label'],'additionalProperties':False}


def settings():return {'structured_output_enabled':True,'structured_output':{'schema':schema()}}


def configured():
    t=task();t['workflow_plan']=base_plan();t['workflow_plan']['nodes'][1]['config'].update(settings())
    t['workflow_plan']['nodes'][-1]['config']['outputs'][0]['value_selector']=['llm','structured_output']
    return t


def root():
    text,checked=compile_workflow_plan(configured());assert checked['valid'],checked
    return yaml.safe_load(text)


def test_compile_explicit_native_schema_and_object_types_do_not_mutate_or_claim_runtime():
    t=configured();before=copy.deepcopy(t);text,checked=compile_workflow_plan(t)
    assert checked['valid'] and t==before and any('修复JSON' in v for v in checked['warnings'])
    node=next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='llm')
    assert node['structured_output_enabled'] is True and node['structured_output']=={'schema':schema()}
    nodes={n['id']:n for n in t['workflow_plan']['nodes']}
    assert resolve(nodes,['llm','structured_output'])==iteration_type(nodes,['llm','structured_output'])=='object'
    assert resolve(nodes,['llm','text'])=='string'
    assert resolve(nodes,['llm','structured_output','label']) is None
    assert validate_dsl(text)['valid'] and validate_preserved(yaml.safe_load(text))['valid']


@pytest.mark.parametrize('change',[
    lambda s:s.update(type='array'),
    lambda s:s.pop('additionalProperties'),
    lambda s:s.update(additionalProperties=True),
    lambda s:s.update(required=['missing']),
    lambda s:s.update(required=['label','label']),
    lambda s:s.update(**{'$ref':'https://example.com/schema'}),
    lambda s:s.update(anyOf=[{'type':'object'}]),
    lambda s:s['properties']['label'].update(pattern='.*'),
    lambda s:s['properties']['label'].update(default='售后'),
    lambda s:s['properties']['label'].update(enum=['售后',1]),
    lambda s:s['properties']['label'].update(minLength=30,maxLength=20),
    lambda s:s['properties']['scores'].update(items=None),
    lambda s:s['properties']['scores']['items'].update(minimum=True),
    lambda s:s['properties']['approved'].update(type=['boolean','null']),
])
def test_unsupported_or_inconsistent_schema_rejected_without_stripping(change):
    value=settings();change(value['structured_output']['schema']);before=copy.deepcopy(value)
    assert validate(value) and value==before
    with pytest.raises(ValueError):native(value)


@pytest.mark.parametrize('value',[
    {'structured_output_enabled':'true','structured_output':{'schema':schema()}},
    {'structured_output':{'schema':schema()}},
    {'structured_output_enabled':True,'structured_output':'{unfinished'},
    {'structured_output_enabled':True,'structured_output':{'schema':schema(),'unknown':1}},
    {'structured_output_enabled':True},
])
def test_switch_and_raw_json_never_coerced_or_implicitly_enabled(value):
    assert validate(value) and output_type(value) is None


def test_disabled_schema_kept_but_unavailable_source_rejected_in_ir_and_native():
    value=settings();value['structured_output_enabled']=False;before=copy.deepcopy(value)
    assert not validate(value) and native(value)==before and output_type(value) is None
    assert native({'structured_output_enabled':False,'structured_output':{'schema':{}}})=={'structured_output_enabled':False,'structured_output':{'schema':{}}}
    t=configured();t['workflow_plan']['nodes'][1]['config'].update(value)
    assert not validate_plan(t,t['workflow_plan'])['valid']
    original=root();next(n['data'] for n in original['workflow']['graph']['nodes'] if n['id']=='llm')['structured_output_enabled']=False
    assert not validate_preserved(original)['valid']
    assert not validate_dsl(yaml.safe_dump(original,allow_unicode=True))['valid']


def test_preserved_manual_schema_in_final_semantics_not_old_ir_or_silently_omitted():
    from app.case_dsl_semantics import summary
    original=root();data=next(n['data'] for n in original['workflow']['graph']['nodes'] if n['id']=='llm')
    data['structured_output']['schema']['properties']['label']['enum']=['新客户规则'];before=copy.deepcopy(original)
    assert validate_preserved(original)['valid'] and original==before
    result=summary(original);row=next(n for n in result['nodes'] if n['id']=='llm')
    assert row['config']['structured_output']==data['structured_output']
    assert not any('structured_output' in row['fields'] for row in result['omitted_node_fields'])
    data['structured_output']['schema']['required']=['not-declared']
    assert not validate_preserved(original)['valid']


def test_array_of_objects_iteration_uses_enabled_body_output_and_preserves_it():
    from test_iteration import batch_plan,task as batch_task,iteration
    p=batch_plan();cfg=iteration(p);cfg.update(output_selector=['extract','structured_output'],output_type='array[object]')
    cfg['nodes']=[{'id':'extract','type':'llm','config':{'user_prompt':'{{#batch.item#}}',**settings()}}]
    text,checked=compile_workflow_plan(batch_task(p,dify_model_provider='test/provider',dify_model='test-model'))
    assert checked['valid'],checked
    result=yaml.safe_load(text);assert validate_preserved(result)['valid']
    cfg['nodes'][0]['config']['structured_output_enabled']=False
    assert not validate_plan(batch_task(p),p)['valid']


def test_schema_bounds_numeric_enum_duplicates_and_nonfinite_values():
    value=schema();value['description']='x'*64000;assert schema_errors(value)
    value=schema();value['properties']={f'field{i}':{'type':'string'} for i in range(51)};assert schema_errors(value)
    value=schema();value['properties']['scores']['items']['enum']=[1,1.0];assert schema_errors(value)
    value=schema();value['properties']['scores']['items']['maximum']=float('inf');assert schema_errors(value)
    value=schema();value['properties']['cycle']=value;assert schema_errors(value)
    value=schema();child=value
    for _ in range(10):child['properties']={'next':{'type':'object','properties':{},'additionalProperties':False}};child=child['properties']['next']
    assert schema_errors(value)


def test_old_scope_16_cannot_send_new_final_schema_without_confirmation(client,monkeypatch):
    from test_assistant_routing import setup,enable,state
    from app import main
    t,_,light=setup(client);assert enable(client,t,light).status_code==200
    saved=main.routing.get(t['id']);saved['scope_version']=16;main.store.put('assistant_routing',t['id'],saved)
    def forbidden(*args,**kwargs):pytest.fail('旧范围不能调用模型')
    monkeypatch.setattr(main,'call_model',forbidden)
    current=state(client,t)
    assert current['required_scope_version']==18 and '完整JSON Schema' in current['scope_note'] and current['blocker']
    assert enable(client,t,light,scope_version=16).status_code==409
    assert main.routing.get(t['id'])['scope_version']==16
