import copy,json
from uuid import uuid4
import pytest
from test_api import client,approved,code_only_plan
from test_iteration import batch_plan,iteration,task
from test_loop import loop_plan
from app import main
from app.execution_scale import estimate

def test_unknown_iteration_count_is_not_zero_and_nonmodel_counts_stay_known():
 p=batch_plan();value=estimate(task(p),p,{})
 assert value['max_declared_node_visits'] is None and value['has_unknown_item_count']
 assert value['max_resource_node_visits']=={'model_nodes':0,'retrieval_nodes':0,'http_nodes':0}
 assert value['containers'][0]['multiplier'] is None
 assert not value['actual_api_calls_known'] and not value['cost_estimate_available'] and value['cost_usd'] is None
 assert value['source_kind']=='editor_plan_only' and not value['final_dsl_checked']
 assert any('Dify手改保留' in n and '不代表目标应用实际次数' in n for n in value['notes'])

@pytest.mark.parametrize('count',[0,1,20,100000])
def test_explicit_item_count_counts_only_declared_nodes_and_never_mutates_plan(count):
 p=batch_plan();before=copy.deepcopy(p);value=estimate(task(p),p,{'batch':count})
 assert value['max_declared_node_visits']==4+count
 assert value['containers'][0]['basis']=='manual_item_count' and value['item_counts']=={'batch':count}
 assert not value['network_requested'] and not value['task_changed'] and not value['business_verified']
 assert p==before

def test_one_model_node_per_item_is_a_visit_upper_bound_not_api_or_price_quote():
 p=batch_plan();cfg=iteration(p);cfg['nodes']=[{'id':'model','type':'llm','config':{'system_prompt':'开发固定样例','user_prompt':'{{#batch.item#}}'}}];cfg['output_selector']=['model','text']
 t=task(p,dify_model_provider='synthetic/provider',dify_model='synthetic-model')
 unknown=estimate(t,p,{})
 assert unknown['max_resource_node_visits']['model_nodes'] is None
 assert estimate(t,p,{'batch':20})['max_resource_node_visits']['model_nodes']==20
 assert estimate(t,p,{'batch':0})['max_resource_node_visits']['model_nodes']==0
 assert any('不是API请求次数上界' in note for note in unknown['notes'])

def test_root_llm_visits_once_and_plain_code_not_assumed_free():
 p={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'text-input','required':True}]}},{'id':'model','type':'llm','config':{'system_prompt':'固定说明','user_prompt':'{{#start.query#}}'}},{'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['model','text']}]}}], 'edges':[{'source':'start','target':'model'},{'source':'model','target':'end'}]}
 value=estimate(task(p,dify_model_provider='test/provider',dify_model='test-model'),p,{})
 assert value['max_declared_node_visits']==3 and value['max_resource_node_visits']['model_nodes']==1
 code=code_only_plan();value=estimate(task(code),code,{})
 assert value['cost_usd'] is None and any('不能证明' in note and '免费' in note for note in value['notes'])

def test_unknown_container_model_count_stays_unknown_with_a_later_root_model():
 p=batch_plan();cfg=iteration(p);cfg['nodes']=[{'id':'model','type':'llm','config':{'system_prompt':'固定','user_prompt':'{{#batch.item#}}'}}];cfg['output_selector']=['model','text']
 p['nodes'].insert(-1,{'id':'final_model','type':'llm','config':{'system_prompt':'固定','user_prompt':'{{#batch.output#}}'}})
 p['edges'][-1]={'source':'batch','target':'final_model'};p['edges'].append({'source':'final_model','target':'end'})
 t=task(p,dify_model_provider='test/provider',dify_model='test-model')
 assert estimate(t,p,{})['max_resource_node_visits']['model_nodes'] is None
 assert estimate(t,p,{'batch':0})['max_resource_node_visits']['model_nodes']==1
 assert estimate(t,p,{'batch':20})['max_resource_node_visits']['model_nodes']==21

def test_chatflow_declared_answer_is_not_changed_to_workflow_or_counted_as_model():
 p={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[]}},{'id':'answer','type':'answer','config':{'answer':'固定说明'}}],'edges':[{'source':'start','target':'answer'}]}
 result=estimate({'app_type':'advanced-chat','configuration':{}},p,{})
 assert result['app_type']=='advanced-chat' and result['max_declared_node_visits']==2
 assert result['max_resource_node_visits']['model_nodes']==0

