import copy,uuid
import pytest
from fastapi import HTTPException
from test_api import client,approved,create_env
from test_resource_progress import row,put
from app import main

def section(text):return text.split('## 独立资源与原目标待办',1)[1].split('## 助手模型累计预算',1)[0]

def test_delivery_contains_original_resource_metadata_and_pending_not_fake_import_or_clearance(client,monkeypatch):
 env=create_env(client);t=approved(client,env_id=env['id']);put('human_runtime_run',row(t,env,'waiting_human'));put('schedule_publication',row(t,env,'stop_not_confirmed'));put('schedule_enable',row(t,env,'enabled'));before=copy.deepcopy(main.get_task(t['id']))
 async def forbidden(*args,**kw):pytest.fail('交付快照不能请求模型或Dify')
 monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.store,'secret',lambda *a,**kw:pytest.fail('本分区不解密凭据'))
 response=client.get(f"/api/tasks/{t['id']}/report");assert response.status_code==200,response.text;part=section(response.text)
 assert 'waiting_human' in part and 'stop_not_confirmed' in part and 'enabled' in part and '原App／Run／Form' in part
 assert 'PRIVATE-' not in part and '"handoff_clearance_verified": false' in part and '"business_verified": false' in part
 assert '尚无匹配的真实导入记录' in response.text and main.get_task(t['id'])==before

def test_empty_resource_index_still_no_platform_clearance_or_business_pass(client):
 t=approved(client);response=client.get(f"/api/tasks/{t['id']}/report");assert response.status_code==200
 part=section(response.text);assert '"total": 0' in part and '"platform_checked": false' in part and '"handoff_clearance_verified": false' in part

def test_old_targets_and_truncated_history_in_export_are_explicit(client):
 env=create_env(client);t=approved(client,env_id=env['id'])
 for i in range(30):put('human_runtime_run',row(t,env,'unknown',revision=t['revision']-1))
 env['base_url']='http://127.0.0.1:8082';main.store.put('environment',env['id'],env)
 part=section(client.get(f"/api/tasks/{t['id']}/report").text)
 assert '"history_truncated": true' in part and '最近25条' in part and '"total": 30' in part and '旧App ID' in part
 assert 'https://dify.example' in part and 'http://127.0.0.1:8082' not in part and 'PRIVATE-' not in part

def test_index_failure_explicit_not_silent_omission_or_empty_clearance(client,monkeypatch):
 t=approved(client)
 def fail(*a,**kw):raise HTTPException(503,'PRIVATE-INTERNAL-DETAIL')
 monkeypatch.setattr(main.resource_progress,'snapshot',fail)
 response=client.get(f"/api/tasks/{t['id']}/report");assert response.status_code==200
 part=section(response.text);assert 'local_index_unavailable' in part and '"records": null' in part and '不能用缺失或空列表' in part and 'PRIVATE-' not in part

def test_report_does_not_mix_new_task_revision_with_old_header(client,monkeypatch):
 t=approved(client);original=main.resource_progress.snapshot
 def changed(item_id,*a,**kw):
  task=main.get_task(item_id);task['revision']+=1;main.store.put('task',item_id,task);return original(item_id,*a,**kw)
 monkeypatch.setattr(main.resource_progress,'snapshot',changed)
 response=client.get(f"/api/tasks/{t['id']}/report");assert response.status_code==409 and '当前版本' in response.text

def test_snapshot_rejects_boolean_limit_without_any_platform_lookup(client):
 t=approved(client)
 with pytest.raises(HTTPException) as exc:main.resource_progress.snapshot(t['id'],True)
 assert exc.value.status_code==422
