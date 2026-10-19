import copy,json,uuid
import pytest,yaml
from test_api import client
from test_file_model_run import uploaded_model,model_document,inputs
from test_file_run import plan,run,remote,PUBLISHED,RUN
from app import main
from app.file_run import KIND,plan_token
from app.file_run_flow import describe

def shape():return {'type':'object','properties':{'customer':{'type':'string','minLength':1},'approved':{'type':'boolean'},'amount':{'type':'number','minimum':0},'tags':{'type':'array','items':{'type':'string'},'maxItems':3}},'required':['customer','approved'],'additionalProperties':False}

@pytest.mark.parametrize('envelope',[None,{}, {'unknown':'private-output'}])
def test_trusted_success_with_missing_object_output_keeps_safe_identity_for_diagnostics(client,monkeypatch,envelope):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();value=result({});value['data']['outputs']=envelope;calls,_=remote(monkeypatch,t,env,result=value)
 r=execute(client,t,q);assert r.status_code==502 and 'private-output' not in r.text and len(calls)==3
 row=main.store.get(KIND,q['id']);assert row['output_contract_rejected'] is True and row['workflow_run_id']==RUN and row['state']=='unknown'
 record=main.get_task(t['id'])['runs'][-1];assert record['status']=='unknown' and record['result']['data']['id']==RUN and record['result']['data']['workflow_id']==PUBLISHED and 'outputs' not in record['result']['data']
 d=client.post(f"/api/tasks/{t['id']}/runs/{record['id']}/diagnose",json={'revision':t['revision'],'read_remote':False});assert d.status_code==200 and d.json()['remote_run_id']==RUN and len(calls)==3

def structured(root):
 llm=root['workflow']['graph']['nodes'][2]['data'];llm.update(structured_output_enabled=True,structured_output={'schema':shape()})
 end=root['workflow']['graph']['nodes'][-1]['data']['outputs'][0];end.update(value_selector=['summary','structured_output'],value_type='object')

def ready(client,monkeypatch):return uploaded_model(client,monkeypatch,patch=structured)
def result(value):return {'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'succeeded','outputs':{'result':value},'total_tokens':20,'elapsed_time':0.2}}
def execute(client,t,q,**patch):return run(client,t,q,acknowledge_model_egress=True,acknowledge_unpriced_model_cost=True,**patch)

def test_structured_file_plan_freezes_full_schema_without_network_or_task_change(client,monkeypatch):
 t,env,p,root=ready(client,monkeypatch);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*args,**kwargs):pytest.fail('准备Schema文件方案不联网、解密或调用模型')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 r=plan(client,t,p,inputs(p));assert r.status_code==200,r.text;q=r.json();f=q['data_flow'];s=f['structured_output']
 assert q['plan_schema_version']==6 and f['schema_version']==5 and f['scenario']=='document_model_object' and f['output_kind']=='json-object'
 assert s['schema']==shape() and json.loads(s['schema_text'])==shape() and s['node_id']=='summary' and s['output_variable']=='result'
 assert s['verification']=='declared_schema_and_local_instance_check_only' and f['model_egress'] and f['planned_llm_node_executions']==1
 assert f['prompt_template']==root['workflow']['graph']['nodes'][2]['data']['prompt_template'] and f['cost_estimate_usd'] is None and not f['hard_cost_cap']
 assert '真正JSON对象' in q['note'] and main.get_task(t['id'])==before

@pytest.mark.parametrize('output',[{'customer':'甲','approved':False},{'customer':'甲','approved':True,'amount':12.5,'tags':['A','B']}])
def test_schema_valid_real_object_is_preserved_and_runs_once_with_existing_egress_cost_approvals(client,monkeypatch,output):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();calls,_=remote(monkeypatch,t,env,result=result(output))
 assert run(client,t,q).status_code==422 and not calls
 r=execute(client,t,q);assert r.status_code==200,r.text;record=r.json()['task']['runs'][-1]
 assert record['status']=='success' and record['result']['data']['outputs']=={'result':output} and [c[0] for c in calls]==['keys','published','run']
 assert not record.get('evaluation') and execute(client,t,q).status_code==409 and len(calls)==3

