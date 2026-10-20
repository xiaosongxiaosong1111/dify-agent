import copy
import httpx
import pytest
from test_api import client
from test_runtime_repair import ready,preview,apply
from app import main
from app.runtime_repair import checksum
from app.run_diagnostics import binding,source_hash
from app.diagnostic_graph_source import artifact

CASE={'id':'original-case','name':'原失败问题','input':{'query':'two   words'},'expectation':{'mode':'equals','target':'result','expected':'two words'},'required':True}

@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
 def forbidden(*args,**kwargs):
  pytest.fail('AT-13 隔离检查不得访问真实 HTTP 或调用真实模型')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)


def applied(client,formal=True,extra_cases=(),mock=False):
 task=ready(client);task['runs'][-1]['input']=copy.deepcopy(CASE['input'])
 if formal:
  task['test_cases']=[copy.deepcopy(CASE)];task['runs'][-1]['test_case']=copy.deepcopy(CASE)
 task['test_cases'].extend(copy.deepcopy(extra_cases))
 if mock:task['configuration']['mock_dependencies']='测试用模拟接口，真实接入及重新验收待办'
 task['runs'][-1]['diagnostics'][-1]['source_hash']=source_hash(task['runs'][-1]);main.save_task(task)
 record=preview(client,task).json();response=apply(client,task,record);assert response.status_code==200,response.text
 return response.json()['task'],response.json()['repair']

def summary(client,task,record):
 response=client.get(f"/api/tasks/{task['id']}/runtime-repairs/{record['id']}/verification");assert response.status_code==200,response.text
 return response.json()

def build_import(client,task):
 task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':'configuration'}).json()
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200,response.text
 task=response.json();task['dify_app_id']='repaired-application';main.save_task(task);return task

def new_run(task,formal=True,status='success'):
 env=main.store.get('environment',task['environment_id'])
 run={'id':'new-run','kind':'run','revision':task['revision'],'app_type':task['app_type'],'app_id':task['dify_app_id'],'environment_id':task['environment_id'],'environment_binding':binding(env),'status':status,'input':copy.deepcopy(CASE['input']),'result':{'data':{'status':'succeeded' if status=='success' else 'failed','outputs':{'result':'two words'}}}}
 if formal:run['test_case']=copy.deepcopy(CASE)
 task['runs'].append(run);main.save_task(task);return run

def proof(task,run):
 graph=artifact(main,task)
 run['diagnostics']=[{'id':'new-proof','source_revision':task['revision'],'captured_at_revision':task['revision'],'app_id':task['dify_app_id'],'current_source':True,'source_hash':source_hash(run),'trace_state':'read','remote_status':'succeeded','truncated':False,'source_graph':{'matched':True,'artifact':graph,'execution':graph,'published':graph},'nodes':[{'node_id':'code','status':'succeeded','error':''}]}];main.save_task(task)

def test_followup_tracks_confirm_build_import_replay_trace_and_verified(client):
 task,record=applied(client);assert summary(client,task,record)['state']=='needs_configuration'
 response=client.post(f"/api/tasks/{task['id']}/runtime-repairs/{record['id']}/prepare-input",json={'revision':task['revision']});assert response.status_code==200,response.text
 assert response.json()['input']==CASE['input'] and response.json()['case_id']==CASE['id']
 assert main.get_task(task['id'])==task
 task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':'configuration'}).json();assert summary(client,task,record)['state']=='needs_build'
 task=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']}).json();assert summary(client,task,record)['state']=='needs_import'
 task['dify_app_id']='repaired-application';main.save_task(task);assert summary(client,task,record)['state']=='not_run'
 run=new_run(task);assert summary(client,task,record)['state']=='needs_trace'
 proof(task,run);result=summary(client,task,record);assert result['state']=='verified' and result['error_cleared'] and result['cases'][0]['status']=='passed'
 assert task['runs'][-2]['status']=='failed'

