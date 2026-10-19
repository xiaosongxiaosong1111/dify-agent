import copy,json,uuid,hashlib
import pytest
from test_api import client
from test_file_run import uploaded
from test_file_cases import capture,prepare_case
from app import main
from app.runtime_files import KIND as UPLOAD

def match(client,t,c,**patch):
 return client.post(f"/api/tasks/{t['id']}/file-cases/{c['cases'][0]['id']}/match",json={'revision':t['revision'],'catalog_revision':c['catalog_revision'],'selections':{},**patch})

def test_unique_mapping_is_read_only_and_adoptable_without_remote_reads(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();before=copy.deepcopy(main.get_task(t['id']));rows=main.store.list(UPLOAD)
 def forbidden(*a,**kw):pytest.fail('本机文件匹配不能联网或解密')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 r=match(client,t,c);assert r.status_code==200,r.text;v=r.json();assert v['state']=='ready' and v['slots'][0]['selected_id']==p['id']
 assert json.loads(v['input_text'])=={'document':{'sierra_file_id':p['id']}} and v['input_sha256']==hashlib.sha256(v['input_text'].encode()).hexdigest()
 assert prepare_case(client,t,p,c,input_text=v['input_text']).status_code==200
 assert main.get_task(t['id'])==before and main.store.list(UPLOAD)==rows and v['workflow_runs']==0
 assert all(s not in r.text for s in ['remote_id','remote_created_by','fixture-service-key','fixture-console-token','binding_digest','credential_stamp'])

def test_multiple_same_fingerprints_require_explicit_record_selection(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();second=main.store.get(UPLOAD,p['id']);second.update(id=str(uuid.uuid4()),remote_id=str(uuid.uuid4()),filename='other.TXT');main.store.put(UPLOAD,second['id'],second)
 r=match(client,t,c);assert r.status_code==200,r.text;v=r.json();assert v['state']=='needs_selection' and len(v['slots'][0]['candidates'])==2 and v['input_text'] is None
 selected=match(client,t,c,selections={'document:0':second['id']}).json();assert selected['state']=='ready' and json.loads(selected['input_text'])['document']=={'sierra_file_id':second['id']}
 assert match(client,t,c,selections={'document:0':str(uuid.uuid4())}).status_code==409
 assert match(client,t,c,selections={'document:9':p['id']}).status_code==422

@pytest.mark.parametrize('mutation',['task','revision','artifact','app','variable','state','key','owner','receipt','content','size','extension'])
def test_missing_compatible_upload_is_explicit_and_not_replaced(client,monkeypatch,mutation):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();row=main.store.get(UPLOAD,p['id'])
 changes={'task':('task_id',str(uuid.uuid4())),'revision':('revision',t['revision']+1),'artifact':('artifact_sha256','a'*64),'app':('app_id',str(uuid.uuid4())),'variable':('variable','other'),'state':('state','unknown'),'key':('credential_stamp','a'*64),'owner':('remote_created_by','bad'),'receipt':('remote_upload_observed',False),'content':('content_sha256','a'*64),'size':('size',1),'extension':('filename','sample.md')}
 key,value=changes[mutation];row[key]=value;main.store.put(UPLOAD,row['id'],row)
 r=match(client,t,c);assert r.status_code==200,r.text;v=r.json();assert v['state']=='missing_files' and v['slots'][0]['candidates']==[] and v['input_text'] is None
 assert not main.get_task(t['id'])['runs']

def test_duplicate_file_positions_and_empty_list_are_not_deduplicated_or_filled(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch,'file-list');values={'document':[{'sierra_file_id':p['id']},{'sierra_file_id':p['id']}]};c=capture(client,t,p,input_text=json.dumps(values)).json()
 v=match(client,t,c).json();assert v['state']=='ready' and len(v['slots'])==2 and json.loads(v['input_text'])==values
 c=capture(client,t,p,1,input_text='{"document":[]}').json();c['cases']=[c['cases'][1]]
 v=match(client,t,c).json();assert v['state']=='ready' and v['slots']==[] and json.loads(v['input_text'])=={'document':[]}

def test_large_nonfile_parameters_and_raw_input_text_remain_exact(client,monkeypatch):
 from test_file_model_run import uploaded_model
 def extra(root):root['workflow']['graph']['nodes'][0]['data']['variables'].append({'variable':'amount','type':'number','label':'数值','required':True})
 t,env,p,_=uploaded_model(client,monkeypatch,extra);large=900719925474099312345678901
 values={'document':{'sierra_file_id':p['id']},'question':'原问题','amount':large};c=capture(client,t,p,input_text=json.dumps(values)).json();r=match(client,t,c);assert r.status_code==200,r.text
 assert str(large) in r.json()['input_text'] and json.loads(r.json()['input_text'])==values

def test_catalog_update_and_stale_context_refuse_mapping(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();capture(client,t,p,1)
 assert match(client,t,c).status_code==409
 current=client.get(f"/api/tasks/{t['id']}/file-cases").json();path=main.artifact_path(t);path.write_text(path.read_text(encoding='utf-8')+'\n',encoding='utf-8');assert match(client,t,current).status_code==409

@pytest.mark.parametrize('payload',[{'selections':{'document:0':None}},{'selections':{'document:0':True}},{'catalog_revision':True},{'extra':'private-sentinel'}])
def test_bad_mapping_request_does_not_echo_or_dispatch(client,monkeypatch,payload):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();r=match(client,t,c,**payload);assert r.status_code==422 and 'private-sentinel' not in r.text and not main.get_task(t['id'])['runs']
