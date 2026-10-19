import asyncio,base64,copy,json,time,uuid
import pytest,yaml
from test_api import client,approved,create_env
from test_file_inputs import plan
from test_workflow_plan import plan_task
from app.workflow_plan import compile_workflow_plan
from app import main
from app.runtime_files import KIND,MAX_BYTES
from app.dify import DifyError

CONTENT=b'private-file-content-sentinel'
APP=str(uuid.uuid4());REMOTE=str(uuid.uuid4());OWNER=str(uuid.uuid4())


def ready(client,kind='file'):
 env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':APP,'service_api_key':'fixture-service-key'})
 t=approved(client,env_id=env['id']);t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();main.artifact_path(t).write_text(compile_workflow_plan(plan_task(plan(kind)))[0],encoding='utf-8');t['dify_app_id']=APP;main.save_task(t);return t,env


def prepare(client,t,**patch):return client.post(f"/api/tasks/{t['id']}/runtime-files/prepare",content=json.dumps({'revision':t['revision'],'variable':'document','filename':'sample.txt','content_base64':base64.b64encode(CONTENT).decode(),**patch},ensure_ascii=True),headers={'content-type':'application/json'})
def execute(client,t,p,**patch):return client.post(f"/api/tasks/{t['id']}/runtime-files/{p['id']}/execute",json={'revision':t['revision'],'resource_token':p['resource_token'],'acknowledge_upload':True,'note':'已核对文件内容和原目标，只批准这个文件单次上传。',**patch})
def receipt(name='sample.txt',size=len(CONTENT)):return {'id':REMOTE,'name':name,'size':size,'created_by':OWNER,'preview_url':'private-signed-url-sentinel','file_key':'private-storage-key-sentinel'}

@pytest.mark.parametrize('kind',['file','file-list'])
def test_local_encrypted_prepare_keeps_original_task_and_never_decrypts_or_requests(client,monkeypatch,kind):
 t,env=ready(client,kind);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('prepare不得联网、解密或调用模型')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 r=prepare(client,t);assert r.status_code==200,r.text;p=r.json();assert p['state']=='prepared' and p['size']==len(CONTENT) and p['attempts']==0
 assert p['input_kind']==kind and p['upload_count']==1 and p['model_calls']==p['workflow_runs']==0 and not p['runtime_reference_ready']
 assert 'credential_stamp' not in p and 'file_content' not in r.text and 'content_base64' not in r.text and CONTENT.decode() not in r.text
 with main.store.connect() as conn:
  blob=bytes(conn.execute('select value from secrets where id=?',(p['id']+':file_content',)).fetchone()[0]);assert CONTENT not in blob and base64.b64encode(CONTENT) not in blob
 assert main.get_task(t['id'])==before

@pytest.mark.parametrize('patch',[{'filename':'../x.txt'},{'filename':'C:\\x.txt'},{'filename':'x\n.txt'},{'filename':' x.txt'},{'filename':'x.exe'},{'filename':'x.md'},{'filename':'\ud800.txt'},{'content_base64':'private-not-base64'},{'content_base64':''},{'variable':'missing'},{'revision':True},{'unknown':'private-field-sentinel'}])
def test_invalid_staging_does_not_store_body_or_ignore_policy(client,patch):
 t,_=ready(client);r=prepare(client,t,**patch);assert r.status_code in (409,422),r.text
 assert not main.store.list(KIND) and 'private-not-base64' not in r.text and 'private-field-sentinel' not in r.text


def test_size_duplicate_keys_and_five_pending_plans_have_explicit_limits(client):
 t,_=ready(client);r=prepare(client,t,content_base64=base64.b64encode(b'x'*(MAX_BYTES+1)).decode());assert r.status_code==422
 raw=json.dumps({'revision':t['revision'],'variable':'document','filename':'x.txt','content_base64':'eA=='});raw=raw[:-1]+',"filename":"private-second.txt"}'
 r=client.post(f"/api/tasks/{t['id']}/runtime-files/prepare",content=raw,headers={'content-type':'application/json'});assert r.status_code==422 and 'private-second.txt' not in r.text
 for _ in range(5):assert prepare(client,t).status_code==200
 assert prepare(client,t).status_code==409


