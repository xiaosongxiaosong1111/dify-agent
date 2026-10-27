import copy,time,uuid
import pytest
from fastapi import HTTPException
from test_api import client,forbid_api_external_calls
from test_workflow_publication import setup,prepare,confirm,writes
from app import main
from app.dify import DifyError
from app.storage import Store
from app import publication_recovery as recovery


def unknown(client,monkeypatch):
 task,env,state=setup(client,monkeypatch);p=prepare(client,task).json()
 state['post_error']=DifyError('synthetic admission stop before physical HTTP')
 assert confirm(client,task,p).status_code==502
 state.pop('post_error');state['calls'].clear()
 task=main.store.get('task',task['id']);old=main.store.get('workflow_publication',p['id'])
 summary={'schema_version':1,'task_id':task['id'],'revision':task['revision'],'app_id':task['dify_app_id'],'publication_id':p['id'],'environment_id':env['id'],'graph_digest':old['graph_digest'],'source_commit':'a'*40,'report_path':'docs/synthetic.json','batch_id':'synthetic-only','publish_dispatches':0,**{k:'b'*64 for k in ('report_sha256','plan_sha256','manifest_sha256','approval_sha256','attempt_sha256')}}
 proof,created=recovery.register_evidence(main,summary,'agent_delegated','隔离替身的本机一致性声明，不是平台证据。');assert created
 return task,env,state,old,proof

def route(client,task,action,**body):
 return client.post(f"/api/tasks/{task['id']}/publication-recovery/{action}",json={'revision':task['revision']}|body)
def ready(client,task,proof):
 r=route(client,task,'prepare',evidence_id=proof['id']);assert r.status_code==200,r.text;p=r.json()
 r=route(client,task,'confirm',recovery_id=p['id'],review_token=p['review_token'],acknowledge_no_dispatch=True,acknowledge_new_attempt=True,actor='agent_delegated',actor_note='按既有委托核对隔离证据。');assert r.status_code==200,r.text
 return r.json()
def new_prepare(client,task,res):return client.post(f"/api/tasks/{task['id']}/workflow-publication/prepare",json={'revision':task['revision'],'recovery_id':res['id']})

def test_local_review_preserves_history_seal_and_requires_new_explicit_publication(client,monkeypatch):
 task,env,state,old,proof=unknown(client,monkeypatch);saved=copy.deepcopy(task)
 assert prepare(client,task).status_code==409 and not state['calls']
 res=ready(client,task,proof)
 assert not state['calls'] and main.store.get('task',task['id'])==saved and main.store.get('workflow_publication',old['id'])==old
 text=client.get(f"/api/tasks/{task['id']}/publication-recovery").text
 assert 'seal' not in text and 'binding' not in text and 'isolated-token' not in text
 assert Store(main.store.root).get(recovery.RECOVERY,res['id'])['state']=='ready'
 assert prepare(client,task).status_code==409
 r=new_prepare(client,task,res);assert r.status_code==200,r.text;p=r.json();assert p['recovery_id']==res['id'] and len(state['calls'])==2 and writes(state)==0
 assert new_prepare(client,task,res).status_code==409
 assert confirm(client,task,p).status_code==409 and writes(state)==0
 r=confirm(client,task,p,recovery_id=res['id']);assert r.status_code==200,r.text
 assert writes(state)==1 and len(state['calls'])==6 and main.store.get('workflow_publication',old['id'])==old
 assert main.store.get('task',task['id'])['runs'][:-1]==saved['runs']
 assert main.store.get(recovery.RECOVERY,res['id'])['state']=='consumed'
 history=client.get(f"/api/tasks/{task['id']}/publication-recovery").json()
 assert history['recoveries'][0]['state']=='consumed' and history['recoveries'][0]['publication_id']==old['id'] and not history['recoveries'][0]['current_source']
 assert new_prepare(client,task,res).status_code==409 and prepare(client,task).status_code==409
 assert route(client,task,'prepare',evidence_id=proof['id']).status_code==409
 assert writes(state)==1

@pytest.mark.parametrize('change',['ack1','ack2','string_bool','actor','empty_note','credential','extra','token','expiry','cross_task','seal','old_run','environment','artifact','revision'])
def test_local_invalid_review_never_reads_remote_or_changes_unknown(client,monkeypatch,change):
 task,env,state,old,proof=unknown(client,monkeypatch)
 p=route(client,task,'prepare',evidence_id=proof['id']).json()
 body={'recovery_id':p['id'],'review_token':p['review_token'],'acknowledge_no_dispatch':True,'acknowledge_new_attempt':True,'actor':'user','actor_note':'明确核对本机证据。'}
 if change=='ack1':body['acknowledge_no_dispatch']=False
 elif change=='ack2':body['acknowledge_new_attempt']=False
 elif change=='string_bool':body['acknowledge_no_dispatch']='true'
 elif change=='actor':body['actor']='fabricated_human'
 elif change=='empty_note':body['actor_note']=' '
 elif change=='credential':body['actor_note']='password=never-output-this-credential'
 elif change=='extra':body['unexpected']='never-output-this-credential'
 elif change=='token':body['review_token']='wrong'
 elif change in ('expiry','seal','cross_task'):
  row=main.store.get(recovery.RECOVERY,p['id'])
  if change=='expiry':row['expires_at']=0;row=recovery.signed(main,row)
  elif change=='seal':row['state']='ready'
  else:row['task_id']=str(uuid.uuid4());row=recovery.signed(main,row)
  main.store.put(recovery.RECOVERY,p['id'],row)
 elif change=='environment':
  e=main.store.get('environment',env['id']);e['connection_revision']='changed';main.store.put('environment',env['id'],e)
 elif change=='artifact':main.artifact_path(task).write_text('changed','utf-8')
 else:
  current=main.store.get('task',task['id'])
  if change=='old_run':current['runs'][-1]['error']='altered history'
  else:current['revision']+=1
  main.store.put('task',task['id'],current)
 r=route(client,task,'confirm',**body);assert r.status_code in (409,422),r.text
 assert 'never-output-this-credential' not in r.text and not state['calls']
 assert main.store.get('workflow_publication',old['id'])==old