@pytest.mark.parametrize('mutation',['plan','configuration','requirements','cases','environment','revision','original'])
def test_changed_contract_or_original_is_historical_not_reusable(client,mutation):
 task,record=applied(client)
 if mutation=='plan':task['workflow_plan']['nodes'][1]['config']['code']+='\n# changed'
 elif mutation=='configuration':task['configuration']['temperature']=0.1
 elif mutation=='requirements':task['requirements']['goal']='different goal'
 elif mutation=='cases':task['test_cases'][0]['expectation']['expected']='different'
 elif mutation=='environment':env=main.store.get('environment',task['environment_id']);env['base_url']='http://changed';main.store.put('environment',env['id'],env)
 elif mutation=='revision':task['revision']+=1
 else:task['runs'][-1]['error']='changed original'
 main.save_task(task);before=copy.deepcopy(task)
 assert summary(client,task,record)['state']=='stale'
 assert client.post(f"/api/tasks/{task['id']}/runtime-repairs/{record['id']}/prepare-input",json={'revision':task['revision']}).status_code==409
 assert main.get_task(task['id'])==before

@pytest.mark.parametrize('status,state',[('pending','unknown'),('unknown','unknown'),('failed','failed')])
def test_failed_or_uncertain_rerun_does_not_pass(client,status,state):
 task,record=applied(client);task=build_import(client,task);new_run(task,status=status)
 result=summary(client,task,record);assert result['state']==state and not result['error_cleared']

@pytest.mark.parametrize('mutation',['old_revision','old_app','old_env','different_input','different_expectation','bool_input'])
def test_other_runs_and_changed_case_cannot_replace_original_failure(client,mutation):
 task,record=applied(client);task=build_import(client,task);run=new_run(task)
 if mutation=='old_revision':run['revision']-=1
 elif mutation=='old_app':run['app_id']='old-app'
 elif mutation=='old_env':run['environment_binding']='old-env'
 elif mutation=='different_input':run['input']={'query':'different'}
 elif mutation=='bool_input':run['input']={'query':True}
 else:run['test_case']['expectation']['expected']='different'
 main.save_task(task);assert summary(client,task,record)['state'] in {'not_run','needs_trace'}
 assert not summary(client,task,record)['error_cleared']

@pytest.mark.parametrize('mutation',['no_node','node_failed','truncated','old_hash','wrong_graph','old_app','not_remote_success','different_turn'])
def test_successful_response_without_matching_node_proof_is_not_error_cleared(client,mutation):
 task,record=applied(client);task=build_import(client,task);run=new_run(task);proof(task,run);report=run['diagnostics'][-1]
 if mutation=='no_node':report['nodes']=[]
 elif mutation=='node_failed':report['nodes'][0].update(status='failed',error="NameError: name 're' is not defined")
 elif mutation=='truncated':report['truncated']=True
 elif mutation=='old_hash':report['source_hash']='changed'
 elif mutation=='wrong_graph':report['source_graph']['published']=None
 elif mutation=='old_app':report['app_id']='old-app'
 elif mutation=='different_turn':report['selected_turn']=2
 else:report['remote_status']='failed'
 main.save_task(task);result=summary(client,task,record);assert result['state']=='needs_trace' and not result['error_cleared']

def test_output_rules_are_recomputed_not_taken_from_saved_pass_label(client):
 task,record=applied(client);task=build_import(client,task);run=new_run(task);run['result']['data']['outputs']={'result':'wrong'};run['evaluation']={'status':'passed'};proof(task,run)
 assert summary(client,task,record)['state']=='failed'

def test_all_cases_need_new_evidence_and_no_cases_is_not_full_verification(client):
 task,record=applied(client);task['test_cases'].append(dict(copy.deepcopy(CASE),id='another-case',name='另一分支'))
 from app.repair_verification import contract
 record['verification_contract']=contract(task,main.store.get('environment',task['environment_id']));main.store.put('runtime_repair',record['id'],record);main.save_task(task)
 task=build_import(client,task);run=new_run(task);proof(task,run);result=summary(client,task,record)
 assert result['state']=='needs_cases' and result['cases'][1]['status']=='not_run'
 task,record=applied(client,formal=False);task=build_import(client,task);run=new_run(task,formal=False);proof(task,run)
 assert summary(client,task,record)['state']=='needs_cases'

def test_conversation_source_is_not_silently_replayed_as_new_context(client):
 task,record=applied(client,formal=False);task['runs'][-1]['conversation_context']={'source_run_id':'old-context'}
 record['source_run_hash']=source_hash(task['runs'][-1]);main.store.put('runtime_repair',record['id'],record);main.save_task(task)
 response=client.post(f"/api/tasks/{task['id']}/runtime-repairs/{record['id']}/prepare-input",json={'revision':task['revision']})
 assert response.status_code==422 and not summary(client,task,record)['can_prepare']


