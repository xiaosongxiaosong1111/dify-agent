import copy
import json
import httpx
import pytest
from test_api import client
from test_dsl_roundtrip import prepared
from test_failure_watch import repeated, read as failure_state, decide
from app import main
from app.dify import DifyClient
from app.run_diagnostics import source_hash
from app.storage import Store


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
 def forbidden(*args,**kwargs):
  pytest.fail('AT-21 隔离检查不得访问真实 HTTP、Dify 请求或付费模型')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(DifyClient,'request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)

def state(client,t):return client.get(f"/api/tasks/{t['id']}/execution-limits").json()
def save(client,t,count=None,minutes=None,**patch):
 return client.patch(f"/api/tasks/{t['id']}/execution-limits",json={'revision':t['revision'],'policy_revision':state(client,t)['policy']['policy_revision'],'max_started_runs':count,'max_total_minutes':minutes,'acknowledge_scope':True,'note':'本次任务投入限制',**patch})

def test_zero_start_cap_blocks_before_external_operation_without_mutation(client,monkeypatch):
 from app.dify import DifyClient
 task,_=prepared(client);calls=[]
 env=main.store.get('environment',task['environment_id']);env['service_app_id']=task['dify_app_id'];main.store.put('environment',env['id'],env);main.store.set_secret(env['id'],'service_api_key','fake-service-key')
 async def fake(*a,**kw):calls.append(kw);return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
 monkeypatch.setattr(DifyClient,'run_workflow',fake)
 assert save(client,task,count=0).status_code==200
 before=copy.deepcopy(main.get_task(task['id']))
 response=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'x'}})
 assert response.status_code==409 and not calls and main.get_task(task['id'])==before,response.text

def test_old_revision_failed_and_unknown_starts_count_once_per_batch(client):
 task,_=prepared(client)
 task['runs'] += [{'id':'old','kind':'run','revision':1,'status':'failed'},{'id':'unknown','kind':'run','revision':2,'status':'unknown','result':{'conversation_case':True,'turns':[{},{}]}}]
 main.save_task(task);assert save(client,task,count=2).status_code==200
 result=state(client,task);assert result['started_runs']==2 and not result['can_start'] and result['unknown_duration_runs']==2
 task['revision']+=1;main.save_task(task);assert state(client,task)['started_runs']==2

def test_elapsed_budget_uses_recorded_request_time_and_unknown_is_not_zero(client):
 task,_=prepared(client);task['runs'].append({'id':'timed','kind':'run','status':'success','created_at':'2026-10-12T00:00:00+00:00','completed_at':'2026-10-12T00:01:00+00:00'});main.save_task(task)
 assert save(client,task,minutes=1).status_code==200
 result=state(client,task);assert result['known_elapsed_seconds']=='60' and not result['can_start']
 assert save(client,task,minutes=2).status_code==200 and state(client,task)['can_start']
 task['runs'].append({'id':'no-time','kind':'run','status':'failed'});main.save_task(task);assert not state(client,task)['can_start']

def test_policy_changes_audit_and_do_not_invalidate_business_or_reset_history(client):
 task,_=prepared(client);before=copy.deepcopy(task)
 assert save(client,task,count=2).status_code==200 and save(client,task,count=5).status_code==200
 result=state(client,task);assert len(result['policy']['history'])==2 and result['policy']['policy_revision']==2
 assert main.get_task(task['id'])==before
 assert save(client,task,count=10,policy_revision=0).status_code==409
 assert save(client,task,acknowledge_scope=False).status_code==422

def test_unknown_remote_result_does_not_use_restart_time_as_actual_completion(client):
 task,_=prepared(client);task['runs'].append({'id':'old-unknown','kind':'run','revision':1,'status':'unknown','created_at':'2026-10-12T00:00:00+00:00','completed_at':'2026-10-12T00:00:01+00:00'});main.save_task(task)
 assert save(client,task,minutes=2).status_code==200
 result=state(client,task);assert result['unknown_duration_runs']==1 and result['known_elapsed_seconds']=='0' and not result['can_start']

@pytest.mark.parametrize('count,minutes',[(True,None),(-1,None),(10001,None),(None,0),(None,True),(None,10081)])
def test_invalid_policy_is_rejected_without_task_mutation(client,count,minutes):
 task,_=prepared(client);before=copy.deepcopy(task);assert save(client,task,count=count,minutes=minutes).status_code==422
 assert main.get_task(task['id'])==before


def dispatch(client,task,query='example'):
 return client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':query}})


def configure_service(task):
 env=main.store.get('environment',task['environment_id'])
 env['service_app_id']=task['dify_app_id']
 main.store.put('environment',env['id'],env)
 main.store.set_secret(env['id'],'service_api_key','synthetic-at21-key')


def stop_report(client,task):
 response=client.get(f"/api/tasks/{task['id']}/report")
 assert response.status_code==200,response.text
 return json.loads(response.text.split('## 执行停止策略与重复失败决定\n\n',1)[1].split('\n\n',1)[0])


