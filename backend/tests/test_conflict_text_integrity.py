"""Lone surrogates in conflict reviews are refused before any task mutation."""
import copy,json

import httpx
import pytest

from test_api import client
from test_conflicts import choose,prepared,review
from app import main
from app.conflicts import summary,validate_review


@pytest.fixture(autouse=True)
def forbid_conflict_external_calls(monkeypatch):
 def forbidden(*args,**kwargs):
  pytest.fail('冲突隔离检查不得访问真实 HTTP 或调用真实模型')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)

BAD=[('high',chr(0xd800)),('low',chr(0xdfff))]
FIELDS=['notes','title','question','recommendation_reason','option_label','option_experience','option_cost','option_manual_work','patch_rules']


def taint(candidate,field,char):
 row=candidate['conflicts'][0]
 if field=='notes':candidate['notes']+=char
 elif field=='patch_rules':row['options'][0]['requirements_patch']['rules']+=char
 elif field.startswith('option_'):row['options'][0][field[7:]]+=char
 else:row[field]+=char


def save_raw(client,task,candidate):
 payload={'revision':task['revision'],'review':candidate}
 return client.post(f"/api/tasks/{task['id']}/conflicts",content=json.dumps(payload,ensure_ascii=True),headers={'Content-Type':'application/json'})


@pytest.mark.parametrize('char',[value for _,value in BAD],ids=[name for name,_ in BAD])
@pytest.mark.parametrize('field',FIELDS)
def test_lone_surrogate_is_rejected_before_save_and_task_is_unchanged(client,field,char):
 task=prepared(client)
 task['artifact']={'fixture':'未被覆盖的旧成果'}
 task.setdefault('confirmations',[]).append({'kind':'requirements','revision':task['revision'],'created_at':'fixture'})
 main.save_task(task)
 before=copy.deepcopy(main.get_task(task['id']))
 budget=copy.deepcopy(main.budgets.get(task['id']))
 candidate=review(task);taint(candidate,field,char)
 checked=validate_review(task,candidate)
 assert checked['valid'] is False and len(checked['errors'])==1
 assert '孤立代理字符' in checked['errors'][0] and char not in checked['errors'][0]
 response=save_raw(client,task,candidate)
 assert response.status_code==422,response.text
 assert '孤立代理字符' in response.text and char not in response.text
 assert main.get_task(task['id'])==before
 assert main.budgets.get(task['id'])==budget
 assert not summary(main.get_task(task['id']))['enabled']


def test_valid_unicode_is_stored_verbatim_and_decision_continues(client):
 task=prepared(client)
 candidate=review(task)
 emoji=chr(0x1F600);combining='e'+chr(0x301)
 note=f'合法中文与表情 {emoji}，组合字符 {combining}；不做归一化。'
 title=f'退款期限分歧 {emoji} {combining}'
 candidate['notes']=note
 candidate['conflicts'][0]['title']=title
 candidate['conflicts'][0]['recommendation_reason']=f'请用户核对 {emoji}'
 candidate['conflicts'][0]['options'][0]['label']=f'保留 7 天 {emoji}'
 assert validate_review(task,candidate)['valid'] is True
 response=save_raw(client,task,candidate)
 assert response.status_code==200,response.text
 saved=response.json();stored=saved['conflict_review']['review']
 assert stored==candidate and stored['notes']==note and stored['conflicts'][0]['title']==title
 assert stored['conflicts'][0]['options'][0]['label']==candidate['conflicts'][0]['options'][0]['label']
 reloaded=client.get(f"/api/tasks/{task['id']}").json()
 assert reloaded['conflict_review']['review']==candidate
 chosen=choose(client,saved)
 assert chosen.status_code==200,chosen.text
 updated=chosen.json();decision=updated['conflict_decisions'][-1]
 assert decision['conflict']==candidate['conflicts'][0]
 assert decision['conflict']['sources']==candidate['conflicts'][0]['sources']
 assert updated['requirements']['rules']==candidate['conflicts'][0]['options'][1]['requirements_patch']['rules']
