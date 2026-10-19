import copy,hashlib,json
import pytest,yaml
from test_api import client
from test_file_model_run import uploaded_model,model_document,inputs
from test_file_structured_run import structured,shape,result
from test_file_run import plan,run,remote,PUBLISHED,RUN
from app import main
from app.file_run import KIND,plan_token
from app.file_run_flow import describe
from app.structured_guard import guard_code
from app.file_schema_guard import validate_saved

GUARD='summary__schema_check'

def guarded(root,selector='model'):
 structured(root);graph=root['workflow']['graph'];llm=graph['nodes'][2]
 guard=copy.deepcopy(graph['nodes'][-1]);guard['id']=GUARD;guard['data']={'type':'code','title':'严格校验结构化对象','code_language':'python3','code':guard_code(shape()),'variables':[{'variable':'data','value_selector':[llm['id'],'structured_output']}],'outputs':{'result':{'type':'object','children':None}}}
 graph['nodes'].insert(-1,guard)
 outgoing=graph['edges'][-1];outgoing['target']=GUARD;outgoing['data']['targetType']='code';outgoing['id']='summary-to-guard'
 edge=copy.deepcopy(outgoing);edge.update(id='guard-to-end',source=GUARD,target='end');edge['data'].update(sourceType='code',targetType='end');graph['edges'].append(edge)
 if selector=='guard':graph['nodes'][-1]['data']['outputs'][0]['value_selector']=[GUARD,'result']

def ready(client,monkeypatch,selector='model'):return uploaded_model(client,monkeypatch,patch=lambda root:guarded(root,selector))
def execute(client,t,q,**patch):return run(client,t,q,acknowledge_model_egress=True,acknowledge_unpriced_model_cost=True,acknowledge_strict_guard=True,**patch)

@pytest.mark.parametrize('selector',['model','guard'])
def test_guarded_file_plan_freezes_full_code_schema_bindings_and_only_one_model(client,monkeypatch,selector):
 t,env,p,root=ready(client,monkeypatch,selector);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*args,**kwargs):pytest.fail('方案准备不能联网、解密、调用模型或执行生成代码')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 r=plan(client,t,p,inputs(p));assert r.status_code==200,r.text;q=r.json();flow=q['data_flow'];guard=flow['strict_guard']
 assert q['plan_schema_version']==7 and flow['schema_version']==6 and flow['scenario']=='document_model_guarded_object'
 assert flow['node_types']==['start','document-extractor','llm','code','end'] and flow['planned_llm_node_executions']==1 and flow['output_kind']=='json-object'
 assert guard['code_text']==guard_code(shape()) and guard['code_sha256']==hashlib.sha256(guard_code(shape()).encode()).hexdigest()
 assert guard['source_node_id']=='summary' and guard['node_id']==GUARD and guard['end_selector']==(['summary','structured_output'] if selector=='model' else [GUARD,'result'])
 assert guard['failure_behavior']=='fail_workflow_no_defaults_no_retry' and guard['platform_checked'] is False and guard['business_verified'] is False
 validate_saved(guard,'summary',flow['structured_output']['schema']);assert not q.get('strict_guard_approved') and main.get_task(t['id'])==before

@pytest.mark.parametrize('acks',[{}, {'acknowledge_model_egress':True,'acknowledge_unpriced_model_cost':True}, {'acknowledge_model_egress':True,'acknowledge_strict_guard':True}, {'acknowledge_unpriced_model_cost':True,'acknowledge_strict_guard':True}, {'acknowledge_model_egress':True,'acknowledge_unpriced_model_cost':True,'acknowledge_strict_guard':1}])
def test_guard_failure_and_model_egress_cost_require_independent_strict_approvals(client,monkeypatch,acks):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();calls,_=remote(monkeypatch,t,env)
 r=run(client,t,q,**acks);assert r.status_code==422 and not calls and main.store.get(KIND,q['id'])['attempts']==0 and not main.get_task(t['id'])['runs']

@pytest.mark.parametrize('selector',['model','guard'])
def test_approved_guarded_flow_records_valid_object_once_without_rewriting_graph(client,monkeypatch,selector):
 t,env,p,root=ready(client,monkeypatch,selector);q=plan(client,t,p,inputs(p)).json();output={'customer':'甲','approved':False};calls,_=remote(monkeypatch,t,env,result=result(output))
 r=execute(client,t,q);assert r.status_code==200,r.text;record=r.json()['task']['runs'][-1]
 assert record['status']=='success' and record['result']['data']['outputs']=={'result':output} and main.store.get(KIND,q['id'])['strict_guard_approved'] is True
 assert [c[0] for c in calls]==['keys','published','run'] and execute(client,t,q).status_code==409 and len(calls)==3
 assert yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'))==root

