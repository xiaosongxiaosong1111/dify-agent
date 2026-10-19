import copy,json,uuid
import pytest,yaml
from test_api import client
from test_file_join import POLICY,ACKS
from test_file_joined_structured import values
from test_file_model_run import MODEL
from test_file_structured_run import shape,result
from test_runtime_files import ready as base_ready,prepare as upload_prepare,execute as upload_execute,receipt
from test_file_run import plan,run,remote,PUBLISHED,RUN
from test_workflow_plan import plan_task
from test_optional_branch_audit import reader,diagnose
from app import main
from app.file_run import KIND,plan_token
from app.file_structured_template import joined_template
from app.workflow_plan import compile_workflow_plan
from app.structured_guard import candidate
from app.dsl_roundtrip import validate_preserved
from app.file_run_flow import describe

GUARD='answer_llm__schema_check'
ALL={**ACKS,'acknowledge_strict_guard':True}

def document(selector='model'):
 p=joined_template(json.dumps(shape()),POLICY,['.txt']);p['nodes'][3]['config']['model']=copy.deepcopy(MODEL)
 before=copy.deepcopy(p);p=candidate(plan_task(p),p,'answer_llm')['plan']
 assert p['nodes'][2]==before['nodes'][2] and p['nodes'][3]==before['nodes'][3]
 if selector=='guard':p['nodes'][-1]['config']['outputs'][0]['value_selector']=[GUARD,'result']
 text,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked
 root=yaml.safe_load(text);assert validate_preserved(root)['valid'];return root

def ready(client,monkeypatch,selector='model'):
 t,env=base_ready(client,'file-list');root=document(selector);main.artifact_path(t).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8');main.store.set_secret(env['id'],'console_token','fixture-console-token')
 async def upload(*args):return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload);u=upload_prepare(client,t).json();r=upload_execute(client,t,u);assert r.status_code==200,r.text
 return t,env,u,root

@pytest.mark.parametrize('selector',['model','guard'])
def test_generated_join_plus_guard_keeps_both_policies_and_one_model(selector):
 root=document(selector);before=copy.deepcopy(root);f=describe(root)
 assert f['schema_version']==8 and f['scenario']=='document_list_model_guarded_object' and f['node_types']==['start','document-extractor','code','llm','code','end']
 assert f['join_policy']['policy']==POLICY and f['strict_guard']['node_id']==GUARD and f['strict_guard']['end_selector']==(['answer_llm','structured_output'] if selector=='model' else [GUARD,'result'])
 assert f['structured_output']['schema']==shape() and f['planned_llm_node_executions']==1 and root==before

@pytest.mark.parametrize('missing',['acknowledge_model_egress','acknowledge_unpriced_model_cost','acknowledge_join_policy','acknowledge_strict_guard'])
def test_all_four_specific_approvals_are_independent_before_any_reads(client,monkeypatch,missing):
 t,env,u,_=ready(client,monkeypatch);q=plan(client,t,u,values(u)).json();assert q['plan_schema_version']==9
 calls,_=remote(monkeypatch,t,env);r=run(client,t,q,**{**ALL,missing:False});assert r.status_code==422 and not calls and main.store.get(KIND,q['id'])['attempts']==0

@pytest.mark.parametrize('selector',['model','guard'])
def test_approved_combined_flow_runs_once_with_original_duplicate_file_order(client,monkeypatch,selector):
 t,env,u,root=ready(client,monkeypatch,selector);q=plan(client,t,u,values(u)).json();calls,_=remote(monkeypatch,t,env,result=result({'customer':'甲','approved':False}));r=run(client,t,q,**ALL);assert r.status_code==200,r.text
 saved=main.store.get(KIND,q['id']);assert saved['join_policy_approved'] and saved['strict_guard_approved'] and [c[0] for c in calls]==['keys','published','run']
 assert r.json()['task']['runs'][-1]['input']==values(u) and yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'))==root
 assert run(client,t,q,**ALL).status_code==409 and len(calls)==3

@pytest.mark.parametrize('scope',[6,7,8])
def test_old_object_and_single_guard_scopes_never_expand_to_combination(client,monkeypatch,scope):
 t,env,u,_=ready(client,monkeypatch);q=plan(client,t,u,values(u)).json();row=main.store.get(KIND,q['id']);row['plan_schema_version']=scope;row['resource_token']=plan_token(row);main.store.put(KIND,row['id'],row);calls,_=remote(monkeypatch,t,env)
 assert run(client,t,row,**ALL).status_code==409 and not calls

