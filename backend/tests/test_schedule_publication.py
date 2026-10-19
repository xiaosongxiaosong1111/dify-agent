import copy,json,uuid,yaml
import pytest
from test_api import client
from test_schedule_observation import setup,APP,PUBLISHED,TRIGGER
from app import main
from app.dify import DifyError

def prepare(client,t):return client.post(f"/api/tasks/{t['id']}/schedule-publication/prepare",json={'revision':t['revision']})
def execute(client,t,p,**patch):return client.post(f"/api/tasks/{t['id']}/schedule-publication/{p['id']}/execute",json={'revision':t['revision'],'resource_token':p['resource_token'],'approve_resource_plan':True,'accept_possible_activation':True,**patch})

def platform(monkeypatch,t,root,mode='ok'):
 calls=[];state={'enabled':mode!='already_disabled'}
 async def request(self,method,path,**kw):
  calls.append((method,path));stage='preflight' if path.endswith('/apps') else 'import' if path.endswith('/imports') else 'stop' if path.endswith('/trigger-enable') else 'trigger' if path.endswith('/triggers') else 'publish'
  if mode==stage and (method=='POST' or stage=='preflight'):raise DifyError('隔离请求结果未知，不重试。')
  if stage=='import':
   assert 'app_id' not in kw['json'];return {'app_id':APP,'status':'completed-with-warnings' if mode=='warnings' else 'completed'}
  if stage=='publish':
   if method=='POST':return {'result':'success'}
   value={'id':PUBLISHED,**copy.deepcopy(root['workflow'])}
   if mode=='graph':value['graph']['nodes'][1]['data']['template']='changed'
   if mode=='config':value['features']['speech_to_text']['enabled']=True
   return value
  if stage=='trigger':
   rows=[{'id':TRIGGER,'node_id':'timer','trigger_type':'trigger-schedule','status':'enabled' if state['enabled'] else 'disabled'}]
   if mode=='missing':rows=[]
   if mode=='duplicate':rows.append(copy.deepcopy(rows[0]))
   return {'data':rows}
  if stage=='stop':
   assert kw['json']=={'trigger_id':TRIGGER,'enable_trigger':False}
   if mode!='not_stopped':state['enabled']=False
   return {}
  return {'data':[]}
 monkeypatch.setattr(main.DifyClient,'request',request);return calls,state

def test_frozen_local_preparation_and_explicit_activation_acknowledgement(client,monkeypatch):
 t,env,root=setup(client);before=copy.deepcopy(main.get_task(t['id']));calls,state=platform(monkeypatch,t,root);response=prepare(client,t);assert response.status_code==200,response.text;p=response.json()
 assert p['possible_natural_activation'] and not p['host_cost_guaranteed_zero'] and not p['business_verified']
 assert p['resource_counts']=={'new_apps':1,'publish_attempts':1,'stop_attempts':1,'new_keys':0,'manual_runs':0} and calls==[]
 assert execute(client,t,p,accept_possible_activation=False).status_code==422 and execute(client,t,p,approve_resource_plan=False).status_code==422
 assert calls==[] and main.get_task(t['id'])==before

@pytest.mark.parametrize('mode,posts,reads',[('ok',3,5),('already_disabled',2,4)])
def test_new_publish_verified_disabled_without_manual_run_or_old_app_change(client,monkeypatch,mode,posts,reads):
 t,env,root=setup(client);before=copy.deepcopy(main.get_task(t['id']));p=prepare(client,t).json();calls,state=platform(monkeypatch,t,root,mode);response=execute(client,t,p);assert response.status_code==200,response.text;row=response.json()
 assert row['state']=='published_and_disabled' and row['stop_observed'] and row['publication_matched'] and row['app_id']==APP and row['published_workflow_id']==PUBLISHED and row['trigger_id']==TRIGGER
 assert sum(m=='POST' for m,_ in calls)==posts and sum(m=='GET' for m,_ in calls)==reads and row['reads_attempted']==reads
 assert not state['enabled'] and not row['business_verified'] and main.get_task(t['id'])==before
 count=len(calls);assert execute(client,t,p).status_code==409 and len(calls)==count

@pytest.mark.parametrize('mode,posts,stopped',[('preflight',0,False),('import',1,False),('warnings',1,False),('publish',3,True),('graph',3,True),('config',3,True),('stop',3,False),('not_stopped',3,False),('missing',2,False),('duplicate',2,False)])
def test_failed_publish_still_attempts_only_approved_original_stop_and_keeps_checkpoint(client,monkeypatch,mode,posts,stopped):
 t,env,root=setup(client);p=prepare(client,t).json();calls,state=platform(monkeypatch,t,root,mode);response=execute(client,t,p);assert response.status_code==200,response.text;row=response.json()
 assert row['state']!='published_and_disabled' and row['stop_observed']==stopped and not row['business_verified']
 assert sum(m=='POST' for m,_ in calls)==posts and row['reads_attempted']<=5 and not any('/v1/' in path or 'api-keys' in path for _,path in calls)
 if mode not in {'preflight','import'}:assert row['app_id']==APP
 count=len(calls);assert execute(client,t,p).status_code==409 and len(calls)==count
 if row['state'] in {'stop_not_confirmed','unknown'}:assert execute(client,t,prepare(client,t).json()).status_code==409

