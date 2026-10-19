import copy,json
import pytest
from test_api import client,create
from test_assistant_usage_groups import row
from app import main
from app.assistant_usage_groups import summarize

@pytest.mark.parametrize('kind',['mixed','empty','incomplete'])
def test_report_contains_original_read_only_grouping_and_never_promotes_business_or_savings(client,monkeypatch,kind):
 t=create(client);ledger=main.budgets.get(t['id'])
 if kind=='mixed':ledger['entries']=[row('a',charged_usd='1E-18',private_payload='private-row-sentinel'),row('b',status='unknown',charged_usd=None,reserved_usd='0.2',call_status='failed_or_interrupted',usage=None)]
 elif kind=='incomplete':ledger['entries']=[row('a',provider_id=None)]
 main.store.put('task_budget',t['id'],ledger);before=copy.deepcopy(main.get_task(t['id']));old=copy.deepcopy(main.budgets.get(t['id']))
 def forbidden(*args,**kwargs):pytest.fail('报告不能解密或派发模型／Dify请求')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 r=client.get(f"/api/tasks/{t['id']}/report");assert r.status_code==200,r.text
 section=r.text.split('## 助手历史用量分组（非受控质量比较）',1)[1].split('## 轻量建议模型路由',1)[0]
 public=json.loads(section.split('```json\n',1)[1].split('\n```',1)[0]);expected=summarize(ledger)
 assert public['task_id']==t['id'] and public['task_revision']==t['revision'] and public['state']==expected['state'] and public['groups']==expected['groups'] and public['totals']==expected['totals']
 assert public['business_quality_verified'] is False and public['savings_verified'] is False and 'private-row-sentinel' not in section
 assert main.get_task(t['id'])==before and main.budgets.get(t['id'])==old
