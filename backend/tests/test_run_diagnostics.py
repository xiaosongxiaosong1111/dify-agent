import copy
import pytest
from test_api import client
from test_dsl_roundtrip import prepared,APP
from app import main
from app.dify import DifyClient,DifyError
from app.run_diagnostics import binding,safe_text,classify,selected_result,remote_id

REMOTE='5b66dc55-cce6-4457-bd4b-8f48ecdfc1bd'
OTHER='895a778d-e2b2-4c41-9e26-5b08747dd59b'

def recorded(client,status='failed'):
 task,_=prepared(client);env=main.store.get('environment',task['environment_id'])
 run={'id':'failed-run','kind':'run','revision':task['revision'],'environment_id':env['id'],'environment_binding':binding(env),'app_type':'workflow','app_id':APP,'status':status,'error':'实际工作流未成功执行','result':{'workflow_run_id':REMOTE,'data':{'id':REMOTE,'status':'failed','error':'SyntaxError: invalid syntax, line 2'}}}
 task['runs'].append(run);main.save_task(task);return task,run

def diagnose(client,task,remote=False,**payload):
 return client.post(f"/api/tasks/{task['id']}/runs/failed-run/diagnose",json={'revision':task['revision'],'read_remote':remote,**payload})


def test_reimport_same_revision_different_application_is_historical_diagnostic(client):
 task,run=recorded(client);task['dify_app_id']=OTHER;main.save_task(task)
 response=diagnose(client,task);assert response.status_code==200
 report=response.json();assert not report['current_source'] and report['app_id']==APP and report['source_revision']==task['revision']

def trace(error='SyntaxError: invalid syntax'):
 return {'data':[{'id':'execution','node_id':'code','node_type':'code','title':'代码','status':'failed','error':error,'inputs':{'password':'private input'},'outputs':{'token':'private output'},'process_data':{'secret':'private process'}}]}

def mock_reader(monkeypatch,detail=None,nodes=None):
 calls=[]
 async def request(self,method,path,**kwargs):
  calls.append((method,path,kwargs));assert method=='GET' and kwargs['credential']=='console_token'
  return (trace() if nodes is None else nodes) if path.endswith('/node-executions') else ({'id':REMOTE,'status':'failed','error':'error'} if detail is None else detail)
 monkeypatch.setattr(DifyClient,'request',request);return calls

def test_local_analysis_preserves_original_status_and_does_not_call_dify(client,monkeypatch):
 task,run=recorded(client);before=copy.deepcopy(run);calls=mock_reader(monkeypatch)
 response=diagnose(client,task);assert response.status_code==200,response.text
 report=response.json();assert report['findings'][0]['category']=='code_syntax' and report['trace_state']=='local_only' and not calls
 current=main.get_task(task['id']);saved=current['runs'][-1];assert current['revision']==task['revision'] and current['configuration_confirmed']
 assert {k:v for k,v in saved.items() if k!='diagnostics'}==before
 assert '运行诊断（只读证据，不改变验收）' in client.get(f"/api/tasks/{task['id']}/report").text

def test_remote_read_is_bound_to_snapshot_and_sanitized(client,monkeypatch):
 task,run=recorded(client);secret='secret-admin-123456';main.store.set_secret(task['environment_id'],'console_token',secret)
 calls=mock_reader(monkeypatch,nodes=trace('SyntaxError: token='+secret+' sk-123456789abcdef password="private two words"'))
 report=diagnose(client,task,True).json();assert report['trace_state']=='read' and report['node_count']==1
 assert len(calls)==2 and all(APP in path and REMOTE in path for _,path,_ in calls)
 stored=str(main.get_task(task['id'])['runs'][-1]['diagnostics']);assert secret not in stored and 'private two words' not in stored and 'private input' not in stored and 'private output' not in stored and 'private process' not in stored
 assert report['findings'][0]['node_id']=='code'

@pytest.mark.parametrize('field,value',[('app_type','agent'),('app_type',None),('app_id','../../other'),('environment_binding',None),('environment_binding','different')])
def test_legacy_or_untrusted_binding_does_not_request_wrong_app(client,monkeypatch,field,value):
 task,run=recorded(client);run[field]=value;main.save_task(task);calls=mock_reader(monkeypatch)
 report=diagnose(client,task,True).json();assert report['trace_state']=='unavailable' and report['trace_error'] and not calls

