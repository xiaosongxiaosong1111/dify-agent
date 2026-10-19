import copy,json,hashlib,uuid
import pytest
from test_api import client
from test_file_run import uploaded,remote,run,plan
from test_file_cases import capture,prepare_case
from app import main

def completed(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);c=capture(client,t,p).json();q=prepare_case(client,t,p,c).json();remote(monkeypatch,t,env);r=run(client,t,q);assert r.status_code==200,r.text;return t,r.json()['task']['runs'][-1]
def url(t,r):return f"/api/tasks/{t['id']}/file-cases/runs/{r['id']}"

def test_receipt_preview_and_hash_bound_full_download_are_local_and_unchanged(client,monkeypatch):
 t,run=completed(client,monkeypatch);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('只读原回执不得联网、读成果、写Task或解密')
 monkeypatch.setattr(main,'artifact_path',forbidden);monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.store,'put',forbidden)
 r=client.get(url(t,run)+'/evidence');assert r.status_code==200,r.text;v=r.json();assert v['outputs_available'] and not v['preview_truncated'] and not v['current_acceptance_rechecked']
 downloaded=client.get(url(t,run)+'/outputs.json',params={'sha256':v['outputs_sha256']});assert downloaded.status_code==200
 assert downloaded.json()==run['result']['data']['outputs'] and hashlib.sha256(downloaded.content).hexdigest()==v['outputs_sha256']
 assert downloaded.headers['cache-control']=='no-store' and 'attachment' in downloaded.headers['content-disposition'] and main.get_task(t['id'])==before
 assert all(s not in r.text for s in ['credential_stamp','binding_digest','remote_id','fixture-service-key','fixture-console-token'])

def test_large_unicode_output_is_explicitly_truncated_and_full_download_preserves_exact_bytes(client,monkeypatch):
 t,record=completed(client,monkeypatch);task=main.get_task(t['id']);task['runs'][-1]['result']['data']['outputs']={'result':'汉字😀'*10000};main.save_task(task)
 v=client.get(url(t,record)+'/evidence').json();assert v['preview_truncated'] and len(v['outputs_preview'].encode('utf-8'))<=64000
 r=client.get(url(t,record)+'/outputs.json',params={'sha256':v['outputs_sha256']});assert r.status_code==200 and r.json()['result']=='汉字😀'*10000 and len(r.content)==v['output_bytes']

@pytest.mark.parametrize('state',['unknown','failed','pending'])
def test_unsuccessful_runs_do_not_offer_outputs_or_download(client,monkeypatch,state):
 t,record=completed(client,monkeypatch);task=main.get_task(t['id']);task['runs'][-1].update(status=state,result=None);main.save_task(task)
 v=client.get(url(t,record)+'/evidence').json();assert not v['outputs_available'] and v['outputs_preview'] is None and v['outputs_sha256'] is None
 assert client.get(url(t,record)+'/outputs.json',params={'sha256':'a'*64}).status_code==409

def test_free_runs_other_task_and_wrong_hash_cannot_be_read_as_fixed_case_receipts(client,monkeypatch):
 t,record=completed(client,monkeypatch);assert client.get(url(t,record)+'/outputs.json',params={'sha256':'a'*64}).status_code==409
 assert client.get(url(t,{'id':str(uuid.uuid4())})+'/evidence').status_code==404
 task=main.get_task(t['id']);task['runs'][-1].pop('file_case');main.save_task(task)
 assert client.get(url(t,record)+'/evidence').status_code==422

def test_old_case_result_can_be_read_without_rechecking_or_inheriting_current_acceptance(client,monkeypatch):
 t,record=completed(client,monkeypatch);task=main.get_task(t['id']);task['revision']+=1;task['artifact']=None;main.save_task(task)
 r=client.get(url(t,record)+'/evidence');assert r.status_code==200,r.text;v=r.json();assert v['run_revision']!=v['revision'] and v['current_acceptance_rechecked'] is False
