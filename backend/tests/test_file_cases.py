import asyncio,copy,json,uuid
import pytest
from test_api import client
from test_file_run import uploaded,remote,run,plan
from app import main
from app.file_cases import KIND,scope,FileProof
from app.file_run import KIND as RUN_KIND
from app.runtime_files import KIND as UPLOAD

def capture(client,t,p,rev=0,**patch):
 return client.post(f"/api/tasks/{t['id']}/file-cases/capture",json={'revision':t['revision'],'catalog_revision':rev,'name':'原文件固定提取','input_text':json.dumps({'document':{'sierra_file_id':p['id']}}),'expectation':{'mode':'contains','target':'result','expected':'隔离回执'},**patch})
def prepare_case(client,t,p,catalog,**patch):
 return client.post(f"/api/tasks/{t['id']}/file-runs/prepare",json={'revision':t['revision'],'input_text':json.dumps({'document':{'sierra_file_id':p['id']}}),'case_id':catalog['cases'][0]['id'],'case_catalog_revision':catalog['catalog_revision'],**patch})
def read(client,t):return client.get(f"/api/tasks/{t['id']}/file-cases")
def summary(client,t):return client.get(f"/api/tasks/{t['id']}/acceptance").json()

def test_capture_is_local_stable_and_does_not_invalidate_current_upload_or_task(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);before=copy.deepcopy(main.get_task(t['id']));upload_before=main.store.get(UPLOAD,p['id'])
 def forbidden(*a,**kw):pytest.fail('本机样例不得解密或出站')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 r=capture(client,t,p);assert r.status_code==200,r.text;c=r.json();assert c['catalog_revision']==1 and c['network_requested'] is False and c['task_changed'] is False
 fixture=c['cases'][0]['input']['document']['sierra_file_fixture'];assert fixture=={'sha256':p['content_sha256'],'size':p['size'],'extension':'.txt'}
 assert all(x not in r.text for x in [p['id'],'sierra_file_id','remote_id','credential_stamp','fixture-service-key','fixture-console-token'])
 assert main.get_task(t['id'])==before and main.store.get(UPLOAD,p['id'])==upload_before
 assert read(client,t).json()['results'][0]['status']=='not_run'

