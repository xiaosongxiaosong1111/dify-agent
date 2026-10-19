"""Only fixed pure-code fixtures are executed; no Dify or customer execution."""
import copy,json
import pytest,yaml
from test_iteration import batch_plan,task,iteration
from app.iteration_outcomes import candidate as outcomes
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app import iteration_summary as summary

def plan():
    p=batch_plan()
    return json.loads(outcomes(task(p),p,'batch',True)['plan_text'])

def propose(p=None,ack=True):
    p=p or plan()
    return summary.candidate(task(p),p,'batch',ack)

def function():
    scope={};exec(summary.SUMMARY_CODE,scope)
    # Known fixtures supply a matching original-input count unless a test
    # explicitly examines count mismatch. No customer input is executed here.
    fn=scope['main']
    return lambda results,source_items=None: fn(results,['fixture']*len(results) if source_items is None and isinstance(results,list) else source_items)

def rows():return [{'index':0,'ok':True,'value':'A','error_category':None},{'index':1,'ok':False,'value':None,'error_category':'ValueError'},{'index':2,'ok':True,'value':'A','error_category':None},{'index':3,'ok':True,'value':'','error_category':None}]

def test_summary_counts_failed_position_duplicates_and_empty_text():
    r=rows();before=copy.deepcopy(r);out=function()(r)
    assert out=={'items':r,'successes':[r[0],r[2],r[3]],'failures':[r[1]],'total':4,'succeeded':3,'failed':1}
    assert r==before

def test_empty_input_has_explicit_zero_counts():
    assert function()([])=={'items':[],'successes':[],'failures':[],'total':0,'succeeded':0,'failed':0}

@pytest.mark.parametrize('replace', [None,{},'bad',[None],[{'index':0,'ok':True,'value':'A','error_category':None,'extra':'private'}],[{'index':1,'ok':True,'value':'A','error_category':None}],[{'index':True,'ok':True,'value':'A','error_category':None}],[{'index':0,'ok':1,'value':'A','error_category':None}],[{'index':0,'ok':True,'value':None,'error_category':None}],[{'index':0,'ok':True,'value':'A','error_category':'ValueError'}],[{'index':0,'ok':False,'value':'made up','error_category':'ValueError'}],[{'index':0,'ok':False,'value':None,'error_category':'private'}],[{'index':0,'ok':False,'value':None,'error_category':None}]])
def test_no_partial_summary_or_private_value_on_invalid_envelope(replace):
    with pytest.raises(TypeError) as error:function()(replace)
    assert 'private' not in str(error.value)

def test_later_bad_record_does_not_return_partial_counts():
    r=rows();r[3]['index']=99
    with pytest.raises(TypeError):function()(r)


@pytest.mark.parametrize('items',[[],['one'],['one','two','three','four','five'],[1,2,3,4],{},'private'])
def test_original_input_count_or_type_mismatch_terminates(items):
    with pytest.raises(TypeError) as error:function()(rows(),items)
    assert 'private' not in str(error.value)


def test_missing_tail_cannot_be_mistaken_for_complete_batch():
    r=rows()[:-1]
    with pytest.raises(TypeError):function()(r,['a','bad','a',''])

def test_exact_source_code_contract_and_native_roundtrip():
    p=plan();before=copy.deepcopy(p);v=propose(p);after=json.loads(v['plan_text'])
    assert p==before and len(after['nodes'])==5
    assert after['nodes'][:3]==p['nodes'][:3]
    assert after['nodes'][-1]['id']==p['nodes'][-1]['id']
    assert after['nodes'][-1]['config']['outputs'][0]['variable']=='results'
    assert len(after['nodes'][-1]['config']['outputs'])==6
    assert after['nodes'][-2]['config']['code']==summary.SUMMARY_CODE
    assert after['nodes'][-2]['config']['outputs']==summary.SUMMARY_OUTPUTS
    native,checked=compile_workflow_plan(task(after));assert checked['valid'],checked['errors']
    assert validate_preserved(yaml.safe_load(native))['valid']
    assert v['task_changed'] is v['network_requested'] is v['platform_checked'] is v['business_verified'] is False

@pytest.mark.parametrize('ack',[False,None,1,'true'])
def test_explicit_result_field_choice_is_required(ack):
    with pytest.raises(ValueError):propose(ack=ack)

def test_existing_result_field_name_collision_is_not_renamed():
    p=plan();p['nodes'][-1]['config']['outputs'][0]['variable']='total';before=copy.deepcopy(p)
    with pytest.raises(ValueError):propose(p)
    assert p==before

def test_new_summary_node_avoids_all_existing_ids():
    p=batch_plan();iteration(p)['nodes'][0]['id']='batch_summary';iteration(p)['output_selector']=['batch_summary','result']
    p=json.loads(outcomes(task(p),p,'batch',True)['plan_text']);v=propose(p)
    assert v['summary_node_id']=='batch_summary_2'

def test_manual_outcome_policy_change_is_preserved_by_refusal():
    p=plan();iteration(p)['nodes'][0]['config']['code']=iteration(p)['nodes'][0]['config']['code'].replace("'ok': False","'ok': True")
    before=copy.deepcopy(p)
    with pytest.raises(ValueError):propose(p)
    assert p==before

