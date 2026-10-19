import copy,json,uuid
import pytest,yaml
from test_api import client
from test_optional_file_run import optional_ready,prepare,upload,returned
from test_file_run import remote,run,PUBLISHED,RUN
from app import main
from app.file_run import KIND

def recorded(client,monkeypatch,present=False,op='exists'):
 t,env=optional_ready(client,op);values={}
 if present:values={'document':{'sierra_file_id':upload(client,monkeypatch,t)['id']}}
 p=prepare(client,t,values).json();remote(monkeypatch,t,env,result=returned('隔离文件提取文字' if present else '本次没有提供文件'))
 r=run(client,t,p,acknowledge_optional_branch=True);assert r.status_code==200,r.text
 p=main.store.get(KIND,p['id']);t=main.get_task(t['id']);record=t['runs'][-1];root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'));graph=root['workflow']['graph'];types={n['id']:n['data']['type'] for n in graph['nodes']}
 detail={'id':RUN,'status':'succeeded','total_steps':len(p['data_flow']['resolved_branch']['expected_node_ids']),'graph':graph,'inputs':{'password':'private-input'},'outputs':{'result':'private-output'}}
 trace={'data':[{'id':str(uuid.uuid4()),'node_id':nid,'node_type':types[nid],'status':'succeeded','error':None,'inputs':{'private':'not-retained'},'outputs':{'private':'not-retained'}} for nid in p['data_flow']['resolved_branch']['expected_node_ids']]}
 published={'id':PUBLISHED,**root['workflow']};return t,record,p,detail,trace,published

def reader(monkeypatch,detail,trace,published):
 calls=[]
 async def request(self,method,path,**kwargs):
  calls.append(path);assert method=='GET' and kwargs['credential']=='console_token'
  return trace if path.endswith('/node-executions') else published if path.endswith('/workflows/publish') else detail
 monkeypatch.setattr(main.DifyClient,'request',request);return calls

def diagnose(client,t,record,remote=True):return client.post(f"/api/tasks/{t['id']}/runs/{record['id']}/diagnose",json={'revision':t['revision'],'read_remote':remote})

@pytest.mark.parametrize('present,op',[(False,'exists'),(True,'exists'),(False,'not exists'),(True,'not exists')])
def test_observed_optional_node_set_matches_original_bound_plan_without_extra_reads_or_promoting_acceptance(client,monkeypatch,present,op):
 t,record,p,detail,trace,published=recorded(client,monkeypatch,present,op);before=copy.deepcopy(record);plan=copy.deepcopy(p);calls=reader(monkeypatch,detail,trace,published)
 trace['data'].reverse() # API order is not claimed to be execution-time order.
 response=diagnose(client,t,record);assert response.status_code==200,response.text;r=response.json();a=r['optional_branch_audit'];assert len(calls)==3
 assert a['state']=='matched' and a['node_set_matches'] and a['expected_path']==('file_present' if present else 'file_missing')
 assert a['plan_id']==p['id'] and not a['execution_order_verified'] and not a['business_verified'] and not a['run_state_changed'] and not a['plan_changed']
 assert a['missing_node_ids']==a['unexpected_node_ids']==[] and 'private-' not in response.text and 'not-retained' not in response.text
 assert main.store.get(KIND,p['id'])==plan
 saved=main.get_task(t['id'])['runs'][-1];assert {k:v for k,v in saved.items() if k!='diagnostics'}==before
 assert 'workflow_id' not in detail # The pinned console detail schema does not expose it.
 assert 'observed_optional_node_set_only' in client.get(f"/api/tasks/{t['id']}/report").text and len(calls)==3

@pytest.mark.parametrize('mutation',['wrong_graph','missing_steps','bool_steps','count_mismatch','pagination','duplicate_node','duplicate_execution','wrong_type','failed_node','unknown_node','wrong_saved_version','input_changed','approval_missing','ambiguous_plan','unfinished'])
def test_incomplete_or_unbound_evidence_never_proves_branch(client,monkeypatch,mutation):
 t,record,p,detail,trace,published=recorded(client,monkeypatch)
 if mutation=='wrong_graph':detail['graph']['nodes'][0]['data']['desc']='changed'
 elif mutation=='missing_steps':detail.pop('total_steps')
 elif mutation=='bool_steps':detail['total_steps']=True
 elif mutation=='count_mismatch':detail['total_steps']=4
 elif mutation=='pagination':trace['has_more']=True
 elif mutation=='duplicate_node':trace['data'][2]['node_id']='guard';trace['data'][2]['node_type']='if-else'
 elif mutation=='duplicate_execution':trace['data'][2]['id']=trace['data'][0]['id']
 elif mutation=='wrong_type':trace['data'][2]['node_type']='code'
 elif mutation=='failed_node':trace['data'][2]['status']='failed'
 elif mutation=='unknown_node':trace['data'][2]['node_id']='other'
 elif mutation=='wrong_saved_version':record['result']['data']['workflow_id']=str(uuid.uuid4());main.save_task(t)
 elif mutation=='input_changed':record['input']={'document':None};main.save_task(t)
 elif mutation=='approval_missing':p['optional_branch_approved']=False;main.store.put(KIND,p['id'],p)
 elif mutation=='ambiguous_plan':other=copy.deepcopy(p);other['id']=str(uuid.uuid4());main.store.put(KIND,other['id'],other)
 elif mutation=='unfinished':detail['status']='running'
 reader(monkeypatch,detail,trace,published);r=diagnose(client,t,record);assert r.status_code==200,r.text
 a=r.json()['optional_branch_audit'];assert a['state']=='insufficient' and not a['node_set_matches'] and not a['business_verified']

def test_complete_different_node_set_is_reported_without_changing_original_run_or_plan(client,monkeypatch):
 t,record,p,detail,trace,published=recorded(client,monkeypatch);trace['data'][-1]['node_id']='end';before=copy.deepcopy(record)
 reader(monkeypatch,detail,trace,published);a=diagnose(client,t,record).json()['optional_branch_audit']
 assert a['state']=='different' and a['missing_node_ids']==['no_file'] and a['unexpected_node_ids']==['end'] and not a['node_set_matches']
 assert main.store.get(KIND,p['id'])==p and {k:v for k,v in main.get_task(t['id'])['runs'][-1].items() if k!='diagnostics'}==before

def test_local_only_remains_insufficient_without_network_and_does_not_substitute_static_expectation(client,monkeypatch):
 t,record,p,detail,trace,published=recorded(client,monkeypatch);calls=reader(monkeypatch,detail,trace,published)
 r=diagnose(client,t,record,False);assert r.status_code==200 and not calls and r.json()['optional_branch_audit']['state']=='insufficient'

def test_original_node_set_can_be_compared_but_is_not_current_artifact_proof(client,monkeypatch):
 t,record,p,detail,trace,published=recorded(client,monkeypatch);t['revision']+=1;main.save_task(t);reader(monkeypatch,detail,trace,published)
 r=diagnose(client,t,record);assert r.status_code==200,r.text;v=r.json()
 assert not v['current_source'] and not v['snapshot_matches_current'] and v['optional_branch_audit']['state']=='matched' and v['optional_branch_audit']['plan_revision']==record['revision']
