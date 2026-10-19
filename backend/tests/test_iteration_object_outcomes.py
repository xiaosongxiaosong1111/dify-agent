"""Execute fixed developer fixtures only, never customer code or Dify."""
import copy
import hashlib
import json
from uuid import uuid4

import pytest
import yaml
from test_iteration import batch_plan, iteration, task
from test_api import client, approved
from app import main
from app.iteration_outcomes import candidate, wrapped, has_protocol, requires_requirement_review
from app.iteration_object_contract import schema_contract, schema_from_text, original_object, MARKER
from app.iteration_summary import candidate as summarize, summary_code, original_contract
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved

SCHEMA = {'type':'object','properties':{'label':{'type':'string'},'score':{'type':'number','minimum':0,'maximum':100}},'required':['label','score'],'additionalProperties':False}
CODE = 'import json\n# 固定开发样例\ndef main(item: str) -> dict:\n    return {"result": json.loads(item)}\n'


def object_plan():
    p = batch_plan(); cfg = iteration(p)
    cfg['output_type'] = 'array[object]'
    cfg['nodes'][0]['config'].update(code=CODE, outputs={'result':{'type':'object','children':None}})
    return p


def known(code=CODE, schema=SCHEMA):
    scope = {}; exec(wrapped(code, 'object', schema), scope)
    return scope['main']


def row(value, index=0): return {'index':index,'ok':True,'value':value,'error_category':None}


def test_object_candidate_exact_graph_schema_and_native_preservation():
    p = object_plan(); before = copy.deepcopy(p)
    iteration(p).update(is_parallel=True,parallel_nums=3,parallel_safe=True,parallel_reason='Independent fixed calculations without external requests.')
    before = copy.deepcopy(p)
    r = candidate(task(p),p,'batch',True,SCHEMA); out = json.loads(r['plan_text'])
    assert p == before and r['value_type'] == 'object' and len(r['result_schema_sha256']) == 64
    assert out['edges'] == p['edges'] and out['nodes'][:2] == p['nodes'][:2] and out['nodes'][-1] == p['nodes'][-1]
    c = iteration(out); code = c['nodes'][0]['config']['code']
    assert original_object(code) == (CODE,SCHEMA) and original_contract(code) == (CODE,'object')
    assert c['parallel_nums'] == 3 and c['error_handle_mode'] == 'terminated' and c['flatten_output'] is False
    assert CODE.replace('def main(', 'def _sierra_calculate(',1) in code
    native, checked = compile_workflow_plan(task(out)); assert checked['valid'], checked
    from app.parallel_preservation import candidates
    root=yaml.safe_load(native); reviews={x['id']:{'acknowledge_independence':True,'reason':'Fixed independent developer computations.','root_token':x['root_token']} for x in candidates(root)}
    assert validate_preserved(root,parallel_reviews=reviews)['valid']
    assert all(r[k] is False for k in ('platform_checked','business_verified','task_changed','network_requested'))


def test_object_values_duplicates_indexes_and_jsondecodeerror_base_category():
    fn = known(); value = {'label':'开发样例','score':12.5}
    rows = [fn(v,i)['outcome'] for i,v in enumerate([json.dumps(value),'not-json',json.dumps(value)])]
    assert rows == [row(value),{'index':1,'ok':False,'value':None,'error_category':'ValueError'},row(value,2)]
    assert 'not-json' not in json.dumps(rows)
    assert type(rows[0]['value']['score']) is float


@pytest.mark.parametrize('value', [None,[],True,'x',{'label':'x'}, {'label':'x','score':True}, {'label':'x','score':101}, {'label':'x','score':1,'extra':'private'}, {'label':'x','score':float('nan')}, {'label':'x','score':float('inf')}])
def test_bad_object_contract_terminates_outside_calculation_catch(value):
    fn = known()
    with pytest.raises(TypeError,match='object output'): fn(json.dumps(value),0)


@pytest.mark.parametrize('index', [True,-1,0.0])
def test_object_input_index_contract_not_business_failure(index):
    with pytest.raises(TypeError): known()('{}',index)


def test_unknown_fault_not_caught_and_reserved_names_blocked():
    fn = known('def main(item: str) -> dict:\n    assert item == "valid"\n    return {"result": {"label": item, "score": 1}}\n')
    with pytest.raises(AssertionError): fn('invalid',0)
    for code in ['import os\ndef main(item):\n return {"result": {}}\n', 'def main(item):\n return {"result": _sierra_schema}\n']:
        with pytest.raises(ValueError): known(code)