@pytest.mark.parametrize('counts',[{'batch':True},{'batch':-1},{'batch':100001},{'batch':'20'},{'old':1},{'batch':1.5}])
def test_bad_or_stale_assumptions_rejected_without_partial_counts(counts):
 p=batch_plan()
 with pytest.raises(ValueError):estimate(task(p),p,counts)

def test_agent_not_silently_counted_as_explicit_workflow():
 p=batch_plan()
 with pytest.raises(ValueError,match='Agent'):estimate({'app_type':'agent'},p,{})

def test_actual_assistant_catalog_explains_supported_scale_scope_without_agent_promise():
 from app.capabilities import catalog
 for kind in ('workflow','advanced-chat'):
  assert any('逻辑节点执行次数' in n and '不估实际API请求' in n for n in catalog(kind,'0.190.0')['notes'])
 assert not any('逻辑节点执行次数' in n for n in catalog('agent','0.190.0')['notes'])

def test_invalid_plan_rejected_instead_of_returning_partial_lower_count():
 p=batch_plan();p['nodes'].append({'id':'unknown','type':'plugin','config':{}})
 with pytest.raises(ValueError):estimate(task(p),p,{'batch':20})

def test_loop_declared_cap_used_and_cannot_be_overridden_as_item_count():
 p=loop_plan();value=estimate(task(p),p,{})
 row=next(c for c in value['containers'] if c['node_type']=='loop')
 cfg=next(n['config'] for n in p['nodes'] if n['type']=='loop')
 assert row['basis']=='declared_loop_count' and row['multiplier']==cfg['loop_count']
 assert value['max_declared_node_visits']==len(p['nodes'])+len(cfg['nodes'])*cfg['loop_count']
 with pytest.raises(ValueError):estimate(task(p),p,{row['node_id']:1})

def test_api_only_reads_current_task_and_does_not_touch_budget_or_dispatch(client,monkeypatch):
 t=approved(client);p=batch_plan();before=copy.deepcopy(main.store.get('task',t['id']));ledger=copy.deepcopy(main.store.get('task_budget',t['id']))
 def forbidden(*a,**kw):raise AssertionError('Must remain local')
 monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main,'DifyClient',forbidden)
 payload={'revision':t['revision'],'plan_text':json.dumps(p),'item_counts':{'batch':20},'request_nonce':str(uuid4())}
 response=client.post(f"/api/tasks/{t['id']}/execution-scale",json=payload)
 assert response.status_code==200,response.text
 value=response.json();assert value['task_id']==t['id'] and value['request_nonce']==payload['request_nonce']
 assert value['max_declared_node_visits']==24
 assert main.store.get('task',t['id'])==before and main.store.get('task_budget',t['id'])==ledger
 payload['revision']+=1;assert client.post(f"/api/tasks/{t['id']}/execution-scale",json=payload).status_code==409

@pytest.mark.parametrize('change',[{'item_counts':{'batch':True}},{'revision':True},{'price':'PRIVATE'}, {'item_counts':{'batch':-1}}])
def test_invalid_request_does_not_echo_inputs_or_create_records(client,change):
 t=approved(client);p=batch_plan();before=copy.deepcopy(main.store.get('task',t['id']))
 payload={'revision':t['revision'],'plan_text':json.dumps(p),'item_counts':{},'request_nonce':str(uuid4()),**change}
 response=client.post(f"/api/tasks/{t['id']}/execution-scale",json=payload)
 assert response.status_code==422 and 'PRIVATE' not in response.text
 assert main.store.get('task',t['id'])==before
