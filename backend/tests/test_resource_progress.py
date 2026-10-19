import copy,sqlite3,uuid
import pytest
from test_api import client,approved,create_env
from app import main
from app.resource_progress import KINDS
from app.run_diagnostics import binding
from app.schedule_stop import binding as schedule_binding

APP=str(uuid.uuid4());RUN=str(uuid.uuid4());FORM=str(uuid.uuid4());TRIGGER=str(uuid.uuid4())

def row(t,env,state='unknown',**fields):return {'id':str(uuid.uuid4()),'task_id':t['id'],'revision':t['revision'],'environment_id':env['id'],'environment_url':env['base_url'],'environment_binding':binding(env),'state':state,'app_id':APP,'workflow_run_id':RUN,'form':{'form_id':FORM,'content':'PRIVATE-OLD-CUSTOMER-CONTENT','form_token':'PRIVATE-TOKEN'},'trigger_id':TRIGGER,'outbound_dsl':'PRIVATE-DSL','input':{'secret':'PRIVATE-INPUT'},'api_key':'PRIVATE-KEY','error':'PRIVATE-ERROR','created_at':'2026-10-14T10:00:00Z',**fields}
def put(kind,r):main.store.put(kind,r['id'],r)

def test_existing_six_kinds_and_new_empty_upload_group_remain_private_after_plan_removed(client,monkeypatch):
 env=create_env(client);t=approved(client,env_id=env['id']);other=approved(client,env_id=env['id']);states=['prepared_unapproved','waiting_human','unknown','stop_not_confirmed','enabled','disabled']
 for kind,state in zip(KINDS,states):put(kind,row(t,env,state));put(kind,row(other,env,'unknown'))
 before=copy.deepcopy(main.get_task(t['id']))
 async def forbidden(*args,**kw):pytest.fail('本机资源摘要不能请求平台或模型')
 monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 monkeypatch.setattr(main.store,'secret',lambda *a,**kw:pytest.fail('元数据索引不得读取或解密凭据'))
 response=client.get(f"/api/tasks/{t['id']}/resource-progress");assert response.status_code==200,response.text;value=response.json()
 assert len(value['groups'])==8 and len(value['records'])==6 and value['totals']=={'total':6,'ongoing':1,'uncertain':2,'enabled_observed':1}
 assert all(r['environment_url']==env['base_url'] and r['app_id']==APP and r['form_id']==FORM and r['current_revision'] for r in value['records'])
 assert 'PRIVATE-' not in response.text and not value['platform_checked'] and not value['business_verified']
 assert main.get_task(t['id'])==before and all(not r['business_verified'] for r in value['records'])

def test_old_revision_original_target_kept_not_replaced_by_current_profile(client):
 env=create_env(client);t=approved(client,env_id=env['id']);r=row(t,env,'waiting_human');put('human_runtime_run',r)
 nextenv=copy.deepcopy(env);nextenv['id']=str(uuid.uuid4());nextenv['base_url']='http://127.0.0.1:8081';main.store.put('environment',nextenv['id'],nextenv)
 t.update(revision=t['revision']+1,environment_id=nextenv['id'],workflow_plan=None);main.store.put('task',t['id'],t)
 got=client.get(f"/api/tasks/{t['id']}/resource-progress").json()['records'][0]
 assert not got['current_revision'] and not got['current_task_target'] and got['original_profile_matches'] and got['environment_url']==env['base_url']
 env['base_url']='http://127.0.0.1:8082';main.store.put('environment',env['id'],env)
 got=client.get(f"/api/tasks/{t['id']}/resource-progress").json()['records'][0]
 assert not got['original_profile_matches'] and got['environment_url']=='https://dify.example'

def test_legacy_stop_address_only_recovered_when_original_binding_matches(client):
 env=create_env(client);t=approved(client,env_id=env['id']);r=row(t,env,'disabled');r.pop('environment_url');r.pop('environment_binding');r['environment_binding_sha256']=schedule_binding(env);put('schedule_stop',r)
 got=client.get(f"/api/tasks/{t['id']}/resource-progress").json()['records'][0];assert got['environment_url']==env['base_url']
 env['base_url']='http://127.0.0.1:8082';main.store.put('environment',env['id'],env)
 got=client.get(f"/api/tasks/{t['id']}/resource-progress").json()['records'][0];assert got['environment_url'] is None and not got['original_profile_matches']

def test_totals_full_history_while_display_bounded_not_dropped_silently(client):
 env=create_env(client);t=approved(client,env_id=env['id'])
 for i in range(15):put('human_runtime_run',row(t,env,'unknown' if i==0 else 'waiting_human'))
 value=client.get(f"/api/tasks/{t['id']}/resource-progress?limit=2").json()
 assert value['totals']['total']==15 and value['totals']['ongoing']==14 and value['totals']['uncertain']==1 and len(value['records'])==2
 assert value['history_truncated'] and next(g for g in value['groups'] if g['kind']=='human_runtime_run')['history_truncated']

