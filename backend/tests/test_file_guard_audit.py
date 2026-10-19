import copy,uuid,yaml
import pytest
from test_api import client
from test_file_schema_guard import ready,execute,GUARD
from test_file_structured_run import result
from test_file_model_run import inputs
from test_file_run import plan,remote,PUBLISHED,RUN
from test_optional_branch_audit import reader,diagnose
from app import main
from app.file_run import KIND

def recorded(client,monkeypatch,mode='succeeded'):
 t,env,p,root=ready(client,monkeypatch);q=plan(client,t,p,inputs(p)).json();receipt=result({'customer':'甲','approved':False})
 if mode!='succeeded':receipt['data']['status']='failed'
 setup,_=remote(monkeypatch,t,env,result=receipt);response=execute(client,t,q)
 assert response.status_code==(200 if mode=='succeeded' else 502),response.text
 t=main.get_task(t['id']);run=t['runs'][-1];p=main.store.get(KIND,q['id']);graph=root['workflow']['graph'];chain=[n['id'] for n in graph['nodes']];ids=chain[:4] if mode=='guard_failed' else chain
 types={n['id']:n['data']['type'] for n in graph['nodes']}
 trace={'data':[{'id':str(uuid.uuid4()),'workflow_run_id':RUN,'node_id':nid,'node_type':types[nid],'status':'failed' if nid==(GUARD if mode=='guard_failed' else 'end' if mode=='end_failed' else None) else 'succeeded','error':None,'inputs':{'api_key':'private-input'},'outputs':{'data':'private-output'}} for nid in ids]}
 detail={'id':RUN,'status':'succeeded' if mode=='succeeded' else 'failed','total_steps':len(ids),'graph':graph,'inputs':{'password':'not-retained'},'outputs':{'value':'not-retained'}}
 return t,run,p,detail,trace,{'id':PUBLISHED,**root['workflow']},setup

@pytest.mark.parametrize('mode,state',[('succeeded','observed_succeeded'),('guard_failed','observed_failed'),('end_failed','observed_succeeded')])
def test_original_guard_status_is_observed_from_existing_reads_without_promoting_run_or_acceptance(client,monkeypatch,mode,state):
 t,run,p,detail,trace,published,setup=recorded(client,monkeypatch,mode);before=copy.deepcopy(run);original=copy.deepcopy(p);trace['data'].reverse();calls=reader(monkeypatch,detail,trace,published)
 r=diagnose(client,t,run);assert r.status_code==200,r.text;a=r.json()['file_guard_audit'];assert a['state']==state and a['guard_status_observed'] and a['execution_graph_matches_original']
 assert a['plan_id']==p['id'] and a['guard_node_id']==GUARD and a['plan_revision']==run['revision'] and all(a[k] is False for k in ('business_verified','run_state_changed','plan_changed'))
 assert len(calls)==3 and len(setup)==3 and 'private-' not in r.text and 'not-retained' not in r.text
 assert main.store.get(KIND,p['id'])==original and {k:v for k,v in main.get_task(t['id'])['runs'][-1].items() if k!='diagnostics'}==before
 assert 'observed_file_guard_node_status_only' in client.get(f"/api/tasks/{t['id']}/report").text and len(calls)==3
 if mode=='guard_failed':assert '沙箱' in a['message'] and main.get_task(t['id'])['runs'][-1]['status']=='failed'
 if mode=='end_failed':assert main.get_task(t['id'])['runs'][-1]['status']=='failed' and a['observed_status']=='succeeded'

@pytest.mark.parametrize('mutation',['graph','steps_missing','steps_bool','steps_count','pagination','duplicate_node','duplicate_execution','other_run','wrong_type','unknown_node','before_failed','guard_missing','guard_stopped','success_error','success_inconsistent','original_publish','approval','egress','attempt_bool','input','recipe','schema_hash','ambiguous','unfinished'])
def test_missing_contradictory_or_unbound_trace_never_proves_guard(client,monkeypatch,mutation):
 t,run,p,detail,trace,published,_=recorded(client,monkeypatch)
 if mutation=='graph':detail['graph']['nodes'][0]['data']['desc']='changed'
 elif mutation=='steps_missing':detail.pop('total_steps')
 elif mutation=='steps_bool':detail['total_steps']=True
 elif mutation=='steps_count':detail['total_steps']=4
 elif mutation=='pagination':trace['has_more']=True
 elif mutation=='duplicate_node':trace['data'][4].update(node_id=GUARD,node_type='code')
 elif mutation=='duplicate_execution':trace['data'][4]['id']=trace['data'][3]['id']
 elif mutation=='other_run':trace['data'][3]['workflow_run_id']=str(uuid.uuid4())
 elif mutation=='wrong_type':trace['data'][3]['node_type']='template-transform'
 elif mutation=='unknown_node':trace['data'][3]['node_id']='other'
 elif mutation=='before_failed':trace['data'][2]['status']='failed'
 elif mutation=='guard_missing':trace['data'].pop(3);detail['total_steps']=4
 elif mutation=='guard_stopped':trace['data'][3]['status']='stopped';detail['status']='stopped'
 elif mutation=='success_error':trace['data'][3]['error']='成功与错误矛盾'
 elif mutation=='success_inconsistent':trace['data'][4]['status']='failed'
 elif mutation=='original_publish':run['result']['data']['workflow_id']=str(uuid.uuid4());main.save_task(t)
 elif mutation=='approval':p['strict_guard_approved']=False;main.store.put(KIND,p['id'],p)
 elif mutation=='egress':p['model_egress_approved']=False;main.store.put(KIND,p['id'],p)
 elif mutation=='attempt_bool':p['attempts']=True;main.store.put(KIND,p['id'],p)
 elif mutation=='input':run['input']={};main.save_task(t)
 elif mutation=='recipe':p['data_flow']['strict_guard']['code_text']+='\n# changed';main.store.put(KIND,p['id'],p)
 elif mutation=='schema_hash':p['data_flow']['strict_guard']['schema_text_sha256']='0'*64;main.store.put(KIND,p['id'],p)
 elif mutation=='ambiguous':other=copy.deepcopy(p);other['id']=str(uuid.uuid4());main.store.put(KIND,other['id'],other)
 elif mutation=='unfinished':detail['status']='running'
 calls=reader(monkeypatch,detail,trace,published);r=diagnose(client,t,run);assert r.status_code==200,r.text;a=r.json()['file_guard_audit'];assert a['state']=='insufficient' and not a['guard_status_observed'] and a['business_verified'] is False and len(calls)<=3

def test_local_only_has_no_observed_guard_status_and_no_extra_request(client,monkeypatch):
 t,run,p,detail,trace,published,_=recorded(client,monkeypatch);calls=reader(monkeypatch,detail,trace,published)
 r=diagnose(client,t,run,False);assert r.status_code==200 and not calls and r.json()['file_guard_audit']['state']=='insufficient'

def test_historical_guard_status_does_not_remove_current_revision_warning(client,monkeypatch):
 t,run,p,detail,trace,published,_=recorded(client,monkeypatch);t['revision']+=1;main.save_task(t);reader(monkeypatch,detail,trace,published)
 r=diagnose(client,t,run);assert r.status_code==200,r.text;v=r.json();assert v['file_guard_audit']['state']=='observed_succeeded' and not v['current_source'] and not v['snapshot_matches_current'] and v['file_guard_audit']['plan_revision']==run['revision']
