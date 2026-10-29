import copy,json,uuid,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import main
from app.plan_review import linear_plan,needed
from test_api import client,approved,restore_payload
from test_intake import new,manual

def ready(client,mode='workflow'):
    task=new(client,mode);task=manual(client,task).json();url='/api/tasks/'+task['id']
    task=client.post(url+'/confirm',json={'revision':task['revision'],'kind':'requirements'}).json()
    return client.patch(url,json={'configuration':{'dify_model_provider':'test/provider','dify_model':'test-model'}}).json()

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_new_task_requires_reviewable_graph_before_configuration_or_build(client,mode):
    t=ready(client,mode);url='/api/tasks/'+t['id'];assert t['plan_review_required'] and needed(t)
    before=copy.deepcopy(main.store.get('task',t['id']))
    for endpoint,body in [('confirm',{'kind':'configuration'}),('build',{})]:
        r=client.post(url+'/'+endpoint,json={'revision':t['revision'],**body});assert r.status_code==422 and '流程' in r.json()['detail']
        assert main.store.get('task',t['id'])==before
    assert client.get(url+'/next-step',params={'revision':t['revision']}).json()['state']=='plan_required'
    assert client.patch(url,json={'plan_review_required':False}).status_code==422

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
@pytest.mark.parametrize('datasets',[[],['11111111-1111-4111-8111-111111111111']])
def test_explicit_linear_preview_is_stateless_and_only_saved_plan_unlocks(client,mode,datasets):
    t=ready(client,mode);url='/api/tasks/'+t['id'];t=client.patch(url,json={'configuration':{'dataset_ids':datasets}}).json()
    original=copy.deepcopy(t);ledger=copy.deepcopy(main.store.get('task_budget',t['id']));nonce=str(uuid.uuid4())
    r=client.post(url+'/linear-plan-preview',json={'revision':t['revision'],'request_nonce':nonce});assert r.status_code==200,r.text
    v=r.json();p=json.loads(v['plan_text']);assert v['task_id']==t['id'] and v['request_nonce']==nonce
    assert len(p['nodes'])==(4 if datasets else 3) and p['nodes'][-1]['type']==('end' if mode=='workflow' else 'answer')
    assert all(v[k] is False for k in ['task_changed','network_requested','model_called','business_verified'])
    assert '无命中分支' in v['note'] and client.get(url).json()==original and main.store.get('task_budget',t['id'])==ledger
    assert client.post(url+'/confirm',json={'revision':t['revision'],'kind':'configuration'}).status_code==422
    t=client.post(url+'/plan',json={'revision':t['revision'],'plan_text':v['plan_text']}).json()
    assert t['requirements_confirmed'] and not t['configuration_confirmed'] and not needed(t)
    r=client.post(url+'/confirm',json={'revision':t['revision'],'kind':'configuration'});assert r.status_code==200,r.text
    assert client.post(url+'/build',json={'revision':t['revision']}).status_code==200
    t=client.patch(url,json={'workflow_plan':None}).json()
    assert t['plan_review_required'] and needed(t) and t['artifact'] is None and not t['configuration_confirmed']

def test_legacy_implicit_template_task_still_works_without_data_migration(client):
    t=approved(client);assert 'plan_review_required' not in t
    assert client.post('/api/tasks/'+t['id']+'/build',json={'revision':t['revision']}).status_code==200

@pytest.mark.parametrize('key,value',[('workflow_plan',{'schema_version':1}),('dsl_reference',{'id':'kept'}),('artifact',{'revision':1}),('dify_app_id','kept')])
def test_preview_never_replaces_existing_source_or_saved_work(client,key,value):
    t=ready(client);t[key]=value;main.store.put('task',t['id'],t);before=copy.deepcopy(main.get_task(t['id']))
    r=client.post('/api/tasks/'+t['id']+'/linear-plan-preview',json={'revision':t['revision'],'request_nonce':str(uuid.uuid4())})
    assert r.status_code==422 and client.get('/api/tasks/'+t['id']).json()==before

