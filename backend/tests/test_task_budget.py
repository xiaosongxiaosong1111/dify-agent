import asyncio,copy,json
import shutil
from decimal import Decimal
import httpx
import pytest
from fastapi.testclient import TestClient
from test_api import client,create,approved
from test_planning import plan
from test_coverage import items
from app import main
from app.task_budget import money
from app.planning import PlanningStopped
from app.providers import ProviderError
from app.storage import Store


@pytest.fixture(autouse=True)
def forbid_budget_external_calls(monkeypatch):
 def forbidden(*args,**kwargs):
  pytest.fail('AT-20 隔离检查不得访问真实 HTTP、Dify 或付费模型')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(main.DifyClient,'request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)

RATES={'input_per_million_usd':1,'output_per_million_usd':2,'cached_input_per_million_usd':.1}
USAGE={'prompt_tokens':100,'completion_tokens':20}
MESSAGES=[{'role':'user','content':'private prompt'}]

def provider(client,priced=True):
 data={'name':'预算测试','provider':'custom','base_url':'https://example.com/v1','model':'test','api_key':'not-a-real-key','role':'main'}
 if priced:data['pricing']=RATES
 return client.post('/api/providers',json=data).json()

def policy(client,t,limit='1',**kw):
 b=client.get(f"/api/tasks/{t['id']}/budget").json()
 return client.patch(f"/api/tasks/{t['id']}/budget",json={'revision':t['revision'],'policy_revision':b['policy_revision'],'limit_usd':limit,'acknowledge_change':True,'note':'测试累计预算',**kw})

def call(t,p,kind='interview'):
 return main.budgets.call(t['id'],t['revision'],kind,p,'not-a-real-key',MESSAGES,max_tokens=100)

def ledger(client,t):return client.get(f"/api/tasks/{t['id']}/budget").json()

def test_all_four_routes_account_in_one_ledger(client,monkeypatch):
 t=approved(client);p=provider(client);t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json();assert policy(client,t).status_code==200
 replies=[{'message':'继续核对需求','requirements_patch':{}},plan()]
 generated=[]
 async def model(*a,**kw):
  current=main.get_task(t['id'])
  result=replies.pop(0) if replies else ({'schema_version':1,'items':items(current)} if len(generated)==2 else {'schema_version':1,'conflicts':[],'notes':'测试'})
  generated.append(result)
  return json.dumps(result,ensure_ascii=False),USAGE
 monkeypatch.setattr(main,'call_model',model)
 assert client.post(f"/api/tasks/{t['id']}/messages",json={'content':'继续'}).status_code==200
 for path in ('plan','coverage','conflicts'):
  current=main.get_task(t['id']);r=client.post(f"/api/tasks/{t['id']}/{path}/generate",json={'revision':current['revision']});assert r.status_code==200,r.text
 b=ledger(client,t)
 assert [e['kind'] for e in b['entries']]==['interview','plan','coverage','conflicts']
 assert len(b['entries'])==4 and Decimal(b['known_estimated_usd'])==Decimal('.00056')
 assert 'private prompt' not in json.dumps(b) and 'not-a-real-key' not in json.dumps(b)

def test_next_call_refused_across_revision_and_task_restore(client,monkeypatch):
 t=create(client);p=provider(client);assert policy(client,t,'.0014').status_code==200
 async def model(*a,**kw):return 'x',{'prompt_tokens':1000,'completion_tokens':100}
 monkeypatch.setattr(main,'call_model',model);asyncio.run(call(t,p))
 old=copy.deepcopy(t);t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':{'goal':'新修订'}}).json()
 with pytest.raises(PlanningStopped):asyncio.run(call(t,p))
 main.store.put('task',t['id'],old)
 with pytest.raises(PlanningStopped):asyncio.run(call(old,p))
 assert len(ledger(client,t)['entries'])==1

def test_reservations_atomic_and_pending_blocks_edits(client,monkeypatch):
 t=create(client);p=provider(client);assert policy(client,t,'.0014').status_code==200
 async def run():
  entered=asyncio.Event();release=asyncio.Event()
  async def model(*a,**kw):entered.set();await release.wait();return 'x',USAGE
  monkeypatch.setattr(main,'call_model',model)
  first=asyncio.create_task(call(t,p));await entered.wait()
  with pytest.raises(PlanningStopped):await call(t,p)
  assert client.patch(f"/api/tasks/{t['id']}",json={'requirements':{'goal':'禁止并发'}}).status_code==409
  assert policy(client,t).status_code==409
  release.set();await first
 asyncio.run(run());assert len(ledger(client,t)['entries'])==1

@pytest.mark.parametrize('result',['missing_usage','provider_failure','cancel','unpriced'])
def test_unknown_is_not_free_and_explicit_reconciliation(client,monkeypatch,result):
 t=create(client);p=provider(client,result!='unpriced');assert policy(client,t,None if result=='unpriced' else '1').status_code==200
 async def model(*a,**kw):
  if result=='provider_failure':raise ProviderError('超时')
  if result=='cancel':raise asyncio.CancelledError()
  return 'x',{} if result=='missing_usage' else USAGE
 monkeypatch.setattr(main,'call_model',model)
 if result in {'provider_failure','cancel'}:
  with pytest.raises(BaseException):asyncio.run(call(t,p))
 else:asyncio.run(call(t,p))
 b=ledger(client,t);e=b['entries'][0];assert e['status']=='unknown' and e['charged_usd'] is None
 assert policy(client,t,'1').status_code==200
 with pytest.raises(PlanningStopped):asyncio.run(call(t,p))
 b=ledger(client,t);body={'revision':t['revision'],'policy_revision':b['policy_revision'],'actual_cost_usd':'.002','acknowledge_actual_bill':False,'note':'人工核对供应商账单'}
 path=f"/api/tasks/{t['id']}/budget/entries/{e['id']}/reconcile"
 assert client.post(path,json=body).status_code==422
 body['acknowledge_actual_bill']=True;assert client.post(path,json=body).status_code==200
 b=ledger(client,t);assert b['entries'][0]['cost_basis']=='user_declared_bill' and b['unknown_count']==0
 assert b['entries'][0]['reserved_usd']==e['reserved_usd'] and Decimal(b['known_estimated_usd'])==Decimal('.002')
 assert client.post(path,json=body).status_code==409
 assert policy(client,t,None).status_code==200 and len(ledger(client,t)['entries'])==1

def test_missing_price_cap_stops_before_dispatch(client,monkeypatch):
 t=create(client);p=provider(client,False);policy(client,t)
 async def model(*a,**kw):pytest.fail('不得派发')
 monkeypatch.setattr(main,'call_model',model)
 with pytest.raises(PlanningStopped):asyncio.run(call(t,p))
 assert not ledger(client,t)['entries']

def test_provider_failure_with_usage_charged_and_cache_safelist(client,monkeypatch):
 t=create(client);p=provider(client)
 async def model(*a,**kw):raise ProviderError('拒绝',usage={**USAGE,'prompt_tokens_details':{'cached_tokens':50,'secret':'hide'},'api_key':'hide'})
 monkeypatch.setattr(main,'call_model',model)
 with pytest.raises(ProviderError):asyncio.run(call(t,p))
 b=ledger(client,t);assert Decimal(b['known_estimated_usd'])==Decimal('.000095') and 'hide' not in json.dumps(b)

def test_plan_cap_refusal_not_logged_as_unknown_charge(client,monkeypatch):
 t=approved(client);p=provider(client);t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json();policy(client,t,'0')
 async def model(*a,**kw):pytest.fail('零预算不派发')
 monkeypatch.setattr(main,'call_model',model)
 r=client.post(f"/api/tasks/{t['id']}/plan/generate",json={'revision':t['revision']});assert r.status_code==422
 b=ledger(client,t);assert not b['entries'] and not b['unknown_count']
 attempt=main.get_task(t['id'])['planning_runs'][-1]['attempts'][0]
 assert attempt['status']=='not_dispatched' and attempt['estimated_cost_usd']==0

@pytest.mark.parametrize('response',['bad-json','valid'])
def test_interview_overrun_or_invalid_retains_response_not_requirements(client,monkeypatch,response):
 t=create(client);p=provider(client);policy(client,t,'.08')
 async def model(*a,**kw):return ('bad-json' if response=='bad-json' else json.dumps({'message':'新需求','requirements_patch':{'goal':'不应写入'}})),{'prompt_tokens':100000,'completion_tokens':20}
 monkeypatch.setattr(main,'call_model',model)
 r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'继续'});assert r.status_code==200,r.text
 current=r.json();assert current['status']=='paused' and current['requirements']['goal']==t['requirements']['goal']
 assert current['interview_attempts'] and not current.get('active_interview_id') and ledger(client,t)['blocker']