@pytest.mark.parametrize('change',['published','draft','expiry','evidence','new_unknown'])
def test_recovery_rechecks_remote_and_never_reuses_unknown(client,monkeypatch,change):
 task,env,state,old,proof=unknown(client,monkeypatch);res=ready(client,task,proof)
 if change=='published':state['published']=copy.deepcopy(state['draft'])|{'id':str(uuid.uuid4())}
 elif change=='draft':state['draft']['hash']='changed';state['draft']['graph']['nodes'][0]['data']['title']='changed'
 elif change=='expiry':
  row=main.store.get(recovery.RECOVERY,res['id']);row['expires_at']=0;main.store.put(recovery.RECOVERY,res['id'],recovery.signed(main,row))
 elif change=='evidence':
  row=main.store.get(recovery.EVIDENCE,proof['id']);row['source']['publish_dispatches']=0.0;main.store.put(recovery.EVIDENCE,proof['id'],row)
 else:
  p=new_prepare(client,task,res).json();state['post_error']=DifyError('synthetic lost reply')
  assert confirm(client,task,p,recovery_id=res['id']).status_code==502
  assert main.store.get(recovery.RECOVERY,res['id'])['state']=='consumed'
 r=new_prepare(client,task,res);assert r.status_code==409,r.text
 assert writes(state)==(1 if change=='new_unknown' else 0)
 assert main.store.get('workflow_publication',old['id'])==old

def test_repeated_registration_deduplicates_and_bad_summary_rejected(client,monkeypatch):
 task,env,state,old,proof=unknown(client,monkeypatch)
 row,created=recovery.register_evidence(main,proof['source'],'agent_delegated','再次核对同一依据。');assert not created and row==proof
 changed=copy.deepcopy(proof['source']);changed['publish_dispatches']=1
 with pytest.raises(HTTPException):recovery.register_evidence(main,changed,'user','核对')
 p=route(client,task,'prepare',evidence_id=proof['id']).json();q=route(client,task,'prepare',evidence_id=proof['id']).json();assert p==q
 assert not state['calls']

def test_prewrite_failure_allows_only_new_local_review_not_replay(client,monkeypatch):
 task,env,state,old,proof=unknown(client,monkeypatch);res=ready(client,task,proof);p=new_prepare(client,task,res).json()
 state['draft']['hash']='externally-changed'
 assert confirm(client,task,p,recovery_id=res['id']).status_code==409
 assert main.store.get('workflow_publication',p['id'])['state']=='failed' and writes(state)==0
 assert new_prepare(client,task,res).status_code==409
 q=route(client,task,'prepare',evidence_id=proof['id']);assert q.status_code==200,q.text
 assert q.json()['id']!=res['id'] and q.json()['state']=='prepared' and main.store.get('workflow_publication',old['id'])==old


def test_concurrent_new_preparations_reserve_only_one_and_restart_does_not_dispatch(client,monkeypatch):
 import threading
 from concurrent.futures import ThreadPoolExecutor
 task,env,state,old,proof=unknown(client,monkeypatch);res=ready(client,task,proof)
 barrier=threading.Barrier(2);state['read_hook']=lambda:barrier.wait(timeout=10)
 with ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(lambda _:new_prepare(client,task,res),range(2)))
 assert sorted(r.status_code for r in results)==[200,409]
 assert writes(state)==0
 stored=Store(main.store.root);assert stored.get(recovery.RECOVERY,res['id'])['state']=='reserved'
 before=copy.deepcopy(state['calls']);main.recover_external_actions();assert state['calls']==before
 assert stored.get('workflow_publication',old['id'])==old
 state.pop('read_hook')
 proposal=next(r.json() for r in results if r.status_code==200)
 assert confirm(client,task,proposal,recovery_id=res['id']).status_code==200
 assert writes(state)==1


def test_second_remote_check_can_stop_before_consumption(client,monkeypatch):
 task,env,state,old,proof=unknown(client,monkeypatch);res=ready(client,task,proof);p=new_prepare(client,task,res).json()
 state['published']=copy.deepcopy(state['draft'])|{'id':str(uuid.uuid4())}
 assert confirm(client,task,p,recovery_id=res['id']).status_code==409
 assert writes(state)==0 and main.store.get(recovery.RECOVERY,res['id'])['state']=='reserved'
 assert main.store.get('workflow_publication',old['id'])==old
