import asyncio,copy,json,logging,time,uuid
import httpx,pytest
from test_api import client
from test_human_runtime_plan import setup,prepare
from test_human_runtime_execution import platform,execute,APP,RUN,FORM,KEY,TOKEN
from app import main
from app.dify import DifyError
from app.human_decision import FormClient

def pending(client,monkeypatch):
 t,env=setup(client);p=prepare(client,t).json();calls=platform(monkeypatch,t);row=execute(client,t,p).json();return t,env,row,calls
def decision(client,t,r,action='approve'):return client.post(f"/api/tasks/{t['id']}/human-runtime/runs/{r['id']}/decision/prepare",json={'revision':t['revision'],'action':action})
def submit(client,t,d,**patch):return client.post(f"/api/tasks/{t['id']}/human-decisions/{d['id']}/submit",json={'revision':t['revision'],'resource_token':d['resource_token'],'approve_human_action':True,**patch})
def form_platform(monkeypatch,r,mode='ok'):
 calls=[]
 async def request(self,method,payload=None):
  calls.append((method,copy.deepcopy(payload)))
  if mode==method:raise DifyError('隔离表单读取／提交中断，结果可能未知。')
  if method=='GET':
   value={'form_content':r['form']['content'],'inputs':[],'resolved_default_values':{},'user_actions':r['form']['actions'],'expiration_time':r['form']['expiration_time']}
   if mode=='definition':value['form_content']='其它对象'
   if mode=='expiry':value['expiration_time']=int(time.time())-1
   return value
  return {'unexpected':TOKEN} if mode=='body' else {}
 monkeypatch.setattr(FormClient,'request',request);return calls

@pytest.mark.parametrize('action',['approve','reject'])
def test_local_action_preview_then_separate_explicit_once_submission(client,monkeypatch,action):
 t,env,r,oldcalls=pending(client,monkeypatch);before=copy.deepcopy(main.get_task(t['id']));fcalls=form_platform(monkeypatch,r)
 d=decision(client,t,r,action).json();assert d['state']=='prepared_unapproved' and not d['write_attempted'] and d['form_id']==FORM and d['content']==r['form']['content']
 assert d['action']==action and fcalls==[] and len(oldcalls)==8
 response=submit(client,t,d);assert response.status_code==200,response.text
 assert response.json()['state']=='accepted' and not response.json()['business_verified']
 assert fcalls==[('GET',None),('POST',{'action':action,'inputs':{},'user':'sierra-human-'+r['id']})]
 saved=main.store.get('human_runtime_run',r['id']);assert saved['state']=='awaiting_resume' and saved['human_submission_attempted']
 assert main.get_task(t['id'])==before and TOKEN not in response.text and KEY not in response.text
 assert submit(client,t,d).status_code==409 and decision(client,t,r,'reject' if action=='approve' else 'approve').status_code==409 and len(fcalls)==2

@pytest.mark.parametrize('patch',[{'approve_human_action':False},{'approve_human_action':'true'},{'resource_token':'x'*64},{'revision':99}])
def test_resource_approval_not_reused_and_wrong_action_approval_zero_post(client,monkeypatch,patch):
 t,_,r,_=pending(client,monkeypatch);d=decision(client,t,r).json();fcalls=form_platform(monkeypatch,r)
 assert submit(client,t,d,**patch).status_code in {409,422} and fcalls==[]

@pytest.mark.parametrize('mode,attempted',[('GET',False),('definition',False),('expiry',False),('POST',True),('body',True)])
def test_failed_prechecks_and_unknown_submission_never_repeat(client,monkeypatch,mode,attempted):
 t,_,r,_=pending(client,monkeypatch);d=decision(client,t,r).json();fcalls=form_platform(monkeypatch,r,mode);response=submit(client,t,d)
 assert response.status_code==502 and TOKEN not in response.text
 row=main.store.get('human_decision',d['id']);assert row['write_attempted']==attempted and row['state']==('unknown' if attempted else 'not_dispatched')
 assert sum(m=='POST' for m,_ in fcalls)==int(attempted);count=len(fcalls)
 assert submit(client,t,d).status_code==409 and len(fcalls)==count
 if attempted:assert decision(client,t,r).status_code==409

@pytest.mark.parametrize('change',['artifact','revision','run_record','key','console','expiry'])
def test_changes_and_stale_source_reject_old_submission(client,monkeypatch,change):
 t,env,r,_=pending(client,monkeypatch);d=decision(client,t,r).json();fcalls=form_platform(monkeypatch,r)
 if change=='artifact':main.artifact_path(t).write_text(main.artifact_path(t).read_text(encoding='utf-8')+'\n',encoding='utf-8')
 elif change=='revision':t['revision']+=1;main.store.put('task',t['id'],t)
 elif change in {'run_record','expiry'}:
  row=main.store.get('human_runtime_run',r['id'])
  if change=='expiry':row['form']['expiration_time']=int(time.time())-1
  else:row['message']='changed'
  main.store.put('human_runtime_run',r['id'],row)
 else:
  async def detail(self,app,rid):
   main.store.set_secret(r['id'] if change=='key' else env['id'],'service_api_key' if change=='key' else 'console_token','rotated-private-value');return {'id':RUN,'status':'paused','graph':{}}
  monkeypatch.setattr(main.DifyClient,'workflow_run_detail',detail)
 assert submit(client,t,d).status_code==409 and fcalls==[]

def test_two_local_action_preparations_share_one_form_attempt_guard(client,monkeypatch):
 t,_,r,_=pending(client,monkeypatch);a=decision(client,t,r,'approve').json();b=decision(client,t,r,'reject').json();fcalls=form_platform(monkeypatch,r)
 assert submit(client,t,a).status_code==200 and submit(client,t,b).status_code==409 and sum(m=='POST' for m,_ in fcalls)==1

def test_recovery_does_not_replay_human_submission(client,monkeypatch):
 t,_,r,_=pending(client,monkeypatch);d=decision(client,t,r).json();d.update(state='submitting',write_attempted=True);main.store.put('human_decision',d['id'],d);run=main.store.get('human_runtime_run',r['id']);run['state']='submitting_decision';main.store.put('human_runtime_run',r['id'],run)
 main.human_decisions.recover();assert main.store.get('human_decision',d['id'])['state']=='unknown' and main.store.get('human_runtime_run',r['id'])['state']=='unknown'

@pytest.mark.parametrize('method,status',[('GET',200),('POST',200),('GET',412),('POST',500)])
def test_native_sensitive_path_never_in_logs_errors_or_public_result(monkeypatch,caplog,method,status):
 real=httpx.AsyncClient;calls=[]
 async def handle(req):calls.append(req);return httpx.Response(status,json={} if method=='POST' else {'form_content':'fixed'})
 monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handle),**kw));caplog.set_level(logging.DEBUG)
 async def invoke():return await FormClient({'id':'fixed','base_url':'http://127.0.0.1:8080'},KEY,TOKEN).request(method,{'action':'approve','inputs':{},'user':'fixed'} if method=='POST' else None)
 if status==200:asyncio.run(invoke())
 else:
  with pytest.raises(DifyError) as exc:asyncio.run(invoke())
  assert TOKEN not in str(exc.value) and KEY not in str(exc.value)
 assert len(calls)==1 and calls[0].url.path.endswith(TOKEN) and calls[0].headers['Authorization']=='Bearer '+KEY
 assert TOKEN not in caplog.text and KEY not in caplog.text