@pytest.mark.parametrize('mutation',['code','schema','input','output','language','retry','error_default','extra','version','container','fake_bool','wrong_end','bypass','wrong_order'])
def test_modified_guard_or_bypassed_path_is_rejected_without_simplification(mutation):
 root=yaml.safe_load(model_document());guarded(root);before=copy.deepcopy(root);graph=root['workflow']['graph'];guard=graph['nodes'][3]['data']
 if mutation=='code':guard['code']+='\n# human edit'
 elif mutation=='schema':graph['nodes'][2]['data']['structured_output']['schema']['required'].append('amount')
 elif mutation=='input':guard['variables'][0]['value_selector']=['summary','text']
 elif mutation=='output':guard['outputs']['result']['type']='string'
 elif mutation=='language':guard['code_language']='javascript'
 elif mutation=='retry':guard['retry_config']={'retry_enabled':True,'max_retries':2}
 elif mutation=='error_default':guard['error_strategy']='default-value';guard['default_value']=[{'key':'result','value':{}}]
 elif mutation=='extra':guard['future_execution_setting']='unknown'
 elif mutation=='version':guard['version']='2'
 elif mutation=='container':guard['isInIteration']=True
 elif mutation=='fake_bool':guard['isInLoop']=0
 elif mutation=='wrong_end':graph['nodes'][-1]['data']['outputs'][0]['value_selector']=[GUARD,'text']
 elif mutation=='bypass':graph['edges'].append({'source':'summary','target':'end'})
 else:graph['edges'][-1].update(source='extract',target='end')
 changed=copy.deepcopy(root)
 with pytest.raises(ValueError):describe(root)
 assert root==changed and root!=before

def test_schema_guard_change_after_approval_stops_before_any_platform_read(client,monkeypatch):
 t,env,p,root=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();calls,_=remote(monkeypatch,t,env)
 root['workflow']['graph']['nodes'][3]['data']['code']+='\n# changed';main.artifact_path(t).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8')
 assert execute(client,t,q).status_code==422 and not calls

def test_old_plan_cannot_expand_into_guarded_object_even_with_recalculated_local_token(client,monkeypatch):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();row=main.store.get(KIND,q['id']);row['plan_schema_version']=6;row['resource_token']=plan_token(row);main.store.put(KIND,row['id'],row);calls,_=remote(monkeypatch,t,env)
 assert execute(client,t,row).status_code==409 and not calls

def test_bad_object_on_reported_platform_success_keeps_safe_identity_not_invalid_output(client,monkeypatch):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();calls,_=remote(monkeypatch,t,env,result=result({'customer':'甲','approved':'private-value'}));r=execute(client,t,q)
 assert r.status_code==502 and 'private-value' not in r.text and len(calls)==3;row=main.store.get(KIND,q['id']);assert row['output_contract_rejected'] and row['state']=='unknown'
 record=main.get_task(t['id'])['runs'][-1];assert record['status']=='unknown' and record['result']['data']['id']==RUN and 'outputs' not in record['result']['data']

def test_guard_platform_failure_keeps_safe_diagnostic_identity_without_retry(client,monkeypatch):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();receipt=result({});receipt['data'].update(status='failed',error='private-code-error');calls,_=remote(monkeypatch,t,env,result=receipt)
 r=execute(client,t,q);assert r.status_code==502 and 'private-code-error' not in r.text and len(calls)==3
 row=main.store.get(KIND,q['id']);assert row['state']=='platform_failed' and main.get_task(t['id'])['runs'][-1]['status']=='failed';assert execute(client,t,q).status_code==409

def test_guarded_file_case_evidence_requires_original_guard_approval_and_complete_recipe(client,monkeypatch):
 t,env,p,_=ready(client,monkeypatch);values=inputs(p);c=client.post(f"/api/tasks/{t['id']}/file-cases/capture",json={'revision':t['revision'],'catalog_revision':0,'input_text':json.dumps(values),'name':'校验对象','expectation':{'mode':'json_schema','target':'result','expected':shape()}});assert c.status_code==200,c.text;catalog=c.json()
 q=client.post(f"/api/tasks/{t['id']}/file-runs/prepare",json={'revision':t['revision'],'input_text':json.dumps(values),'case_id':catalog['saved_case_id'],'case_catalog_revision':1});assert q.status_code==200,q.text
 remote(monkeypatch,t,env,result=result({'customer':'甲','approved':True}));r=execute(client,t,q.json());assert r.status_code==200,r.text;record=r.json()['task']['runs'][-1];url=f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/evidence"
 e=client.get(url);assert e.status_code==200,e.text;assert json.loads(e.json()['outputs_preview'])['result']['approved'] is True
 row=main.store.get(KIND,q.json()['id']);original=copy.deepcopy(row);row['strict_guard_approved']=False;main.store.put(KIND,row['id'],row);assert client.get(url).status_code==422
 row=copy.deepcopy(original);row['data_flow']['strict_guard']['code_text']+='\n# tampered';main.store.put(KIND,row['id'],row);assert client.get(url).status_code==422
 row=copy.deepcopy(original);row['data_flow']['strict_guard']['platform_checked']=0;main.store.put(KIND,row['id'],row);assert client.get(url).status_code==422

def test_guard_has_independent_identity_and_complete_exact_raw_schema_hash():
 root=yaml.safe_load(model_document());guarded(root);flow=describe(root)
 assert flow['strict_guard']['schema_text_sha256']==hashlib.sha256(flow['structured_output']['schema_text'].encode('utf-8')).hexdigest()
 root['workflow']['graph']['nodes'][3]['id']='summary'
 with pytest.raises(ValueError):describe(root)

def test_dispatched_plan_token_does_not_change_when_recording_new_guard_approval(client,monkeypatch):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();remote(monkeypatch,t,env,result=result({'customer':'甲','approved':True}));r=execute(client,t,q)
 assert r.status_code==200,r.text;row=main.store.get(KIND,q['id']);assert row['strict_guard_approved'] is True
 # Execution observation fields are deliberately separate from the frozen token;
 # adding the approval must not change what the user actually approved.
 original=copy.deepcopy(row);original.pop('strict_guard_approved')
 assert plan_token(row)==plan_token(original)
