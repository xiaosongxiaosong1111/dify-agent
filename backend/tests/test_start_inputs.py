import copy
import pytest
import yaml
from test_api import client, approved, create_env
from test_workflow_plan import base_plan, task, plan_task
from app import main
from app.start_inputs import check_values, preflight
from app.workflow_plan import validate_plan, compile_workflow_plan
from app.declared_types import resolve
from app.iteration import output_type
from app.dsl_roundtrip import validate_preserved


def plan():
    value=base_plan()
    value['nodes'][0]['config']['variables']=[
        {'variable':'amount','type':'number','required':True,'default':0,'description':'金额','hide':False},
        {'variable':'category','type':'select','required':False,'options':['售后','退款'],'default':'售后'},
    ]
    value['nodes'][1]['config']['user_prompt']='{{#start.amount#}} {{#start.category#}}'
    return value


def root():
    content,checked=compile_workflow_plan(plan_task(plan()))
    assert checked['valid'],checked
    return yaml.safe_load(content)


def test_numeric_select_compile_types_and_preserved_native_fields():
    value=plan();native=root();by_id={n['id']:n for n in value['nodes']}
    assert resolve(by_id,['start','amount'])==output_type(by_id,['start','amount'])=='number'
    assert resolve(by_id,['start','category'])==output_type(by_id,['start','category'])=='string'
    variables=native['workflow']['graph']['nodes'][0]['data']['variables']
    assert variables[0]['default']==0 and variables[0]['hide'] is False and variables[0]['description']=='金额'
    before=copy.deepcopy(native);assert validate_preserved(native)['valid'];assert native==before


@pytest.mark.parametrize('row',[
 {'variable':'x','type':'number','default':True},
 {'variable':'x','type':'number','default':'0'},
 {'variable':'x','type':'number','default':float('inf')},
 {'variable':'x','type':'number','required':False},
 {'variable':'x','type':'number','options':['one']},
 {'variable':'x','type':'number','minimum':0},
 {'variable':'x','type':'select','options':[]},
 {'variable':'x','type':'select','options':['a','a']},
 {'variable':'x','type':'select','options':['a','']},
 {'variable':'x','type':'select','options':['a'],'default':'b'},
 {'variable':'x','type':'select','options':['a'],'required':False},
 {'variable':'x','type':'number','required':'false'},
])
def test_bad_typed_declarations_rejected_without_coercion(row):
    value=plan();value['nodes'][0]['config']['variables'][0]=row
    before=copy.deepcopy(value);checked=validate_plan(task(),value)
    assert not checked['valid'] and value==before


@pytest.mark.parametrize('values',[{}, {'amount':None}, {'amount':False}, {'amount':'1'}, {'amount':float('nan')}, {'amount':1,'category':'unknown'}, {'amount':1,'extra':1}])
def test_preflight_refuses_wrong_values_without_mutation(values):
    # NaN equality is not used; invalid values must still remain uncoerced.
    with pytest.raises(ValueError):preflight(root(),values)


def test_defaults_omission_null_zero_and_raw_identity():
    value=root();rows=value['workflow']['graph']['nodes'][0]['data']['variables']
    for inputs in ({'amount':0},{'amount':-2.5,'category':None},{'amount':2,'category':'退款'}):
        before=copy.deepcopy(inputs);preflight(value,inputs);assert inputs==before
    rows[0].update(required=False,default=0);preflight(value,{})
    rows[0]['required']=True
    with pytest.raises(ValueError):check_values(rows,{})


def test_actual_native_select_changes_drive_checks_and_semantics():
    native=root();native['workflow']['graph']['nodes'][0]['data']['variables'][1].update(options=['查询'],default='查询')
    assert validate_preserved(native)['valid']
    preflight(native,{'amount':1,'category':'查询'})
    with pytest.raises(ValueError):preflight(native,{'amount':1,'category':'售后'})
    from app.case_dsl_semantics import summary
    assert summary(native)['nodes'][0]['config']['variables'][1]['options']==['查询']


