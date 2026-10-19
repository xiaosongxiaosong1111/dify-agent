import asyncio,copy,json
from datetime import datetime,timezone,timedelta
import pytest
from test_api import client,approved,create_env,create
from test_task_budget import provider
from app import main
from app import configuration_proposals as module
from app.dify import DifyError

RULES=[{'name':'temperature','type':'float','min':0,'max':1},{'name':'max_tokens','type':'int','min':1,'max':4096},{'name':'thinking','type':'boolean','required':False}]
class Adapter:
 calls=[]
 def __init__(self,*a):pass
 async def models(self,kind):
  self.calls.append('models');return {'data':[{'provider':'test/provider','models':[{'model':'test-model','status':'active','model_properties':{'mode':'chat'}}]}]}
 async def model_parameters(self,*a):self.calls.append('parameters');return {'data':RULES}
 async def console_datasets(self,page,limit):self.calls.append('datasets');return {'data':[{'id':'kb_readable','name':'产品说明','document_count':2}], 'has_more':False}

def prepared(client,monkeypatch,app_type='workflow'):
 env=create_env(client);t=approved(client,app_type=app_type,env_id=env['id']);Adapter.calls=[];monkeypatch.setattr(module,'DifyClient',Adapter)
 r=client.post(f"/api/tasks/{t['id']}/configuration-proposal/resources",json={'revision':t['revision']});assert r.status_code==200,r.text
 return t
def candidate(**patch):
 patch=patch or {'temperature':.3,'max_tokens':1024}
 return {'schema_version':1,'configuration':patch,'reasons':[{'field':k,'reason':'按测试说明拟议，需用户检查。','experience':'输出变化，待验证。','cost':'依用量计费，单价未知。','manual_work':'核对样例。'} for k in patch],'open_issues':[],'notes':'只是技术配置候选，不是业务或真实资源验证。'}
def save(t,c):assert main.configuration_proposals.validate(t,c)['valid'];main.configuration_proposals.save(t,c)
def state(client,t):return client.get(f"/api/tasks/{t['id']}/configuration-proposal").json()
def adopt(client,t,**kw):
 s=state(client,t);r=s['record'];return client.post(f"/api/tasks/{t['id']}/configuration-proposal/adopt",json={'revision':t['revision'],'proposal_id':r['id'],'proposal_token':r['proposal_token'],'acknowledge_changes':True,**kw})

def test_discovery_reads_only_and_never_changes_configuration(client,monkeypatch):
 t=prepared(client,monkeypatch);s=state(client,t);assert Adapter.calls==['models','parameters','datasets']
 assert s['snapshot_current'] and s['snapshot']['models'][0]['rules']==[{**r,'label':r['name']} for r in RULES] and s['snapshot']['datasets'][0]['id']=='kb_readable'
 assert main.get_task(t['id'])['configuration']==t['configuration'] and not s['record']

def test_generate_saves_proposal_and_counts_budget_without_applying(client,monkeypatch):
 t=prepared(client,monkeypatch);p=provider(client);t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json();old=copy.deepcopy(t['configuration'])
 async def model(*a,**kw):return json.dumps(candidate()),{'prompt_tokens':10,'completion_tokens':20}
 monkeypatch.setattr(main,'call_model',model)
 r=client.post(f"/api/tasks/{t['id']}/configuration-proposal/generate",json={'revision':t['revision']});assert r.status_code==200,r.text
 assert r.json()['configuration']==old and not r.json()['configuration_confirmed']
 s=state(client,t);assert s['can_adopt'] and len(s['diffs'])==2 and main.budgets.get(t['id'])['entries'][0]['kind']=='configuration'
 assert main.get_task(t['id'])['planning_runs'][-1]['status']=='succeeded'

def test_explicit_adoption_revision_invalidation_and_no_dify_write(client,monkeypatch):
 t=prepared(client,monkeypatch);save(t,candidate());assert adopt(client,t,acknowledge_changes=False).status_code==422
 r=adopt(client,t);assert r.status_code==200,r.text;t2=r.json();assert t2['revision']==t['revision']+1 and t2['requirements_confirmed'] and not t2['configuration_confirmed']
 assert t2['configuration']['temperature']==.3 and not t2['dify_app_id'] and not t2['runs']
 assert adopt(client,t2).status_code==409 and state(client,t2)['record']['status']=='adopted'
 assert '集中配置方案记录' in client.get(f"/api/tasks/{t2['id']}/report").text