def test_untrusted_identifiers_status_url_dates_do_not_echo_and_flag_uncertain(client):
 env=create_env(client);t=approved(client,env_id=env['id']);r=row(t,env,'PRIVATE-STATE',app_id='PRIVATE-APP',environment_url='http://user:PRIVATE-PASSWORD@localhost',created_at='PRIVATE-DATE');put('human_runtime_run',r)
 response=client.get(f"/api/tasks/{t['id']}/resource-progress");assert response.status_code==200 and 'PRIVATE-' not in response.text
 value=response.json();got=value['records'][0];assert got['state']=='unrecognized_record' and got['uncertain'] and got['app_id'] is None and got['created_at'] is None
 assert value['totals']['uncertain']==1

def test_boolean_revision_not_displayed_as_current_integer_revision(client):
 env=create_env(client);t=approved(client,env_id=env['id']);r=row(t,env,'unknown',revision=True);put('human_runtime_run',r)
 value=client.get(f"/api/tasks/{t['id']}/resource-progress").json()['records'][0]
 assert value['revision'] is None and not value['current_revision']

@pytest.mark.parametrize('same_task',[True,False])
def test_decision_parent_link_only_to_same_task_app_and_remote_run(client,same_task):
 env=create_env(client);t=approved(client,env_id=env['id']);other=t if same_task else approved(client,env_id=env['id'])
 parent=row(other,env,'awaiting_resume');put('human_runtime_run',parent);child=row(t,env,'accepted',run_id=parent['id']);put('human_decision',child)
 value=client.get(f"/api/tasks/{t['id']}/resource-progress").json();item=next(r for r in value['records'] if r['kind']=='human_decision')
 assert item['parent_run_id']==(parent['id'] if same_task else None)

@pytest.mark.parametrize('kind,state,status,ongoing,enabled',[
 ('schedule_publication','published_and_disabled','enabled',0,1),
 ('schedule_enable','enabled','disabled',0,0),
 ('human_runtime_run','platform_finished','paused',1,0)])
def test_later_saved_observation_not_hidden_by_original_write_outcome(client,kind,state,status,ongoing,enabled):
 env=create_env(client);t=approved(client,env_id=env['id']);r=row(t,env,state,reconciled_status=status,reconciled_at='2026-10-14T12:00:00Z')
 if kind=='human_runtime_run':r.update(observed_status=status,observed_at=r['reconciled_at'])
 put(kind,r);value=client.get(f"/api/tasks/{t['id']}/resource-progress").json()
 assert value['totals']['ongoing']==ongoing and value['totals']['enabled_observed']==enabled
 assert value['records'][0]['state']==state and value['records'][0]['latest_observed_status']==status

def test_equal_time_conflicting_observations_flag_uncertain_not_choose_a_winner(client):
 env=create_env(client);t=approved(client,env_id=env['id']);r=row(t,env,'platform_finished',observed_status='paused',observed_at='2026-10-14T12:00:00Z',resume_evidence={'platform_status':'succeeded','checked_at':'2026-10-14T12:00:00Z'});put('human_runtime_run',r)
 value=client.get(f"/api/tasks/{t['id']}/resource-progress").json()
 assert value['totals']['ongoing']==1 and value['totals']['uncertain']==1 and value['records'][0]['latest_observed_status']=='conflicting_observations'

def test_unattributable_corrupt_record_reported_not_claimed_absent(client):
 t=approved(client)
 with main.store.connect() as conn:conn.execute('INSERT INTO objects VALUES(?,?,?)',('human_runtime_run',str(uuid.uuid4()),'PRIVATE-CORRUPT-JSON'))
 response=client.get(f"/api/tasks/{t['id']}/resource-progress");assert response.status_code==200,response.text
 assert response.json()['unattributable_corrupt_record_present'] and 'PRIVATE-' not in response.text

def test_db_failure_safe_and_untouched(client,monkeypatch):
 t=approved(client);original=main.store.connect
 def fail():raise sqlite3.OperationalError('PRIVATE-INTERNAL-DETAIL')
 monkeypatch.setattr(main.store,'connect',fail)
 # Task read also uses connect: only fail once metadata connection starts.
 from app import resource_progress
 monkeypatch.setattr(main,'get_task',lambda item:t)
 response=client.get(f"/api/tasks/{t['id']}/resource-progress");assert response.status_code==503 and 'PRIVATE-' not in response.text
 monkeypatch.setattr(main.store,'connect',original)

@pytest.mark.parametrize('limit',[0,26,'invalid'])
def test_summary_limits_and_missing_task(client,limit):
 t=approved(client);assert client.get(f"/api/tasks/{t['id']}/resource-progress?limit={limit}").status_code==422
 assert client.get('/api/tasks/'+str(uuid.uuid4())+'/resource-progress').status_code==404
