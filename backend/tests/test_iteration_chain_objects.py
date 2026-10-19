"""Fixed developer object computations only; no customer code/model/HTTP/Dify."""
import copy,hashlib,json
from uuid import uuid4
import pytest,yaml
from test_api import client,approved
from test_iteration import task
from test_iteration_chain_upstream import upstream_plan,node
from app import main
from app.iteration_chain import candidate,ChainStageError
from app.iteration_chain_objects import original,wrapped,summary_code,MARKER,SUMMARY_MARKER
from app.iteration_outcomes import has_protocol,requires_requirement_review
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved

Q={'type':'object','properties':{'quantity':{'type':'integer'}},'required':['quantity'],'additionalProperties':False}
A={'type':'object','properties':{'answer':{'type':'number'}},'required':['answer'],'additionalProperties':False}


def object_plan(final='object'):
    p=upstream_plan('branch');cfg=node(p,'batch')['config'];children=cfg['nodes']
    children[0]['config'].update(code='def main(item):\n return {"result": {"quantity": int(item)}}\n',outputs={'result':{'type':'object','children':None}})
    children[1]['config']['code']='def main(value):\n return {"result": 100 / value["quantity"]}\n'
    if final=='object':children[2]['config'].update(code='def main(amount):\n return {"result": {"answer": amount}}\n',outputs={'result':{'type':'object','children':None}})
    elif final=='number':
        cfg['nodes']=children[:2];cfg['output_selector']=['divide','result']
    cfg['output_type']='array['+final+']';return p


def texts(final='object'):
    return {'clean':json.dumps(Q),'format':json.dumps(A)} if final=='object' else {'clean':json.dumps(Q)}


def propose(p=None,summary=False,schemas=None):
    p=object_plan() if p is None else p
    return candidate(task(p),p,'batch',True,summary,summary,'wrap',texts() if schemas is None else schemas)


def scopes(plan):
    values=[]
    for n in node(plan,'batch')['config']['nodes']:
        value={};exec(n['config']['code'],value);values.append(value)
    return values


def run(plan,items):
    fns=scopes(plan);rows=[]
    for i,item in enumerate(items):
        value=fns[0]['main'](item,i)['outcome']
        for fn in fns[1:]:value=fn['main'](value,i)['outcome']
        rows.append(value)
    return rows


@pytest.mark.parametrize('final',['object','number','string'])
@pytest.mark.parametrize('summary',[False,True])
def test_mixed_object_chain_compiles_preserves_upstream_and_summary(final,summary):
    p=object_plan(final);before=copy.deepcopy(p);assert validate_plan(task(p),p)['valid']
    value=propose(p,summary,texts(final));out=json.loads(value['plan_text']);assert p==before
    for n in p['nodes']:
        if n['id'] not in ('batch','end'):assert node(out,n['id'])==n
    for a,b in zip(node(p,'batch')['config']['nodes'],node(out,'batch')['config']['nodes']):assert original(b['config']['code'])[0]==a['config']['code']
    rows=run(out,['2','0','bad','2','']);assert [r['failed_stage'] for r in rows]==[None,2,1,None,1]
    assert rows[0]['value']==({'answer':50.0} if final=='object' else 50.0 if final=='number' else '50.0')
    assert value['stage_schema_text_sha256']=={k:hashlib.sha256(v.encode()).hexdigest() for k,v in texts(final).items()}
    assert set(value['stage_schema_sha256'])==set(texts(final))
    assert (value['result_schema_sha256'] is not None)==(final=='object')
    if summary:
        scope={};exec(node(out,value['summary_node_id'])['config']['code'],scope);result=scope['main'](rows,['2','0','bad','2','']);assert result['total']==5 and result['succeeded']==2 and result['failed']==3
        assert scope['main']([],[])['total']==0
    native,checked=compile_workflow_plan(task(out));assert checked['valid'],checked;assert validate_preserved(yaml.safe_load(native))['valid']
    assert has_protocol(out) and requires_requirement_review(p,out)


def test_failed_item_skips_all_later_original_object_calculations():
    out=json.loads(propose()['plan_text']);fns=scopes(out);row=fns[0]['main']('bad',0)['outcome']
    def forbidden(_):raise AssertionError('Do not run original calculation on failed item')
    for fn in fns[1:]:fn['_sierra_calculate']=forbidden;assert fn['main'](row,0)=={'outcome':row}


