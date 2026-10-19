"""Execute fixed developer computations only; no user code or Dify."""
import copy,json
from uuid import uuid4
import pytest,yaml
from test_iteration import batch_plan,iteration,task
from test_api import client,approved
from app import main
from app.iteration_chain import candidate,wrapped,original,summary_code,MARKER
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved


def chain_plan(text_final=False):
    p=batch_plan();cfg=iteration(p);first=cfg['nodes'][0]
    first['config'].update(code='def main(item: str) -> dict:\n    return {"result": int(item)}\n',outputs={'result':{'type':'number','children':None}})
    cfg['nodes'].append({'id':'divide','type':'code','title':'固定样例除法','config':{'code_language':'python3','code':'def main(value: float) -> dict:\n    return {"result": 100 / value}\n','variables':[{'variable':'value','value_selector':[first['id'],'result']}],'outputs':{'result':{'type':'number','children':None}}}})
    cfg.update(output_selector=['divide','result'],output_type='array[number]')
    if text_final:
        cfg['nodes'].append({'id':'format','type':'code','title':'固定文字结果','config':{'code_language':'python3','code':'def main(amount: float) -> dict:\n    return {"result": str(amount)}\n','variables':[{'variable':'amount','value_selector':['divide','result']}],'outputs':{'result':{'type':'string','children':None}}}})
        cfg.update(output_selector=['format','result'],output_type='array[string]')
    return p


def propose(p=None,summary=False):
    p=chain_plan() if p is None else p
    return candidate(task(p),p,'batch',True,summary,summary)


def functions(p):
    result=[]
    for node in iteration(p)['nodes']:
        scope={};exec(node['config']['code'],scope);result.append(scope)
    return result


def execute_fixed(p,items):
    scopes=functions(p);rows=[]
    for i,item in enumerate(items):
        value=scopes[0]['main'](item,i)['outcome']
        for scope in scopes[1:]:value=scope['main'](value,i)['outcome']
        rows.append(value)
    return rows


def test_full_chain_preserves_original_bodies_order_graph_and_parallel_setting():
    p=chain_plan(True);before=copy.deepcopy(p);value=propose(p,True);out=json.loads(value['plan_text'])
    assert p==before and value['value_type']=='string' and value['added_nodes']==1 and len(value['stages'])==3
    assert [n['id'] for n in iteration(out)['nodes']]==[n['id'] for n in iteration(p)['nodes']]
    assert out['nodes'][:2]==p['nodes'][:2]
    for a,b in zip(iteration(p)['nodes'],iteration(out)['nodes']):
        assert a.get('title')==b.get('title') and original(b['config']['code'])[0]==a['config']['code']
    assert iteration(out)['error_handle_mode']=='terminated' and iteration(out)['flatten_output'] is False
    native,checked=compile_workflow_plan(task(out));assert checked['valid'],checked
    assert validate_preserved(yaml.safe_load(native))['valid']


def test_failures_have_first_failed_stage_duplicates_empty_and_exact_position():
    out=json.loads(propose()['plan_text']);rows=execute_fixed(out,['2','bad','0','2',''])
    assert rows==[
        {'index':0,'ok':True,'value':50.0,'error_category':None,'failed_stage':None},
        {'index':1,'ok':False,'value':None,'error_category':'ValueError','failed_stage':1},
        {'index':2,'ok':False,'value':None,'error_category':'ZeroDivisionError','failed_stage':2},
        {'index':3,'ok':True,'value':50.0,'error_category':None,'failed_stage':None},
        {'index':4,'ok':False,'value':None,'error_category':'ValueError','failed_stage':1}]
    assert 'bad' not in json.dumps(rows)


def test_downstream_failed_item_never_calls_original_calculation():
    out=json.loads(propose(chain_plan(True))['plan_text']);scopes=functions(out);row=scopes[0]['main']('bad',3)['outcome']
    def forbidden(_):raise AssertionError('A failed item must not execute later calculations')
    for scope in scopes[1:]:
        scope['_sierra_calculate']=forbidden
        assert scope['main'](row,3)=={'outcome':row}


@pytest.mark.parametrize('kind',['ValueError','TypeError','ZeroDivisionError','KeyError','IndexError','OverflowError'])
def test_six_calculation_errors_normalize_without_private_message(kind):
    code=f'def main(value):\n raise {kind}("private developer fixture")\n return {{"result": 1}}\n'
    scope={};exec(wrapped(code,'value','number','number',2,2),scope)
    previous={'index':0,'ok':True,'value':1,'error_category':None,'failed_stage':None}
    assert scope['main'](previous,0)['outcome']=={'index':0,'ok':False,'value':None,'error_category':kind,'failed_stage':2}


