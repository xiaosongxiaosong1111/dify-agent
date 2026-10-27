"""Exercise actual HTTPX response streaming/client order, with zero physical transport."""
import asyncio,copy,importlib.util,json,sys
from pathlib import Path
import httpx,pytest
ROOT=Path(__file__).resolve().parents[2];TOOLS=ROOT/'tools/public-batch-platform342'
sys.path[:0]=[str(TOOLS),str(ROOT/"backend")]
from execute import dispatch
from boundary import Boundary
from synthetic_transport import SyntheticDify
from app.dify import DifyClient,DifyError
from test_api import client
from app import main

WORKSPACE='22222222-2222-4222-8222-222222222222'
BASE='https://dify-fixture.invalid'

class Chunks(httpx.AsyncByteStream):
 def __init__(self,raw=b'{"result":"success"}',error=None,close_error=False):self.raw=raw;self.error=error;self.closed=False;self.close_error=close_error
 async def __aiter__(self):
  for i in range(0,len(self.raw),5):yield self.raw[i:i+5]
  if self.error:raise self.error
 async def aclose(self):
  self.closed=True
  if self.close_error:raise RuntimeError('PRIVATE_CLOSE_FAILURE')

@pytest.fixture(autouse=True)
def no_physical_transport(monkeypatch):
 def forbidden(*a,**kw):raise AssertionError('Physical model/Dify/HTTP forbidden')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)

def boundary():
 record={};return Boundary(BASE,WORKSPACE,'public-graph',{'task_name':'public-task','input':{}},record),record

def request():return httpx.Request('POST',BASE+'/console/api/login',json={'email':'public@example.invalid','password':'PUBLIC_BASE64','remember_me':False})

def test_unread_wire_response_gets_request_before_cookie_and_json_observation():
 b,record=boundary();req=request();stream=Chunks();response=httpx.Response(200,headers=[('set-cookie','access_token=PUBLIC_ACCESS; Path=/'),('set-cookie','csrf_token=PUBLIC_CSRF; Path=/')],stream=stream)
 assert not response.is_stream_consumed
 with pytest.raises(RuntimeError):_ = response.request
 async def forward(r):assert r is req;return response
 returned=asyncio.run(dispatch(b,forward,req))
 assert returned is response and response.json()=={'result':'success'} and response.request is req and stream.closed
 assert b.login_tokens=={'console_token':'PUBLIC_ACCESS','csrf_token':'PUBLIC_CSRF'} and not b.halted
 assert record['dispatch_counts']['login']==1 and record['dispatches'][0]['status']==200
 assert record['dispatches'][0]['response_body_read'] is True and 'PUBLIC_ACCESS' not in json.dumps(record) and 'PUBLIC_CSRF' not in json.dumps(record)

@pytest.mark.parametrize('close_error',[False,True])
def test_body_read_failure_closes_and_stops_before_any_next_dispatch(close_error):
 b,record=boundary();stream=Chunks(error=httpx.ReadError('PRIVATE_BODY_FAILURE'),close_error=close_error);response=httpx.Response(200,stream=stream);calls=[]
 async def forward(req):calls.append(req);return response
 with pytest.raises(httpx.ReadError):asyncio.run(dispatch(b,forward,request()))
 assert stream.closed and b.halted and b.login_tokens is None and record['dispatches'][0]['status']==200 and record['dispatches'][0]['response_body_read'] is False
 with pytest.raises(RuntimeError,match='Batch already stopped'):asyncio.run(dispatch(b,forward,request()))
 assert len(calls)==1 and record['dispatch_counts']['login']==1 and 'PRIVATE_' not in json.dumps(record)

@pytest.mark.parametrize('body',[b'<html>PUBLIC_PROXY</html>',b'not-json'])
def test_invalid_json_closes_and_halts_without_recording_response_body(body):
 b,record=boundary();stream=Chunks(body)
 async def forward(req):return httpx.Response(200,stream=stream)
 with pytest.raises(ValueError):asyncio.run(dispatch(b,forward,request()))
 assert stream.closed and b.halted and b.login_tokens is None and record['dispatches'][0]['response_body_read'] is True and 'PUBLIC_PROXY' not in json.dumps(record)

