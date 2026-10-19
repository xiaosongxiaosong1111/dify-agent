"""Only known, isolated pure-code fixtures are executed; never user code or Dify."""
import copy
import json
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from test_iteration import batch_plan, task, iteration
from app.iteration_outcomes import candidate, wrapped, ERRORS
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app import main
from app.storage import Store


def proposal(plan=None):
    plan = plan or batch_plan()
    return candidate(task(plan), plan, 'batch', True)


def run_known_fixture(code):
    scope = {}
    exec(wrapped(code), scope)
    return scope['main']


def test_candidate_preserves_original_graph_and_native_contract():
    plan = batch_plan()
    before = copy.deepcopy(plan)
    value = proposal(plan)
    after = json.loads(value['plan_text'])
    assert plan == before
    assert after['edges'] == before['edges']
    assert [n['id'] for n in after['nodes']] == [n['id'] for n in before['nodes']]
    assert after['nodes'][0:2] == before['nodes'][0:2]
    assert after['nodes'][-1] == before['nodes'][-1]
    parent = iteration(after)
    assert parent['error_handle_mode'] == 'terminated' and parent['flatten_output'] is False
    assert parent['output_type'] == 'array[object]' and parent['output_selector'] == ['clean', 'outcome']
    assert parent['nodes'][0]['config']['variables'][-1] == {'variable':'sierra_index','value_selector':['batch','index']}
    native, checked = compile_workflow_plan(task(after))
    assert checked['valid'], checked['errors']
    root = yaml.safe_load(native)
    assert validate_preserved(root)['valid']
    nodes = {n['id']:n for n in root['workflow']['graph']['nodes']}
    assert nodes['batch']['data']['output_type'] == 'array[object]'
    assert nodes['clean']['data']['outputs'] == {'outcome':{'type':'object','children':None}}
    assert value['platform_checked'] is value['business_verified'] is value['task_changed'] is value['network_requested'] is False


def test_parallel_metadata_and_exact_original_body_are_retained():
    plan = batch_plan()
    iteration(plan).update(is_parallel=True,parallel_nums=3,parallel_safe=True,parallel_reason='Each known fixture computes independently without external requests.')
    code = '# comment\ndef main(item: str) -> dict:\n    # exact spacing retained\n    return {"result": item.strip().upper()}\n'
    iteration(plan)['nodes'][0]['config']['code'] = code
    after = json.loads(proposal(plan)['plan_text'])
    assert iteration(after)['parallel_reason'] == iteration(plan)['parallel_reason']
    assert iteration(after)['parallel_nums'] == 3 and iteration(after)['parallel_safe'] is True
    assert code.replace('def main(', 'def _sierra_calculate(', 1) in iteration(after)['nodes'][0]['config']['code']


def test_success_failure_duplicate_and_empty_values_keep_original_index():
    fn = run_known_fixture('def main(item: str) -> dict:\n    if item == "bad":\n        raise ValueError("private fixture message")\n    return {"result": item.strip().upper()}\n')
    rows = [fn(v,i)['outcome'] for i,v in enumerate([' a ','bad',' a ',''])]
    assert rows == [
        {'index':0,'ok':True,'value':'A','error_category':None},
        {'index':1,'ok':False,'value':None,'error_category':'ValueError'},
        {'index':2,'ok':True,'value':'A','error_category':None},
        {'index':3,'ok':True,'value':'','error_category':None}]
    assert 'private fixture message' not in json.dumps(rows)


@pytest.mark.parametrize('error', ERRORS)
def test_each_declared_error_returns_category_only(error):
    fn = run_known_fixture(f'def main(item: str) -> dict:\n    raise {error}("private")\n    return {{"result": item}}\n')
    assert fn('x',7)['outcome'] == {'index':7,'ok':False,'value':None,'error_category':error}


@pytest.mark.parametrize('value,index', [('x',True),('x',-1),('x',1.0),(None,0)])
def test_bad_input_contract_is_not_converted_to_recoverable_item(value,index):
    fn = run_known_fixture('def main(item: str) -> dict:\n    return {"result": item}\n')
    with pytest.raises(TypeError): fn(value,index)


def test_bad_output_contract_still_terminates():
    fn = run_known_fixture('def main(item: str) -> dict:\n    return {"result": 42}\n')
    with pytest.raises(TypeError): fn('x',0)


def test_unexpected_fault_is_not_relabelled_as_calculation_failure():
    fn = run_known_fixture('def main(item: str) -> dict:\n    assert len(item) > 2\n    return {"result": item}\n')
    with pytest.raises(AssertionError): fn('x',0)