def test_jsondecodeerror_subclass_uses_base_category():
    code='import json\ndef main(item):\n return {"result": int(json.loads(item))}\n'
    scope={};exec(wrapped(code,'item','string','number',1,2),scope)
    assert scope['main']('bad',0)['outcome']['error_category']=='ValueError'


@pytest.mark.parametrize('change',['index','ok','stage','error','extra','success_type'])
def test_bad_previous_record_is_contract_error_not_recoverable_business_failure(change):
    scope=functions(json.loads(propose()['plan_text']))[1]
    row={'index':0,'ok':False,'value':None,'error_category':'ValueError','failed_stage':1}
    if change=='index':row['index']=True
    elif change=='ok':row['ok']=0
    elif change=='stage':row['failed_stage']=2
    elif change=='error':row['error_category']='JSONDecodeError'
    elif change=='extra':row['private']='hidden'
    else:row.update(ok=True,value=True,error_category=None,failed_stage=None)
    with pytest.raises(TypeError):scope['main'](row,0)


@pytest.mark.parametrize('expression',['True',"float('inf')","float('nan')",'9007199254740992','None','{}'])
def test_output_format_errors_outside_calculation_catch(expression):
    code='def main(item):\n return {"result": '+expression+'}\n';scope={};exec(wrapped(code,'item','string','number',1,2),scope)
    with pytest.raises(TypeError,match='output'):scope['main']('fixed',0)


def test_unknown_and_input_errors_stop():
    code='def main(item):\n assert item == "valid"\n return {"result": item}\n';scope={};exec(wrapped(code,'item','string','string',1,2),scope)
    with pytest.raises(AssertionError):scope['main']('bad',0)
    with pytest.raises(TypeError):scope['main']('valid',True)
    with pytest.raises(TypeError):scope['main'](12,0)


def test_summary_same_contract_full_count_and_empty_arrays():
    out=json.loads(propose(chain_plan(True),True)['plan_text']);rows=execute_fixed(out,['2','0','bad','2']);scope={};exec(next(n['config']['code'] for n in out['nodes'] if n['id']=='batch_chain_summary'),scope)
    value=scope['main'](rows,['2','0','bad','2']);assert value['items']==rows and value['total']==4 and value['succeeded']==2 and value['failed']==2
    assert value['successes']==[rows[0],rows[3]] and value['failures']==[rows[1],rows[2]]
    assert scope['main']([],[])=={'items':[],'successes':[],'failures':[],'total':0,'succeeded':0,'failed':0}
    for bad in [rows[:-1],list(reversed(rows)),[{**rows[0],'failed_stage':True}]+rows[1:]]:
        with pytest.raises(TypeError):scope['main'](bad,['2','0','bad','2'])


def test_append_summary_canonical_reconstruction_keeps_existing_chain():
    p=json.loads(propose()['plan_text']);before=copy.deepcopy(p)
    v=candidate(task(p),p,'batch',True,True,True,'append_summary');out=json.loads(v['plan_text'])
    assert p==before and iteration(out)==iteration(p) and v['operation']=='append_summary'
    p['nodes'][2]['config']['nodes'][1]['config']['code']=p['nodes'][2]['config']['nodes'][1]['config']['code'].replace("return {'outcome': row}","return {'outcome': {}}")
    with pytest.raises(ValueError):candidate(task(p),p,'batch',True,True,True,'append_summary')


@pytest.mark.parametrize('change',['side_input','object','template','dag','consumer','retry','body_count'])
def test_no_implicit_dropping_inputs_nodes_consumers_or_settings(change):
    p=chain_plan();cfg=iteration(p)
    if change=='side_input':cfg['nodes'][1]['config']['variables'].append({'variable':'extra','value_selector':['start','items_json']})
    elif change=='object':cfg['nodes'][0]['config']['outputs']['result']['type']='object'
    elif change=='template':cfg['nodes'][1].update(type='template-transform',config={'template':'constant','variables':[]})
    elif change=='dag':cfg.update(edges=[{'source':'clean','target':'divide'}],entry_node_id='clean')
    elif change=='consumer':p['nodes'][-1]['config']['outputs'].append({'variable':'other','value_selector':['start','items_json']})
    elif change=='retry':cfg['nodes'][1]['config']['retry_config']={'retry_enabled':True}
    else:cfg['nodes']=cfg['nodes'][:1]
    before=copy.deepcopy(p)
    with pytest.raises(ValueError):propose(p)
    assert p==before


