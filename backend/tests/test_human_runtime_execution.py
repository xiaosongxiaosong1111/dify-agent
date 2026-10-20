import copy,json,time,uuid
import httpx,pytest,yaml
from test_api import client,create,approved,planning_provider
from test_human_runtime_plan import setup,prepare
from app import main
from app.dify import DifyError
from app.human_runtime_stream import render
from app.storage import Store


@pytest.fixture(autouse=True)
def forbid_human_runtime_external_calls(monkeypatch):
 def forbidden(*args,**kwargs):pytest.fail('AT-16 隔离检查不得访问真实 HTTP 或调用真实模型')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)

APP=str(uuid.uuid4());WORKFLOW=str(uuid.uuid4());RUN=str(uuid.uuid4());FORM=str(uuid.uuid4());KEYID=str(uuid.uuid4())
KEY='app-private-new-key-0123456789';TOKEN='form-private-token-0123456789'

def execute(client,t,p,**patch):return client.post(f"/api/tasks/{t['id']}/human-runtime/{p['id']}/execute",json={'revision':t['revision'],'resource_token':p['resource_token'],'approve_resource_plan':True,**patch})

def platform(monkeypatch,t,mode='ok'):
 calls=[];root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'))
 async def request(self,method,path,**kw):
  calls.append((method,path));stage='import' if path.endswith('/imports') else 'publish' if path.endswith('/workflows/publish') else 'key' if path.endswith('/api-keys') else 'preflight'
  if mode==stage and (stage=='preflight' or method=='POST'):raise DifyError('隔离平台连接中断，结果可能未知。')
  if path.endswith('/imports'):
   assert 'app_id' not in kw['json'];return {'status':'completed','app_id':APP}
  if path.endswith('/workflows/publish'):
   if method=='POST':return {'result':'success'}
   value={**copy.deepcopy(root['workflow']),'id':WORKFLOW}
   if mode=='graph':value['graph']['nodes'][2]['data']['template']='另一版本'
   if mode=='config':value['features']['speech_to_text']['enabled']=True
   return value
  if '/workflow-runs/' in path:return {'id':RUN,'status':'paused','graph':copy.deepcopy(root['workflow']['graph'])}
  if path.endswith('/api-keys'):return {'id':KEYID,'token':KEY}
  return {'data':[]}
 async def collect(c,inputs,user,p):
  calls.append(('POST','/v1/workflows/run'));assert c.store.secret(c.env['id'],'service_api_key')==KEY
  assert c.store.secret('another-environment','service_api_key') is None
  assert user.startswith('sierra-human-') and inputs=={'query':'仅本机技术审核对象'}
  p.run_id=RUN
  if mode=='run':raise p.failure()
  assert p.rendered==render(root,inputs)
  return {'form_id':FORM,'node_id':'review','workflow_run_id':RUN,'published_workflow_id':WORKFLOW,'content':p.rendered,'actions':p.review['actions'],'expiration_time':int(time.time())+3000,'inputs':[],'source_verified':True,'business_verified':False},TOKEN
 monkeypatch.setattr(main.DifyClient,'request',request)
 monkeypatch.setattr('app.human_runtime_execution.collect',collect)
 return calls

def test_approved_once_independent_resources_encrypted_tokens_and_no_task_overwrite(client,monkeypatch):
 t,env=setup(client);before=copy.deepcopy(main.get_task(t['id']));main.store.set_secret(env['id'],'service_api_key','old-environment-key');p=prepare(client,t).json();calls=platform(monkeypatch,t)
 response=execute(client,t,p);assert response.status_code==200,response.text;row=response.json()
 assert row['state']=='waiting_human' and row['attempts']=={'import':1,'publish':1,'create_key':1,'run':1}
 assert row['app_id']==APP and row['workflow_run_id']==RUN and not row['business_verified']
 assert main.store.secret(env['id'],'service_api_key')=='old-environment-key'
 assert main.store.secret(row['id'],'service_api_key')==KEY and main.store.secret(row['id'],'form_token')==TOKEN
 assert main.get_task(t['id'])==before
 assert len(calls)==8 and sum(m=='POST' for m,_ in calls)==4
 history=client.get(f"/api/tasks/{t['id']}/human-runtime/runs");assert history.json()['records'][0]['form']['form_id']==FORM
 with main.store.connect() as conn:
  public=''.join(r[0] for r in conn.execute('SELECT value FROM objects'));cipher=b''.join(r[0] for r in conn.execute('SELECT value FROM secrets'))
 assert KEY not in public and TOKEN not in public and KEY.encode() not in cipher and TOKEN.encode() not in cipher
 assert KEY not in response.text+history.text and TOKEN not in response.text+history.text
 assert execute(client,t,p).status_code==409 and len(calls)==8
 newer=prepare(client,t).json();assert execute(client,t,newer).status_code==409 and len(calls)==8