@pytest.mark.parametrize('data',[{'data':'bad'},{'data':[None]},{'data':[{'id':'one','error':{}}]},{'data':[{'id':'same'},{'id':'same'}]},{'data':[{'id':str(i)} for i in range(2001)]}])
def test_malformed_trace_is_not_fake_empty_success(client,monkeypatch,data):
 task,_=recorded(client);mock_reader(monkeypatch,nodes=data);report=diagnose(client,task,True).json()
 assert report['trace_state']=='read_failed' and report['trace_error'] and report['findings'][0]['category']=='code_syntax'

def test_mismatched_remote_identity_stops_before_node_read(client,monkeypatch):
 task,_=recorded(client);calls=mock_reader(monkeypatch,detail={'id':OTHER,'status':'failed'})
 report=diagnose(client,task,True).json();assert report['trace_state']=='read_failed' and len(calls)==1

def test_empty_and_truncated_trace_have_explicit_limits(client,monkeypatch):
 task,_=recorded(client);mock_reader(monkeypatch,nodes={'data':[]});report=diagnose(client,task,True).json()
 assert report['trace_state']=='read' and any('列表为空' in text for text in report['notes'])
 mock_reader(monkeypatch,nodes={'data':[{'id':str(i),'node_id':'code','node_type':'code','status':'failed' if i==599 else 'succeeded','error':'SyntaxError' if i==599 else None} for i in range(600)]})
 report=diagnose(client,task,True).json();assert report['truncated'] and report['node_count']==600 and len(report['nodes'])<=500 and report['findings'][0]['execution_id']=='599'

def test_read_failure_keeps_local_evidence_and_unknown_guard(client,monkeypatch):
 task,run=recorded(client,'unknown')
 env=main.store.get('environment',task['environment_id']);env['service_app_id']=APP;main.store.put('environment',env['id'],env);main.store.set_secret(env['id'],'service_api_key','service-test-key')
 async def request(*args,**kwargs):raise DifyError('Dify 返回 HTTP 401')
 monkeypatch.setattr(DifyClient,'request',request)
 report=diagnose(client,task,True).json();assert report['trace_state']=='read_failed' and any('重跑保护保持' in n for n in report['notes'])
 assert main.get_task(task['id'])['runs'][-1]['status']=='unknown'
 assert client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'x'}}).status_code==409

def test_evaluation_failure_and_selected_conversation_turn(client):
 task,run=recorded(client,'success');run['evaluation']={'status':'failed','mode':'equals'}
 run['result']={'conversation_case':True,'turns':[{'index':1,'result':{'answer':'a'},'evaluation':{'status':'passed'}},{'index':2,'result':{'answer':'b'},'evaluation':{'status':'failed'}}]};main.save_task(task)
 report=diagnose(client,task).json();assert report['selected_turn']==2 and report['findings'][0]['category']=='expectation_mismatch'
 run['result']['pending_turn']={'index':3,'result':{'workflow_run_id':REMOTE}};assert selected_result(run)[1]==3

@pytest.mark.parametrize('mutation',['result','environment','revision'])
def test_source_changed_while_reading_is_not_applied(client,monkeypatch,mutation):
 task,_=recorded(client)
 async def request(self,method,path,**kwargs):
  current=main.get_task(task['id'])
  if mutation=='result':current['runs'][-1]['result']={};main.save_task(current)
  elif mutation=='revision':current['revision']+=1;main.save_task(current)
  else:env=main.store.get('environment',task['environment_id']);env['base_url']='http://localhost:9999';main.store.put('environment',env['id'],env)
  return trace() if path.endswith('/node-executions') else {'id':REMOTE,'status':'failed'}
 monkeypatch.setattr(DifyClient,'request',request);assert diagnose(client,task,True).status_code==409
 assert not main.get_task(task['id'])['runs'][-1].get('diagnostics')

@pytest.mark.parametrize('error,category',[('JSONDecodeError','json_parse'),('Sandbox connection failed','sandbox'),('Rate limit exceeded','quota'),('invalid API key','credential'),('Output variable result missing','output_schema'),('Variable result not found','variable'),('timed out','timeout'),('unexplained failure','unclassified')])
def test_deterministic_hints_do_not_claim_certain_root_cause(error,category):
 finding=classify(error);assert finding['category']==category and finding['confidence'] in {'需核对','未知'}