@pytest.mark.parametrize('bad',[{'quantity':True},{'quantity':9007199254740992},{'quantity':float('inf')},{'quantity':1,'extra':2},{},None])
def test_bad_previous_object_is_contract_failure_outside_catch(bad):
    fn=scopes(json.loads(propose()['plan_text']))[1]
    row={'index':0,'ok':True,'value':bad,'error_category':None,'failed_stage':None}
    with pytest.raises(TypeError,match='success mismatch'):fn['main'](row,0)


@pytest.mark.parametrize('result',['{"quantity": True}','{"quantity": 9007199254740992}','{"quantity": 1, "extra": 2}','{}','None'])
def test_bad_current_object_is_contract_failure_not_recoverable_calculation(result):
    code='def main(item):\n return {"result": '+result+'}\n';scope={};exec(wrapped(code,'item','string','object',1,2,None,Q),scope)
    with pytest.raises(TypeError,match='output mismatch'):scope['main']('fixed',0)


def test_schema_rule_minimum_rejects_output_without_default_or_coercion():
    schema=copy.deepcopy(Q);schema['properties']['quantity']['minimum']=0
    code='def main(item):\n return {"result": {"quantity": int(item)}}\n';scope={};exec(wrapped(code,'item','string','object',1,2,None,schema),scope)
    with pytest.raises(TypeError):scope['main']('-1',0)
    assert scope['main']('bad',0)['outcome']['error_category']=='ValueError'


@pytest.mark.parametrize('schemas',[{}, {'clean':json.dumps(Q)}, {'clean':json.dumps(Q),'format':json.dumps(A),'divide':json.dumps(A)}],ids=['none','missing','extra'])
def test_require_exact_schema_mapping_for_object_output_steps(schemas):
    p=object_plan();before=copy.deepcopy(p)
    with pytest.raises(ValueError):propose(p,schemas=schemas)
    assert p==before


@pytest.mark.parametrize('raw',['{"type":"object","type":"object"}','{"type":"object","additionalProperties":false,"properties":{"private_customer_field":{"type":"private_bad_type"}}}', 'NaN','{bad',json.dumps({'type':'object','properties':{},'additionalProperties':True})],ids=['duplicate','private-rule','nan','syntax','extra-fields'])
def test_schema_errors_have_safe_known_step_without_raw_rule_names(raw):
    data=texts();data['clean']=raw;p=object_plan();before=copy.deepcopy(p)
    with pytest.raises(ChainStageError) as caught:propose(p,schemas=data)
    assert caught.value.position==1 and caught.value.code=='stage_configuration' and 'private' not in str(caught.value) and p==before


def test_summary_rechecks_full_object_schema_and_item_count():
    out=json.loads(propose()['plan_text']);rows=run(out,['2','bad']);scope={};exec(summary_code('object',3,A),scope)
    for bad in [rows[:1],[{**rows[0],'value':{'answer':True}},rows[1]],[rows[1],rows[0]]]:
        with pytest.raises(TypeError):scope['main'](bad,['2','bad'])


def test_append_summary_preserves_original_schemas_and_manual_upstream_and_code():
    p=json.loads(propose()['plan_text']);cfg=node(p,'batch')['config']['nodes'][0]['config'];raw,c=original(cfg['code']);raw=raw.replace('int(item)','int(item)*2')
    cfg['code']=wrapped(raw,c['argument'],c['input_type'],c['value_type'],c['position'],c['total'],c['input_schema'],c['value_schema']);node(p,'parse')['title']='保留手改上游'
    before=copy.deepcopy(p);v=candidate(task(p),p,'batch',True,True,True,'append_summary',{});out=json.loads(v['plan_text'])
    assert p==before and node(out,'batch')==node(p,'batch') and node(out,'parse')==node(p,'parse')
    assert v['stage_schema_text_sha256']=={} and run(out,['2'])[0]['value']=={'answer':25.0}
    with pytest.raises(ValueError):candidate(task(p),p,'batch',True,True,True,'append_summary',texts())