@pytest.mark.parametrize('patch',[{'approve_resource_plan':False},{'approve_resource_plan':'true'},{'resource_token':'x'*64},{'revision':100}])
def test_missing_or_wrong_concrete_approval_never_dispatches(client,monkeypatch,patch):
 t,_=setup(client);p=prepare(client,t).json();calls=platform(monkeypatch,t)
 assert execute(client,t,p,**patch).status_code in {409,422} and calls==[] and main.store.list('human_runtime_run')==[]

@pytest.mark.parametrize('change',['source','environment','confirmation','old_plan'])
def test_stale_plan_never_dispatches(client,monkeypatch,change):
 t,env=setup(client);p=prepare(client,t).json();calls=platform(monkeypatch,t)
 if change=='source':main.artifact_path(t).write_text(main.artifact_path(t).read_text(encoding='utf-8')+'\n',encoding='utf-8')
 elif change=='environment':env['base_url']='http://127.0.0.1:8081';main.store.put('environment',env['id'],env)
 elif change=='confirmation':t['configuration_confirmed']=False;main.store.put('task',t['id'],t)
 else:
  row=main.store.get('human_runtime_plan',p['id']);row['execution_available']=False;main.store.put('human_runtime_plan',row['id'],row)
 assert execute(client,t,p).status_code==409 and calls==[]

@pytest.mark.parametrize('mode,posts',[('preflight',0),('import',1),('publish',2),('graph',2),('config',2),('key',3),('run',4)])
def test_failure_checkpoints_known_resources_no_repeat_no_raw_secret(client,monkeypatch,mode,posts):
 t,_=setup(client);p=prepare(client,t).json();calls=platform(monkeypatch,t,mode);response=execute(client,t,p)
 assert response.status_code==502 and sum(m=='POST' for m,_ in calls)==posts
 rows=client.get(f"/api/tasks/{t['id']}/human-runtime/runs").json()['records'];row=rows[0]
 assert row['state']==('not_dispatched' if posts==0 else 'unknown') and not row.get('form')
 if posts>=2:assert row['app_id']==APP
 if mode=='run':assert row['workflow_run_id']==RUN
 count=len(calls);assert execute(client,t,p).status_code==409 and len(calls)==count
 assert KEY not in json.dumps(rows)+response.text and TOKEN not in json.dumps(rows)+response.text

def test_recover_does_not_replay_or_drop_known_ids(client,monkeypatch):
 t,_=setup(client);row={'id':str(uuid.uuid4()),'task_id':t['id'],'state':'executing','app_id':APP,'attempts':{'import':1},'stage':'import'};main.store.put('human_runtime_run',row['id'],row)
 main.human_runtime_executions.recover();saved=main.store.get('human_runtime_run',row['id'])
 assert saved['state']=='unknown' and saved['app_id']==APP and saved['attempts']=={'import':1}

@pytest.mark.parametrize('status',['paused','running','succeeded','failed','stopped','partial-succeeded'])
def test_original_owned_run_readonly_never_evaluates_or_submits(client,monkeypatch,status):
 t,env=setup(client);p=prepare(client,t).json();calls=platform(monkeypatch,t);row=execute(client,t,p).json();before=copy.deepcopy(main.get_task(t['id']));reads=[]
 async def detail(self,app,rid):
  reads.append((self.env['id'],app,rid));return {'id':RUN,'status':status,'outputs':{'private':'drop'},'error':TOKEN}
 monkeypatch.setattr(main.DifyClient,'workflow_run_detail',detail)
 response=client.get(f"/api/tasks/{t['id']}/human-runtime/runs/{row['id']}/state");assert response.status_code==200,response.text
 saved=response.json();assert saved['observed_status']==status and not saved['business_verified']
 assert saved['state']==('waiting_human' if status in {'paused','running'} else 'platform_finished')
 assert reads==[(env['id'],APP,RUN)] and len(calls)==8 and TOKEN not in response.text and 'private' not in response.text
 assert main.get_task(t['id'])==before