def test_pause_no_reentry_late_reply_not_applied(client,monkeypatch):
 t=create(client);provider(client)
 async def model(*a,**kw):
  main.pause(t['id']);r=await asyncio.to_thread(client.post,f"/api/tasks/{t['id']}/messages",json={'content':'重复'});assert r.status_code==409
  return json.dumps({'message':'迟到','requirements_patch':{'goal':'不写入'}}),USAGE
 monkeypatch.setattr(main,'call_model',model)
 r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'继续'});assert r.status_code==200
 assert r.json()['status']=='paused' and not r.json()['requirements']['goal'] and not r.json().get('active_interview_id')
 assert ledger(client,t)['entries'][0]['status']=='settled'

def test_restart_does_not_clear_reservation_or_replay(client,monkeypatch):
 t=create(client);p=provider(client);policy(client,t)
 async def model(*a,**kw):
  current=main.get_task(t['id']);current.update(status='paused',active_interview_id='unfinished');main.save_task(current)
  main.budgets.recover();return 'x',USAGE
 monkeypatch.setattr(main,'call_model',model);asyncio.run(call(t,p))
 current=main.get_task(t['id']);assert current['status']=='paused' and not current.get('active_interview_id')
 # A crash snapshot with no eventual response preserves its reservation as unknown.
 b=main.budgets.get(t['id']);b['entries'][0].update(status='reserved',charged_usd=None);main.store.put('task_budget',t['id'],b)
 main.budgets.recover();b=ledger(client,t);assert b['unknown_count']==1 and Decimal(b['held_estimated_usd'])>0

