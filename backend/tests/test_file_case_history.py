import copy,json
import pytest
from test_api import client,create
from test_file_run import uploaded
from test_file_cases import capture
from app import main
from app.file_cases import KIND

def history(client,t,version=None):return client.get(f"/api/tasks/{t['id']}/file-cases/history"+(f'/{version}' if version is not None else ''))

def test_empty_history_requires_no_files_or_artifact_and_never_writes(client,monkeypatch):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('历史只读不能修改任务、读成果、解密或联网')
 monkeypatch.setattr(main,'artifact_path',forbidden);monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.store,'put',forbidden)
 r=history(client,t);assert r.status_code==200,r.text;v=r.json();assert v['records']==[] and v['current_catalog_revision']==0 and v['restored'] is False
 assert main.get_task(t['id'])==before and history(client,t,1).status_code==404

def test_index_and_explicit_definition_preserve_values_and_report_exact_changed_fields(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);large=900719925474099312345678901
 old=capture(client,t,p,expectation={'mode':'equals','target':'result','expected':{'n':large}}).json()
 capture(client,t,p,1,case_id=old['cases'][0]['id'],name='新名称',required=False,expectation={'mode':'contains','target':'result','expected':'new'})
 before=copy.deepcopy(main.get_task(t['id']));record=copy.deepcopy(main.store.get(KIND,t['id']))
 def forbidden(*a,**kw):pytest.fail('旧定义查询不能联网或解密')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 index=history(client,t);assert index.status_code==200,index.text;v=index.json();assert len(v['records'])==1 and 'cases' not in v['records'][0]
 row=v['records'][0];assert row['catalog_revision']==1 and row['executable'] is False and row['target_recorded'] and row['target']['environment_id']==env['id']
 changes=row['changes_to_next'];assert changes['next_catalog_revision']==2 and not changes['source_binding_changed'] and changes['added']==changes['removed']==[]
 assert changes['changed'][0]['fields']==['name','expectation','required']
 detail=history(client,t,1);assert detail.status_code==200;case=detail.json()['snapshot']['cases'][0]
 assert str(large) in case['definition_text'] and json.loads(case['expectation_text'])['expected']['n']==large
 assert main.get_task(t['id'])==before and main.store.get(KIND,t['id'])==record
 assert all(x not in detail.text for x in ['binding_digest','credential_stamp','fixture-service-key','fixture-console-token','remote_id','sierra_file_id','resource_token'])

def test_removed_case_and_new_case_are_different_changes(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);old=capture(client,t,p).json();new=capture(client,t,p,1,name='新增样例').json()
 url=f"/api/tasks/{t['id']}/file-cases/{old['cases'][0]['id']}/remove";assert client.post(url,json={'revision':t['revision'],'catalog_revision':2}).status_code==200
 rows=history(client,t).json()['records'];assert [r['catalog_revision'] for r in rows]==[2,1]
 assert rows[0]['changes_to_next']['removed'][0]['id']==old['cases'][0]['id']
 assert rows[1]['changes_to_next']['added'][0]['id']==new['cases'][1]['id']

def test_legacy_target_missing_is_unknown_and_deleted_current_artifact_does_not_block_history(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);old=capture(client,t,p).json();capture(client,t,p,1)
 row=main.store.get(KIND,t['id'])
 for key in ('environment_id','environment_url','environment_version','app_id'):row['history'][0].pop(key)
 main.store.put(KIND,t['id'],row);main.artifact_path(t).unlink()
 r=history(client,t);assert r.status_code==200,r.text;assert r.json()['records'][0]['target'] is None and r.json()['records'][0]['target_recorded'] is False
 assert history(client,t,1).json()['snapshot']['cases'][0]['input']==old['cases'][0]['input']

def test_history_is_bounded_and_missing_snapshot_is_not_replaced(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);capture(client,t,p);row=main.store.get(KIND,t['id']);prior={k:copy.deepcopy(v) for k,v in row.items() if k!='history'}
 row['catalog_revision']=24;row['history']=[{**copy.deepcopy(prior),'catalog_revision':i} for i in range(1,24)];main.store.put(KIND,t['id'],row)
 r=history(client,t).json();assert len(r['records'])==20 and r['older_history_may_be_missing'] and r['records'][-1]['catalog_revision']==4
 assert history(client,t,3).status_code==404 and history(client,t,24).status_code==404 and history(client,t,4).status_code==200

def test_binding_change_is_reported_without_guessing_which_private_credential_changed(client,monkeypatch):
 t,env,p=uploaded(client,monkeypatch);capture(client,t,p);capture(client,t,p,1);row=main.store.get(KIND,t['id']);row['binding_digest']='a'*64;main.store.put(KIND,t['id'],row)
 r=history(client,t);assert r.status_code==200 and r.json()['records'][0]['changes_to_next']['source_binding_changed'] and 'binding_digest' not in r.text
