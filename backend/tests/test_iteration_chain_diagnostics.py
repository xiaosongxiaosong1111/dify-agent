"""Preparation diagnostics only; no user code is executed or resources accessed."""
import copy,hashlib,json
from uuid import uuid4
import pytest
from test_api import client,approved
from test_iteration import task,iteration
from test_iteration_chain import chain_plan,propose
from app import main
from app.iteration_chain import candidate,wrapped,original,ChainStageError


def bad_plan(code,position=2):
    p=chain_plan(True)
    if code in ('wrapper_contract','stage_order'):
        p=json.loads(propose(p)['plan_text']);cfg=iteration(p)['nodes'][position-1]['config']
        if code=='wrapper_contract':cfg['code']+='\n# private developer diagnostic\n'
        else:
            raw,c=original(cfg['code']);cfg['code']=wrapped(raw,c['argument'],c['input_type'],c['value_type'],position,4)
    elif code=='stage_configuration':
        iteration(p)['nodes'][position-1]['config']['variables'].append({'variable':'extra','value_selector':['start','items_json']})
    else:
        cfg=iteration(p)['nodes'][position-1]['config'];arg=cfg['variables'][0]['variable']
        cfg['code']=f'def main({arg}):\n    print("private developer diagnostic")\n    return {{"result": 1}}\n'
    return p


@pytest.mark.parametrize('code',['stage_configuration','calculation_scope','wrapper_contract','stage_order'])
@pytest.mark.parametrize('position',[1,2,3])
def test_known_step_failure_has_safe_position_without_mutation(code,position):
    p=bad_plan(code,position);before=copy.deepcopy(p);append=code in ('wrapper_contract','stage_order')
    with pytest.raises(ChainStageError) as caught:candidate(task(p),p,'batch',True,append,append,'append_summary' if append else 'wrap')
    assert caught.value.diagnostic()=={'code':code,'stage_position':position,'stage_count':3}
    assert 'private' not in str(caught.value) and p==before


@pytest.mark.parametrize('code',['stage_configuration','calculation_scope','wrapper_contract','stage_order'])
def test_api_diagnostic_is_stateless_bound_and_not_execution_result(client,monkeypatch,code):
    t=approved(client);url=f"/api/tasks/{t['id']}";before=copy.deepcopy(main.store.get('task',t['id']))
    def forbidden(*a,**kw):raise AssertionError('No execution or resource access')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main,'DifyClient',forbidden)
    p=bad_plan(code);append=code in ('wrapper_contract','stage_order');text=json.dumps(p,ensure_ascii=False,indent=3)+'\n'
    payload={'revision':t['revision'],'plan_text':text,'node_id':'batch','acknowledge_chain_contract':True,'include_summary':append,'acknowledge_summary_outputs':append,'operation':'append_summary' if append else 'wrap','request_nonce':str(uuid4())}
    response=client.post(url+'/iteration-chain-outcomes',json=payload);assert response.status_code==422,response.text
    assert response.json()=={'detail':{'code':code,'stage_position':2,'stage_count':3,'kind':'chain_stage_preparation','task_id':t['id'],'revision':t['revision'],'request_nonce':payload['request_nonce'],'node_id':'batch','operation':payload['operation'],'include_summary':append,'source_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'verification':'local_chain_preparation_only','task_changed':False,'network_requested':False,'platform_checked':False,'business_verified':False}}
    assert 'private' not in response.text and 'failed_stage' not in response.text
    assert main.store.get('task',t['id'])==before


@pytest.mark.parametrize('change',['unconfirmed','stale','graph','syntax','unknown_target','summary_conflict'])
def test_other_scope_failures_do_not_invent_step_location(client,change):
    t=approved(client);p=chain_plan(True)
    payload={'revision':t['revision'],'plan_text':json.dumps(p),'node_id':'batch','acknowledge_chain_contract':True,'request_nonce':str(uuid4())}
    if change=='unconfirmed':payload['acknowledge_chain_contract']=False
    elif change=='stale':payload['revision']+=1
    elif change=='graph':p['edges'].pop();payload['plan_text']=json.dumps(p)
    elif change=='syntax':payload['plan_text']='{invalid private'
    elif change=='unknown_target':payload['node_id']='unknown'
    else:
        p['nodes'][-1]['config']['outputs'][0]['variable']='total';payload.update(plan_text=json.dumps(p),include_summary=True,acknowledge_summary_outputs=True)
    response=client.post(f"/api/tasks/{t['id']}/iteration-chain-outcomes",json=payload)
    assert response.status_code==(409 if change=='stale' else 422)
    assert 'chain_stage_preparation' not in response.text and 'stage_position' not in response.text and 'private' not in response.text


# SHA256 over canonical complete successful responses frozen from 0.195, not new code.
@pytest.mark.parametrize('operation,summary,expected',[
    ('wrap',False,'299b9a2593bda3d30d69987c1844bc6a7c72096317e335c0ddb4a73354055aa3'),
    ('wrap',True,'ec1d989999b6492229cb3306482c4154c9d6f3c9a9af31505f984bc5eb75a818'),
    ('append_summary',True,'cbcea7986dbf52ecea443f3c8a125dc1c20a824eb2698cfbe299d2b96fbce0a8')],ids=['plain','summary','append'])
def test_success_contract_and_generated_code_remain_byte_identical_to_195(operation,summary,expected):
    p=chain_plan(True)
    if operation=='append_summary':p=json.loads(propose(p)['plan_text'])
    before=copy.deepcopy(p);value=candidate(task(p),p,'batch',True,summary,summary,operation)
    assert hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()==expected
    assert p==before


@pytest.mark.parametrize('code,position,total',[('private',1,3),('calculation_scope',True,3),('calculation_scope',0,3),('calculation_scope',4,3),('calculation_scope',1,9),('calculation_scope',1,True)])
def test_internal_invalid_diagnostic_cannot_claim_a_position(code,position,total):
    with pytest.raises(ValueError) as caught:ChainStageError(code,position,total)
    assert not isinstance(caught.value,ChainStageError) and 'private' not in str(caught.value)
