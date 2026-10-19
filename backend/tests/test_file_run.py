import asyncio,copy,json,time,uuid
import pytest,yaml
from test_api import client
from test_runtime_files import ready,prepare,execute,receipt,APP,REMOTE,OWNER
from app import main
from app.file_run import KIND
from app.runtime_files import KIND as UPLOAD
from app.file_run import failed_receipt
from app.dify import DifyError

PUBLISHED=str(uuid.uuid4());RUN=str(uuid.uuid4())

def uploaded(client,monkeypatch,kind='file'):
 t,env=ready(client,kind)
 main.store.set_secret(env['id'],'console_token','fixture-console-token')
 async def upload(*args):return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload)
 p=prepare(client,t).json();assert execute(client,t,p).status_code==200
 return t,env,p

def plan(client,t,p,values=None):
 if values is None:values={'document':{'sierra_file_id':p['id']}}
 return client.post(f"/api/tasks/{t['id']}/file-runs/prepare",json={'revision':t['revision'],'input_text':json.dumps(values)})
def run(client,t,p,**patch):return client.post(f"/api/tasks/{t['id']}/file-runs/{p['id']}/execute",json={'revision':t['revision'],'resource_token':p['resource_token'],'acknowledge_run':True,**patch})
def remote(monkeypatch,t,env,*,keys=None,published=None,result=None):
 calls=[];root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'));workflow={**root['workflow'],'id':PUBLISHED}
 async def request(self,method,path,**kw):
  calls.append(('keys',method,path));assert method=='GET' and path==f'/console/api/apps/{APP}/api-keys';assert self.store.secret(env['id'],'console_token')=='fixture-console-token'
  return keys if keys is not None else {'data':[{'id':str(uuid.uuid4()),'token':'fixture-service-key'}]}
 async def publish(self,app_id):calls.append(('published',app_id));return published if published is not None else workflow
 async def workflow_run(self,values):
  calls.append(('run',copy.deepcopy(values)));assert self.store.secret(env['id'],'service_api_key')=='fixture-service-key'
  return result if result is not None else {'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'succeeded','outputs':{'result':'真实提取文字的隔离回执'},'total_tokens':0,'elapsed_time':0.2},'private_upload_id':REMOTE}
 monkeypatch.setattr(main.DifyClient,'request',request);monkeypatch.setattr(main.DifyClient,'published_workflow',publish);monkeypatch.setattr(main.DifyClient,'run_workflow',workflow_run)
 return calls,workflow

def test_prepare_is_local_no_decryption_and_keeps_private_remote_ids_out_of_public_plan(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('准备阶段不能联网、解密或调用模型')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 r=plan(client,t,p);assert r.status_code==200,r.text
 v=r.json();assert v['state']=='prepared' and v['attempts']==0 and v['files'][0]['id']==p['id'] and v['workflow_runs']==1
 assert all(s not in r.text for s in [REMOTE,OWNER,'fixture-service-key','fixture-console-token','credential_stamp','file_binding_digest'])
 assert main.get_task(t['id'])==before

def test_successful_frozen_file_run_records_opaque_input_and_normal_result_once(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,_=remote(monkeypatch,t,env)
 r=run(client,t,q);assert r.status_code==200,r.text;v=r.json();assert v['plan']['state']=='platform_finished' and not v['plan']['business_verified']
 record=v['task']['runs'][-1];assert record['status']=='success' and record['input']==q['input'] and record['result']['data']['outputs']['result']=='真实提取文字的隔离回执'
 assert record['id']==v['plan']['run_id'] and 'evaluation' not in record and REMOTE not in json.dumps(v)
 assert [c[0] for c in calls]==['keys','published','run'] and calls[-1][1]=={'document':{'type':'document','transfer_method':'local_file','upload_file_id':REMOTE}}
 assert run(client,t,q).status_code==409 and len(calls)==3
 assert client.get(f"/api/tasks/{t['id']}/resource-progress").json()['totals']['total']==2

@pytest.mark.parametrize('values',[{}, {'document':None},{'document':{'upload_file_id':REMOTE}},{'document':{'sierra_file_id':str(uuid.uuid4())}},{'document':{'sierra_file_id':REMOTE,'url':'https://private.invalid'}},{'document':[]},{'document':{'sierra_file_id':REMOTE},'extra':'private'}],ids=['missing','null','native-id','unknown-record','mixed-url','wrong-list','unknown-field'])
def test_untrusted_values_never_prepare_or_dispatch(client,monkeypatch,values):
 t,_,p=uploaded(client,monkeypatch);r=plan(client,t,p,values);assert r.status_code in (409,422),r.text;assert not main.store.list(KIND)

@pytest.mark.parametrize('mutation',['task','revision','artifact','variable','kind','key','url','app','owner','state','receipt','extension'])
def test_upload_provenance_mutations_cannot_be_adopted(client,monkeypatch,mutation):
 t,env,p=uploaded(client,monkeypatch);r=main.store.get(UPLOAD,p['id'])
 mapping={'task':('task_id',str(uuid.uuid4())),'revision':('revision',t['revision']+1),'artifact':('artifact_sha256','a'*64),'variable':('variable','other'),'kind':('input_kind','file-list'),'key':('credential_stamp','a'*64),'url':('environment_url','https://different.invalid'),'app':('app_id',str(uuid.uuid4())),'owner':('remote_created_by','bad'),'state':('state','unknown'),'receipt':('remote_upload_observed',False),'extension':('filename','file.pdf')}
 key,value=mapping[mutation];r[key]=value;main.store.put(UPLOAD,p['id'],r)
 assert plan(client,t,p).status_code in (409,422)

@pytest.mark.parametrize('keys',[{}, {'data':[]},{'data':[{'id':str(uuid.uuid4()),'token':'wrong-key'}]},{'data':[{'id':'bad','token':'fixture-service-key'}]},{'data':[{'id':str(uuid.uuid4()),'token':'fixture-service-key'},{'id':str(uuid.uuid4()),'token':'fixture-service-key'}]}],ids=['missing','empty','different','malformed','ambiguous'])
def test_service_key_ownership_requires_unique_exact_match_before_any_run(client,monkeypatch,keys):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,_=remote(monkeypatch,t,env,keys=keys)
 r=run(client,t,q);assert r.status_code==502 and [c[0] for c in calls]==['keys'];assert main.store.get(KIND,q['id'])['state']=='not_dispatched' and not main.get_task(t['id'])['runs']

@pytest.mark.parametrize('mutation',['graph','features','variables','id'])
def test_actual_published_graph_config_and_id_must_match(client,monkeypatch,mutation):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,workflow=remote(monkeypatch,t,env)
 if mutation=='graph':workflow['graph']['nodes'][1]['data']['desc']='changed'
 elif mutation=='features':workflow['features']['new_flag']=True
 elif mutation=='variables':workflow.pop('environment_variables')
 else:workflow['id']='bad'
 assert run(client,t,q).status_code==502 and [c[0] for c in calls]==['keys','published'] and not main.get_task(t['id'])['runs']

@pytest.mark.parametrize('mutation',['service','console','artifact','revision','receipt'])
def test_changes_during_readonly_verification_prevent_run_and_pending_record(client,monkeypatch,mutation):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,workflow=remote(monkeypatch,t,env)
 async def publish(self,app):
  if mutation in ('service','console'):main.store.set_secret(env['id'],'service_api_key' if mutation=='service' else 'console_token','changed')
  elif mutation=='artifact':main.artifact_path(t).write_text(main.artifact_path(t).read_text(encoding='utf-8')+'\n',encoding='utf-8')
  elif mutation=='receipt':r=main.store.get(UPLOAD,p['id']);r['remote_id']=str(uuid.uuid4());main.store.put(UPLOAD,p['id'],r)
  else:current=main.get_task(t['id']);current['revision']+=1;main.save_task(current)
  return workflow
 monkeypatch.setattr(main.DifyClient,'published_workflow',publish);assert run(client,t,q).status_code==409 and not main.get_task(t['id'])['runs'];assert not any(c[0]=='run' for c in calls)

@pytest.mark.parametrize('result',[{'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':str(uuid.uuid4()),'status':'succeeded'}},{'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'paused','form_token':'private-form-token'}},{'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'succeeded','outputs':{'result':{'upload_file_id':REMOTE}}}}],ids=['different-publish','paused','file-output'])
def test_uncertain_runtime_is_not_success_and_does_not_leak_raw_file_or_form_receipt(client,monkeypatch,result):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,_=remote(monkeypatch,t,env,result=result)
 assert run(client,t,q).status_code==502;row=main.get_task(t['id']);record=row['runs'][-1];assert record['status']=='unknown' and 'result' not in record
 assert main.store.get(KIND,q['id'])['state']=='unknown' and REMOTE not in json.dumps(row) and 'private-form-token' not in json.dumps(row)
 assert run(client,t,q).status_code==409 and [c[0] for c in calls].count('run')==1

@pytest.mark.parametrize('empty',[False,True])
def test_file_list_preserves_order_duplicates_and_empty_array(client,monkeypatch,empty):
 t,env,p=uploaded(client,monkeypatch,'file-list');values={'document':[] if empty else [{'sierra_file_id':p['id']},{'sierra_file_id':p['id']}]};q=plan(client,t,p,values).json()
 text=[] if empty else ['first','first'];result={'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'succeeded','outputs':{'result':text}}};calls,_=remote(monkeypatch,t,env,result=result)
 r=run(client,t,q);assert r.status_code==200,r.text;assert len(calls[-1][1]['document'])==len(text) and r.json()['task']['runs'][-1]['input']==values

def test_explicit_approval_expiry_and_restart_never_replay(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,_=remote(monkeypatch,t,env)
 assert run(client,t,q,acknowledge_run=False).status_code==422 and not calls
 row=main.store.get(KIND,q['id']);row['expires_at']=time.time()-1;main.store.put(KIND,q['id'],row);assert run(client,t,q).status_code==409
 row.update(state='verifying',attempts=1);main.store.put(KIND,q['id'],row);main.file_runs.recover();assert main.store.get(KIND,q['id'])['state']=='not_dispatched' and not calls

def test_strict_json_rejects_duplicate_keys_and_nonfinite_without_echo(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch)
 for raw in ['{"document":{},"document":"private-sentinel"}','{"document":NaN}','[]']:
  r=client.post(f"/api/tasks/{t['id']}/file-runs/prepare",json={'revision':t['revision'],'input_text':raw});assert r.status_code==422 and 'private-sentinel' not in r.text

def test_normal_run_still_refuses_raw_or_opaque_file_values_without_new_plan(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);calls,_=remote(monkeypatch,t,env)
 assert client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':{'document':{'sierra_file_id':p['id']}}}).status_code==422 and not calls

def test_file_run_budget_and_confirmation_gates_still_apply(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,_=remote(monkeypatch,t,env)
 main.store.put('execution_limits',t['id'],{'id':t['id'],'policy_revision':1,'max_started_runs':0,'max_total_minutes':None,'history':[]})
 assert run(client,t,q).status_code in (409,422) and not main.get_task(t['id'])['runs'] and not any(c[0]=='run' for c in calls)

@pytest.mark.parametrize('failure',['timeout','cancel','transport'])
def test_request_interruption_keeps_normal_record_unknown_and_does_not_retry(client,monkeypatch,failure):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,_=remote(monkeypatch,t,env)
 async def broken(*a):
  calls.append(('broken-run',))
  if failure=='timeout':raise TimeoutError('private-transport-error')
  if failure=='cancel':raise asyncio.CancelledError()
  raise RuntimeError('private-transport-error')
 monkeypatch.setattr(main.DifyClient,'run_workflow',broken)
 r=run(client,t,q);assert r.status_code==502 and 'private-transport-error' not in r.text
 record=main.get_task(t['id'])['runs'][-1];assert record['status']=='unknown' and not record.get('result')
 assert run(client,t,q).status_code==409 and [c[0] for c in calls].count('broken-run')==1

def test_expiry_during_readonly_verification_never_dispatches(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,workflow=remote(monkeypatch,t,env);clock=[time.time()]
 monkeypatch.setattr('app.file_run.time.time',lambda:clock[0])
 async def publish(*a):clock[0]=q['expires_at']+1;return workflow
 monkeypatch.setattr(main.DifyClient,'published_workflow',publish)
 assert run(client,t,q).status_code==409 and not main.get_task(t['id'])['runs'] and not any(c[0]=='run' for c in calls)

def test_unadapted_graph_does_not_get_simplified_and_file_outputs_are_refused(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'));end=next(n for n in root['workflow']['graph']['nodes'] if n['data']['type']=='end');end['data']['outputs'][0]['value_selector']=['start','document']
 main.artifact_path(t).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8');r=plan(client,t,p);assert r.status_code==422 and not main.store.list(KIND)

def test_history_and_resource_index_do_not_expose_file_content_or_native_ids(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();main.store.get(KIND,q['id'])
 history=client.get(f"/api/tasks/{t['id']}/file-runs");index=client.get(f"/api/tasks/{t['id']}/resource-progress")
 assert history.status_code==index.status_code==200 and history.json()['records'][0]['id']==q['id']
 for raw in (history.text,index.text):assert all(secret not in raw for secret in (REMOTE,OWNER,'fixture-service-key','fixture-console-token','private-file-content-sentinel'))
 assert 'sample.txt' not in index.text and 'sierra_file_id' not in index.text

@pytest.mark.parametrize('status',['failed','stopped','partial-succeeded'])
def test_known_terminal_failure_keeps_safe_ids_and_explicit_diagnostic_reader(client,monkeypatch,status):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json()
 raw={'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':status,'total_tokens':0,'elapsed_time':0.2,'outputs':{'private_file':{'upload_file_id':REMOTE}},'error':'private-parser-error','reasons':[{'form_token':'private-form-token'}]},'private_field':'private-extra'}
 calls,_=remote(monkeypatch,t,env,result=raw)
 r=run(client,t,q);assert r.status_code==502
 task=main.get_task(t['id']);record=task['runs'][-1];assert record['status']=='failed' and record['result']['data']['status']==status and record['result']['workflow_run_id']==RUN and record['result']['data']['total_tokens']==0
 assert all(s not in json.dumps(record) for s in (REMOTE,'private-parser-error','private-form-token','private-extra'))
 stored=main.store.get(KIND,q['id']);assert stored['state']=='platform_failed' and stored['workflow_run_id']==RUN
 index=client.get(f"/api/tasks/{t['id']}/resource-progress").json();entry=next(v for v in index['records'] if v['kind']==KIND);assert not entry['ongoing'] and not entry['uncertain'] and entry['workflow_run_id']==RUN
 local=client.post(f"/api/tasks/{t['id']}/runs/{record['id']}/diagnose",json={'revision':t['revision'],'read_remote':False});assert local.status_code==200 and local.json()['remote_run_id']==RUN and [c[0] for c in calls]==['keys','published','run']
 async def read(self,method,path,**kw):
  calls.append(('diagnostic',method,path));assert method=='GET' and kw['credential']=='console_token'
  if path.endswith('/node-executions'):return {'data':[{'id':'extract-execution','node_id':'extract','node_type':'document-extractor','title':'文档提取','status':'failed','error':'Unsupported file type','inputs':{'file_token':'private-trace-token'},'outputs':{}}]}
  return {'id':RUN,'status':status}
 monkeypatch.setattr(main.DifyClient,'request',read)
 read=client.post(f"/api/tasks/{t['id']}/runs/{record['id']}/diagnose",json={'revision':t['revision'],'read_remote':True});assert read.status_code==200,read.text
 report=read.json();assert report['trace_state']=='read' and report['remote_run_id']==RUN and report['nodes'][0]['node_id']=='extract' and 'private-trace-token' not in read.text
 assert [c[0] for c in calls].count('diagnostic')==2 and run(client,t,q).status_code==409

@pytest.mark.parametrize('code',[401,403,413,500])
def test_file_request_http_status_is_safe_and_unknown_without_raw_server_receipt(client,monkeypatch,code):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();calls,_=remote(monkeypatch,t,env)
 async def broken(*a):raise DifyError('private-server-error',result={'token':'private-token'},http_status=code)
 monkeypatch.setattr(main.DifyClient,'run_workflow',broken);assert run(client,t,q).status_code==502
 record=main.get_task(t['id'])['runs'][-1];assert record['status']=='unknown' and record['http_status']==code and str(code) in record['error'] and 'private-' not in json.dumps(record)

@pytest.mark.parametrize('mutation',['different-publish','different-id','missing-id','malformed-status'])
def test_failure_claim_without_same_published_and_run_identity_stays_unknown(client,monkeypatch,mutation):
 t,env,p=uploaded(client,monkeypatch);q=plan(client,t,p).json();raw={'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'failed','outputs':{'secret':'private-failure-output'}}}
 if mutation=='different-publish':raw['data']['workflow_id']=str(uuid.uuid4())
 elif mutation=='different-id':raw['data']['id']=str(uuid.uuid4())
 elif mutation=='missing-id':raw.pop('workflow_run_id')
 else:raw['data']['status']=[]
 remote(monkeypatch,t,env,result=raw);assert run(client,t,q).status_code==502
 record=main.get_task(t['id'])['runs'][-1];assert record['status']=='unknown' and 'result' not in record

def test_failure_receipt_counters_do_not_coerce_or_accept_overflow_nonfinite():
 raw={'workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':PUBLISHED,'status':'failed','total_tokens':False,'total_steps':-1,'created_at':'not-an-int','finished_at':9007199254740992,'elapsed_time':10**400}}
 value=failed_receipt(raw,PUBLISHED);assert set(value['data'])=={'id','workflow_id','status'}
 raw['data']['elapsed_time']=float('nan');assert 'elapsed_time' not in failed_receipt(raw,PUBLISHED)['data']