def test_repeated_failure_blocks_public_run_and_preserves_evidence_after_reopen(client):
 task=repeated(client);configure_service(task);before=copy.deepcopy(main.get_task(task['id']))
 for _ in range(3):
  response=dispatch(client,task)
  assert response.status_code==409 and '相同输入连续两次' in response.text,response.text
 assert main.get_task(task['id'])==before
 assert not main.store.list('failure_decision')
 main.store=Store(main.store.root)
 watch=failure_state(client,task);group=watch['paused_groups'][0]
 assert group['run_ids']==['failed-re-run','failed-again']
 assert group['consecutive_failures']==2 and group['nodes'][0]['node_id']=='code'
 assert {option['action'] for option in watch['options']}=={'run','model_repair','change_plan'}
 assert 'example' not in json.dumps(watch) and "name 're'" not in json.dumps(watch)
 report=stop_report(client,task)
 assert report['repeated_failures'][0]['run_ids']==group['run_ids']
 assert report['verification']=='saved_controls_not_business_acceptance'
 # 暂停的是匹配输入的操作门禁；任务总状态不一定改为 paused。
 assert main.get_task(task['id'])==before


@pytest.mark.parametrize('action',['change_plan','model_repair'])
def test_other_next_step_never_authorizes_a_run(client,action):
 task=repeated(client);configure_service(task);before=copy.deepcopy(main.get_task(task['id']))
 assert decide(client,task,action).status_code==200
 response=dispatch(client,task)
 assert response.status_code==409 and '下一步' in response.text,response.text
 permission=failure_state(client,task)['paused_groups'][0]['permission']
 assert permission['action']==action
 assert permission['status']==('paused' if action=='change_plan' else 'ready')
 assert main.get_task(task['id'])==before


def test_explicit_once_run_failure_is_recorded_without_automatic_retry(client,monkeypatch):
 task=repeated(client);configure_service(task);calls=[]
 async def failed(*args,**kwargs):
  calls.append(1)
  return {'data':{'status':'failed','error':"NameError: name 're' is not defined"}}
 monkeypatch.setattr(DifyClient,'run_workflow',failed)
 assert decide(client,task).status_code==200
 main.store=Store(main.store.root)
 response=dispatch(client,task)
 assert response.status_code==502 and calls==[1],response.text
 current=main.get_task(task['id']);latest=current['runs'][-1]
 assert latest['status']=='failed' and latest['result']['data']['status']=='failed'
 assert current['runs'][:-1]==task['runs']
 assert main.store.list('failure_decision')[0]['status']=='used'
 # 新运行须另读可信轨迹；本地合成匹配轨迹后，同一失败再次暂停。
 report=copy.deepcopy(task['runs'][-1]['diagnostics'][-1])
 report.update(id='third-synthetic-diagnostic',source_hash=source_hash(latest))
 latest['diagnostics']=[report];main.save_task(current)
 group=failure_state(client,current)['paused_groups'][0]
 assert group['consecutive_failures']==3 and group['permission'] is None
 assert dispatch(client,current).status_code==409 and calls==[1]
 assert decide(client,current,evidence_token=main.store.list('failure_decision')[0]['evidence_token']).status_code==409
 assert len(main.get_task(task['id'])['runs'])==len(current['runs'])


@pytest.mark.parametrize('limit',['starts','elapsed','unknown_price'])
def test_repeated_failure_permission_cannot_bypass_limits_or_be_consumed_by_them(client,limit):
 task=repeated(client);configure_service(task)
 if limit=='elapsed':
  for run in task['runs']:
   if run['kind']=='run':run.update(created_at='2026-10-21T00:00:00+00:00',completed_at='2026-10-21T00:01:00+00:00')
  main.save_task(task)
 patch={'starts':{'count':2},'elapsed':{'minutes':2},'unknown_price':{'max_reported_cost_usd':'1'}}[limit]
 assert save(client,task,**patch).status_code==200
 assert decide(client,task).status_code==200
 before=copy.deepcopy(main.get_task(task['id']));policy=copy.deepcopy(state(client,task))
 response=dispatch(client,task)
 assert response.status_code==409 and not policy['can_start'],response.text
 assert policy['blockers'] and policy['blockers'][0] in response.json()['detail']
 assert main.get_task(task['id'])==before and state(client,task)==policy
 assert failure_state(client,task)['paused_groups'][0]['permission']['status']=='ready'
 report=stop_report(client,task)
 assert report['limit_blockers']==policy['blockers'] and not report['can_start_by_limits']