def test_explicit_single_upload_frozen_key_original_bytes_no_runtime_reference(client,monkeypatch):
 t,env=ready(client);p=prepare(client,t).json();before=copy.deepcopy(main.get_task(t['id']));calls=[]
 async def upload(self,name,content,mime):calls.append((self.store.secret(env['id'],'service_api_key'),name,content,mime));return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload)
 r=execute(client,t,p);assert r.status_code==200,r.text;v=r.json();assert v['state']=='uploaded' and v['attempts']==1 and v['remote_upload_observed'] and not v['runtime_reference_ready'] and not v['platform_target_verified']
 assert calls==[('fixture-service-key','sample.txt',CONTENT,'text/plain')]
 assert all(secret not in r.text for secret in ('fixture-service-key','private-signed-url-sentinel','private-storage-key-sentinel',REMOTE,OWNER,CONTENT.decode()))
 assert main.store.secret(p['id'],'file_content')=='' and main.get_task(t['id'])==before
 assert execute(client,t,p).status_code==409 and len(calls)==1

@pytest.mark.parametrize('mutation',['revision','artifact','key','app','url','expiry','token'])
def test_changed_approved_context_stops_before_remote_or_attempt(client,monkeypatch,mutation):
 t,env=ready(client);p=prepare(client,t).json()
 if mutation=='revision':t['revision']+=1;main.save_task(t)
 elif mutation=='artifact':main.artifact_path(t).write_text(main.artifact_path(t).read_text(encoding='utf-8')+'\n',encoding='utf-8')
 elif mutation=='key':main.store.set_secret(env['id'],'service_api_key','different-key')
 elif mutation in ('app','url'):
  e=main.store.get('environment',env['id']);e['service_app_id' if mutation=='app' else 'base_url']=str(uuid.uuid4()) if mutation=='app' else 'https://other.invalid';main.store.put('environment',env['id'],e)
 elif mutation=='expiry':row=main.store.get(KIND,p['id']);row['expires_at']=time.time()-1;main.store.put(KIND,p['id'],row)
 elif mutation=='token':p['resource_token']='0'*64
 async def forbidden(*a,**kw):pytest.fail('旧批准不得派发')
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',forbidden)
 r=execute(client,t,p);assert r.status_code in (409,422),r.text;assert main.store.get(KIND,p['id'])['attempts']==0

@pytest.mark.parametrize('patch',[{'acknowledge_upload':False},{'acknowledge_upload':1},{'note':''},{'resource_token':'bad'}])
def test_missing_explicit_approval_refused(client,patch):
 t,_=ready(client);p=prepare(client,t).json();r=execute(client,t,p,**patch);assert r.status_code==422 and main.store.get(KIND,p['id'])['attempts']==0

@pytest.mark.parametrize('failure',['timeout','http413','bad-receipt','interrupt'])
def test_uncertain_result_preserves_one_attempt_without_retries_or_body(client,monkeypatch,failure):
 t,_=ready(client);p=prepare(client,t).json();calls=[]
 async def upload(*a,**kw):
  calls.append(True)
  if failure=='timeout':raise TimeoutError('private-transport-sentinel')
  if failure=='http413':raise DifyError('private-error-sentinel',http_status=413)
  if failure=='interrupt':raise asyncio.CancelledError()
  return {'id':REMOTE,'name':'sample.txt','size':True,'created_by':OWNER}
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload);r=execute(client,t,p);assert r.status_code in (502,504) and 'private-' not in r.text
 row=main.store.get(KIND,p['id']);assert row['state']=='unknown' and row['attempts']==1 and main.store.secret(p['id'],'file_content')==''
 assert execute(client,t,p).status_code==409 and len(calls)==1
 if failure=='http413':assert row['http_status']==413 and 'HTTP 413' in row['message']


def test_key_change_after_dispatch_keeps_original_target_receipt_and_does_not_reuse(client,monkeypatch):
 t,env=ready(client);p=prepare(client,t).json()
 async def upload(self,*a):
  main.store.set_secret(env['id'],'service_api_key','changed-mid-upload');assert self.store.secret(env['id'],'service_api_key')=='fixture-service-key';return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload);r=execute(client,t,p);assert r.status_code==200,r.text
 assert r.json()['state']=='uploaded_stale' and r.json()['remote_upload_observed'] and main.store.get(KIND,p['id'])['remote_id']==REMOTE


def test_busy_task_edits_and_startup_recovery_do_not_restart_upload(client,monkeypatch):
 t,_=ready(client);p=prepare(client,t).json();row=main.store.get(KIND,p['id']);row.update(state='executing',attempts=1);main.store.put(KIND,p['id'],row)
 assert client.patch(f"/api/tasks/{t['id']}",json={'name':'修改中'}).status_code==409
 main.runtime_files.recover();assert main.store.get(KIND,p['id'])['state']=='unknown' and main.store.secret(p['id'],'file_content')==''
 assert execute(client,t,p).status_code==409