@pytest.mark.parametrize('expression', ['9007199254740992','-9007199254740992',"float('inf')", "float('nan')", 'None', 'set()', 'b"bytes"'])
def test_unsafe_nested_values_are_never_coerced_or_replaced(expression):
    schema = {'type':'object','properties':{'v':{'type':'number'}},'required':['v'],'additionalProperties':False}
    fn = known('def main(item):\n return {"result": {"v": '+expression+'}}\n',schema)
    with pytest.raises(TypeError): fn('fixed',0)


def test_nested_schema_optional_fields_strict_extra_and_exact_number_bool_semantics():
    schema = {'type':'object','properties':{'rows':{'type':'array','items':{'type':'object','properties':{'ok':{'type':'boolean'},'count':{'type':'integer','minimum':0,'maximum':9}},'required':['ok'],'additionalProperties':False},'maxItems':3}},'required':['rows'],'additionalProperties':False}
    fn = known(schema=schema)
    value = {'rows':[{'ok':True},{'ok':False,'count':2.0}]}
    assert fn(json.dumps(value),0)['outcome'] == row(value)
    for bad in [{'rows':[{'ok':1}]},{'rows':[{'ok':True,'count':True}]},{'rows':[{'ok':True,'x':1}]}]:
        with pytest.raises(TypeError): fn(json.dumps(bad),0)


def test_object_limits_utf8_value_count_cycles_and_invalid_unicode_fail_closed():
    schema = {'type':'object','properties':{'v':{'type':'string'}},'required':['v'],'additionalProperties':False}
    fn = known(schema=schema)
    assert fn(json.dumps({'v':'x'*63992}),0)['outcome']['ok']
    for bad in [{'v':'x'*63993},{'v':'中'*22000},{'v':'\ud800'}]:
        with pytest.raises(TypeError): fn(json.dumps(bad),0)
    schema = {'type':'object','properties':{'v':{'type':'array','items':{'type':'number'}}},'required':['v'],'additionalProperties':False}
    with pytest.raises(TypeError): known(schema=schema)(json.dumps({'v':[0]*20000}),0)
    fn = known('def main(item):\n v = {}\n v["v"] = v\n return {"result": v}\n',schema)
    with pytest.raises(TypeError): fn('fixed',0)


@pytest.mark.parametrize('schema', [None,{}, {'type':'string'}, {**SCHEMA,'additionalProperties':True}, {**SCHEMA,'default':{}}, {**SCHEMA,'properties':{'n':{'type':'integer','maximum':9007199254740992}}}])
def test_missing_or_unsupported_schema_never_inferred_or_simplified(schema):
    with pytest.raises(ValueError): known(schema=schema)


@pytest.mark.parametrize('text', ['{"type":"object","type":"string"}', '{"x":NaN}', '{"x":"\\ud800"}', '[1]', '{}', '"private"'])
def test_schema_text_rejects_duplicate_nonfinite_invalid_encoding_without_echo(text):
    with pytest.raises(ValueError) as exc: schema_from_text(text)
    assert 'private' not in str(exc.value)


def test_legacy_contract_bytes_and_ignored_schema_prevention():
    from app.iteration_summary import SUMMARY_CODE
    code='def main(item: str) -> dict:\n    return {"result": item.strip()}\n'
    assert hashlib.sha256(wrapped(code).encode()).hexdigest() == 'a35a7926ff20470218ac22d5adae67b3f2dacb2f6a0d2791faf4b2b6ca6725a2'
    assert summary_code() == SUMMARY_CODE
    for typ in ('string','number'):
        with pytest.raises(ValueError): wrapped(code,typ,SCHEMA)
        with pytest.raises(ValueError): summary_code(typ,SCHEMA)
    p = batch_plan()
    with pytest.raises(ValueError): candidate(task(p),p,'batch',True,SCHEMA)


def test_object_summary_reconstructs_exact_contract_and_preserves_native_graph():
    p = object_plan(); out = json.loads(candidate(task(p),p,'batch',True,SCHEMA)['plan_text']); before = copy.deepcopy(out)
    r = summarize(task(out),out,'batch',True); full = json.loads(r['plan_text'])
    assert out == before and r['value_type'] == 'object'
    assert iteration(full) == iteration(out)
    code = next(n['config']['code'] for n in full['nodes'] if n['id'] == r['summary_node_id'])
    assert code == summary_code('object',SCHEMA)
    native, checked = compile_workflow_plan(task(full)); assert checked['valid'],checked
    assert validate_preserved(yaml.safe_load(native))['valid']
    scope={};exec(code,scope)
    fn=known(); rows=[fn(v,i)['outcome'] for i,v in enumerate(['{"label":"x","score":1}','bad','{"label":"x","score":1}'])]
    result=scope['main'](rows,['a','b','a'])
    assert result['items']==rows and result['successes']==[rows[0],rows[2]] and result['failed']==1 and result['total']==3
    assert scope['main']([],[])['total']==0
    for bad in [[row({'label':'x','score':True})], [row({'label':'x','score':1},1)], [], [{**row({'label':'x','score':1}),'extra':1}]]:
        with pytest.raises(TypeError): scope['main'](bad,['a'])