@pytest.mark.parametrize('output',['{"customer":"甲","approved":true}',[],None,True,{}, {'customer':'甲'},{'customer':'','approved':True},{'customer':'甲','approved':1},{'customer':'甲','approved':True,'extra':'private-value'},{'customer':'甲','approved':True,'amount':-1},{'customer':'甲','approved':True,'tags':['1','2','3','4']},{'customer':'甲','approved':True,'amount':9007199254740992},{'customer':'甲','approved':True,'amount':float('nan')},{'customer':'\ud800','approved':True},{'customer':'x'*64000,'approved':True}])
def test_invalid_structured_receipt_is_not_coerced_repaired_or_retried(client,monkeypatch,output):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();calls,_=remote(monkeypatch,t,env,result=result(output));r=execute(client,t,q)
 assert r.status_code==502,r.text;assert main.store.get(KIND,q['id'])['state']=='unknown' and main.get_task(t['id'])['runs'][-1]['status']=='unknown'
 assert 'private-value' not in r.text and execute(client,t,q).status_code==409 and len(calls)==3
 saved=main.get_task(t['id'])['runs'][-1];assert saved['result']=={'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'succeeded'}}
 assert main.store.get(KIND,q['id'])['output_contract_rejected'] is True
 d=client.post(f"/api/tasks/{t['id']}/runs/{saved['id']}/diagnose",json={'revision':t['revision'],'read_remote':False})
 assert d.status_code==200 and d.json()['remote_run_id']==RUN and len(calls)==3

@pytest.mark.parametrize('mutation',['text_end','nested_field','two_outputs','extra_schema','unbounded_object','union','wrong_schema_root','list_input'])
def test_unsupported_structured_scope_never_drops_rules_or_changes_output_kind(mutation):
 root=yaml.safe_load(model_document());structured(root);nodes=root['workflow']['graph']['nodes'];schema=nodes[2]['data']['structured_output']['schema'];outputs=nodes[-1]['data']['outputs']
 if mutation=='text_end':outputs[0]['value_selector']=['summary','text']
 elif mutation=='nested_field':outputs[0]['value_selector']=['summary','structured_output','customer']
 elif mutation=='two_outputs':outputs.append(copy.deepcopy(outputs[0]))
 elif mutation=='extra_schema':nodes[2]['data']['structured_output']['future_mode']='unknown'
 elif mutation=='unbounded_object':schema['additionalProperties']=True
 elif mutation=='union':schema['properties']['customer']['anyOf']=[{'type':'string'},{'type':'number'}]
 elif mutation=='wrong_schema_root':schema['type']='array'
 elif mutation=='list_input':nodes[0]['data']['variables'][0].update(type='file-list',max_length=5);nodes[1]['data']['is_array_file']=True
 before=copy.deepcopy(root)
 with pytest.raises(ValueError):describe(root)
 assert root==before

def test_schema_change_invalidates_original_proposal_before_any_remote_read(client,monkeypatch):
 t,env,p,root=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();calls,_=remote(monkeypatch,t,env)
 root['workflow']['graph']['nodes'][2]['data']['structured_output']['schema']['required'].append('amount');main.artifact_path(t).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8')
 assert execute(client,t,q).status_code==409 and not calls

def test_old_text_approval_cannot_be_upgraded_to_object_output(client,monkeypatch):
 t,env,p,_=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();row=main.store.get(KIND,q['id']);row['plan_schema_version']=4;row['resource_token']=plan_token(row);main.store.put(KIND,row['id'],row);calls,_=remote(monkeypatch,t,env)
 assert execute(client,t,row).status_code==409 and not calls

def test_final_bytes_cannot_change_between_file_source_proof_and_flow_description(client,monkeypatch):
 from app import file_run as module
 t,env,p,_=ready(client,monkeypatch);original=module.target
 def changed(h,task):
  value=original(h,task);path=main.artifact_path(task);path.write_bytes(path.read_bytes()+b'\n# changed between bounded reads\n');return value
 monkeypatch.setattr(module,'target',changed);r=plan(client,t,p,inputs(p))
 assert r.status_code==409 and not main.store.list(KIND) and not main.get_task(t['id'])['runs']

def test_frozen_schema_text_preserves_large_numeric_limit_even_when_no_amount_is_returned():
 root=yaml.safe_load(model_document());structured(root);value=900719925474099312345678901;root['workflow']['graph']['nodes'][2]['data']['structured_output']['schema']['properties']['amount']['maximum']=value
 s=describe(root)['structured_output'];assert s['schema']['properties']['amount']['maximum']==value and str(value) in s['schema_text']

def test_structured_file_fixed_case_uses_original_object_and_declared_schema_rule(client,monkeypatch):
 t,env,p,_=ready(client,monkeypatch);values=inputs(p);c=client.post(f"/api/tasks/{t['id']}/file-cases/capture",json={'revision':t['revision'],'catalog_revision':0,'input_text':json.dumps(values),'name':'对象提取规则','expectation':{'mode':'json_schema','target':'result','expected':shape()}});assert c.status_code==200,c.text;catalog=c.json()
 q=client.post(f"/api/tasks/{t['id']}/file-runs/prepare",json={'revision':t['revision'],'input_text':json.dumps(values),'case_id':catalog['saved_case_id'],'case_catalog_revision':1});assert q.status_code==200,q.text
 output={'customer':'甲','approved':False};remote(monkeypatch,t,env,result=result(output));r=execute(client,t,q.json());assert r.status_code==200,r.text
 assert r.json()['task']['runs'][-1]['result']['data']['outputs']['result']==output and client.get(f"/api/tasks/{t['id']}/acceptance").json()['required']['passed']==1
 record=r.json()['task']['runs'][-1];e=client.get(f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/evidence");assert e.status_code==200,e.text;e=e.json()
 assert e['outputs_available'] and json.loads(e['outputs_preview'])=={'result':output} and not e['network_requested']
 download=client.get(f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/outputs.json",params={'sha256':e['outputs_sha256']});assert download.status_code==200 and download.json()=={'result':output}
 row=main.store.get(KIND,q.json()['id']);row['model_egress_approved']=False;main.store.put(KIND,row['id'],row)
 assert client.get(f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/evidence").status_code==422
 row['model_egress_approved']=True;row['data_flow']['structured_output']['schema']['required'].append('amount');main.store.put(KIND,row['id'],row)
 assert client.get(f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/evidence").status_code==422