def test_parallel_preserved_and_summary_output_name_conflict_explicit():
    p=chain_plan();iteration(p).update(is_parallel=True,parallel_nums=3,parallel_safe=True,parallel_reason='Independent development calculations, no external side effects.')
    out=json.loads(propose(p)['plan_text']);assert iteration(out)['parallel_nums']==3
    p=chain_plan();p['nodes'][-1]['config']['outputs'][0]['variable']='total'
    assert propose(p)['include_summary'] is False
    with pytest.raises(ValueError):propose(p,True)


@pytest.mark.parametrize('ack,summary,ack_summary',[(False,False,False),(True,True,False),(True,False,True),(1,False,False)])
def test_explicit_acknowledgements(ack,summary,ack_summary):
    p=chain_plan()
    with pytest.raises(ValueError):candidate(task(p),p,'batch',ack,summary,ack_summary)


def test_api_stateless_and_saved_contract_invalidates_approval(client,monkeypatch):
    t=approved(client);url=f"/api/tasks/{t['id']}";before=copy.deepcopy(main.store.get('task',t['id']))
    def forbidden(*a,**kw):raise AssertionError('No real model or Dify')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main,'DifyClient',forbidden)
    payload={'revision':t['revision'],'plan_text':json.dumps(chain_plan()),'node_id':'batch','acknowledge_chain_contract':True,'include_summary':True,'acknowledge_summary_outputs':True,'request_nonce':str(uuid4())}
    r=client.post(url+'/iteration-chain-outcomes',json=payload);assert r.status_code==200,r.text
    value=r.json();assert value['request_nonce']==payload['request_nonce'] and value['task_id']==t['id']
    assert main.store.get('task',t['id'])==before
    r=client.post(url+'/plan',json={'revision':t['revision'],'plan_text':value['plan_text']});assert r.status_code==200,r.text
    saved=r.json();assert saved['requirements_confirmed'] is saved['configuration_confirmed'] is False and saved['intake_required'] is True
    assert client.post(url+'/build',json={'revision':saved['revision']}).status_code==422


@pytest.mark.parametrize('field,value,status', [('revision',True,422),('revision',999,409),('operation','private',422),('acknowledge_chain_contract',1,422),('include_summary','yes',422),('request_nonce','private',422),('extra','private',422)])
def test_api_strict_rejects_stale_unconfirmed_or_unknown(client,field,value,status):
    t=approved(client);p={'revision':t['revision'],'plan_text':json.dumps(chain_plan()),'node_id':'batch','acknowledge_chain_contract':True,'request_nonce':str(uuid4())};p[field]=value
    r=client.post(f"/api/tasks/{t['id']}/iteration-chain-outcomes",json=p)
    assert r.status_code==status and 'private' not in r.text


def test_two_and_eight_stage_boundaries_and_code_identity_collision():
    p=chain_plan();cfg=iteration(p)
    for index in range(3,9):
        prev=cfg['nodes'][-1]['id'];nid='stage'+str(index)
        cfg['nodes'].append({'id':nid,'type':'code','config':{'code_language':'python3','code':'def main(value):\n return {"result": value+1}\n','variables':[{'variable':'value','value_selector':[prev,'result']}],'outputs':{'result':{'type':'number','children':None}}}})
    cfg['output_selector']=[nid,'result'];v=propose(p,True);assert len(v['stages'])==8
    out=json.loads(v['plan_text']);rows=execute_fixed(out,['2','bad']);assert rows[0]['value']==56 and rows[1]['failed_stage']==1
    native,checked=compile_workflow_plan(task(out));assert checked['valid'] and validate_preserved(yaml.safe_load(native))['valid']


def test_hand_modified_original_calculation_can_be_retained_with_canonical_wrapper():
    p=json.loads(propose()['plan_text']);cc=iteration(p)['nodes'][1]['config']
    raw,contract=original(cc['code']);raw=raw.replace('100 / value','200 / value')
    cc['code']=wrapped(raw,contract['argument'],contract['input_type'],contract['value_type'],2,2)
    out=json.loads(candidate(task(p),p,'batch',True,True,True,'append_summary')['plan_text'])
    assert iteration(out)==iteration(p) and execute_fixed(out,['2'])[0]['value']==100