@pytest.mark.parametrize('change',['artifact','revision','environment','confirmation'])
def test_stale_scope_never_dispatches(client,monkeypatch,change):
 t,env,root=setup(client);p=prepare(client,t).json();calls,_=platform(monkeypatch,t,root)
 if change=='artifact':main.artifact_path(t).write_text(main.artifact_path(t).read_text(encoding='utf-8')+'\n',encoding='utf-8')
 elif change=='environment':env['base_url']='http://127.0.0.1:8081';main.store.put('environment',env['id'],env)
 else:t['revision' if change=='revision' else 'configuration_confirmed']=99 if change=='revision' else False;main.store.put('task',t['id'],t)
 assert execute(client,t,p).status_code==409 and calls==[]

@pytest.mark.parametrize('change',['dynamic','extra_feature','secret','model','end'])
def test_unadapted_content_refused_not_removed(client,change):
 t,_,root=setup(client);nodes=root['workflow']['graph']['nodes']
 if change=='dynamic':nodes[1]['data']['template']='{{7*7}}'
 elif change=='extra_feature':root['workflow']['features']['speech_to_text']['enabled']=True
 elif change=='secret':nodes[1]['data']['template']='sk-private-not-for-outbound-0123456789'
 elif change=='model':nodes[1]['data']['type']='llm'
 else:nodes[2]['data']['outputs'][0]['variable']='another'
 main.artifact_path(t).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8')
 assert prepare(client,t).status_code==422 and main.store.list('schedule_publication')==[]

def test_recover_never_republishes_or_stops(client):
 t,_,_=setup(client);row={'id':str(uuid.uuid4()),'task_id':t['id'],'state':'executing','app_id':APP,'attempts':{'import':1,'publish':1}}
 main.store.put('schedule_publication',row['id'],row);main.schedule_publications.recover();saved=main.store.get('schedule_publication',row['id'])
 assert saved['state']=='unknown' and saved['app_id']==APP and saved['attempts']==row['attempts']

def test_escaped_saved_credential_not_published_or_returned(client):
 t,env,root=setup(client);path=main.artifact_path(t);text=path.read_text(encoding='utf-8')
 text=text.replace('定时技术固定结果','"\\u0074est-console"');path.write_text(text,encoding='utf-8')
 response=prepare(client,t);assert response.status_code==422 and 'test-console' not in response.text and main.store.list('schedule_publication')==[]

@pytest.mark.parametrize('change',['revision','credentials'])
def test_post_publish_change_keeps_original_stop_target_or_reports_manual_need(client,monkeypatch,change):
 t,env,root=setup(client);p=prepare(client,t).json();calls,state=platform(monkeypatch,t,root);original=main.DifyClient.request
 async def request(self,method,path,**kw):
  value=await original(self,method,path,**kw)
  if method=='POST' and path.endswith('/workflows/publish'):
   if change=='revision':row=main.get_task(t['id']);row['revision']+=1;main.store.put('task',row['id'],row)
   else:main.store.set_secret(env['id'],'console_token','rotated-private-connection')
  return value
 monkeypatch.setattr(main.DifyClient,'request',request)
 row=execute(client,t,p).json();assert row['app_id']==APP and not row['business_verified']
 stops=[path for m,path in calls if m=='POST' and path.endswith('/trigger-enable')]
 if change=='revision':assert row['stop_observed'] and stops==[f'/console/api/apps/{APP}/trigger-enable'] and main.get_task(t['id'])['revision']==t['revision']+1
 else:assert not row['stop_observed'] and stops==[] and row['state']=='stop_not_confirmed'

def test_read_original_target_after_task_changes_not_current_environment(client,monkeypatch):
 t,env,root=setup(client);p=prepare(client,t).json();calls,state=platform(monkeypatch,t,root,'not_stopped');row=execute(client,t,p).json();count=len(calls)
 other=copy.deepcopy(env);other['id']=str(uuid.uuid4());other['base_url']='http://127.0.0.1:8081';main.store.put('environment',other['id'],other)
 changed=main.get_task(t['id']);changed.update(environment_id=other['id'],revision=changed['revision']+1);main.store.put('task',changed['id'],changed);before=copy.deepcopy(changed)
 state['enabled']=False;original=main.DifyClient.request
 async def request(self,method,path,**kw):assert self.env['id']==env['id'] and method=='GET';return await original(self,method,path,**kw)
 monkeypatch.setattr(main.DifyClient,'request',request)
 response=client.get(f"/api/tasks/{t['id']}/schedule-publication/{p['id']}/reconcile");assert response.status_code==200,response.text;r=response.json()
 assert r['state']=='disabled_observed_later' and r['reconciled_core_matched'] and r['environment_id']==env['id'] and not r['business_verified']
 assert len(calls)==count+2 and main.get_task(t['id'])==before

def test_changed_original_profile_no_wrong_target_read(client,monkeypatch):
 t,env,root=setup(client);p=prepare(client,t).json();calls,state=platform(monkeypatch,t,root);execute(client,t,p);count=len(calls)
 env['base_url']='http://127.0.0.1:8081';main.store.put('environment',env['id'],env)
 assert client.get(f"/api/tasks/{t['id']}/schedule-publication/{p['id']}/reconcile").status_code==409 and len(calls)==count
