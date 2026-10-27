import copy
import pytest
from fastapi import HTTPException
from test_code_samples import api,task,prepare,execute
from app import code_sample_docker as d
from app import code_sample_maintenance as m

@pytest.fixture
def setup(api,monkeypatch):
 t=task(api)
 monkeypatch.setattr(d,'execute',lambda *a,**kw:{'status':'unknown','error_category':'cleanup_unknown','cleanup_verified':False})
 prepared=prepare(api,t).json();unknown=execute(api,t,prepared).json();saved=copy.deepcopy(api[1].store.get('code_sample',unknown['id']));calls=[]
 monkeypatch.setattr(m,'resource',lambda *a:None)
 def call(self,*args,**kw):calls.append(args);return 0,b'',b''
 monkeypatch.setattr(d.LocalDocker,'call',call)
 return api,t,saved,calls

def plan(setup):
 api,t,row,_=setup
 return api[0].post('/api/tasks/'+t['id']+'/code-sample-maintenance/prepare',json={'revision':t['revision'],'sample_id':row['id']})
def confirm(setup,row,**changes):
 api,t,_,_=setup
 return api[0].post('/api/tasks/'+t['id']+'/code-sample-maintenance/confirm',json={'revision':t['revision'],'proposal_id':row['id'],'review_token':row['review_token'],'acknowledge_cleanup':True}|changes)
def snap(original,ident='a'*64):return {'id':ident,'name':'/sierra-code-'+original['id'],'image':d.IMAGE,'state':'created','operation_id':original['id'],'profile':d.PROFILE}

def test_absent_resource_verified_without_grading_or_code_execution(setup):
 api,t,original,calls=setup;before=copy.deepcopy(api[1].store.get('task',t['id']));proposal=plan(setup);assert proposal.status_code==200
 result=confirm(setup,proposal.json());assert result.json()['state']=='verified' and result.json()['result']['status']=='verified_absent'
 current=api[1].store.get('code_sample',original['id']);assert current['state']=='unknown' and current['result']==original['result'] and current['last_cleanup']['verified'] is True
 assert api[1].store.get('task',t['id'])==before and not calls
 assert confirm(setup,proposal.json()).status_code==409
 history=api[0].get('/api/tasks/'+t['id']+'/code-sample-maintenance').json();assert history['samples'][0]['state']=='unknown' and 'result' not in history['samples'][0]

@pytest.mark.parametrize('change',[{'acknowledge_cleanup':False},{'acknowledge_cleanup':1},{'review_token':'wrong'}])
def test_confirmation_is_specific_and_explicit(setup,change):
 proposal=plan(setup).json();assert confirm(setup,proposal,**change).status_code in (409,422) and not setup[3]

def test_only_exact_previewed_owned_id_can_be_removed(setup,monkeypatch):
 api,t,original,calls=setup;values=iter([snap(original),snap(original),None]);monkeypatch.setattr(m,'resource',lambda *a:next(values));proposal=plan(setup).json();result=confirm(setup,proposal).json()
 assert result['state']=='verified' and result['result']['removed'] and calls==[('rm','--force','a'*64)]
 assert api[1].store.get('code_sample',original['id'])['result']==original['result']

@pytest.mark.parametrize('initial,current',[(None,'exists'),('exists','other')])
def test_appearance_or_replacement_refuses_deletion(setup,monkeypatch,initial,current):
 original=setup[2];values=iter([snap(original) if initial else None,snap(original,'a'*64 if current=='exists' else 'b'*64)]);monkeypatch.setattr(m,'resource',lambda *a:next(values));proposal=plan(setup).json();result=confirm(setup,proposal).json()
 assert result['state']=='unknown' and result['result']['status']=='resource_changed' and not setup[3]

def test_auto_removed_between_preview_and_confirm_is_safe_absence(setup,monkeypatch):
 values=iter([snap(setup[2]),None]);monkeypatch.setattr(m,'resource',lambda *a:next(values));result=confirm(setup,plan(setup).json()).json();assert result['state']=='verified' and not result['result']['removed'] and not setup[3]

def test_sample_state_change_invalidates_old_maintenance_plan(setup):
 api,_,original,_=setup;proposal=plan(setup).json();row=api[1].store.get('code_sample',original['id']);row['result']['error_category']='changed';api[1].store.put('code_sample',row['id'],row)
 assert confirm(setup,proposal).status_code==409 and not setup[3]

def test_history_and_maintenance_of_old_revision_do_not_restore_old_task(setup):
 api,t,original,_=setup;r=api[0].patch('/api/tasks/'+t['id'],json={'expected_revision':t['revision'],'requirements':{'goal':'new business revision'}});assert r.status_code==200
 t.update(revision=r.json()['revision']);before=copy.deepcopy(api[1].store.get('task',t['id']));proposal=plan(setup).json();assert proposal['sample_revision']!=proposal['revision'];assert confirm(setup,proposal).json()['state']=='verified'
 assert api[1].store.get('task',t['id'])==before

def test_foreign_sample_and_expiry_refuse(setup):
 api,t,_,_=setup;proposal=plan(setup).json();other=task(api)
 r=api[0].post('/api/tasks/'+other['id']+'/code-sample-maintenance/confirm',json={'revision':other['revision'],'proposal_id':proposal['id'],'review_token':proposal['review_token'],'acknowledge_cleanup':True});assert r.status_code==409
 row=api[1].store.get(m.KIND,proposal['id']);row['expires_at']=0;api[1].store.put(m.KIND,row['id'],row);assert confirm(setup,proposal).status_code==409 and not setup[3]

def test_failed_query_is_not_absence_and_unknown_operation_does_not_retry(setup,monkeypatch):
 def fail(*a):raise d.DockerProblem('query_failed')
 monkeypatch.setattr(m,'resource',fail);assert plan(setup).status_code==503 and not setup[3]
 monkeypatch.setattr(m,'resource',lambda *a:None);proposal=plan(setup).json();monkeypatch.setattr(m,'resource',fail)
 result=confirm(setup,proposal);assert result.json()['state']=='unknown' and result.json()['result']['verified'] is False
 assert confirm(setup,proposal).status_code==409 and not setup[3]

def test_recover_records_unknown_without_transport_or_task_change(setup):
 api,_,_,calls=setup;proposal=plan(setup).json();row=api[1].store.get(m.KIND,proposal['id']);row['state']='executing';api[1].store.put(m.KIND,row['id'],row);api[1].code_sample_maintenance_recover()
 assert api[1].store.get(m.KIND,row['id'])['state']=='unknown' and not calls

def test_same_name_with_foreign_labels_is_not_verified_absent():
 operation='11111111-1111-4111-8111-111111111111'
 class Client:
  owned=d.LocalDocker.owned
  def call(self,*a,**kw):return 0,b'aaaaaaaaaaaa',b''
  def inspect(self,*a):return {'id':'a'*64,'name':'/sierra-code-'+operation,'image':d.IMAGE,'config_image':d.IMAGE,'labels':{}}
 with pytest.raises(d.DockerProblem):m.resource(Client(),operation)