def test_old_history_requires_explicit_exclusion_ack(client):
 t=create(client);main.store.delete('task_budget',t['id']);t['messages'].append({'source':'model','content':'旧调用','role':'assistant'});main.save_task(t)
 assert policy(client,t).status_code==422
 assert policy(client,t,acknowledge_excluded_history=True).status_code==200
 assert ledger(client,t)['excluded_history_present'] and not ledger(client,t)['entries']

@pytest.mark.parametrize('value',['NaN','Infinity','-1','1000001','1e-100000',True,'0.0000000000001','x'])
def test_invalid_money(value):
 with pytest.raises(ValueError):money(value)

def test_policy_revision_ack_and_foreign_entry_guard(client):
 t=create(client);other=create(client);assert policy(client,t).status_code==200
 b=ledger(client,t);body={'revision':t['revision'],'policy_revision':0,'limit_usd':'2','acknowledge_change':True,'note':'明确变更'}
 assert client.patch(f"/api/tasks/{t['id']}/budget",json=body).status_code==409
 body['policy_revision']=b['policy_revision'];body['acknowledge_change']=False
 assert client.patch(f"/api/tasks/{t['id']}/budget",json=body).status_code==422
 assert client.post(f"/api/tasks/{other['id']}/budget/entries/foreign/reconcile",json={'revision':other['revision'],'policy_revision':0,'actual_cost_usd':'0','acknowledge_actual_bill':True,'note':'核对'}).status_code==422



def test_interrupted_stream_partial_cumulative_usage_is_not_final_charge(client,monkeypatch):
 t=create(client);p=provider(client);assert policy(client,t,'1').status_code==200
 async def model(*a,**kw):raise ProviderError('流中断',usage={},partial_usage={'prompt_tokens':100,'completion_tokens':5,'secret':'private'})
 monkeypatch.setattr(main,'call_model',model)
 with pytest.raises(ProviderError):asyncio.run(call(t,p))
 entry=ledger(client,t)['entries'][0]
 assert entry['status']=='unknown' and entry['charged_usd'] is None and entry['usage']=={}
 assert entry['partial_reported_usage']=={'prompt_tokens':100,'completion_tokens':5} and entry['partial_usage_is_final'] is False
 assert Decimal(ledger(client,t)['held_estimated_usd'])>0 and 'private' not in json.dumps(entry)
 with pytest.raises(PlanningStopped):asyncio.run(call(t,p))