def test_current_file_case_runs_evaluates_and_merges_into_acceptance_and_report(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();q=prepare_case(client,t,p,c);assert q.status_code==200,q.text
 calls,_=remote(monkeypatch,t,env);r=run(client,t,q.json());assert r.status_code==200,r.text
 record=r.json()['task']['runs'][-1];assert record['file_case']['case']==json.loads(c['cases'][0]['definition_text']) and 'test_case' not in record and record['file_case_evaluation']['status']=='passed'
 assert [x[0] for x in calls]==['keys','published','run']
 s=summary(client,t);assert s['required']['total']==s['required']['passed']==1 and s['all_required_passed'] and s['verification']=='declared_checks_only'
 assert read(client,t).json()['results'][0]['status']=='passed'
 report=client.get(f"/api/tasks/{t['id']}/report");assert report.status_code==200 and '固定文件验收样例' in report.text and '原文件固定提取' in report.text
 assert not r.json()['plan']['business_verified'] and not run(client,t,q.json()).status_code==200

def test_same_bytes_new_upload_record_can_map_but_old_plan_does_not_change(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();q=prepare_case(client,t,p,c).json()
 row=main.store.get(UPLOAD,p['id']);row['id']=str(uuid.uuid4());row['filename']='renamed.TXT';row['remote_id']=str(uuid.uuid4());main.store.put(UPLOAD,row['id'],row)
 replacement={**p,'id':row['id']};new=prepare_case(client,t,replacement,c);assert new.status_code==200,new.text
 assert q['input']!=new.json()['input'] and q['file_case']['case']['input']==new.json()['file_case']['case']['input']
 assert main.store.get(RUN_KIND,q['id'])['input']==q['input']

@pytest.mark.parametrize('field,value',[('content_sha256','a'*64),('size',1),('filename','sample.md')])
def test_wrong_fingerprint_size_or_extension_never_prepares(client,monkeypatch,field,value):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();row=main.store.get(UPLOAD,p['id']);row[field]=value;main.store.put(UPLOAD,row['id'],row)
 r=prepare_case(client,t,p,c);assert r.status_code==422,r.text;assert not main.store.list(RUN_KIND)

def test_list_empty_order_duplicates_are_part_of_fixed_input(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch,'file-list');first=main.store.get(UPLOAD,p['id']);second={**first,'id':str(uuid.uuid4()),'content_sha256':'a'*64,'remote_id':str(uuid.uuid4())};main.store.put(UPLOAD,second['id'],second)
 def text(ids):return json.dumps({'document':[{'sierra_file_id':i} for i in ids]})
 c=capture(client,t,p,input_text=text([first['id'],second['id'],first['id']])).json()
 for ids in ([second['id'],first['id'],first['id']],[first['id'],second['id']],[]):
  assert prepare_case(client,t,p,c,input_text=text(ids)).status_code==422
 assert prepare_case(client,t,p,c,input_text=text([first['id'],second['id'],first['id']])).status_code==200
 empty=capture(client,t,p,1,input_text=text([])).json();assert prepare_case(client,t,p,{**empty,'cases':[empty['cases'][1]]},input_text=text([])).status_code==200

def test_nonfile_inputs_use_strict_json_equality(client,monkeypatch):
 from test_file_model_run import uploaded_model
 # Use an actual model-chain fixture, without invoking a model.
 t,env,p,_=uploaded_model(client,monkeypatch)
 values={'document':{'sierra_file_id':p['id']},'question':'原问题'}
 c=capture(client,t,p,input_text=json.dumps(values)).json();assert prepare_case(client,t,p,c,input_text=json.dumps({**values,'question':'新问题'})).status_code==422
 assert prepare_case(client,t,p,c,input_text=json.dumps(values)).status_code==200

def test_catalog_updates_expire_old_plans_and_results_without_changing_revision(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();q=prepare_case(client,t,p,c).json();calls,_=remote(monkeypatch,t,env)
 assert run(client,t,q).status_code==200
 c2=capture(client,t,p,1,case_id=c['cases'][0]['id'],expectation={'mode':'equals','target':'result','expected':'changed'});assert c2.status_code==200,c2.text
 assert main.get_task(t['id'])['revision']==t['revision'] and summary(client,t)['required']['needs_review']==1
 old=prepare_case(client,t,p,c);assert old.status_code==409 and len(calls)==3
 new=prepare_case(client,t,p,c2.json()).json();capture(client,t,p,2,name='另一样例');assert run(client,t,new).status_code==409 and len(calls)==3

def test_case_edit_during_management_verification_is_blocked_and_direct_change_detected(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();q=prepare_case(client,t,p,c).json();calls,workflow=remote(monkeypatch,t,env)
 async def publish(*a):
  response=await asyncio.to_thread(capture,client,t,p,1,name='并发修改');assert response.status_code==409,response.text
  row=main.store.get(KIND,t['id']);row['cases'][0]['expectation']['expected']='changed';main.store.put(KIND,t['id'],row)
  return workflow
 monkeypatch.setattr(main.DifyClient,'published_workflow',publish)
 assert run(client,t,q).status_code==409 and not main.get_task(t['id'])['runs'] and not any(x[0]=='run' for x in calls)

def test_stale_artifact_requires_explicit_new_catalog_and_keeps_archived_definition(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();file=main.artifact_path(t);file.write_text(file.read_text(encoding='utf-8')+'\n',encoding='utf-8')
 assert read(client,t).json()['stale'] and summary(client,t)['cases'][0]['status']=='needs_review'
 # Rebind only a mock upload receipt to the new artifact; production upload provenance remains strict.
 import hashlib
 row=main.store.get(UPLOAD,p['id']);row['artifact_sha256']=hashlib.sha256(file.read_bytes()).hexdigest();main.store.put(UPLOAD,row['id'],row)
 assert capture(client,t,p,1).status_code==409
 r=capture(client,t,p,1,replace_stale=True);assert r.status_code==200,r.text
 assert len(r.json()['cases'])==1 and r.json()['cases'][0]['id']!=c['cases'][0]['id'] and not r.json()['stale']
 assert main.store.get(KIND,t['id'])['history'][-1]['cases']==[json.loads(x['definition_text']) for x in c['cases']]

@pytest.mark.parametrize('patch',[{'case_catalog_revision':None},{'case_id':None},{'case_catalog_revision':99},{'case_id':str(uuid.uuid4())},{'case_catalog_revision':True}])
def test_bad_case_selection_does_not_downgrade_to_free_run(client,monkeypatch,patch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();r=prepare_case(client,t,p,c,**patch);assert r.status_code in (409,422,404),r.text;assert not main.store.list(RUN_KIND)

@pytest.mark.parametrize('raw',['{"mode":"contains","mode":"equals","target":"result","expected":"private-sentinel"}','{"mode":"equals","target":"result","expected":1e999}','{"mode":"unknown","target":"result","expected":"x"}','{"mode":"manual","description":" "}','{"mode":"contains","target":"result","expected":"x","arbitrary":"private-sentinel"}'])
def test_bad_expectations_are_not_silently_repaired_or_saved(client,monkeypatch,raw):
 t,env,p=uploaded(client,monkeypatch)
 body={'revision':t['revision'],'catalog_revision':0,'input_text':json.dumps({'document':{'sierra_file_id':p['id']}}),'name':'sample'}
 request=json.dumps(body)[:-1]+',"expectation":'+raw+'}'
 r=client.post(f"/api/tasks/{t['id']}/file-cases/capture",content=request,headers={'content-type':'application/json'})
 assert r.status_code==422,r.text;assert not main.store.get(KIND,t['id']) and 'private-sentinel' not in r.text

def test_manual_review_requires_actual_matching_success_and_cannot_override_rule(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p,expectation={'mode':'manual','description':'检查提取完整性'}).json();q=prepare_case(client,t,p,c).json();remote(monkeypatch,t,env);result=run(client,t,q).json();record=result['task']['runs'][-1]
 assert summary(client,t)['required']['needs_review']==1
 url=f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/review";payload={'revision':t['revision'],'catalog_revision':1,'decision':'passed','reason':'已检查原始结果'}
 assert client.post(url,json=payload).status_code==200 and summary(client,t)['required']['passed']==1
 assert client.post(url,json={**payload,'decision':'failed','reason':'发现缺失'}).status_code==200 and summary(client,t)['required']['failed']==1
 c2=capture(client,t,p,1,case_id=c['cases'][0]['id'],expectation={'mode':'contains','target':'result','expected':'missing'}).json();q=prepare_case(client,t,p,c2).json();record=run(client,t,q).json()['task']['runs'][-1]
 assert client.post(f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/review",json={**payload,'catalog_revision':2}).status_code==422 and summary(client,t)['required']['failed']==1

def test_removal_optimistic_conflict_and_old_checkpoints_are_retained(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();url=f"/api/tasks/{t['id']}/file-cases/{c['cases'][0]['id']}/remove"
 assert capture(client,t,p,0).status_code==409
 assert client.post(url,json={'revision':t['revision'],'catalog_revision':99}).status_code==409
 r=client.post(url,json={'revision':t['revision'],'catalog_revision':1});assert r.status_code==200 and not r.json()['cases'] and r.json()['catalog_revision']==2
 assert main.store.get(KIND,t['id'])['history'][-1]['cases']==[json.loads(x['definition_text']) for x in c['cases']] and summary(client,t)['required']['total']==0 and not summary(client,t)['all_required_passed']

def test_free_file_runs_are_never_counted_as_fixed_case_passes(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);capture(client,t,p);q=plan(client,t,p).json();remote(monkeypatch,t,env);assert run(client,t,q).status_code==200
 assert summary(client,t)['required']['not_run']==1 and not summary(client,t)['all_required_passed']

def test_canonical_text_keeps_large_integer_rules_and_plan_preview_exact(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);large=900719925474099312345678901
 expectation={'mode':'equals','target':'result','expected':{'nested':[large,1.2345678901234567]}}
 c=capture(client,t,p,expectation=expectation).json();case=c['cases'][0]
 assert str(large) in case['expectation_text'] and json.loads(case['expectation_text'])==expectation
 assert json.loads(case['definition_text'])['expectation']==expectation and 'sierra_file_id' not in case['input_text']
 q=prepare_case(client,t,p,c);assert q.status_code==200,q.text
 assert str(large) in q.json()['file_case']['case_text'] and json.loads(q.json()['file_case']['case_text'])['expectation']==expectation

def test_canonical_text_cannot_be_submitted_as_unreviewed_expectation_fields(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch)
 r=capture(client,t,p,expectation={'mode':'equals','target':'result','expected':1,'expectation_text':'private-sentinel'})
 assert r.status_code==422 and not main.store.get(KIND,t['id']) and 'private-sentinel' not in r.text

def test_fixed_nonfile_number_stays_exact_in_canonical_input_and_matching(client,monkeypatch):
 from test_file_model_run import uploaded_model
 def extra(root):root['workflow']['graph']['nodes'][0]['data']['variables'].append({'variable':'amount','type':'number','label':'数值','required':True})
 t,env,p,_=uploaded_model(client,monkeypatch,patch=extra);large=900719925474099312345678901
 values={'document':{'sierra_file_id':p['id']},'question':'原问题','amount':large}
 c=capture(client,t,p,input_text=json.dumps(values)).json();assert str(large) in c['cases'][0]['input_text']
 assert prepare_case(client,t,p,c,input_text=json.dumps(values)).status_code==200
 assert prepare_case(client,t,p,c,input_text=json.dumps({**values,'amount':large+1})).status_code==422

def test_file_and_ordinary_case_identifiers_cannot_collide_in_summary(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();task=main.get_task(t['id'])
 task['test_cases']=[{'id':'file:'+c['cases'][0]['id'],'name':'普通样例','input':{},'required':True,'expectation':{'mode':'contains','target':'result','expected':'value'}}];main.save_task(task)
 rows=summary(client,t)['cases'];assert len(rows)==2 and len({r['id'] for r in rows})==2 and rows[1]['case_id']==c['cases'][0]['id']