def test_discard_and_history_remain_available_after_revision_changes_without_foreign_access(client):
 t,_=ready(client);p=prepare(client,t).json();other,_=ready(client)
 assert client.post(f"/api/tasks/{other['id']}/runtime-files/{p['id']}/discard").status_code==404
 t['revision']+=1;main.save_task(t);r=client.get(f"/api/tasks/{t['id']}/runtime-files");assert r.status_code==200 and r.json()['records'][0]['revision']==p['revision']
 r=client.post(f"/api/tasks/{t['id']}/runtime-files/{p['id']}/discard");assert r.status_code==200 and r.json()['state']=='discarded' and main.store.secret(p['id'],'file_content')==''


def test_resource_progress_exposes_only_safe_metadata_and_keeps_old_context(client):
 t,_=ready(client);p=prepare(client,t).json();t['revision']+=1;main.save_task(t)
 r=client.get(f"/api/tasks/{t['id']}/resource-progress");assert r.status_code==200
 row=next(x for x in r.json()['records'] if x['kind']==KIND);assert row['state']=='prepared' and not row['current_revision']
 assert 'content_sha256' not in r.text and CONTENT.decode() not in r.text and 'credential_stamp' not in r.text


def test_adapter_sends_single_multipart_file_and_same_end_user_without_network(monkeypatch):
 from app.dify import DifyClient
 calls=[]
 async def request(self,method,path,**kw):calls.append((method,path,kw));return receipt()
 monkeypatch.setattr(DifyClient,'request',request);d=DifyClient({'id':'fixture','base_url':'https://dify.example'},None)
 asyncio.run(d.upload_runtime_file('sample.txt',CONTENT,'text/plain'))
 assert calls==[('POST','/v1/files/upload',{'credential':'service_api_key','files':{'file':('sample.txt',CONTENT,'text/plain')},'data':{'user':'flowcraft-local'}})]


def test_ciphertext_corruption_or_body_hash_change_refused_before_attempt(client,monkeypatch):
 t,_=ready(client);p=prepare(client,t).json();main.store.set_secret(p['id'],'file_content',base64.b64encode(b'changed').decode())
 async def forbidden(*a,**kw):pytest.fail('不可派发损坏正文')
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',forbidden)
 assert execute(client,t,p).status_code==409 and main.store.get(KIND,p['id'])['attempts']==0


def test_target_deleted_after_remote_receipt_retains_known_remote_identifier(client,monkeypatch):
 t,env=ready(client);p=prepare(client,t).json()
 async def upload(*a,**kw):main.store.delete('environment',env['id']);return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload);r=execute(client,t,p);assert r.status_code==422
 row=main.store.get(KIND,p['id']);assert row['state']=='unknown' and row['remote_upload_observed'] and row['remote_id']==REMOTE and row['attempts']==1
 assert main.store.secret(p['id'],'file_content')==''


def test_final_file_declarations_read_without_environment_or_decryption(client,monkeypatch):
 t,env=ready(client);main.store.delete('environment',env['id']);before=copy.deepcopy(main.get_task(t['id']))
 monkeypatch.setattr(main.store,'secret',lambda *a,**kw:pytest.fail('读声明不能解密'))
 r=client.get(f"/api/tasks/{t['id']}/runtime-files/source",params={'revision':t['revision']});assert r.status_code==200,r.text
 assert r.json()['fields'][0]['variable']=='document' and r.json()['max_bytes']==2000000 and not r.json()['network_requested'] and main.get_task(t['id'])==before


def test_uploaded_receipt_does_not_unlock_raw_file_reference_run(client,monkeypatch):
 t,_=ready(client);p=prepare(client,t).json()
 async def upload(*a,**kw):return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload);assert execute(client,t,p).status_code==200
 def forbidden(*a,**kw):pytest.fail('没有可信运行绑定，不得派发')
 monkeypatch.setattr(main.DifyClient,'run_workflow',forbidden);monkeypatch.setattr(main.execution_limits,'require_start',forbidden)
 r=client.post(f"/api/tasks/{t['id']}/run",json={'revision':t['revision'],'input':{'document':{'type':'document','transfer_method':'local_file','upload_file_id':REMOTE}}});assert r.status_code==422 and '冻结运行绑定' in r.text


def test_bounded_request_body_and_sensitive_validation_errors_do_not_echo(client):
 t,_=ready(client)
 r=client.post(f"/api/tasks/{t['id']}/runtime-files/prepare",content=b'x'*2800001,headers={'content-type':'application/json'});assert r.status_code==413 and not main.store.list(KIND)
 p=prepare(client,t).json();r=execute(client,t,p,acknowledge_upload='private-confirmation-sentinel');assert r.status_code==422 and 'private-confirmation-sentinel' not in r.text and '文件操作方案' in r.text
