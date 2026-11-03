import copy,hashlib
import pytest,yaml
from test_api import client,approved,create
from test_node_policy import root as native_root
from app import main
from app.node_policy_audit import audit

def built(client,root=None):
 t=approved(client);response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text;t=response.json()
 if root is not None:
  path=main.artifact_path(t);path.write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8')
  t['artifact']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();main.store.put('task',t['id'],t)
 return t

def get(client,t):return client.get(f"/api/tasks/{t['id']}/node-policy-audit",params={'revision':t['revision']})

def test_complete_local_report_all_nodes_without_values_credentials_or_mutation(client,monkeypatch):
 root=native_root();root['workflow']['graph']['nodes'][1]['data'].update(title='private-title-sentinel',prompt_template=[{'role':'user','text':'private-prompt-sentinel'}],retry_config={'retry_enabled':True,'max_retries':2,'retry_interval':1000})
 root['workflow']['graph']['nodes'][2]['data']['default_value']=[{'key':'result','value':'private-fallback-sentinel'}]
 t=built(client,root);before=copy.deepcopy(main.get_task(t['id']));raw=main.artifact_path(t).read_text(encoding='utf-8')
 def forbidden(*args,**kwargs):pytest.fail('readonly audit must not mutate/decrypt/request')
 monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 response=get(client,t);assert response.status_code==200,response.text;r=response.json()
 assert r['task_id']==t['id'] and r['revision']==t['revision'] and r['total_nodes']==3 and len(r['nodes'])==3
 assert r['decision_nodes']==2 and r['issue_count']==2 and r['verification']=='local_execution_policy_only'
 assert r['source_sha256']==hashlib.sha256(raw.encode()).hexdigest() and response.headers['cache-control']=='no-store'
 assert all(r[k] is False for k in ('network_requested','credentials_decrypted','platform_checked','business_verified','run_authorized'))
 assert r['nodes'][1]['declared_retry']=='enabled' and r['nodes'][2]['source_path']=='/workflow/graph/nodes/2/data'
 assert all(s not in response.text for s in ('private-title-sentinel','private-prompt-sentinel','private-fallback-sentinel'))
 assert 'valid' not in r and 'can_start' not in r and main.get_task(t['id'])==before

def test_default_policy_report_is_not_runtime_permission(client):
 t=built(client);r=get(client,t).json();assert r['decision_nodes']==0 and r['issue_count']==0 and not r['run_authorized'] and not r['business_verified']

@pytest.mark.parametrize('policy,status',[({},'disabled'),({'retry_enabled':False},'disabled'),({'retry_enabled':'false'},'invalid')])
def test_retry_declaration_is_not_coerced_or_returned(policy,status):
 root=native_root();root['workflow']['graph']['nodes'][1]['data']['retry_config']=policy;r=audit(root)
 assert r['nodes'][1]['declared_retry']==status
 assert bool(r['nodes'][1]['issues'])==(status=='invalid')


def test_http_enabled_supported_and_document_unknown_parser_both_reported():
 from test_preservation_extensions import http_plan
 from test_workflow_plan import plan_task
 from app.workflow_plan import compile_workflow_plan
 p=http_plan();p['nodes'][1]['config']['retry_config']={'retry_enabled':True,'max_retries':2,'retry_interval':1000}
 root=yaml.safe_load(compile_workflow_plan(plan_task(p))[0]);r=audit(root);assert r['decision_nodes']==0 and r['nodes'][1]['declared_retry']=='enabled'
 from test_document_policy import root as docroot,data
 value=docroot();data(value)['unknown_parser']='private-parser-sentinel';r=audit(value);assert r['decision_nodes']==1 and 'private-parser-sentinel' not in str(r)


def test_file_entrance_report_does_not_require_upload_form_or_environment(client):
 from test_file_inputs import plan
 from test_workflow_plan import plan_task
 from app.workflow_plan import compile_workflow_plan
 t=built(client,yaml.safe_load(compile_workflow_plan(plan_task(plan('file-list')))[0]));response=get(client,t)
 assert response.status_code==200 and response.json()['total_nodes']==3 and response.json()['decision_nodes']==0


def test_revision_and_unbuilt_and_type_gates(client):
 t=create(client);assert get(client,t).status_code==404
 assert client.get(f"/api/tasks/{t['id']}/node-policy-audit",params={'revision':t['revision']+1}).status_code==409
 a=create(client,'agent');assert get(client,a).status_code==422

@pytest.mark.parametrize('raw',[b'private-yaml-sentinel: [',b'private-encoding-sentinel: \xff',b'a'*2_000_001],ids=['invalid-yaml','invalid-encoding','oversized'])
def test_invalid_or_oversized_source_returns_no_raw_or_partial_success(client,raw):
 t=built(client);path=main.artifact_path(t);path.write_bytes(raw)
 t['artifact']['sha256']=hashlib.sha256(raw).hexdigest();main.store.put('task',t['id'],t);response=get(client,t)
 assert response.status_code==422 and 'nodes' not in response.json() and 'private-' not in response.text


def test_source_change_during_read_rejects_old_report(client,monkeypatch):
 import app.node_policy_audit as module
 t=built(client);original=module.audit;path=main.artifact_path(t)
 def changed(root):
  result=original(root);path.write_text(path.read_text(encoding='utf-8')+'\n# changed',encoding='utf-8');return result
 monkeypatch.setattr(module,'audit',changed);response=get(client,t);assert response.status_code==409 and 'source_sha256' not in response.json()


def test_revision_change_during_read_does_not_overwrite_new_task(client,monkeypatch):
 import app.node_policy_audit as module
 t=built(client);original=module.audit
 def changed(root):
  result=original(root);new=main.get_task(t['id']);new['revision']+=1;main.store.put('task',t['id'],new);return result
 monkeypatch.setattr(module,'audit',changed);assert get(client,t).status_code==409 and main.get_task(t['id'])['revision']==t['revision']+1


def test_many_nodes_and_unknown_type_never_truncated_or_echoed():
 with pytest.raises(ValueError):audit({'workflow':{'graph':{'nodes':[{}]*1001}}})
 root=native_root();root['workflow']['graph']['nodes'][1]['data']['type']='private-type-sentinel';r=audit(root)
 assert r['nodes'][1]['node_kind']=='other' and 'private-type-sentinel' not in str(r)



def test_preservation_guard_also_reports_all_policy_locations_without_repair():
 from app.node_policy import require_native
 root=native_root();root['workflow']['graph']['nodes'][1]['data']['error_strategy']='default-value';root['workflow']['graph']['nodes'][2]['data']['error_strategy']='fail-branch';before=copy.deepcopy(root)
 with pytest.raises(ValueError) as error:require_native(root)
 assert '/workflow/graph/nodes/1/data' in str(error.value) and '/workflow/graph/nodes/2/data' in str(error.value) and root==before