def test_append_rejects_changed_guard_and_earlier_object_schema_mismatch():
    p=json.loads(propose()['plan_text']);cfg=node(p,'batch')['config']['nodes'][1]['config'];cfg['code']+='\n# developer manual wrapper change\n'
    with pytest.raises(ChainStageError) as caught:candidate(task(p),p,'batch',True,True,True,'append_summary',{})
    assert caught.value.code=='wrapper_contract' and caught.value.position==2
    p=json.loads(propose()['plan_text']);cfg=node(p,'batch')['config']['nodes'][1]['config'];raw,c=original(cfg['code']);changed=copy.deepcopy(Q);changed['properties']['quantity']['minimum']=0
    cfg['code']=wrapped(raw,c['argument'],c['input_type'],c['value_type'],2,3,changed,None)
    with pytest.raises(ValueError):candidate(task(p),p,'batch',True,True,True,'append_summary',{})


def test_raw_schema_text_hash_changes_but_canonical_contract_and_code_stay():
    a=propose();values={'clean':json.dumps(Q,indent=3)+'\n','format':json.dumps(A,indent=2)+'\n'};b=propose(schemas=values)
    assert a['plan_text']==b['plan_text'] and a['stage_schema_sha256']==b['stage_schema_sha256']
    assert a['stage_schema_text_sha256']!=b['stage_schema_text_sha256']


def test_api_strict_schema_text_receipt_stateless_and_save_invalidation(client,monkeypatch):
    t=approved(client);before=copy.deepcopy(main.store.get('task',t['id']))
    def forbidden(*a,**kw):raise AssertionError('No real model or Dify')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main,'DifyClient',forbidden)
    payload={'revision':t['revision'],'plan_text':json.dumps(object_plan()),'node_id':'batch','acknowledge_chain_contract':True,'request_nonce':str(uuid4()),'stage_schema_texts':texts()}
    response=client.post(f"/api/tasks/{t['id']}/iteration-chain-outcomes",json=payload);assert response.status_code==200,response.text;v=response.json();assert v['request_nonce']==payload['request_nonce'] and v['value_type']=='object'
    assert main.store.get('task',t['id'])==before
    saved=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan_text':v['plan_text']});assert saved.status_code==200,saved.text;s=saved.json();assert s['requirements_confirmed'] is False and s['configuration_confirmed'] is False and s['intake_required'] is True


@pytest.mark.parametrize('value',[{'clean':1}, {'clean':'x'*64001}, {str(i):'{}' for i in range(9)}],ids=['not-text','too-long','too-many'])
def test_api_refuses_unbounded_or_non_text_schema_maps(client,value):
    t=approved(client);payload={'revision':t['revision'],'plan_text':json.dumps(object_plan()),'node_id':'batch','acknowledge_chain_contract':True,'request_nonce':str(uuid4()),'stage_schema_texts':value}
    response=client.post(f"/api/tasks/{t['id']}/iteration-chain-outcomes",json=payload);assert response.status_code==422 and 'x'*30 not in response.text


def test_malformed_legacy_outputs_do_not_bypass_safe_validation(client):
    t=approved(client);p=object_plan();node(p,'batch')['config']['nodes'][0]['config']['outputs']=[]
    payload={'revision':t['revision'],'plan_text':json.dumps(p),'node_id':'batch','acknowledge_chain_contract':True,'request_nonce':str(uuid4())}
    response=client.post(f"/api/tasks/{t['id']}/iteration-chain-outcomes",json=payload);assert response.status_code==422


@pytest.mark.parametrize('problem',['private-rule','credentials','unicode'])
def test_api_schema_rejections_never_echo_private_input(client,problem):
    t=approved(client);before=copy.deepcopy(main.store.get('task',t['id']));data=texts()
    if problem=='private-rule':data['clean']='{"type":"object","properties":{"private_customer_field":{"type":"private_bad_type"}},"additionalProperties":false}'
    elif problem=='credentials':
        schema=copy.deepcopy(Q);schema['description']='sk-'+'x'*32;data['clean']=json.dumps(schema)
    else:data['clean']='{"private_customer_field":"'+chr(0xd800)+'"}'
    payload={'revision':t['revision'],'plan_text':json.dumps(object_plan()),'node_id':'batch','acknowledge_chain_contract':True,'request_nonce':str(uuid4()),'stage_schema_texts':data}
    response=client.post(f"/api/tasks/{t['id']}/iteration-chain-outcomes",content=json.dumps(payload,ensure_ascii=True).encode(),headers={'Content-Type':'application/json'})
    assert response.status_code==422 and 'private_customer_field' not in response.text and 'private_bad_type' not in response.text and 'x'*16 not in response.text
    if problem=='private-rule':assert response.json()['detail']['stage_position']==1
    assert main.store.get('task',t['id'])==before