def test_original_body_comments_and_unicode_survive_canonical_check():
    p=batch_plan();iteration(p)['nodes'][0]['config']['code']='# 保留人工说明\ndef main(item: str) -> dict:\n    return {"result": item.lower()}\n\n'
    p=json.loads(outcomes(task(p),p,'batch',True)['plan_text']);after=json.loads(propose(p)['plan_text'])
    assert iteration(after)==iteration(p)

def test_repeated_summary_is_not_inserted():
    p=json.loads(propose()['plan_text'])
    with pytest.raises(ValueError):propose(p)


from app import main
from app.storage import Store
from fastapi.testclient import TestClient
from uuid import uuid4

@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'store',Store(tmp_path));monkeypatch.setattr(main,'DATA_ROOT',tmp_path)
    with TestClient(main.app) as c:
        t=c.post('/api/tasks',json={'name':'隔离结果汇总','app_type':'workflow'}).json()
        yield c,t

def payload(t):return {'revision':t['revision'],'plan_text':json.dumps(plan()),'node_id':'batch','acknowledge_summary_outputs':True,'request_nonce':str(uuid4())}

def test_api_only_prepares_candidate_no_persistence(api):
    c,t=api;url='/api/tasks/'+t['id'];before=c.get(url).json();draft=c.get(url+'/plan-draft').json();p=payload(t)
    response=c.post(url+'/iteration-summary',json=p);assert response.status_code==200,response.text
    v=response.json();assert v['task_id']==t['id'] and v['revision']==t['revision'] and v['request_nonce']==p['request_nonce']
    assert v['added_nodes']==1 and v['added_end_fields']==['successes','failures','total','succeeded','failed']
    assert c.get(url).json()==before and c.get(url+'/plan-draft').json()==draft

@pytest.mark.parametrize('field,value,status', [('revision',999,409),('revision',True,422),('acknowledge_summary_outputs',False,422),('acknowledge_summary_outputs','yes',422),('plan_text','{"private":NaN}',422),('plan_text','{"x":1,"x":2}',422),('plan_text',{},422),('node_id','missing',422),('request_nonce','private-not-uuid',422),('unknown','private',422)])
def test_api_rejects_stale_malformed_unconfirmed_requests(api,field,value,status):
    c,t=api;p=payload(t);p[field]=value;response=c.post('/api/tasks/'+t['id']+'/iteration-summary',json=p)
    assert response.status_code==status,response.text
    assert 'private' not in response.text


@pytest.mark.parametrize('change',['introduce','summarize','remove','body'])
def test_saving_changed_batch_contract_drops_legacy_business_approval(api,change):
    c,_=api
    from test_api import approved
    t=approved(c);url='/api/tasks/'+t['id']
    previous=None if change=='introduce' else plan()
    t['workflow_plan']=previous;t['plan_stale']=False
    main.store.put('task',t['id'],t)
    if change=='introduce':next_plan=plan()
    elif change=='summarize':next_plan=json.loads(propose()['plan_text'])
    elif change=='remove':next_plan=batch_plan()
    else:
        next_plan=copy.deepcopy(previous)
        iteration(next_plan)['nodes'][0]['config']['code']=iteration(next_plan)['nodes'][0]['config']['code'].replace('item.strip().upper()','item.strip().lower()')
    response=c.post(url+'/plan',json={'revision':t['revision'],'plan_text':json.dumps(next_plan)})
    assert response.status_code==200,response.text
    saved=response.json()
    assert saved['revision']==t['revision']+1
    assert saved['requirements_confirmed'] is saved['configuration_confirmed'] is False
    assert saved['intake_required'] is True and saved['requirements']==t['requirements']
    assert saved['workflow_plan']==next_plan and saved['plan_stale'] is False
    assert saved['confirmations'][:len(t['confirmations'])]==t['confirmations']
    assert c.post(url+'/build',json={'revision':saved['revision']}).status_code==422
    state=c.get(url+'/intake').json()
    assert state['required'] is True and state['can_confirm'] is False
    if change!='remove':assert 'batch_outcomes' in [r['id'] for r in state['standard']]


def test_cosmetic_title_edit_keeps_business_approval_and_intake_scope(api):
    c,_=api
    from test_api import approved
    from app.intake import digest as intake_digest
    t=approved(c);t['workflow_plan']=plan();t['plan_stale']=False
    main.store.put('task',t['id'],t)
    before=intake_digest(t);next_plan=copy.deepcopy(t['workflow_plan'])
    next_plan['nodes'][0]['title']='只改标题'
    iteration(next_plan)['nodes'][0]['title']='只改正文标题'
    response=c.post('/api/tasks/'+t['id']+'/plan',json={'revision':t['revision'],'plan_text':json.dumps(next_plan)})
    assert response.status_code==200,response.text
    saved=response.json();assert saved['requirements_confirmed'] is True and saved['configuration_confirmed'] is False
    assert intake_digest(saved)==before


def test_protocol_code_changes_invalidate_old_intake_digest_without_exposing_code():
    from app.intake import context,digest as intake_digest
    t={'app_type':'workflow','requirements':{k:'明确' for k in main.REQ_KEYS},'workflow_plan':plan(),'messages':[],'materials':[]}
    before=intake_digest(t)
    iteration(t['workflow_plan'])['nodes'][0]['config']['code']+='\n# review new hand edit\n'
    assert intake_digest(t)!=before
    scope=context(t)['batch_plan_scope']
    assert scope['verification']=='draft_protocol_markers_only' and len(scope['semantic_sha256'])==64
    assert 'code' not in json.dumps(scope)