@pytest.mark.parametrize('change', ['schema','code','guard','append'])
def test_object_unwrap_refuses_any_manual_protocol_change(change):
    p=object_plan();out=json.loads(candidate(task(p),p,'batch',True,SCHEMA)['plan_text']);c=iteration(out)['nodes'][0]['config']
    before=c['code']
    if change=='schema':c['code']=before.replace("'maximum': 100","'maximum': 101")
    elif change=='code':c['code']=before.replace('_sierra_calculate(item)','_sierra_calculate(item.strip())')
    elif change=='guard':c['code']=before.replace('<= 64000','<= 99999')
    else:c['code']+='\n# manual\n'
    # Changing the explicit embedded schema is itself a canonical new contract,
    # not a tamper seal. It can be summarized if exact and validated anew.
    if change=='schema': assert summarize(task(out),out,'batch',True)['value_type']=='object'
    else:
        with pytest.raises(ValueError):summarize(task(out),out,'batch',True)


def test_object_protocol_marks_business_review_without_title_false_positive():
    p=object_plan();out=json.loads(candidate(task(p),p,'batch',True,SCHEMA)['plan_text'])
    full=json.loads(summarize(task(out),out,'batch',True)['plan_text'])
    assert has_protocol(out) and has_protocol(full) and requires_requirement_review(p,out) and requires_requirement_review(out,full)
    title=copy.deepcopy(out);title['nodes'][0]['title']='新标题'
    assert not requires_requirement_review(out,title)


def test_object_preview_api_stateless_and_schema_raw_transport(client,monkeypatch):
    t=approved(client);url=f"/api/tasks/{t['id']}";before=copy.deepcopy(main.store.get('task',t['id']))
    def forbidden(*a,**kw):raise AssertionError('No external model/Dify permitted')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main,'DifyClient',forbidden)
    payload={'revision':t['revision'],'plan_text':json.dumps(object_plan()),'node_id':'batch','acknowledge_result_contract':True,'request_nonce':str(uuid4()),'result_schema_text':json.dumps(SCHEMA)}
    res=client.post(url+'/iteration-outcomes',json=payload);assert res.status_code==200,res.text
    value=res.json();assert value['value_type']=='object' and value['request_nonce']==payload['request_nonce']
    res=client.post(url+'/iteration-summary',json={'revision':t['revision'],'plan_text':value['plan_text'],'node_id':'batch','acknowledge_summary_outputs':True,'request_nonce':str(uuid4())})
    assert res.status_code==200,res.text
    for schema in [None,'{}','{"type":"object","type":"string"}',json.dumps({**SCHEMA,'properties':{'x':{'type':'number','maximum':9007199254740992}}})]:
        bad=client.post(url+'/iteration-outcomes',json={**payload,'result_schema_text':schema})
        assert bad.status_code==422,bad.text
    assert main.store.get('task',t['id'])==before


def test_object_schema_secrets_rejected_before_candidate_without_echo(client):
    t=approved(client);url=f"/api/tasks/{t['id']}";before=copy.deepcopy(main.store.get('task',t['id']))
    private='sk-'+'x'*24
    schema={**SCHEMA,'description':private}
    res=client.post(url+'/iteration-outcomes',json={'revision':t['revision'],'plan_text':json.dumps(object_plan()),'node_id':'batch','acknowledge_result_contract':True,'request_nonce':str(uuid4()),'result_schema_text':json.dumps(schema)})
    assert res.status_code==422 and private not in res.text
    assert main.store.get('task',t['id'])==before


@pytest.mark.parametrize('summarized',[False,True])
def test_saving_object_protocol_invalidates_approvals_and_requires_review(client,summarized):
    t=approved(client);url=f"/api/tasks/{t['id']}"
    p=object_plan();out=json.loads(candidate(task(p),p,'batch',True,SCHEMA)['plan_text'])
    if summarized:out=json.loads(summarize(task(out),out,'batch',True)['plan_text'])
    res=client.post(url+'/plan',json={'revision':t['revision'],'plan_text':json.dumps(out)})
    assert res.status_code==200,res.text
    saved=res.json();assert saved['requirements_confirmed'] is saved['configuration_confirmed'] is False
    assert saved['intake_required'] is True and saved['requirements']==t['requirements']
    intake=client.get(url+'/intake').json()
    assert 'batch_outcomes' in [x['id'] for x in intake['standard']]
    assert client.post(url+'/build',json={'revision':saved['revision']}).status_code==422
