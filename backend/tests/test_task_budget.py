import asyncio,copy,json
from decimal import Decimal
import pytest
from test_api import client,create,approved
from test_planning import plan
from test_coverage import items
from app import main
from app.task_budget import money
from app.planning import PlanningStopped
from app.providers import ProviderError

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