@pytest.mark.parametrize('code', [
    'import os\ndef main(item):\n return {"result": item}\n',
    'def main(item):\n return {"result": open(item).read()}\n',
    'def main(item):\n return {"result": eval(item)}\n',
    'def main(item):\n return {"result": item.__class__}\n',
    'def main(item):\n return {"result": item, "extra": item}\n',
    'def main(item):\n return dict(result=item)\n',
    'def main(item):\n def helper():\n  return {"result": item}\n return {"result": item}\n',
    'def main(item):\n return {"result": main(item)}\n',
    'def main(item):\n return {"result": (lambda: item)()}\n',
    'def main(item, default="x"):\n return {"result": item}\n',
    'def main(item):\n return {"result": _sierra_hidden}\n',
    'def main(item):\n return {"result": item.lower}\n',
])
def test_unsupported_code_is_explicitly_rejected(code):
    # A reference to an allowed method is still pure syntax, so the final fixture
    # is accepted statically but its non-string return must fail at execution.
    if code.endswith('item.lower}\n'):
        with pytest.raises(TypeError): run_known_fixture(code)('x',0)
    else:
        plan=batch_plan(); iteration(plan)['nodes'][0]['config']['code']=code
        with pytest.raises(ValueError): proposal(plan)


@pytest.mark.parametrize('ack', [False,None,1,'true'])
def test_explicit_ack_is_required(ack):
    p=batch_plan()
    with pytest.raises(ValueError): candidate(task(p),p,'batch',ack)


def test_no_rewrap_or_other_app_or_target():
    p=batch_plan()
    for typ in ('advanced-chat','agent'):
        with pytest.raises(ValueError):candidate({**task(p),'app_type':typ},p,'batch',True)
    with pytest.raises(ValueError):candidate(task(p),p,'missing',True)
    after=json.loads(proposal(p)['plan_text'])
    with pytest.raises(ValueError):proposal(after)


def test_extra_nodes_and_extra_end_consumers_are_not_deleted():
    p=batch_plan(); p['nodes'][-1]['config']['outputs'].append({'variable':'original','value_selector':['start','items_json']})
    before=copy.deepcopy(p)
    with pytest.raises(ValueError):proposal(p)
    assert p==before


def test_parser_cannot_hide_nested_import():
    p=batch_plan()
    p['nodes'][1]['config']['code']='def main(items_json: str) -> dict:\n    import os\n    return {"items": []}\n'
    with pytest.raises(ValueError):proposal(p)


def test_no_fallback_for_invalid_schema_or_nested_body():
    p=batch_plan();p['schema_version']=99
    with pytest.raises(ValueError):proposal(p)
    p=batch_plan();iteration(p)['nodes'].append(copy.deepcopy(iteration(p)['nodes'][0]))
    with pytest.raises(ValueError):proposal(p)


def test_full_large_integer_in_unaffected_code_is_not_rounded():
    p=batch_plan();p['nodes'][1]['config']['code']=p['nodes'][1]['config']['code'].replace('items = json.loads', 'limit = 900719925474099312345678901\n    items = json.loads')
    value=proposal(p)
    assert '900719925474099312345678901' in value['plan_text']
    assert json.loads(value['plan_text'])['nodes'][1]==p['nodes'][1]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(main,'store',Store(tmp_path))
    monkeypatch.setattr(main,'DATA_ROOT',tmp_path)
    with TestClient(main.app) as client:
        created=client.post('/api/tasks',json={'name':'隔离逐项结果草稿','app_type':'workflow'}).json()
        yield client,created


def payload(task):
    return {'revision':task['revision'],'plan_text':json.dumps(batch_plan()),'node_id':'batch','acknowledge_result_contract':True,'request_nonce':str(uuid4())}


def test_preview_api_never_mutates_task_or_draft(api):
    client,t=api;url=f"/api/tasks/{t['id']}"
    before=client.get(url).json();draft=client.get(url+'/plan-draft').json()
    p=payload(t);res=client.post(url+'/iteration-outcomes',json=p)
    assert res.status_code==200,res.text
    value=res.json()
    assert value['task_id']==t['id'] and value['revision']==t['revision'] and value['request_nonce']==p['request_nonce']
    assert client.get(url).json()==before and client.get(url+'/plan-draft').json()==draft


@pytest.mark.parametrize('field,value,status', [('revision',0,422),('revision',True,422),('revision',999,409),('acknowledge_result_contract',False,422),('acknowledge_result_contract',1,422),('plan_text','{"nodes":[],"nodes":[]}',422),('plan_text','{"x":NaN}',422),('node_id','missing',422),('request_nonce','private-not-uuid',422),('unknown','private',422)])
def test_api_rejects_stale_or_invalid_requests_without_echo(api,field,value,status):
    client,t=api;p=payload(t);p[field]=value
    res=client.post(f"/api/tasks/{t['id']}/iteration-outcomes",json=p)
    assert res.status_code==status,res.text
    assert 'private' not in res.text