def test_source_and_credentials_rotation_drop_readback_without_new_dispatch(client,monkeypatch):
 t,env=setup(client);p=prepare(client,t).json();calls=platform(monkeypatch,t);row=execute(client,t,p).json();before=copy.deepcopy(main.store.get('human_runtime_run',row['id']))
 async def detail(self,app,rid):
  main.store.set_secret(env['id'],'console_token','new-private-console-token');return {'id':RUN,'status':'succeeded'}
 monkeypatch.setattr(main.DifyClient,'workflow_run_detail',detail)
 assert client.get(f"/api/tasks/{t['id']}/human-runtime/runs/{row['id']}/state").status_code==409
 assert main.store.get('human_runtime_run',row['id'])==before and len(calls)==8

def test_changed_final_execution_graph_does_not_adopt_form_token(client,monkeypatch):
 t,_=setup(client);p=prepare(client,t).json();calls=platform(monkeypatch,t)
 async def detail(self,app,rid):return {'id':RUN,'status':'paused','graph':{'nodes':[],'edges':[]}}
 monkeypatch.setattr(main.DifyClient,'workflow_run_detail',detail)
 assert execute(client,t,p).status_code==502;row=main.store.list('human_runtime_run')[0]
 assert row['state']=='unknown' and row['workflow_run_id']==RUN and not row.get('form')
 assert not main.store.has_secret(row['id'],'form_token') and sum(m=='POST' for m,_ in calls)==4


@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_at16_catalog_explains_trigger_review_limits_without_proving_environment(client,mode):
 task=create(client,app_type=mode);before=copy.deepcopy(main.get_task(task['id']))
 response=client.get('/api/capabilities',params={'app_type':mode});assert response.status_code==200
 value=response.json();types={n['type'] for n in value['root_nodes']};notes=''.join(value['notes']);gaps=''.join(value['not_adapted'])
 assert value['verification']=='compiler_scope' and value['target_dify_version']=='1.17.1'
 assert 'Webhook／插件触发' in gaps and '再由用户确认范围' in notes
 if mode=='workflow':
  assert {'trigger-schedule','human-input'}<=types
  assert '真实自然定时业务验收' in gaps and '指定身份、邮件' in gaps
  assert '发布可能直接激活' in notes and '无自动停用' in notes and '不强制审核人身份' in notes
 elif mode=='advanced-chat':
  assert not {'trigger-schedule','human-input'}&types and 'Chatflow定时／人工审核入口' in gaps
 else:
  assert not types and 'Workflow定时、人工审核及容器流程' in gaps
 assert main.get_task(task['id'])==before and main.store.list('human_runtime_plan')==[] and main.store.list('human_runtime_run')==[]