def test_stale_and_malformed_requests_do_not_return_private_values(client):
    t=ready(client);url='/api/tasks/'+t['id']+'/linear-plan-preview'
    for patch,status in [({'revision':t['revision']-1},409),({'revision':True},422),({'request_nonce':'PRIVATE-DO-NOT-ECHO'},422),({'extra':'PRIVATE-DO-NOT-ECHO'},422)]:
        r=client.post(url,json={'revision':t['revision'],'request_nonce':str(uuid.uuid4()),**patch});assert r.status_code==status and 'PRIVATE-DO-NOT-ECHO' not in r.text

def test_confirmed_native_source_uses_existing_preservation_gate_instead_of_linear_fallback():
    t={'app_type':'workflow','plan_review_required':True,'workflow_plan':None,'dsl_reference':{'id':'source'}}
    assert not needed(t)  # Actual confirm/build separately require current native preservation; no empty source is applied here.

def test_restore_older_version_cannot_remove_new_task_plan_review_policy(client):
    t=ready(client);url='/api/tasks/'+t['id'];old=t['versions'][-1]['id']
    p,text=linear_plan(t);t=client.post(url+'/plan',json={'revision':t['revision'],'plan_text':text}).json()
    r=client.post(url+'/restore',json=restore_payload(client,t['id'],old));assert r.status_code==200,r.text
    restored=r.json();assert restored['plan_review_required'] is True and needed(restored)
    assert client.post(url+'/build',json={'revision':restored['revision']}).status_code==422

def test_after_sales_recorded_plan_retains_hit_and_no_hit_routes_through_build_and_revision_change(client):
    # Recorded public synthetic model output, replayed locally; no new model or Dify execution.
    scenario=json.loads((Path(__file__).parent/'fixtures/after_sales_recorded_205.json').read_text('utf-8'));p=scenario['plan']
    t=client.post('/api/tasks',json={'name':'公开合成售后问答主链','app_type':'workflow'}).json();url='/api/tasks/'+t['id']
    t=client.patch(url,json={'requirements':scenario['requirements'],'configuration':scenario['configuration']}).json()
    from app.intake import summary
    s=summary(t);answers={row['id']:t['requirements'].get(row['id'],'本场景已明确仅检索模拟库；当前为静态规划，不进行外部操作。') for row in s['standard']}
    r=client.post(url+'/intake/manual',json={'revision':t['revision'],'context_token':s['context_token'],'answers':answers,'acknowledge_review':True});assert r.status_code==200,r.text;t=r.json()
    t=client.post(url+'/confirm',json={'revision':t['revision'],'kind':'requirements'}).json()
    assert client.post(url+'/confirm',json={'revision':t['revision'],'kind':'configuration'}).status_code==422
    r=client.post(url+'/plan',json={'revision':t['revision'],'plan_text':json.dumps(p,ensure_ascii=False)});assert r.status_code==200,r.text;t=r.json()
    r=client.post(url+'/confirm',json={'revision':t['revision'],'kind':'configuration'});assert r.status_code==200,r.text
    r=client.post(url+'/build',json={'revision':t['revision']});assert r.status_code==200,r.text;t=r.json()
    from app.dsl_roundtrip import parse
    document=parse(client.get(url+'/dsl').json()['content'],'workflow');kinds=[n['data']['type'] for n in document['workflow']['graph']['nodes']]
    assert 'if-else' in kinds and 'knowledge-retrieval' in kinds and 'llm' in kinds and t['runs']==[]
    original=copy.deepcopy(t['workflow_plan']);t=client.patch(url,json={'requirements':{'exceptions':t['requirements']['exceptions']+' 人工提示需包含工单入口说明。'}}).json()
    assert t['artifact'] is None and t['dify_app_id'] is None and not t['requirements_confirmed'] and not t['configuration_confirmed'] and t['plan_stale'] and t['workflow_plan']==original
    assert client.post(url+'/build',json={'revision':t['revision']}).status_code==422