@pytest.mark.parametrize('prefix',['','__Host-'])
def test_real_httpx_client_login_probe_and_pinned_workspace_with_raw_streams(monkeypatch,prefix):
 b,record=boundary();streams=[]
 async def raw_transport(own,req):
  async def forward(request):
   if request.url.path=='/console/api/login':
    payload={'result':'success'};headers=[('set-cookie',prefix+'access_token=PUBLIC_ACCESS; Path=/; Secure'),('set-cookie',prefix+'csrf_token=PUBLIC_CSRF; Path=/; Secure')]
   else:
    assert request.headers['authorization']=='Bearer PUBLIC_ACCESS';payload={'data':[]} if request.url.path=='/console/api/apps' else {'id':WORKSPACE};headers=[]
   stream=Chunks(json.dumps(payload).encode());streams.append(stream);return httpx.Response(200,stream=stream,headers=headers)
  return await dispatch(b,forward,req)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',raw_transport)
 async def exercise():
  adapter=DifyClient({'id':'public-env','base_url':BASE},object());tokens=await adapter.login('public@example.invalid','public-only-password');assert await adapter.login_workspace(tokens)==WORKSPACE
 asyncio.run(exercise());assert b.workspace_verified and len(streams)==3 and all(s.closed for s in streams)
 assert record['dispatch_counts']=={'reads':2,'login':1,'import':0,'publish':0,'key':0,'run':0} and all(e['response_body_read'] for e in record['dispatches'])
 assert 'PUBLIC_ACCESS' not in json.dumps(record) and 'PUBLIC_CSRF' not in json.dumps(record)

@pytest.mark.parametrize('mode',['success','unpublished_404','wrong_workspace','fail_login','import_401','fail_publish','fail_key','lost_key_reply','fail_run','bad_output'])
def test_complete_normal_api_pipeline_with_unread_transport_and_original_guards(client,monkeypatch,mode):
 from data_guard import capture,guarded_store,verify
 from app.storage import Store
 from app.dsl_roundtrip import parse,digest
 from app.workflow_publication import core
 from platform_pipeline import run
 fixture=json.loads((TOOLS/'fixture.json').read_text('utf-8'));graph=digest(core(parse((TOOLS/'candidate.yml').read_text('utf-8'),'workflow')['workflow']))
 env=client.post('/api/environments',json={'name':'公开隔离来源','base_url':BASE,'version':'1.17.1','service_app_id':'11111111-1111-4111-8111-111111111111','service_api_key':'app-PUBLICOLDKEY-FIXTURE'}).json()
 current=main.store.get('environment',env['id']);current.update(console_workspace_id=WORKSPACE,console_login_binding={'base_url':BASE,'version':'1.17.1','workspace_id':WORKSPACE})
 main.store.put_with_secrets('environment',env['id'],current,{'console_login_email':'public@example.invalid','console_login_password':'public-only-password'})
 for i in range(16):assert client.post('/api/tasks',json={'name':'公开保护任务'+str(i),'app_type':'workflow','environment_id':env['id']}).status_code==201
 main.get_settings();old=capture(main.store);record={};b=Boundary(BASE,WORKSPACE,graph,fixture,record,[current['service_app_id']]);Guarded=guarded_store(Store,old,env['id'],b,current,fixture['task_name']);store=Guarded(main.store.root);monkeypatch.setattr(main,'store',store);fake=SyntheticDify(b,mode);streams=[]
 async def transport(own,req):
  async def forward(request):
   response=await fake(request)
   assert not response.is_stream_consumed,'Synthetic transport must match native unread response'
   with pytest.raises(RuntimeError):_=response.request
   streams.append(response)
   if mode=='lost_key_reply' and req.method=='POST' and req.url.path.endswith('/api-keys'):
    await response.aclose();raise httpx.ReadTimeout('PUBLIC_LOST_REPLY',request=req)
   return response
  return await dispatch(b,forward,req)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',transport)
 if mode in ('success','unpublished_404'):
  task,raw=run(client,env['id'],record);assert record['state']=='passed' and record['failure_indices']==[1] and json.loads(raw)['items'][0]['index']==1
  assert len(store.list('task'))==17 and not main.budgets.get(task['id'])['entries']
 else:
  with pytest.raises(Exception):run(client,env['id'],record)
  expected={'wrong_workspace':('reconnect',0,0,0,0),'fail_login':('reconnect',0,0,0,0),'import_401':('import',1,0,0,0),'fail_publish':('publish',1,1,0,0),'fail_key':('create_key',1,1,1,0),'lost_key_reply':('create_key',1,1,1,0),'fail_run':('run',1,1,1,1),'bad_output':('run',1,1,1,1)}[mode]
  assert record['phase']==expected[0] and tuple(b.counts[k] for k in ('import','publish','key','run'))==expected[1:]
  if mode=='lost_key_reply':assert store.list('app_runtime_key_creation')[0]['state']=='unknown'
  if mode=='import_401':assert b.halted and b.counts['login']==1
 assert all(r.is_closed for r in streams) and verify(store,old,env['id'])['original_objects_kept']
 assert b.counts['login']==1 and 'PUBLICCONSOLEFIXTURE' not in json.dumps(record) and 'PUBLICCSRFFIXTURE' not in json.dumps(record)