def test_invalid_request_and_foreign_record_are_rejected(client):
 task,_=recorded(client)
 assert diagnose(client,task,read_remote='true').status_code==422
 assert diagnose(client,task,revision=True).status_code==422
 assert client.post(f"/api/tasks/{task['id']}/runs/not-owned/diagnose",json={'revision':task['revision']}).status_code==404
 assert remote_id({'workflow_run_id':REMOTE,'data':{'id':OTHER}},'workflow') is None
 assert remote_id({'workflow_run_id':'../../other'},'workflow') is None
 assert 'two words' not in safe_text('password="two words"')

def test_new_actual_run_captures_app_environment_and_http_failure(client,monkeypatch):
 task,_=prepared(client);env=main.store.get('environment',task['environment_id']);env['service_app_id']=APP;main.store.put('environment',env['id'],env);main.store.set_secret(env['id'],'service_api_key','service-test-key')
 async def failed(*args,**kwargs):raise DifyError('Dify HTTP 401',http_status=401)
 monkeypatch.setattr(DifyClient,'run_workflow',failed)
 response=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'x'}});assert response.status_code==502
 saved=main.get_task(task['id'])['runs'][-1];assert saved['app_id']==APP and saved['app_type']=='workflow' and saved['environment_binding']==binding(env) and saved['http_status']==401
 response=client.post(f"/api/tasks/{task['id']}/runs/{saved['id']}/diagnose",json={'revision':task['revision']});assert response.json()['findings'][0]['category']=='dify_access'

@pytest.mark.parametrize('error,category',[
 ('API key is required for authorization but was empty. Please provide a valid API key.','http_auth_missing'),
 ('Failed to parse JSON: {broken}','http_body_json'),
])
def test_http_native_errors_are_specific_only_with_http_evidence(error,category):
 finding=classify(error,'http-request')
 assert finding['category']==category and finding['confidence']=='需核对'
 assert '不会自动重跑' in finding['recommendation']
 for kind in (None,'llm','code'):
  assert classify(error,kind)['category']!=category

@pytest.mark.parametrize('error,category',[
 ('AuthorizationConfigError: API key is required for authorization but was empty.','http_auth_missing'),
 ('RequestBodyError: Failed to parse JSON: {broken}','http_body_json'),
])
def test_http_exception_marker_allows_local_hint_without_node_snapshot(error,category):
 assert classify(error)['category']==category

def test_http_failure_diagnostic_is_persisted_without_fixing_or_rerunning(client,monkeypatch):
 task,run=recorded(client);before=copy.deepcopy(run)
 nodes=trace('API key is required for authorization but was empty. Please provide a valid API key.')
 nodes['data'][0].update(node_id='http_1',node_type='http-request',title='提交接口')
 calls=mock_reader(monkeypatch,nodes=nodes)
 response=diagnose(client,task,True);assert response.status_code==200,response.text
 finding=response.json()['findings'][0]
 assert finding['category']=='http_auth_missing' and finding['node_id']=='http_1'
 assert 'Sierra 的大模型 Key' in finding['recommendation']
 saved=main.get_task(task['id']);assert saved['revision']==task['revision']
 assert {k:v for k,v in saved['runs'][-1].items() if k!='diagnostics'}==before
 assert len(calls)==2 and all(method=='GET' for method,_,_ in calls)

def test_http_body_hint_keeps_existing_redaction(client,monkeypatch):
 task,_=recorded(client)
 nodes=trace('RequestBodyError: Failed to parse JSON: {"token":"sk-123456789abcdef"}')
 nodes['data'][0]['node_type']='http-request'
 mock_reader(monkeypatch,nodes=nodes)
 report=diagnose(client,task,True).json()
 assert report['findings'][0]['category']=='http_body_json'
 assert 'sk-123456789abcdef' not in str(report)
 assert 'private input' not in str(report)

def test_exception_class_name_alone_is_not_enough_to_guess_http_cause():
 assert classify('AuthorizationConfigError: invalid authorization type','http-request')['category']=='unclassified'
 assert classify('RequestBodyError: unsupported file type','http-request')['category']=='unclassified'
