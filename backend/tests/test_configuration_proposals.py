import asyncio,copy,json
from datetime import datetime,timezone,timedelta
import pytest
import httpx
from test_api import client,approved,create_env,create
from test_task_budget import provider
from app import main
from app import configuration_proposals as module
from app.dify import DifyError
from app.storage import Store

@pytest.fixture(autouse=True)
def forbid_configuration_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('配置方案隔离检查不得访问真实 HTTP 或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)

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


# AT-07: fixed directory metadata proves local selection gates, not retrieval quality.
CATALOG = [
    {'id': 'kb_product', 'name': '业务资料', 'description': '产品规格说明', 'document_count': 2, 'available_document_count': 2},
    {'id': 'kb_hr', 'name': '业务资料', 'description': '内部人事制度，不属于客户售后范围', 'document_count': 3, 'available_document_count': 3},
    {'id': 'kb_returns', 'name': '业务资料', 'description': '退货流程及期限', 'document_count': 1, 'available_document_count': 1},
]


@pytest.fixture
def multiple_catalog(monkeypatch):
    calls = []

    class Multiple(Adapter):
        async def console_datasets(self, page, limit):
            calls.append((page, limit))
            rows = CATALOG[:2] if page == 1 else CATALOG[2:]
            return {'data': copy.deepcopy(rows), 'has_more': page == 1}

    monkeypatch.setattr(module, 'DifyClient', Multiple)
    return calls


def discover_multiple(client, task):
    response = client.post(f"/api/tasks/{task['id']}/configuration-proposal/resources", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert response.json()['snapshot']['datasets'] == CATALOG
    assert not response.json()['snapshot']['datasets_truncated']
    return response.json()


def dataset_candidate(ids):
    value = candidate(dataset_ids=ids)
    value['reasons'][0].update(
        reason='按客户售后范围选择产品规格库 kb_product 与退货库 kb_returns；人事库 kb_hr 不在本次范围。同名目录不能证明正文正确。',
        experience='组合产品与退货资料；目录元数据不证明检索命中或内容无冲突。',
        cost='检索及模型费用待实际核对，本隔离检查没有真实费用。',
        manual_work='需人工核对具体库 ID、资料授权、正文与售后样例。',
    )
    return value


@pytest.mark.parametrize('app_type', ['workflow', 'advanced-chat', 'agent'])
def test_at07_multiple_datasets_generate_review_adopt_and_persist(client, monkeypatch, multiple_catalog, app_type):
    from test_intake import new, manual

    env = create_env(client)
    task = new(client, app_type)
    response = client.patch(f"/api/tasks/{task['id']}", json={
        'environment_id': env['id'],
        'requirements': {'goal': '回答产品与退货售后问题，不回答人事问题。',
                         'audience': '客户售后人员。', 'input': '单条客户产品或退货问题。',
                         'output': '中文答复并标明参考资料；本检查不执行实际检索。',
                         'rules': '仅使用明确选择的产品与退货库，不将同名人事库用于回答。',
                         'knowledge': '选择已授权的产品规格与退货资料，明确排除人事资料；知识命中待验证。',
                         'exceptions': '缺少资料或无法回答时明确提示并转人工，不编造结论。',
                         'tests': '产品规格与退货问题应参考各自资料；人事问题提示超出范围，真实命中待验证。'},
    })
    assert response.status_code == 200, response.text
    task = response.json()
    response = manual(client, task)
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={'kind': 'requirements', 'revision': task['revision']})
    assert response.status_code == 200, response.text
    p = provider(client)
    response = client.patch(f"/api/tasks/{task['id']}", json={'configuration': {
        'assistant_provider_id': p['id'], 'dify_model_provider': 'test/provider', 'dify_model': 'test-model',
    }})
    assert response.status_code == 200, response.text
    task = response.json()
    before = copy.deepcopy(task)
    discover_multiple(client, task)
    assert multiple_catalog == [(1, 100), (2, 100)]
    assert main.get_task(task['id']) == before
    selected = ['kb_returns', 'kb_product']
    proposed = dataset_candidate(selected)
    calls = []

    async def controlled(*args, **kwargs):
        context = json.loads(args[2][1]['content'])
        calls.append(context)
        assert context['app_type'] == app_type
        assert context['requirements'] == task['requirements']
        assert context['resources']['datasets'] == CATALOG
        assert context['configuration']['dataset_ids'] == []
        return json.dumps(proposed, ensure_ascii=False), {'prompt_tokens': 10, 'completion_tokens': 20}

    monkeypatch.setattr(main, 'call_model', controlled)
    response = client.post(f"/api/tasks/{task['id']}/configuration-proposal/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    generated = response.json()
    assert len(calls) == 1 and generated['revision'] == task['revision']
    assert generated['configuration'] == task['configuration']
    assert generated['requirements_confirmed'] and not generated['configuration_confirmed']
    current = state(client, task)
    assert current['can_adopt'] and current['record']['candidate'] == proposed
    assert current['diffs'] == [{**proposed['reasons'][0], 'before': [], 'after': selected, 'changed': True}]
    assert current['record']['resource_warnings'] == []  # No warning is not proof of retrieval success.
    reopened = Store(main.store.root)
    assert reopened.get('configuration_resources', task['id']) == current['snapshot']
    assert reopened.get('configuration_proposal', current['record']['id']) == current['record']
    monkeypatch.setattr(main, 'store', reopened)
    unchanged = copy.deepcopy(main.get_task(task['id']))
    assert adopt(client, task, acknowledge_changes=False).status_code == 422
    assert main.get_task(task['id']) == unchanged
    response = adopt(client, task)
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied['configuration']['dataset_ids'] == selected
    assert applied['configuration'] == {**task['configuration'], 'dataset_ids': selected}
    assert applied['revision'] == task['revision'] + 1 and applied['app_type'] == app_type
    assert applied['requirements'] == task['requirements'] and applied['requirements_confirmed']
    assert not applied['configuration_confirmed'] and not applied['artifact'] and not applied['dify_app_id'] and not applied['runs']
    assert not applied.get('workflow_plan') and not applied.get('agent_plan')
    final_store = Store(main.store.root)
    assert final_store.get('task', task['id']) == applied
    record = final_store.get('configuration_proposal', current['record']['id'])
    assert record['status'] == 'adopted' and record['applied_revision'] == applied['revision']
    assert record['acknowledgements']['changes']
    assert adopt(client, applied).status_code == 409
    assert multiple_catalog == [(1, 100), (2, 100)]  # Adoption performs no further directory reads.


@pytest.mark.parametrize('ids', [
    ['kb_product', 'kb_product'], ['kb_product', ' '], ['业务资料'], ['kb_product', 'fabricated'],
], ids=['duplicate', 'blank', 'name-not-id', 'invented'])
def test_at07_invalid_dataset_choices_do_not_save_or_apply(client, multiple_catalog, ids):
    task = approved(client, env_id=create_env(client)['id'])
    discover_multiple(client, task)
    before = copy.deepcopy(main.get_task(task['id']))
    checked = main.configuration_proposals.validate(task, dataset_candidate(ids))
    assert not checked['valid'] and '知识库 ID 必须唯一' in checked['errors'][0]
    assert not state(client, task)['record'] and main.get_task(task['id']) == before


@pytest.mark.parametrize('explicit_removal', [False, True], ids=['omitted-preserves', 'explicit-removal'])
def test_at07_existing_choices_preserved_unless_explicitly_removed(client, monkeypatch, multiple_catalog, explicit_removal):
    task = approved(client, env_id=create_env(client)['id'])
    task = client.patch(f"/api/tasks/{task['id']}", json={'configuration': {'dataset_ids': ['kb_product', 'kb_returns']}}).json()
    discover_multiple(client, task)
    value = dataset_candidate(['kb_product']) if explicit_removal else candidate(retrieval_top_k=5)
    if explicit_removal:
        value['reasons'][0].update(reason='明确移除 kb_returns，仅保留 kb_product。', experience='移除退货资料会缩小回答范围，退货问题需人工处理。')
    save(task, value)
    current = state(client, task)
    assert main.get_task(task['id'])['configuration']['dataset_ids'] == ['kb_product', 'kb_returns']
    assert any(d['field'] == 'dataset_ids' for d in current['diffs']) == explicit_removal
    response = adopt(client, task)
    assert response.status_code == 200, response.text
    assert response.json()['configuration']['dataset_ids'] == (['kb_product'] if explicit_removal else ['kb_product', 'kb_returns'])


@pytest.mark.parametrize('missing', ['reason', 'cost'])
def test_at07_dataset_reason_and_impacts_are_required(client, multiple_catalog, missing):
    task = approved(client, env_id=create_env(client)['id'])
    discover_multiple(client, task)
    value = dataset_candidate(['kb_returns', 'kb_product'])
    if missing == 'reason':
        value['reasons'] = []
    else:
        value['reasons'][0]['cost'] = ' '
    assert not main.configuration_proposals.validate(task, value)['valid']
    assert not state(client, task)['record'] and main.get_task(task['id']) == task


def test_at07_other_tasks_catalog_is_not_selection_authority(client, monkeypatch, multiple_catalog):
    first = approved(client, env_id=create_env(client)['id'])
    discover_multiple(client, first)
    second = prepared(client, monkeypatch)
    assert main.configuration_proposals.validate(first, dataset_candidate(['kb_returns']))['valid']
    checked = main.configuration_proposals.validate(second, dataset_candidate(['kb_returns']))
    assert not checked['valid'] and '知识库 ID 必须唯一' in checked['errors'][0]
    assert main.get_task(second['id']) == second and not state(client, second)['record']


@pytest.mark.parametrize('limitation', ['unobserved', 'empty'])
def test_at07_mixed_choices_require_unverified_acknowledgement(client, multiple_catalog, limitation):
    task = approved(client, env_id=create_env(client)['id'])
    if limitation == 'unobserved':
        task = client.patch(f"/api/tasks/{task['id']}", json={'configuration': {'dataset_ids': ['legacy_kb']}}).json()
    discover_multiple(client, task)
    snap = main.configuration_proposals.snapshot(task['id'])
    if limitation == 'empty':
        snap['datasets'][2]['available_document_count'] = 0
        main.store.put('configuration_resources', task['id'], snap)
    selected = ['kb_product', 'legacy_kb' if limitation == 'unobserved' else 'kb_returns']
    save(task, dataset_candidate(selected))
    warnings = state(client, task)['record']['resource_warnings']
    assert len(warnings) == 1 and selected[1] in warnings[0]
    assert ('未在本次目录中核对' if limitation == 'unobserved' else '不能当作已可检索') in warnings[0]
    assert adopt(client, task).status_code == 422
    assert main.get_task(task['id']) == task
    response = adopt(client, task, acknowledge_unverified_resources=True)
    assert response.status_code == 200, response.text
    assert response.json()['configuration']['dataset_ids'] == selected
    assert state(client, response.json())['record']['resource_warnings'] == warnings
    assert not response.json()['runs'] and not response.json()['configuration_confirmed']


def test_at07_unresolved_library_choice_waits_without_applying(client, multiple_catalog):
    task = approved(client, env_id=create_env(client)['id'])
    discover_multiple(client, task)
    value = dataset_candidate(['kb_product'])
    value['open_issues'] = [{'question': '是否同时采用退货库 kb_returns？',
        'recommendation': '建议核对退货范围后明确选择，当前先等待。',
        'experience': '未决定前无法确认退货回答范围。', 'cost': '真实检索费用待核对。', 'manual_work': '需用户确认具体库 ID。'}]
    save(task, value)
    assert not state(client, task)['can_adopt'] and adopt(client, task).status_code == 409
    assert main.get_task(task['id']) == task