@pytest.mark.parametrize('goal,reason,alternative',[
 ('收到业务 Webhook 后自动触发处理。','当前未适配 Webhook／插件触发，也没有目标环境触发能力证据。','保留 Workflow，由用户人工发起；需要自动触发则另行评估外部系统及授权。'),
 ('必须由指定财务人员收到邮件后审核。','当前人工审核不强制指定身份，邮件送达尚未适配，不能保证目标环境权限满足要求。','保留需求并暂停；可另行评估 WebApp 人工核对身份方案，由用户决定是否接受。'),
],ids=['webhook','reviewer-email'])
def test_at16_capability_gap_and_alternative_persist_as_unapproved_questions(client,monkeypatch,tmp_path,goal,reason,alternative):
 planning_provider(client);task=approved(client)
 task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'goal':goal}}).json()
 before=copy.deepcopy(main.get_task(task['id']));calls=[]
 questions=[{'question':'是否接受人工替代方案及其限制？','reason':reason,'recommendation':alternative,
             'experience':'需要主动操作，不能保证自动触发或指定身份限制。','cost':'环境与运行费用尚未核对，不因此批准外部调用。','manual_work':'用户需明确范围并自行完成人工步骤。'}]
 async def controlled(provider,key,messages,**kwargs):
  context=json.loads(messages[1]['content']);calls.append(context)
  assert context['requirements']['goal']==goal and context['user_selected_type']=='workflow'
  catalog=context['capability_catalog'];assert catalog['verification']=='compiler_scope'
  assert 'Webhook／插件触发' in catalog['not_adapted'] and any('指定身份、邮件' in gap for gap in catalog['not_adapted'])
  assert '问题和建议不是用户确认，不自动填答案' in messages[0]['content']
  return json.dumps({'error':reason,'needs_decision':questions},ensure_ascii=False),{'prompt_tokens':90,'completion_tokens':40}
 monkeypatch.setattr(main,'call_model',controlled)
 response=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
 assert response.status_code==422 and '没有自动删减功能' in response.json()['detail'] and len(calls)==1
 saved=main.get_task(task['id']);assert saved['status']=='paused'
 for field in ('revision','app_type','requirements','configuration','requirements_confirmed','configuration_confirmed','confirmations','workflow_plan','artifact','runs','versions','dify_app_id'):
  assert saved.get(field)==before.get(field),field
 record=client.get(f"/api/tasks/{task['id']}/planning").json()['runs'][-1]
 assert record['revision']==task['revision'] and record['status']=='paused' and record['stop_reason']=='needs_decision'
 assert record['decision_report']=={'schema_version':1,'verification':'model_clarification_only','message':reason,'questions':questions,'incomplete':False,'format_valid':True}
 assert len(record['attempts'])==1 and 'last_candidate' not in record
 assert Store(tmp_path).get('task',task['id'])==saved
 ledger=copy.deepcopy(main.budgets.get(task['id']))
 assert client.get(f"/api/tasks/{task['id']}").json()==saved and main.budgets.get(task['id'])==ledger and len(calls)==1
 assert main.store.list('human_runtime_plan')==[] and main.store.list('human_runtime_run')==[]


@pytest.mark.parametrize('version',['1.17.0','unknown'])
def test_at16_unadapted_environment_cannot_prepare_resources(client,version):
 task,env=setup(client);env['version']=version;main.store.put('environment',env['id'],env)
 before=copy.deepcopy(main.get_task(task['id']));response=prepare(client,task)
 assert response.status_code==422 and response.json()['detail']=='当前适配基线为 Dify 1.17.1，请核对环境实际版本。'
 assert main.get_task(task['id'])==before and main.store.list('human_runtime_plan')==[] and main.store.list('human_runtime_run')==[]


@pytest.mark.parametrize('action',['import','run'])
def test_at16_generic_actions_cannot_bypass_independent_review_approval(client,action):
 task,_=setup(client);before=copy.deepcopy(main.get_task(task['id']))
 response=client.post(f"/api/tasks/{task['id']}/{action}",json={'revision':task['revision']})
 assert response.status_code==422 and '人工审核' in response.json()['detail']
 assert main.get_task(task['id'])==before and main.store.list('human_runtime_run')==[]


def test_at16_preparation_discloses_limits_and_does_not_imply_resource_approval(client,tmp_path):
 task,_=setup(client);before=copy.deepcopy(main.get_task(task['id']));response=prepare(client,task)
 assert response.status_code==200,response.text
 plan=response.json()
 assert plan['state']=='prepared_unapproved' and plan['execution_available'] and not plan['role_restriction_enforced']
 assert plan['resource_counts']=={'new_apps':1,'publish_attempts':1,'new_app_keys':1,'workflow_run_attempts':1,'expected_human_forms':1,'human_submissions':0}
 assert not plan['automatic_retry'] and not plan['overwrites_existing_apps'] and plan['leftovers_possible']
 assert not plan['paid_dependencies']['model'] and not plan['paid_dependencies']['host_cost_guaranteed_zero']
 assert '不强制指定审核人' in plan['note'] and '实际平台联调尚未验收' in plan['note']
 stored=Store(tmp_path).get('human_runtime_plan',plan['id'])
 assert stored['revision']==task['revision'] and stored['resource_token']==plan['resource_token'] and stored['state']=='prepared_unapproved'
 response=client.post(f"/api/tasks/{task['id']}/human-runtime/{plan['id']}/execute",json={'revision':task['revision'],'resource_token':plan['resource_token']})
 assert response.status_code==422
 assert main.store.get('human_runtime_plan',plan['id'])==stored and main.store.list('human_runtime_run')==[]
 assert main.get_task(task['id'])==before