@pytest.mark.parametrize('app_type',['workflow','advanced-chat','agent'])
def test_at20_pause_api_preserves_late_candidate_and_settlement(client,monkeypatch,app_type):
 t=create(client,app_type);provider(client);assert policy(client,t).status_code==200
 calls=[]
 candidate={'message':'隔离迟到候选','requirements_patch':{'goal':'不得应用的迟到目标'}}
 async def model(*args,**kwargs):
  calls.append('mock')
  paused=await asyncio.to_thread(client.post,f"/api/tasks/{t['id']}/pause")
  assert paused.status_code==200
  saved=Store(main.DATA_ROOT).get('task',t['id'])
  assert saved['status']=='paused' and saved['active_interview_id']
  assert saved['pause_generation']==1 and saved['requirements']==t['requirements']
  assert '可能仍在执行' in saved['messages'][-1]['content']
  assert (await asyncio.to_thread(ledger,client,t))['pending_count']==1
  duplicate=await asyncio.to_thread(client.post,f"/api/tasks/{t['id']}/messages",json={'content':'重复请求'})
  assert duplicate.status_code==409
  return json.dumps(candidate,ensure_ascii=False),USAGE
 monkeypatch.setattr(main,'call_model',model)
 response=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'继续隔离访谈'})
 assert response.status_code==200,response.text
 current=response.json();b=ledger(client,t)
 assert calls==['mock'] and current['status']=='paused' and not current.get('active_interview_id')
 assert current['app_type']==app_type and current['revision']==t['revision']
 assert current['requirements']==t['requirements']
 attempt=current['interview_attempts'][-1]
 assert attempt['applied'] is False and json.loads(attempt['response_excerpt'])==candidate
 assert attempt['usage']==USAGE and '迟到回复未应用' in attempt['reason']
 assert b['pending_count']==b['unknown_count']==0 and len(b['entries'])==1
 assert b['entries'][0]['status']=='settled' and b['entries'][0]['usage']==USAGE
 assert Decimal(b['known_estimated_usd'])>0
 assert Store(main.DATA_ROOT).get('task',t['id'])==current


@pytest.mark.parametrize('app_type',['workflow','advanced-chat','agent'])
@pytest.mark.parametrize('pause_first',[False,True],ids=['interviewing','paused'])
def test_at20_inflight_database_snapshot_reopens_without_replay(client,monkeypatch,tmp_path,app_type,pause_first):
 # Capture the real persisted in-flight API checkpoint; the source request then
 # finishes normally. This models lost process memory, not an OS process kill.
 t=create(client,app_type);p=provider(client);assert policy(client,t).status_code==200
 async def completed(*args,**kwargs):return '已完成的隔离调用',USAGE
 monkeypatch.setattr(main,'call_model',completed);asyncio.run(call(t,p))
 settled=copy.deepcopy(ledger(client,t)['entries'][0])
 snapshot_root=tmp_path/'restart-snapshot';checkpoint={};calls=[]
 async def inflight(*args,**kwargs):
  calls.append('mock')
  if pause_first:
   assert (await asyncio.to_thread(client.post,f"/api/tasks/{t['id']}/pause")).status_code==200
  checkpoint['task']=main.get_task(t['id'])
  checkpoint['budget']=await asyncio.to_thread(ledger,client,t)
  assert checkpoint['task']['active_interview_id']
  assert checkpoint['budget']['entries'][-1]['status']=='reserved'
  snapshot=Store(snapshot_root)
  shutil.copyfile(main.DATA_ROOT/'.credential-key',snapshot_root/'.credential-key')
  with main.store.connect() as source,snapshot.connect() as destination:
   source.backup(destination)
  return json.dumps({'message':'源请求结束','requirements_patch':{'goal':'快照之后的结果'}}),USAGE
 monkeypatch.setattr(main,'call_model',inflight)
 assert client.post(f"/api/tasks/{t['id']}/messages",json={'content':'隔离在途请求'}).status_code==200
 assert calls==['mock']
 def no_replay(*args,**kwargs):pytest.fail('启动恢复或费用核对前不得重发调用')
 monkeypatch.setattr(main,'call_model',no_replay)
 monkeypatch.setattr(main,'store',Store(snapshot_root));monkeypatch.setattr(main,'DATA_ROOT',snapshot_root)
 operation_id=checkpoint['task']['active_interview_id']
 with TestClient(main.app) as restarted:
  current=restarted.get(f"/api/tasks/{t['id']}").json();b=ledger(restarted,t)
  assert current['status']=='paused' and not current.get('active_interview_id')
  for field in ('app_type','revision','requirements','configuration','runs','planning_runs'):
   assert current[field]==checkpoint['task'][field]
  assert current['messages'][:len(checkpoint['task']['messages'])]==checkpoint['task']['messages']
  assert b['entries'][0]==settled and len(b['entries'])==2
  old=checkpoint['budget']['entries'][-1];entry=b['entries'][-1]
  for field in ('id','operation_id','revision','provider_id','reserved_usd','pricing','policy_revision'):
   assert entry[field]==old[field]
  assert entry['status']=='unknown' and entry['call_status']=='interrupted_by_restart'
  assert entry['charged_usd'] is None and b['unknown_count']==1 and b['pending_count']==0
  assert b['known_estimated_usd']==checkpoint['budget']['known_estimated_usd']
  assert Decimal(b['held_estimated_usd'])==Decimal(old['reserved_usd'])>0 and b['blocker']
  progress=restarted.get(f"/api/tasks/{t['id']}/interviews/{operation_id}").json()
  assert progress['status']=='interrupted' and progress['applied'] is False
  saved_task=copy.deepcopy(current);saved_budget=copy.deepcopy(b)
 # Run the complete startup a second time: no duplicate notes or ledger entries.
 with TestClient(main.app) as restarted:
  assert restarted.get(f"/api/tasks/{t['id']}").json()==saved_task
  assert ledger(restarted,t)==saved_budget
  assert restarted.post(f"/api/tasks/{t['id']}/messages",json={'content':'未核对前继续'}).status_code==200
  assert ledger(restarted,t)['entries']==saved_budget['entries']
  assert policy(restarted,t,'2').status_code==200
  with pytest.raises(PlanningStopped):asyncio.run(call(t,p))
  assert len(ledger(restarted,t)['entries'])==2
  b=ledger(restarted,t)
  response=restarted.post(f"/api/tasks/{t['id']}/budget/entries/{entry['id']}/reconcile",json={
   'revision':t['revision'],'policy_revision':b['policy_revision'],'actual_cost_usd':'.002',
   'acknowledge_actual_bill':True,'note':'隔离模拟人工核对，非真实账单'})
  assert response.status_code==200,response.text
  assert ledger(restarted,t)['entries'][0]==settled and ledger(restarted,t)['unknown_count']==0
  assert calls==['mock']
  async def explicit_continue(*args,**kwargs):
   calls.append('explicit_mock');return json.dumps({'message':'核对后明确继续','requirements_patch':{}}),USAGE
  monkeypatch.setattr(main,'call_model',explicit_continue)
  response=restarted.post(f"/api/tasks/{t['id']}/messages",json={'content':'已核对，明确继续'})
  assert response.status_code==200,response.text
  assert calls==['mock','explicit_mock'] and len(ledger(restarted,t)['entries'])==3
  assert ledger(restarted,t)['entries'][1]['status']=='reconciled'
  assert ledger(restarted,t)['entries'][2]['id']!=entry['id']