@pytest.mark.parametrize('patch',[{'dify_model':'made-up'},{'dataset_ids':['fabricated']},{'temperature':2},{'max_tokens':99999},{'model_parameters':{'made_up':True}},{'model_parameters':{'thinking':'yes'}},{'conversation_memory':True},{'opening_statement':'不会在 Workflow 生效'},{'assistant_provider_id':'attack'},{'api_key':'secret'}])
def test_invented_resources_bad_parameters_and_ignored_fields_rejected(client,monkeypatch,patch):
 t=prepared(client,monkeypatch);v=main.configuration_proposals.validate(t,candidate(**patch));assert not v['valid'],patch

def test_model_change_requires_all_coupled_fields(client,monkeypatch):
 t=prepared(client,monkeypatch);snap=main.configuration_proposals.snapshot(t['id']);snap['models'].append({**snap['models'][0],'model':'second-model'});main.store.put('configuration_resources',t['id'],snap)
 assert not main.configuration_proposals.validate(t,candidate(dify_model_provider='test/provider',dify_model='second-model'))['valid']
 assert main.configuration_proposals.validate(t,candidate(dify_model_provider='test/provider',dify_model='second-model',temperature=.2,max_tokens=1024,model_parameters={}))['valid']

@pytest.mark.parametrize('change',['requirements','environment','refresh','expired'])
def test_stale_proposal_cannot_apply(client,monkeypatch,change):
 t=prepared(client,monkeypatch);save(t,candidate())
 if change=='requirements':t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':{'goal':'改变目标'}}).json()
 elif change=='environment':env=main.store.get('environment',t['environment_id']);env['connection_revision']=99;main.store.put('environment',env['id'],env)
 elif change=='refresh':assert client.post(f"/api/tasks/{t['id']}/configuration-proposal/resources",json={'revision':t['revision']}).status_code==200
 else:snap=main.configuration_proposals.snapshot(t['id']);snap['observed_at']=(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat();main.store.put('configuration_resources',t['id'],snap)
 assert adopt(client,t).status_code==409

def test_open_issues_show_impacts_and_block_adoption(client,monkeypatch):
 t=prepared(client,monkeypatch);c=candidate();c['open_issues']=[{'question':'是否接受关闭重排？','recommendation':'当前不支持，需要用户决定。','experience':'排序体验变化','cost':'费用待核对','manual_work':'需评估检索结果'}];save(t,c)
 assert not state(client,t)['can_adopt'] and adopt(client,t).status_code==409

def test_offline_retained_resources_require_ack_not_invented_ids(client,monkeypatch):
 t=approved(client);r=client.post(f"/api/tasks/{t['id']}/configuration-proposal/resources",json={'revision':t['revision']});assert r.status_code==200
 save(t,candidate());assert state(client,t)['record']['resource_warnings'] and adopt(client,t).status_code==422
 assert adopt(client,t,acknowledge_unverified_resources=True).status_code==200

def test_mock_change_has_separate_explicit_acceptance(client,monkeypatch):
 t=prepared(client,monkeypatch);save(t,candidate(mock_dependencies=['订单接口仅使用样例数据']))
 assert adopt(client,t).status_code==422
 assert adopt(client,t,acknowledge_mock_changes=True).status_code==200

def test_saved_plan_requires_review_after_adoption(client,monkeypatch):
 from test_planning import plan
 t=prepared(client,monkeypatch);t=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':plan()}).json();save(t,candidate());r=adopt(client,t);assert r.status_code==200
 assert r.json()['plan_stale'] and r.json()['workflow_plan']==t['workflow_plan']

def test_source_failure_is_visible_not_fake_success(client,monkeypatch):
 class Failed(Adapter):
  async def models(self,*a):raise DifyError('HTTP 401')
  async def console_datasets(self,*a):raise DifyError('HTTP 403')
 t=prepared(client,monkeypatch);monkeypatch.setattr(module,'DifyClient',Failed)
 r=client.post(f"/api/tasks/{t['id']}/configuration-proposal/resources",json={'revision':t['revision']});assert r.status_code==200
 assert len(r.json()['snapshot']['errors'])==2 and not r.json()['snapshot']['models'] and not r.json()['snapshot']['datasets']

def test_pause_stops_next_read_and_keeps_previous_snapshot(client,monkeypatch):
 t=prepared(client,monkeypatch);old=state(client,t)['snapshot']['id']
 class Pausing(Adapter):
  async def models(self,*a):main.pause(t['id']);return await super().models(*a)
 monkeypatch.setattr(module,'DifyClient',Pausing);r=client.post(f"/api/tasks/{t['id']}/configuration-proposal/resources",json={'revision':t['revision']})
 assert r.status_code==409 and state(client,t)['snapshot']['id']==old and not main.configuration_proposals.busy(t['id'])

def test_restart_clears_read_busy_without_replaying(client):
 t=create(client);main.store.put('configuration_discovery',t['id'],{'id':t['id'],'status':'running'});assert main.configuration_proposals.busy(t['id'])
 main.configuration_proposals.recover();assert not main.configuration_proposals.busy(t['id']) and state(client,t)['discovery']['status']=='interrupted'

def test_code_only_workflow_does_not_require_model_choice(client,monkeypatch):
 from test_planning import plan
 t=prepared(client,monkeypatch);t=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':plan()}).json();t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'dify_model_provider':'','dify_model':''}}).json()
 assert main.configuration_proposals.validate(t,candidate(resource_plan='仅新建代码转换应用，未使用模型。'))['valid']

def test_discovery_is_bounded_and_prioritizes_current_model(client,monkeypatch):
 t=prepared(client,monkeypatch)
 class Many(Adapter):
  async def models(self,*a):return {'data':[{'provider':'test/provider','models':[{'model':name,'status':'active','model_properties':{'mode':'chat'}} for name in ['extra'+str(i) for i in range(8)]+['test-model']]}]}
  async def console_datasets(self,page,limit):return {'data':[{'id':f'page{page}','name':'分页数据'}],'has_more':True}
 monkeypatch.setattr(module,'DifyClient',Many);r=client.post(f"/api/tasks/{t['id']}/configuration-proposal/resources",json={'revision':t['revision']});snap=r.json()['snapshot']
 assert snap['models_truncated'] and len(snap['models'])==6 and snap['models'][0]['model']=='test-model'
 assert snap['datasets_truncated'] and len(snap['datasets'])==3

def test_no_reentry_during_discovery(client,monkeypatch):
 t=prepared(client,monkeypatch)
 class Reading(Adapter):
  async def models(self,*a):
   r=await asyncio.to_thread(client.patch,f"/api/tasks/{t['id']}",json={'configuration':{'temperature':.8}});assert r.status_code==409
   return await super().models(*a)
 monkeypatch.setattr(module,'DifyClient',Reading);assert client.post(f"/api/tasks/{t['id']}/configuration-proposal/resources",json={'revision':t['revision']}).status_code==200

def test_user_pause_keeps_model_candidate_without_applying(client,monkeypatch):
 t=prepared(client,monkeypatch);p=provider(client);t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json()
 async def model(*a,**kw):main.pause(t['id']);return json.dumps(candidate()),{'prompt_tokens':10,'completion_tokens':20}
 monkeypatch.setattr(main,'call_model',model);r=client.post(f"/api/tasks/{t['id']}/configuration-proposal/generate",json={'revision':t['revision']})
 assert r.status_code==422 and not state(client,t)['record'] and main.get_task(t['id'])['configuration']==t['configuration']
 assert main.budgets.get(t['id'])['entries'][0]['status']=='settled'

def test_empty_catalog_requires_model_issue_not_claim_of_completion(client,monkeypatch):
 t=create(client);client.post(f"/api/tasks/{t['id']}/configuration-proposal/resources",json={'revision':t['revision']})
 assert not main.configuration_proposals.validate(t,candidate())['valid']
 c=candidate();c['open_issues']=[{'question':'应用模型未配置','recommendation':'先连接或填写实际资源','experience':'暂不能真实运行','cost':'待核对','manual_work':'提供实际连接条件'}]
 assert main.configuration_proposals.validate(t,c)['valid'];save(t,c);assert not state(client,t)['can_adopt']

def test_catalog_empty_documents_require_resource_acceptance(client,monkeypatch):
 t=prepared(client,monkeypatch);snap=main.configuration_proposals.snapshot(t['id']);snap['datasets'][0]['document_count']=0;main.store.put('configuration_resources',t['id'],snap);save(t,candidate(dataset_ids=['kb_readable']))
 assert state(client,t)['record']['resource_warnings'] and adopt(client,t).status_code==422

def test_cross_task_proposal_cannot_be_adopted(client,monkeypatch):
 t=prepared(client,monkeypatch);other=prepared(client,monkeypatch);save(t,candidate());save(other,candidate());foreign=state(client,other)['record']
 assert adopt(client,t,proposal_id=foreign['id'],proposal_token=foreign['proposal_token']).status_code==409
