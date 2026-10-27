import copy,json,uuid,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import publication_dispatch_receipt as receipt


def dump(value):return json.dumps(value,sort_keys=True).encode()
@pytest.fixture
def bundle(tmp_path,monkeypatch):
 root=tmp_path;folder=root/'work'/'frozen';folder.mkdir(parents=True);(root/'docs').mkdir()
 task,app,pub,env=[str(uuid.uuid4()) for _ in range(4)]
 plan={'batch_id':'synthetic','environment_id':env,'graph_digest':'b'*64,'original_app_ids':[]}
 (folder/'plan.json').write_bytes(dump(plan));plan_sha=receipt.sha((folder/'plan.json').read_bytes())
 manifest={'schema_version':1,'batch_id':'synthetic','files':{'plan.json':plan_sha}}
 (folder/'manifest.json').write_bytes(dump(manifest));manifest_sha=receipt.sha((folder/'manifest.json').read_bytes())
 approval={'batch_id':'synthetic','authorization_source':'direct_human_reply','decision':'approve','question_ref':'synthetic-question','reply':'隔离批准','plan_sha256':plan_sha,'manifest_sha256':manifest_sha,'limits':{'login':1,'import':1,'reads':6,'publish':1,'key':1,'run':1}}
 counts={'reads':2,'login':1,'import':1,'publish':0,'key':0,'run':0}
 events=[{'method':m,'path':p,'kind':k,'status':200,'response_body_read':True} for m,p,k in [('POST','/console/api/login','login'),('POST','/console/api/apps/imports','import'),('GET',f'/console/api/apps/{app}/workflows/draft','reads'),('GET',f'/console/api/apps/{app}/workflows/publish','reads')]]
 attempt={'batch_id':'synthetic','state':'stopped_needs_review','phase':'publish','model_http':0,'plan_sha256':plan_sha,'manifest_sha256':manifest_sha,'dispatch_counts':counts,'dispatches':events,'task_id':task,'revision':6,'new_app_id':app}
 (folder/'approval.json').write_bytes(dump(approval));(folder/'attempt.json').write_bytes(dump(attempt))
 report={'state':'stopped_needs_review','phase':'publish','batch_id':'synthetic','reply':'隔离批准','task_id':task,'revision':6,'app_id':app,'publication_record_id':pub,'saved_publication_state':'unknown','saved_write_attempted':True,'actual_publication_http_posts':0,'new_keys':0,'service_runs':0,'model_http':0,'published_workflow_id':None,'counts':counts,**{name+'_sha256':receipt.sha((folder/(name+'.json')).read_bytes()) for name in ('plan','manifest','approval','attempt')}}
 monkeypatch.setattr(receipt,'committed_blob',lambda *a:dump(report))
 return root,folder,report

def validate(bundle):return receipt.validate(bundle[0],bundle[1],'a'*40,'docs/result.json')
def test_valid_hash_chain_builds_only_public_summary(bundle):
 value=validate(bundle);assert value['publish_dispatches']==0 and value['graph_digest']=='b'*64 and len(value)==16
 assert 'dispatches' not in value and 'reply' not in value

@pytest.mark.parametrize('change',['report_sha','frozen_file','path_traversal','absolute_path','duplicate','nan','wrong_app','wrong_revision','wrong_task','wrong_count','boolean_count','wrong_kind','hidden_publish','unread','model','published','approval','report_state'])
def test_bad_or_ambiguous_receipts_rejected(bundle,monkeypatch,change):
 root,folder,report=bundle
 if change=='report_sha':report['attempt_sha256']='0'*64
 elif change=='frozen_file':(folder/'plan.json').write_bytes(b'changed')
 elif change in ('path_traversal','absolute_path'):
  manifest=json.loads((folder/'manifest.json').read_bytes());manifest['files']['../outside' if change=='path_traversal' else 'C:/outside']='0'*64;(folder/'manifest.json').write_bytes(dump(manifest));report['manifest_sha256']=receipt.sha((folder/'manifest.json').read_bytes())
 elif change in ('duplicate','nan'):
  monkeypatch.setattr(receipt,'committed_blob',lambda *a:b'{"a":1,"a":2}' if change=='duplicate' else b'{"a":NaN}')
 elif change=='report_state':report['state']='succeeded'
 else:
  attempt=json.loads((folder/'attempt.json').read_bytes())
  if change=='wrong_app':attempt['new_app_id']=str(uuid.uuid4())
  elif change=='wrong_revision':attempt['revision']=7
  elif change=='wrong_task':attempt['task_id']=str(uuid.uuid4())
  elif change=='wrong_count':attempt['dispatch_counts']['reads']=3
  elif change=='boolean_count':attempt['dispatch_counts']['publish']=False
  elif change=='wrong_kind':attempt['dispatches'][0]['kind']='reads'
  elif change=='hidden_publish':attempt['dispatches'].append({'method':'POST','path':f"/console/api/apps/{report['app_id']}/workflows/publish",'kind':'reads','status':200,'response_body_read':True})
  elif change=='unread':attempt['dispatches'][0]['response_body_read']=False
  elif change=='model':attempt['model_http']=1
  elif change=='published':report['published_workflow_id']=str(uuid.uuid4())
  elif change=='approval':
   approval=json.loads((folder/'approval.json').read_bytes());approval['decision']='deny';(folder/'approval.json').write_bytes(dump(approval));report['approval_sha256']=receipt.sha((folder/'approval.json').read_bytes())
  (folder/'attempt.json').write_bytes(dump(attempt));report['attempt_sha256']=receipt.sha((folder/'attempt.json').read_bytes())
 with pytest.raises(ValueError):validate(bundle)

def test_source_commit_must_be_full_immutable_id_and_path_under_docs(tmp_path):
 for commit,path in [('main','docs/result.json'),('a'*40,'../secret'),('a'*40,'work/result.json')]:
  with pytest.raises(ValueError):receipt.committed_blob(tmp_path,commit,path)