@pytest.mark.parametrize('kind',['import','run'])
@pytest.mark.parametrize('pause_first',[False,True],ids=['busy','paused'])
def test_at20_external_checkpoint_restart_is_unknown_without_dispatch(client,monkeypatch,kind,pause_first):
 # Synthetic external checkpoints only: no Dify import/run is dispatched.
 t=create(client);finished={'id':'mock-finished','kind':kind,'status':'passed','revision':t['revision'],'outputs':{'fixture':'已保存结果'}}
 pending={'id':'mock-pending','kind':kind,'status':'pending','revision':t['revision'],'inputs':{'fixture':'隔离检查点'}}
 t.update(status='importing' if kind=='import' else 'running',runs=[finished,pending],planning_runs=[])
 main.save_task(t)
 if pause_first:assert client.post(f"/api/tasks/{t['id']}/pause").status_code==200
 before=main.get_task(t['id'])
 monkeypatch.setattr(main,'store',Store(main.DATA_ROOT))
 with TestClient(main.app) as restarted:
  current=restarted.get(f"/api/tasks/{t['id']}").json()
  assert current['status']==('paused' if pause_first else 'error')
  assert current['runs'][0]==finished and len(current['runs'])==2
  recovered=current['runs'][1]
  assert recovered['id']==pending['id'] and recovered['inputs']==pending['inputs']
  assert recovered['status']=='unknown' and recovered['completed_at']
  assert '不自动重复派发' in recovered['error']
  for field in ('revision','app_type','requirements','configuration','dify_app_id','artifact','messages'):
   assert current[field]==before[field]
 with TestClient(main.app) as restarted:
  assert restarted.get(f"/api/tasks/{t['id']}").json()==current
  assert Store(main.DATA_ROOT).get('task',t['id'])==current