@pytest.mark.parametrize('mutation',['revision','evidence','environment'])
def test_stale_next_step_is_rejected_without_changing_current_task(client,mutation):
 task=repeated(client);token=failure_state(client,task)['paused_groups'][0]['evidence_token']
 if mutation=='revision':task['revision']+=1
 elif mutation=='evidence':task['runs'][-1]['diagnostics'][-1]['source_hash']='obsolete'
 else:
  env=main.store.get('environment',task['environment_id']);env['base_url']='https://changed.invalid';main.store.put('environment',env['id'],env)
 main.save_task(task);before=copy.deepcopy(main.get_task(task['id']))
 response=client.post(f"/api/tasks/{task['id']}/failure-watch/decision",json={'revision':task['revision'],'evidence_token':token,'action':'run','acknowledge_review':True,'note':'核对旧证据'})
 assert response.status_code==409,response.text
 assert main.get_task(task['id'])==before and not main.store.list('failure_decision')


@pytest.mark.parametrize('mutation',['unknown','untrusted_graph','truncated','conversation','different_error'])
def test_incomplete_or_changed_evidence_is_not_reported_as_same_failure(client,mutation):
 task=repeated(client);run=task['runs'][-1];report=run['diagnostics'][-1]
 if mutation=='unknown':run['status']='unknown'
 elif mutation=='untrusted_graph':report['source_graph']['matched']=False
 elif mutation=='truncated':report['truncated']=True
 elif mutation=='conversation':run['conversation_context']={'conversation_id':'synthetic-session'}
 else:report['nodes'][0]['error']='TypeError: unsupported operand'
 report['source_hash']=source_hash(run);main.save_task(task)
 assert failure_state(client,task)['paused_groups']==[]
 result=stop_report(client,task)
 assert result['repeated_failures']==[]
 assert result['verification']=='saved_controls_not_business_acceptance'


def test_repeated_failure_blocks_model_candidate_before_budget_or_request_records(client):
 from test_task_budget import provider
 task=repeated(client);p=provider(client)
 task['configuration']['assistant_provider_id']=p['id'];main.save_task(task)
 url=f"/api/tasks/{task['id']}/runs/failed-again"
 response=client.get(url+'/repair-model-outbound',params={'revision':task['revision'],'diagnostic_id':'second-diagnostic'})
 assert response.status_code==200,response.text
 assert response.json()['settings']['max_retries']==0
 before=copy.deepcopy(main.get_task(task['id']));budget=copy.deepcopy(main.store.list('task_budget'))
 response=client.post(url+'/repair-model-generate',json={'revision':task['revision'],'diagnostic_id':'second-diagnostic','outbound_token':response.json()['outbound_token'],'acknowledge_data_and_cost':True})
 assert response.status_code==409 and '相同输入连续两次' in response.text,response.text
 assert main.get_task(task['id'])==before
 assert not main.store.list('repair_model_request') and main.store.list('task_budget')==budget


def test_reaching_limit_does_not_cancel_dispatched_run_and_raise_only_allows_next_start(client,monkeypatch):
 task,_=prepared(client);configure_service(task);calls=[]
 assert save(client,task,count=1).status_code==200
 async def success(*args,**kwargs):
  calls.append(1)
  active=main.execution_limits.state(main.get_task(task['id']))
  assert active['started_runs']==len(calls) and not active['can_start']
  return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
 monkeypatch.setattr(DifyClient,'run_workflow',success)
 response=dispatch(client,task);assert response.status_code==200,response.text
 first=copy.deepcopy(response.json()['runs'])
 assert first[-1]['status']=='success' and calls==[1]
 assert dispatch(client,task).status_code==409 and calls==[1]
 assert save(client,task,count=2).status_code==200
 assert main.get_task(task['id'])['runs']==first and state(client,task)['started_runs']==1
 assert dispatch(client,task).status_code==200 and calls==[1,1]
 assert dispatch(client,task).status_code==409 and calls==[1,1]
 assert main.get_task(task['id'])['runs'][:-1]==first


@pytest.mark.parametrize('price,currency',[('1','USD'),(None,None),('0.01','CNY')])
def test_reported_price_threshold_blocks_without_treating_unknown_or_other_currency_as_zero(client,price,currency):
 from test_execution_costs import run as priced_run
 task,_=prepared(client);configure_service(task)
 # 历史 Chatflow 报价为合成记录；Workflow 返回本身不提供可信费用报价。
 task['runs'].append(priced_run(price=price,currency=currency));main.save_task(task)
 assert save(client,task,max_reported_cost_usd='1').status_code==200
 result=state(client,task);before=copy.deepcopy(main.get_task(task['id']))
 assert not result['can_start']
 assert result['known_reported_usd']==('1' if currency=='USD' else '0')
 assert result['unavailable_usd_executions']==(0 if currency=='USD' else 1)
 response=dispatch(client,task)
 assert response.status_code==409 and result['blockers'][0] in response.json()['detail'],response.text
 assert main.get_task(task['id'])==before
 report=stop_report(client,task)
 assert report['usage']['known_reported_usd']==result['known_reported_usd']
 assert '不代表费用硬上限' in report['limit_note']