@pytest.mark.parametrize('outcome,case_status,state',[
 ('not_run','not_run','needs_cases'),
 ('failed','failed','needs_cases'),
 ('wrong_output','failed','needs_cases'),
 ('manual','needs_review','needs_cases'),
 ('pending','running','unknown'),
 ('unknown','unknown','unknown'),
])
def test_repaired_original_does_not_hide_other_required_case(client,outcome,case_status,state):
 critical=dict(copy.deepcopy(CASE),id='critical-branch',name='关键业务分支',input={'query':'branch'})
 if outcome=='manual':critical['expectation']={'mode':'manual','description':'人工核对关键分支'}
 task,record=applied(client,extra_cases=[critical]);task=build_import(client,task)
 original=new_run(task);proof(task,original)
 if outcome!='not_run':
  branch=new_run(task,status=outcome if outcome in {'failed','pending','unknown'} else 'success')
  branch.update(id='critical-run',input=copy.deepcopy(critical['input']),test_case=copy.deepcopy(critical))
  branch['result']['data']['outputs']={'result':'wrong'}
  # A stale saved pass label must never override actual output/manual review.
  branch['evaluation']={'status':'passed'};main.save_task(task)
 before=copy.deepcopy(main.get_task(task['id']));repair_before=copy.deepcopy(main.store.get('runtime_repair',record['id']))
 result=summary(client,task,record)
 assert result['state']==state and result['error_cleared']
 assert result['reproduction']=={'status':'passed','run_id':original['id']}
 assert [(c['required'],c['status']) for c in result['cases']]==[(True,'passed'),(True,case_status)]
 assert result['verification']=='repair_followup_only' and '完整业务验收' in result['note']
 from app.storage import Store
 main.store=Store(main.store.root)
 assert summary(client,task,record)==result
 assert main.get_task(task['id'])==before
 assert main.store.get('runtime_repair',record['id'])==repair_before


@pytest.mark.parametrize('mock',[False,True])
def test_all_saved_checks_pass_only_gives_bounded_or_mock_result(client,mock):
 task,record=applied(client,mock=mock);task=build_import(client,task)
 run=new_run(task);proof(task,run);before=copy.deepcopy(main.get_task(task['id']))
 result=summary(client,task,record)
 assert result['state']==('mock_only' if mock else 'verified')
 assert result['error_cleared'] and result['cases'][0]['status']=='passed'
 assert ('阶段性成果' if mock else '仍需完整业务验收') in result['message']
 assert result['verification']=='repair_followup_only' and '模拟依赖' in result['note']
 assert main.get_task(task['id'])==before and before['runs'][-2]['status']=='failed'


@pytest.mark.parametrize('failure',['failed','wrong_output'])
def test_latest_failure_overrides_earlier_verified_repair(client,failure):
 task,record=applied(client);task=build_import(client,task)
 passed=new_run(task);passed['id']='earlier-passed';proof(task,passed)
 assert summary(client,task,record)['state']=='verified'
 latest=new_run(task,status='failed' if failure=='failed' else 'success')
 if failure=='wrong_output':latest['result']['data']['outputs']={'result':'wrong'}
 latest['evaluation']={'status':'passed'};proof(task,latest)
 result=summary(client,task,record)
 assert result['state']=='failed' and not result['error_cleared']
 assert result['reproduction']=={'status':'failed','run_id':latest['id']}
 assert result['cases'][0]['status']=='failed' and '不计修复成功' in result['message']
 assert main.get_task(task['id'])['runs'][-2]['status']=='success'


def test_import_receipt_with_failed_key_case_is_not_business_completion(client):
 task=ready(client);task['test_cases']=[copy.deepcopy(CASE)]
 task['runs'][-1].update(input=copy.deepcopy(CASE['input']),test_case=copy.deepcopy(CASE))
 main.save_task(task);before=copy.deepcopy(main.get_task(task['id']))
 response=client.get(f"/api/tasks/{task['id']}/acceptance");assert response.status_code==200,response.text
 result=response.json()
 assert not result['all_required_passed'] and result['required']['failed']==1
 assert result['cases'][0]['status']=='failed' and result['verification']=='declared_checks_only'
 response=client.get(f"/api/tasks/{task['id']}/report");assert response.status_code==200,response.text
 assert '已声明必选样例 0 / 1 通过' in response.text
 assert '完整业务覆盖仍需确认' in response.text and '本版本不自动判定全量业务完成' in response.text
 assert main.get_task(task['id'])==before
