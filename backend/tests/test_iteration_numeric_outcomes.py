"""Execute only fixed developer computations; no customer code or Dify."""
import copy,json
import pytest,yaml
from test_iteration import batch_plan,iteration,task
from test_api import client,approved
from app import main
from app.iteration_outcomes import candidate,wrapped
from app.iteration_summary import candidate as summarize,summary_code,original_contract
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from uuid import uuid4

def numeric_plan():
    p=batch_plan();cfg=iteration(p);cfg['output_type']='array[number]'
    cfg['nodes'][0]['config']['outputs']['result']['type']='number'
    cfg['nodes'][0]['config']['code']='def main(item: str) -> dict:\n    return {"result": int(item)}\n'
    return p

def known(code):
    scope={};exec(wrapped(code,'number'),scope);return scope['main']

def outcome_plan():
    p=numeric_plan();return json.loads(candidate(task(p),p,'batch',True)['plan_text'])

def row(value,index=0):return {'index':index,'ok':True,'value':value,'error_category':None}

def test_numeric_candidate_keeps_calculation_graph_and_type_without_conversion():
    p=numeric_plan();before=copy.deepcopy(p);r=candidate(task(p),p,'batch',True);out=json.loads(r['plan_text'])
    assert p==before and r['value_type']=='number'
    assert out['edges']==p['edges'] and out['nodes'][:2]==p['nodes'][:2] and out['nodes'][-1]==p['nodes'][-1]
    cfg=iteration(out);assert cfg['output_type']=='array[object]' and cfg['error_handle_mode']=='terminated'
    original,kind=original_contract(cfg['nodes'][0]['config']['code'])
    assert original==iteration(p)['nodes'][0]['config']['code'] and kind=='number'
    native,checked=compile_workflow_plan(task(out));assert checked['valid'],checked
    assert validate_preserved(yaml.safe_load(native))['valid']

@pytest.mark.parametrize('value',[0,1,-1,9007199254740991,-9007199254740991,0.0,-0.0,1.25,-3.5])
def test_finite_safe_values_keep_numeric_type(value):
    fn=known('def main(item: str) -> dict:\n    return {"result": '+repr(value)+'}\n')
    result=fn('developer fixture',2)
    assert result['outcome']==row(value,2)
    assert type(result['outcome']['value']) is type(value)

@pytest.mark.parametrize('expression',["float('nan')","float('inf')","-float('inf')",'9007199254740992','-9007199254740992','True','False','"12"','None','{}'])
def test_bad_numeric_contract_stops_instead_of_becoming_business_failure(expression):
    fn=known('def main(item: str) -> dict:\n    return {"result": '+expression+'}\n')
    with pytest.raises(TypeError,match='numeric output'):fn('developer fixture',0)

def test_calculation_exception_is_recorded_but_unknown_or_input_error_still_stops():
    fn=known('def main(item: str) -> dict:\n    return {"result": int(item)}\n')
    assert fn('not an integer',4)['outcome']=={'index':4,'ok':False,'value':None,'error_category':'ValueError'}
    with pytest.raises(TypeError):fn(10,0)
    with pytest.raises(TypeError):fn('10',False)
    fn=known('def main(item: str) -> dict:\n    assert item == "valid"\n    return {"result": 1}\n')
    with pytest.raises(AssertionError):fn('invalid',0)

def test_numeric_summary_preserves_number_types_failures_order_and_empty_input():
    scope={};exec(summary_code('number'),scope);fn=scope['main']
    rows=[row(1),{'index':1,'ok':False,'value':None,'error_category':'ValueError'},row(-2.5,2),row(1,3)]
    result=fn(rows,['1','bad','-2.5','1'])
    assert result['items']==rows and result['successes']==[rows[0],rows[2],rows[3]]
    assert result['failures']==[rows[1]] and result['total']==4 and result['failed']==1
    assert type(result['successes'][0]['value']) is int and type(result['successes'][1]['value']) is float
    assert fn([],[])=={'items':[],'successes':[],'failures':[],'total':0,'succeeded':0,'failed':0}

@pytest.mark.parametrize('value',[True,'1',None,float('nan'),float('inf'),9007199254740992])
def test_summary_does_not_accept_weaker_numeric_contract_or_partial_success(value):
    scope={};exec(summary_code('number'),scope)
    with pytest.raises(TypeError):scope['main']([row(1),row(value,1)],['1','2'])

def test_summary_plan_reconstructs_original_numeric_contract_and_native_preservation():
    p=outcome_plan();before=copy.deepcopy(p);r=summarize(task(p),p,'batch',True);out=json.loads(r['plan_text'])
    assert p==before and r['value_type']=='number'
    assert out['nodes'][2]==p['nodes'][2]
    code=next(n for n in out['nodes'] if n['id']==r['summary_node_id'])['config']['code']
    assert code==summary_code('number') and 'row[\'value\']' in code
    native,checked=compile_workflow_plan(task(out));assert checked['valid'],checked
    assert validate_preserved(yaml.safe_load(native))['valid']

def test_hand_modified_numeric_guard_and_declared_type_are_not_guessed_or_repaired():
    p=outcome_plan();iteration(p)['nodes'][0]['config']['code']=iteration(p)['nodes'][0]['config']['code'].replace('9007199254740991','9007199254740992')
    with pytest.raises(ValueError):summarize(task(p),p,'batch',True)
    p=numeric_plan();iteration(p)['output_type']='array[string]'
    with pytest.raises(ValueError):candidate(task(p),p,'batch',True)

def test_string_wrapper_and_summary_remain_original_canonical_bytes():
    import hashlib
    code='def main(item: str) -> dict:\n    return {"result": item.strip()}\n'
    # Frozen v0.188 canonical string protocol; widening numeric support must not rewrite it.
    assert hashlib.sha256(wrapped(code).encode()).hexdigest()=="a35a7926ff20470218ac22d5adae67b3f2dacb2f6a0d2791faf4b2b6ca6725a2"
    p=batch_plan();r=candidate(task(p),p,'batch',True);assert r['value_type']=='string'

def test_numeric_previews_are_stateless_and_do_not_dispatch_code_or_resources(client,monkeypatch):
    t=approved(client);p=numeric_plan();before=copy.deepcopy(main.store.get('task',t['id']))
    def forbidden(*args,**kwargs):raise AssertionError('No real model or Dify call permitted')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main,'DifyClient',forbidden)
    payload={'revision':t['revision'],'plan_text':json.dumps(p),'node_id':'batch','acknowledge_result_contract':True,'request_nonce':str(uuid4())}
    response=client.post(f"/api/tasks/{t['id']}/iteration-outcomes",json=payload)
    assert response.status_code==200,response.text
    result=response.json();assert result['value_type']=='number'
    payload={'revision':t['revision'],'plan_text':result['plan_text'],'node_id':'batch','acknowledge_summary_outputs':True,'request_nonce':str(uuid4())}
    response=client.post(f"/api/tasks/{t['id']}/iteration-summary",json=payload)
    assert response.status_code==200,response.text
    assert response.json()['value_type']=='number' and main.store.get('task',t['id'])==before