def imported_boundary():
 b,record=boundary();b.app='33333333-3333-4333-8333-333333333333';b.workspace_verified=True;b.counts['login']=1;b.counts['import']=1
 return b,record

def observed_publish_read(b,value,status=200):
 req=httpx.Request('GET',BASE+f'/console/api/apps/{b.app}/workflows/publish');stream=Chunks(json.dumps(value).encode())
 async def forward(request):return httpx.Response(status,stream=stream)
 return asyncio.run(dispatch(b,forward,req))

def publication_request(b):return httpx.Request('POST',BASE+f'/console/api/apps/{b.app}/workflows/publish',json={'marked_name':'public','marked_comment':'explicit public'})

def test_native_null_absence_allows_only_first_publication_not_false_unknown():
 b,record=imported_boundary();observed_publish_read(b,None)
 assert b.unpublished is True and b.published is None and b.counts['publish']==0
 entry=b.admit(publication_request(b));assert entry['kind']=='publish' and b.counts['publish']==1
 with pytest.raises(RuntimeError):b.admit(publication_request(b))

@pytest.mark.parametrize('status',[200,404])
def test_absence_after_any_seen_published_identity_does_not_reopen_permission(status):
 b,record=imported_boundary();b.published='44444444-4444-4444-8444-444444444444'
 with pytest.raises((RuntimeError,DifyError)):observed_publish_read(b,None,status)
 assert b.halted and not b.unpublished and b.counts['publish']==0

def test_existing_published_graph_clears_earlier_absence_and_blocks_overwrite():
 from app.dsl_roundtrip import parse,digest
 from app.workflow_publication import core
 b,record=imported_boundary();published=parse((TOOLS/'candidate.yml').read_text('utf-8'),'workflow')['workflow'];published['id']='44444444-4444-4444-8444-444444444444';b.graph_digest=digest(core(published));b.unpublished=True
 observed_publish_read(b,published);assert b.published==published['id'] and b.unpublished is False
 called=[]
 async def forbidden(req):called.append(req);raise AssertionError('Must reject before physical publish')
 with pytest.raises(RuntimeError):asyncio.run(dispatch(b,forbidden,publication_request(b)))
 assert b.halted and not called and b.counts['publish']==0

@pytest.mark.parametrize('value',[{},[],'null',False,0])
def test_only_literal_null_proves_absence_not_empty_or_false_values(value):
 b,record=imported_boundary();b.unpublished=True
 with pytest.raises(Exception):observed_publish_read(b,value)
 assert b.halted and b.unpublished is False and b.counts['publish']==0

def test_legacy_404_absence_still_supported_without_prior_published_identity():
 b,record=imported_boundary();observed_publish_read(b,{'message':'public-not-found'},404)
 assert b.unpublished and not b.halted and b.published is None and b.counts['publish']==0
