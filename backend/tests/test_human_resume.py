import copy
import pytest,yaml
from test_api import client
from test_human_decision import pending,decision,submit,form_platform
from test_human_runtime_execution import RUN
from app import main

def submitted(client,monkeypatch,action='approve'):
 t,env,run,_=pending(client,monkeypatch);d=decision(client,t,run,action).json();form_platform(monkeypatch,run);assert submit(client,t,d).status_code==200
 return t,env,run,d

def evidence_platform(monkeypatch,t,run,mode='ok',action='approve'):
 root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'));template='result2' if action=='approve' else 'result4';text='已批准' if action=='approve' else '已拒绝'
 detail={'id':RUN,'status':'succeeded','graph':root['workflow']['graph'],'outputs':{'result':text}}
 trace={'data':[{'node_id':'review','node_type':'human-input','status':'succeeded','outputs_truncated':False,'outputs':{'__action_id':action,'__action_value':'批准' if action=='approve' else '拒绝','__rendered_content':run['form']['content'],'private':'DROP-PRIVATE-RAW'}},*({'node_id':nid,'status':'succeeded'} for nid in (template,template+'end'))]}
 if mode=='action':trace['data'][0]['outputs']['__action_id']='reject' if action=='approve' else 'approve'
 elif mode=='truncated':trace['data'][0]['outputs_truncated']=True
 elif mode=='output':detail['outputs']={'result':'wrong-private-output'}
 elif mode=='path':trace['data'].pop()
 elif mode=='other_path':trace['data'].append({'node_id':'result4' if action=='approve' else 'result2','status':'succeeded'})
 elif mode=='graph':detail['graph']['nodes'][2]['data']['template']='changed'
 elif mode=='identity':detail['id']='another-run'
 elif mode=='duplicate':trace['data'].append(copy.deepcopy(trace['data'][0]))
 calls=[]
 async def get_detail(self,app,rid):calls.append(('GET',app,rid));return detail
 async def request(self,method,path,**kw):calls.append((method,path));assert path.endswith('/node-executions');return trace
 monkeypatch.setattr(main.DifyClient,'workflow_run_detail',get_detail);monkeypatch.setattr(main.DifyClient,'request',request)
 return calls

@pytest.mark.parametrize('action',['approve','reject'])
def test_original_resume_action_path_and_fixed_output_verified_without_attribution(client,monkeypatch,action):
 t,env,run,d=submitted(client,monkeypatch,action);before=copy.deepcopy(main.get_task(t['id']));calls=evidence_platform(monkeypatch,t,run,action=action)
 response=client.get(f"/api/tasks/{t['id']}/human-runtime/runs/{run['id']}/resume-evidence");assert response.status_code==200,response.text;e=response.json()['evidence']
 assert e['confirmed_behavior_matched'] and e['observed_action']==action and e['submit_interface_accepted']
 assert not e['business_verified'] and not e['request_attribution_verified'] and len(calls)==2 and all(c[0]=='GET' for c in calls)
 assert 'DROP-PRIVATE-RAW' not in response.text and main.get_task(t['id'])==before
 assert main.store.get('human_runtime_run',run['id'])['state']=='platform_finished'

@pytest.mark.parametrize('mode',['action','truncated','output','path','other_path','graph','duplicate'])
def test_missing_conflicting_or_truncated_evidence_does_not_pass(client,monkeypatch,mode):
 t,_,run,_=submitted(client,monkeypatch);calls=evidence_platform(monkeypatch,t,run,mode)
 response=client.get(f"/api/tasks/{t['id']}/human-runtime/runs/{run['id']}/resume-evidence");assert response.status_code==200,response.text
 assert not response.json()['evidence']['confirmed_behavior_matched'] and not response.json()['evidence']['business_verified']
 assert 'wrong-private-output' not in response.text and 'DROP-PRIVATE-RAW' not in response.text and len(calls)==2

def test_foreign_run_response_not_adopted(client,monkeypatch):
 t,_,run,_=submitted(client,monkeypatch);before=main.store.get('human_runtime_run',run['id']);evidence_platform(monkeypatch,t,run,'identity')
 assert client.get(f"/api/tasks/{t['id']}/human-runtime/runs/{run['id']}/resume-evidence").status_code==502
 assert main.store.get('human_runtime_run',run['id'])==before

def test_no_submit_attempt_no_recovery_guess(client,monkeypatch):
 t,_,run,_=pending(client,monkeypatch)
 assert client.get(f"/api/tasks/{t['id']}/human-runtime/runs/{run['id']}/resume-evidence").status_code==409
