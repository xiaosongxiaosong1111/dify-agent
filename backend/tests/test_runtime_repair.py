import copy,hashlib
import pytest
from test_api import client
from test_dsl_roundtrip import prepared,APP
from app import main
from app.runtime_repair import missing_import
from app.run_diagnostics import binding,source_hash
from app.diagnostic_graph_source import artifact

CODE='def main(query: str) -> dict:\n    return {"result": re.sub(r"\\s+", " ", query)}\n'

def ready(client):
 task,_=prepared(client);task['workflow_plan']['nodes'][1]['config']['code']=CODE
 content,_=main.compile_current(task);path=main.artifact_path(task);path.write_text(content,encoding='utf-8');task['artifact']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();proof=artifact(main,task)
 env=main.store.get('environment',task['environment_id'])
 run={'id':'failed-re-run','kind':'run','revision':task['revision'],'status':'failed','environment_id':env['id'],'environment_binding':binding(env),'app_id':APP,'app_type':'workflow','error':"NameError: name 're' is not defined"}
 report={'id':'re-diagnostic','source_revision':task['revision'],'captured_at_revision':task['revision'],'remote_status':'failed','app_id':APP,'current_source':True,'trace_state':'read','source_hash':source_hash(run),'truncated':False,'source_graph':{'matched':True,'artifact':proof,'execution':proof,'published':proof},'nodes':[{'id':'execution','node_id':'code','node_type':'code','status':'failed','error':run['error']}]}
 run['diagnostics']=[report];task['runs'].append(run);main.save_task(task);return task

def preview(client,task):
 return client.post(f"/api/tasks/{task['id']}/runs/failed-re-run/repair-preview",json={'revision':task['revision'],'diagnostic_id':'re-diagnostic'})

def apply(client,task,record):
 return client.post(f"/api/tasks/{task['id']}/runtime-repairs/{record['id']}/apply",json={'revision':task['revision']})

def test_preview_apply_and_rebuild_keep_old_failure_and_require_new_confirmation(client):
 task=ready(client);before=copy.deepcopy(task);response=preview(client,task);assert response.status_code==200,response.text
 record=response.json();assert record['verification']=='static_only' and record['changes'][0]['module']=='re'
 assert main.get_task(task['id'])==before
 assert preview(client,task).json()['id']==record['id']
 assert client.get(f"/api/tasks/{task['id']}/runtime-repairs").json()['records'][0]==record
 response=apply(client,task,record);assert response.status_code==200,response.text;updated=response.json()['task']
 assert updated['revision']==task['revision']+1 and updated['requirements_confirmed'] and not updated['configuration_confirmed']
 assert updated['artifact'] is None and updated['dify_app_id'] is None and updated['runs']==before['runs']
 assert updated['workflow_plan']['nodes'][1]['config']['code']=='import re\n'+CODE
 assert updated['workflow_plan']['edges']==before['workflow_plan']['edges'] and updated['configuration']==before['configuration']
 assert apply(client,task,record).status_code==409
 assert client.post(f"/api/tasks/{task['id']}/build",json={'revision':updated['revision']}).status_code==422
 confirmed=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':updated['revision'],'kind':'configuration'});assert confirmed.status_code==200,confirmed.text
 built=client.post(f"/api/tasks/{task['id']}/build",json={'revision':updated['revision']});assert built.status_code==200,built.text
 assert built.json()['artifact']['verification']=='static_only' and built.json()['runs'][-1]['status']=='failed'

@pytest.mark.parametrize('mutation',['revision','environment','app','source','artifact','report','unknown','overlay','plan'])
def test_changed_evidence_or_unknown_operation_refuses_apply_without_task_changes(client,mutation):
 task=ready(client);record=preview(client,task).json();current=main.get_task(task['id'])
 if mutation=='revision':current['revision']+=1
 elif mutation=='environment':env=main.store.get('environment',task['environment_id']);env['base_url']='http://other';main.store.put('environment',env['id'],env)
 elif mutation=='app':current['dify_app_id']='another-app'
 elif mutation=='source':current['runs'][-1]['error']='changed'
 elif mutation=='artifact':main.artifact_path(current).write_text('invalid',encoding='utf-8')
 elif mutation=='report':current['runs'][-1]['diagnostics'][-1]['id']='new-report'
 elif mutation=='unknown':current['runs'].append({'id':'unknown-operation','status':'unknown'})
 elif mutation=='overlay':current['dsl_reference']={'id':'manual-reference'}
 else:current['workflow_plan']['nodes'][1]['config']['code']+='\n# hand edit'
 main.save_task(current);snapshot=copy.deepcopy(main.get_task(task['id']))
 assert apply(client,task,record).status_code==409 and main.get_task(task['id'])==snapshot