@pytest.mark.parametrize('mutation',['join_code','guard_code','guard_schema','guard_input','guard_retry','swap_roles','bypass','extra_code','wrong_end','model_text'])
def test_changed_code_bindings_and_graphs_are_rejected_without_simplification(mutation):
 root=document();g=root['workflow']['graph'];join=g['nodes'][2];llm=g['nodes'][3];guard=g['nodes'][4]
 if mutation=='join_code':join['data']['code']+='\n# changed'
 elif mutation=='guard_code':guard['data']['code']+='\n# changed'
 elif mutation=='guard_schema':llm['data']['structured_output']['schema']['required'].append('amount')
 elif mutation=='guard_input':guard['data']['variables'][0]['value_selector']=[join['id'],'text']
 elif mutation=='guard_retry':guard['data']['retry_config']={'retry_enabled':True,'max_retries':2}
 elif mutation=='swap_roles':join['data'],guard['data']=guard['data'],join['data']
 elif mutation=='bypass':g['edges'][-1]['target']='end'
 elif mutation=='extra_code':g['nodes'].append(copy.deepcopy(join))
 elif mutation=='wrong_end':g['nodes'][-1]['data']['outputs'][0]['value_selector']=[join['id'],'text']
 elif mutation=='model_text':llm['data']['structured_output_enabled']=False
 before=copy.deepcopy(root)
 with pytest.raises(ValueError):describe(root)
 assert root==before

@pytest.mark.parametrize('missing',['join_policy_approved','strict_guard_approved'])
def test_original_file_case_object_evidence_requires_both_approvals(client,monkeypatch,missing):
 t,env,u,_=ready(client,monkeypatch);v=values(u);c=client.post(f"/api/tasks/{t['id']}/file-cases/capture",json={'revision':t['revision'],'catalog_revision':0,'input_text':json.dumps(v),'name':'列表严格对象','expectation':{'mode':'json_schema','target':'result','expected':shape()}});assert c.status_code==200,c.text;case=c.json()
 q=client.post(f"/api/tasks/{t['id']}/file-runs/prepare",json={'revision':t['revision'],'input_text':json.dumps(v),'case_id':case['saved_case_id'],'case_catalog_revision':1}).json();remote(monkeypatch,t,env,result=result({'customer':'甲','approved':True}));r=run(client,t,q,**ALL);assert r.status_code==200,r.text;record=r.json()['task']['runs'][-1]
 url=f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/evidence";assert client.get(url).status_code==200
 row=main.store.get(KIND,q['id']);row[missing]=False;main.store.put(KIND,row['id'],row);assert client.get(url).status_code==422

@pytest.mark.parametrize('mode,state',[('succeeded','observed_succeeded'),('guard_failed','observed_failed'),('end_failed','observed_succeeded'),('join_failed','insufficient'),('join_approval','insufficient'),('join_policy','insufficient')])
def test_combined_guard_observation_requires_complete_predecessors_and_original_join(client,monkeypatch,mode,state):
 t,env,u,root=ready(client,monkeypatch);q=plan(client,t,u,values(u)).json();value=result({'customer':'甲','approved':False})
 if mode in {'guard_failed','end_failed','join_failed'}:value['data']['status']='failed'
 setup,_=remote(monkeypatch,t,env,result=value);r=run(client,t,q,**ALL);assert r.status_code==(502 if value['data']['status']=='failed' else 200),r.text
 t=main.get_task(t['id']);record=t['runs'][-1];original=copy.deepcopy(record);p=main.store.get(KIND,q['id']);graph=root['workflow']['graph'];nodes=graph['nodes'][:5] if mode=='guard_failed' else graph['nodes'][:3] if mode=='join_failed' else graph['nodes'];failed=GUARD if mode=='guard_failed' else 'end' if mode=='end_failed' else graph['nodes'][2]['id'] if mode=='join_failed' else None
 trace={'data':[{'id':str(uuid.uuid4()),'workflow_run_id':RUN,'node_id':n['id'],'node_type':n['data']['type'],'status':'failed' if n['id']==failed else 'succeeded','error':None} for n in nodes]};detail={'id':RUN,'status':value['data']['status'],'total_steps':len(nodes),'graph':graph}
 if mode=='join_approval':p['join_policy_approved']=False;main.store.put(KIND,p['id'],p)
 if mode=='join_policy':p['data_flow']['join_policy']['policy']['separator']='different';main.store.put(KIND,p['id'],p)
 calls=reader(monkeypatch,detail,trace,{'id':PUBLISHED,**root['workflow']});d=diagnose(client,t,record);assert d.status_code==200,d.text;a=d.json()['file_guard_audit'];assert a['state']==state and a['business_verified'] is False and len(calls)==3 and len(setup)==3
 assert {k:v for k,v in main.get_task(t['id'])['runs'][-1].items() if k!='diagnostics'}==original
