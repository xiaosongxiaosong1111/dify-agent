import copy,json
from test_api import client
from test_failure_watch import repeated,decide,require
from test_execution_limits import save
from app import main
from app.execution_report import snapshot

def test_delivery_records_limits_and_once_decision_without_exporting_reason_or_input(client):
 task=repeated(client);assert save(client,task,count=5,max_reported_cost_usd='.5').status_code==200
 assert decide(client,task,note='private-decision-reason').status_code==200;require(task)
 before=copy.deepcopy(main.get_task(task['id']));response=client.get(f"/api/tasks/{task['id']}/report");assert response.status_code==200,response.text
 text=response.text;assert '执行停止策略与重复失败决定' in text and 'max_reported_cost_usd' in text and '0.5' in text
 assert 'private-decision-reason' not in text
 value=snapshot(main,task);assert value['repeated_failures'][0]['permission']['status']=='used' and value['decision_audit'][0]['status']=='used'
 assert 'example' not in json.dumps(value) and 'evidence_token' not in json.dumps(value)
 assert main.get_task(task['id'])==before

def test_old_tasks_export_empty_policy_without_creating_state(client):
 from test_dsl_roundtrip import prepared
 task,_=prepared(client);before=copy.deepcopy(task);value=snapshot(main,task)
 assert value['decision_count']==0 and value['policy']['policy_revision']==0 and not value['repeated_failures']
 assert not main.store.list('failure_decision') and not main.store.list('execution_limits') and main.get_task(task['id'])==before

def test_large_decision_audit_is_explicitly_bounded_without_reason_values(client):
 task=repeated(client)
 for i in range(501):main.store.put('failure_decision',str(i),{'id':str(i),'task_id':task['id'],'revision':task['revision'],'action':'change_plan','status':'paused','note':'private-note','created_at':main.now(),'evidence_token':'a'*64})
 value=snapshot(main,task);assert value['decision_count']==501 and value['audit_truncated'] and len(value['decision_audit'])==500
 assert 'private-note' not in json.dumps(value)