def test_run_gate_reads_final_artifact_before_records_or_remote_calls(client,monkeypatch):
    env=create_env(client)
    client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'typed-app','service_api_key':'test-only'})
    saved=approved(client,env_id=env['id']);tid=saved['id']
    saved=client.post(f'/api/tasks/{tid}/build',json={'revision':saved['revision']}).json()
    # Fixture models an approved final artifact with a different entrance from the IR.
    main.artifact_path(saved).write_text(yaml.safe_dump(root(),allow_unicode=True),encoding='utf-8')
    saved['dify_app_id']='typed-app';main.save_task(saved);before=copy.deepcopy(main.get_task(tid));calls=[]
    async def remote(self,inputs):
        calls.append(copy.deepcopy(inputs));return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
    monkeypatch.setattr(main.DifyClient,'run_workflow',remote)
    for inputs in ({'amount':True},{'amount':'0'},{'amount':0,'category':'invalid'},{}):
        response=client.post(f'/api/tasks/{tid}/run',json={'revision':saved['revision'],'input':inputs})
        assert response.status_code==422,response.text
        assert main.get_task(tid)==before and calls==[]
    response=client.post(f'/api/tasks/{tid}/run',json={'revision':saved['revision'],'input':{'amount':0}})
    assert response.status_code==200,response.text
    assert calls==[{'amount':0}] and response.json()['runs'][-1]['input']=={'amount':0}


def test_case_contract_reports_precise_input_schema(client):
    saved=approved(client);saved['workflow_plan']=plan()
    contract=main.case_proposals.contract(saved)
    assert contract['inputs']['amount']['type']=='number'
    assert contract['inputs']['category']['type']=='string'
    assert contract['inputs']['category']['options']==['售后','退款']
    assert contract['inputs']['category']['default']=='售后'


@pytest.mark.parametrize('inputs,valid',[({'amount':0,'category':'退款'},True),({'amount':False},False),({'amount':'1'},False),({'amount':1,'category':'unknown'},False)])
def test_model_case_candidate_checks_typed_inputs(client,inputs,valid):
    from test_case_proposals import candidate
    saved=approved(client);saved['workflow_plan']=plan()
    value=candidate();value['items'][0]['case']['input']=inputs
    checked=main.case_proposals.validate(saved,value)
    assert checked['valid']==valid,checked


@pytest.mark.parametrize('kind', ['text-input', 'paragraph'])
@pytest.mark.parametrize('value', ['', '   ', '\t\r\n', '\u3000', None])
def test_required_text_rejects_blank_without_changing_values(kind, value):
    values = {'query': value}
    before = copy.deepcopy(values)
    with pytest.raises(ValueError, match='必填非空文本'):
        check_values([{'variable': 'query', 'type': kind, 'required': True}], values)
    assert values == before


@pytest.mark.parametrize('kind', ['text-input', 'paragraph'])
@pytest.mark.parametrize('value', ['', '  ', '  genuine question  '])
def test_optional_text_and_nonblank_original_spacing_are_preserved(kind, value):
    rows = [{'variable': 'query', 'type': kind, 'required': False}]
    values = {'query': value}
    check_values(rows, values)
    assert values == {'query': value}
    if value.strip():
        rows[0]['required'] = True
        check_values(rows, values)
        assert values == {'query': value}


@pytest.mark.parametrize('value', ['', '  ', '\t', None])
def test_workflow_text_only_runtime_refuses_blank_before_dispatch(client, monkeypatch, value):
    env = create_env(client)
    task = approved(client, env_id=env['id'])
    workflow = base_plan()
    workflow['nodes'][0]['config']['variables'] = [
        {'variable': 'query', 'type': 'paragraph', 'required': True}]
    task['workflow_plan'] = workflow
    main.save_task(task)
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    saved = response.json()
    saved['dify_app_id'] = 'bound-test-app'
    main.save_task(saved)
    connection = main.store.get('environment', env['id'])
    connection['service_app_id'] = 'bound-test-app'
    main.store.put('environment', env['id'], connection)
    calls = []
    async def run(*args, **kwargs):
        calls.append(True)
        return {'data': {'status': 'succeeded', 'outputs': {'result': 'unexpected'}}}
    monkeypatch.setattr(main.DifyClient, 'run_workflow', run)
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.post(f"/api/tasks/{task['id']}/run", json={
        'revision': saved['revision'], 'input': {'query': value}})
    assert response.status_code == 422, response.text
    assert '必填非空文本' in response.json()['detail']
    assert calls == [] and main.get_task(task['id']) == before