@pytest.mark.parametrize('code',[
 'def main(re):\n    return re.sub("x","y","")\n',
 'import re\ndef main(q):\n    return re.sub("x","y",q)\n',
 'def main(q):\n    re=q\n    return re.sub("x","y",q)\n',
 'def main(q):\n    return other(re)\n',
 'def main(q):\n    global re\n    return re.sub("x","y",q)\n',
 'def main(q):\n    return {"re": q}\n',
 'def main(q)\n    return re.sub("x","y",q)\n',
])
def test_ambiguous_or_already_bound_module_is_not_repaired(code):
 assert missing_import(code,"NameError: name 're' is not defined") is None

def test_import_insert_preserves_future_docstring_comments_and_crlf():
 code='"""original doc"""\r\nfrom __future__ import annotations\r\n# original\r\ndef main(q):\r\n    return math.sqrt(q)\r\n'
 patch=missing_import(code,"NameError: name 'math' is not defined")
 assert patch and patch['inserted_line']==3 and patch['code'].replace('import math\r\n','',1)==code

def test_other_error_or_multiple_failure_is_not_partially_repaired(client):
 task=ready(client);run=task['runs'][-1];run['diagnostics'][-1]['nodes'].append({'node_id':'other','node_type':'http-request','status':'failed','error':'timeout'});main.save_task(task)
 response=preview(client,task);assert response.status_code==422 and not main.store.list('runtime_repair')
 assert missing_import(CODE,"NameError: name 'os' is not defined") is None

def test_proposal_cannot_be_used_by_other_task_or_tampered(client):
 task=ready(client);record=preview(client,task).json();other,_=prepared(client)
 assert apply(client,other,record).status_code==404
 saved=main.store.get('runtime_repair',record['id']);saved['candidate']['nodes'][1]['config']['code']='def main(q):\n return {}';main.store.put('runtime_repair',record['id'],saved)
 assert apply(client,task,record).status_code==409

def test_repeated_failure_in_same_node_produces_one_patch(client):
 task=ready(client);task['runs'][-1]['diagnostics'][-1]['nodes']*=2;main.save_task(task)
 response=preview(client,task);assert response.status_code==200,response.text
 assert len(response.json()['changes'])==1

@pytest.mark.parametrize('field,value',[('remote_status','succeeded'),('trace_state','local_only'),('truncated',True),('current_source',False),('captured_at_revision',0)])
def test_untrusted_diagnostic_is_not_a_repair_source(client,field,value):
 task=ready(client);task['runs'][-1]['diagnostics'][-1][field]=value;main.save_task(task)
 assert preview(client,task).status_code==409 and not main.store.list('runtime_repair')

def test_multiple_error_names_and_different_failures_in_same_node_are_not_guessed(client):
 assert missing_import(CODE,"NameError: name 're' is not defined; NameError: name 'q' is not defined") is None
 task=ready(client);run=task['runs'][-1];extra=copy.deepcopy(run['diagnostics'][-1]['nodes'][0]);extra['error']="NameError: name 'other' is not defined";run['diagnostics'][-1]['nodes'].append(extra);main.save_task(task)
 assert preview(client,task).status_code==422 and not main.store.list('runtime_repair')

def test_restart_retains_candidate_and_rejects_secret_plan_without_echo(client):
 from app.storage import Store
 task=ready(client);record=preview(client,task).json();main.store=Store(main.store.root)
 assert client.get(f"/api/tasks/{task['id']}/runtime-repairs").json()['records'][0]['id']==record['id']
 task['workflow_plan']['nodes'][1]['config']['code']+='\n# sk-123456789abcdef123456789\n';main.save_task(task)
 # Source changed: refuse before generating a new candidate and never echo it.
 response=preview(client,task);assert response.status_code==409 and 'sk-' not in response.text
