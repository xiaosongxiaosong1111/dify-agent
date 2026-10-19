import copy,hashlib,json
import pytest,yaml
from test_api import client,create
from test_node_policy_audit import built
from test_optional_file import optional_plan
from test_workflow_plan import plan_task
from app import main
from app.workflow_plan import compile_workflow_plan
from app.optional_case_templates import templates

def root(op='exists'):
 text,checked=compile_workflow_plan(plan_task(optional_plan(op)));assert checked['valid'];return yaml.safe_load(text)

def get(client,t,**params):return client.get(f"/api/tasks/{t['id']}/optional-file-case-templates",params={'revision':t['revision'],**params})

@pytest.mark.parametrize('op',['exists','not exists'])
def test_templates_are_local_bound_final_source_and_no_file_or_rule_is_invented(client,monkeypatch,op):
 t=built(client,root(op));before=copy.deepcopy(main.get_task(t['id']));raw=main.artifact_path(t).read_bytes()
 def forbidden(*args,**kwargs):pytest.fail('读取样例建议不能解密、保存或联网')
 monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 r=get(client,t);assert r.status_code==200,r.text;v=r.json();assert r.headers['cache-control']=='no-store'
 assert v['artifact_sha256']==hashlib.sha256(raw).hexdigest() and v['comparison_operator']==op
 assert [x['scenario'] for x in v['rows']]==['missing_omitted','missing_null','file_present']
 assert v['rows'][0]['input']=={} and v['rows'][1]['input']=={'document':None}
 assert all(x['expectation']=={'mode':'equals','target':'result','expected':'本次没有提供文件'} for x in v['rows'][:2])
 assert v['rows'][2]['input'] is None and v['rows'][2]['expectation'] is None and not v['rows'][2]['input_ready']
 assert all(v[k] is False for k in ('network_requested','credentials_decrypted','task_changed','catalog_changed','file_uploaded','business_verified')) and v['workflow_runs']==0
 assert main.get_task(t['id'])==before and main.store.list('runtime_file_cases')==[]

def test_exact_user_default_unicode_and_whitespace_are_not_rewritten():
 r=root();start=r['workflow']['graph']['nodes'][0];start['data']['variables'][1]['default']='  请补充资料🙂\n不是自动通过。  '
 before=copy.deepcopy(r);v=templates(r);assert v['missing_message_default']==start['data']['variables'][1]['default'] and v['rows'][0]['expectation']['expected']==v['missing_message_default'] and r==before

@pytest.mark.parametrize('mutation',['pdf','mixed_pdf','no_guard','extra_node','bad_default','unknown_case','empty_extensions'])
def test_unsupported_complete_graph_cannot_be_silently_reduced(mutation):
 r=root();nodes=r['workflow']['graph']['nodes'];field=nodes[0]['data']['variables'][0]
 if mutation=='pdf':field['allowed_file_extensions']=['.pdf']
 elif mutation=='mixed_pdf':field['allowed_file_extensions']=['.txt','.pdf']
 elif mutation=='empty_extensions':field['allowed_file_extensions']=[]
 elif mutation=='no_guard':r['workflow']['graph']['edges'][0]['target']='extract'
 elif mutation=='extra_node':nodes.append({'id':'another','data':{'type':'llm'}})
 elif mutation=='bad_default':nodes[0]['data']['variables'][1]['default']=''
 elif mutation=='unknown_case':next(n for n in nodes if n['id']=='guard')['data']['cases'][0]['unknown_execution']='private-sentinel'
 with pytest.raises(ValueError):templates(r)

def test_no_artifact_or_wrong_revision_never_uses_draft(client):
 t=create(client);assert get(client,t).status_code==404
 t=built(client,root());assert get(client,t,revision=t['revision']+1).status_code==409

def test_chatflow_not_changed_into_workflow(client):
 t=built(client,root());saved=main.get_task(t['id']);saved['app_type']='advanced-chat';main.save_task(saved)
 assert get(client,t).status_code==422

def test_final_bytes_change_during_read_is_rejected(client,monkeypatch):
 from app import optional_case_templates as module
 t=built(client,root());original=module.read_bytes;calls=[]
 def change(path):
  value=original(path);calls.append(1)
  return value if len(calls)==1 else value+b'\n'
 monkeypatch.setattr(module,'read_bytes',change);assert get(client,t).status_code==409

def test_malformed_source_returns_safe_complete_failure_not_partial_suggestions(client):
 t=built(client,root());main.artifact_path(t).write_text('private-sentinel: [broken',encoding='utf-8')
 r=get(client,t);assert r.status_code==422 and 'private-sentinel' not in r.text
