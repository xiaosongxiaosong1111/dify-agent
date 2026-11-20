"""Explicit retirement of a conflict whose material source was removed."""
import copy,json

import httpx
import pytest
from fastapi.testclient import TestClient

from test_api import approved,client,restore_payload
from app import main
from app.conflicts import summary


@pytest.fixture(autouse=True)
def forbid_dismissal_external_calls(monkeypatch):
 def forbidden(*args,**kwargs):
  pytest.fail('失效冲突撤销检查不得访问真实 HTTP 或调用真实模型')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)


RULES='退款期限为 7 天；其他规则保留。'
POLICY='退款政策：退款期限为 30 天；其他规则保留。'
POLICY_QUOTE='退款期限为 30 天；其他规则保留。'
REASON='资料已移除，我已复核其余现行来源并明确撤销这一失效条目。'


def prepared(client):
 task=approved(client)
 response=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':RULES}})
 assert response.status_code==200,response.text
 task=response.json()
 response=client.post(f"/api/tasks/{task['id']}/materials",files={'file':('policy.md',POLICY.encode('utf-8'),'text/markdown')})
 assert response.status_code==200,response.text
 task=response.json();material=task['materials'][-1]
 assert material['status']=='parsed' and material['text']==POLICY
 response=client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",json={'revision':task['revision'],'reference_mode':'borrow'})
 assert response.status_code==200,response.text
 return response.json(),material


def row(conflict_id,sources):
 return {'id':conflict_id,'title':'退款期限分歧','sources':sources,'question':'本次按什么规则处理退款？','recommended_option_id':'A','recommendation_reason':'请用户决定，不自动判真。','options':[
  {'id':'A','label':'保留 7 天规则','requirements_patch':{'rules':RULES},'experience':'采用 7 天窗口','cost':'无','manual_work':'需要核对资料'},
  {'id':'B','label':'采用 30 天规则','requirements_patch':{'rules':'退款期限为 30 天；其他规则保留。'},'experience':'延长期限','cost':'待核对','manual_work':'需更新资料'}]}


def review(task,material,count=1):
 sources=[{'kind':'requirement','id':'rules','quote':task['requirements']['rules']},{'kind':'material','id':material['id'],'quote':POLICY_QUOTE}]
 return {'schema_version':1,'conflicts':[row(f'C{i+1}',copy.deepcopy(sources)) for i in range(count)],'notes':'只核对本次给出资料的固定退款规则，事实由用户处理。'}


def save(client,task,value):
 return client.post(f"/api/tasks/{task['id']}/conflicts",json={'revision':task['revision'],'review':value})


def dismiss(client,task,**patch):
 body=dismiss_body(client,task,**patch)
 return client.post(f"/api/tasks/{task['id']}/conflicts/dismiss",json=body)


def dismiss_body(client,task,**patch):
 state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 body={'revision':task['revision'],'review_token':state['review_token'],'conflict_id':'C1','reason':REASON,'acknowledge_review':True,'acknowledge_dismissal':True}
 body.update(patch)
 return body


def remove(client,task,material):
 response=client.delete(f"/api/tasks/{task['id']}/materials/{material['id']}",params={'revision':task['revision']})
 assert response.status_code==200,response.text
 return response.json()


def test_removed_material_conflict_can_be_dismissed_then_current_scope_reconfirmed(client):
 task,material=prepared(client);candidate=review(task,material)
 response=save(client,task,candidate);assert response.status_code==200,response.text
 saved=response.json()
 requirements=copy.deepcopy(saved['requirements'])
 confirmations=copy.deepcopy(saved['confirmations']);budget=copy.deepcopy(main.budgets.get(task['id']))
 before=copy.deepcopy(main.get_task(task['id']))
 assert client.get(f"/api/tasks/{task['id']}/conflicts").json()['dismissal_candidates']==[]
 assert dismiss(client,saved).status_code==422
 assert main.get_task(task['id'])==before

 changed=remove(client,saved,material);assert changed['revision']==saved['revision']+1
 materials=copy.deepcopy(changed['materials'])
 state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 assert state['stale'] is True and state['confirmed'] is False
 assert state['dismissal_candidates']==[{'conflict_id':'C1','missing_material_ids':[material['id']]}]
 # Normal stale decisions remain blocked; only the explicit removal dismissal is allowed.
 assert client.post(f"/api/tasks/{task['id']}/conflicts/decide",json={'revision':changed['revision'],'review_token':state['review_token'],'conflict_id':'C1','option_id':'A','acknowledge_review':True,'acknowledge_replacement':True}).status_code==409

 response=dismiss(client,changed);assert response.status_code==200,response.text
 updated=response.json();dismissal=updated['conflict_dismissals'][-1]
 assert dismissal['conflict']==candidate['conflicts'][0]
 assert dismissal['reason']==REASON and dismissal['missing_material_ids']==[material['id']]
 assert dismissal['source_revision']==changed['revision'] and dismissal['result_revision']==updated['revision']==changed['revision']+1
 assert updated['requirements']==requirements and updated['materials']==materials
 assert updated['confirmations']==confirmations and main.budgets.get(task['id'])==budget
 assert updated['conflict_review']['source']=='explicit_source_dismissal'
 assert updated['conflict_review']['review']['conflicts']==[] and updated['conflict_review']['confirmation']=={}
 assert '来源资料已被移除' in updated['conflict_review']['review']['notes']
 assert '未判定相关事实为假' in updated['conflict_review']['review']['notes']
 assert not updated['requirements_confirmed'] and not updated['configuration_confirmed']
 assert not updated.get('conflict_decisions')
 assert updated['versions'][-1]['conflict_review']['review']['conflicts'][0]['id']=='C1'

 current=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 assert current['dismissals']==[dismissal] and current['dismissal_candidates']==[]
 assert current['stale'] is False and current['confirmed'] is False
 assert dismiss(client,updated).status_code==422
 assert client.post(f"/api/tasks/{task['id']}/conflicts/confirm",json={'revision':updated['revision'],'review_token':current['review_token'],'acknowledge_review':True}).status_code==200
 response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':updated['revision'],'kind':'requirements'})
 assert response.status_code==200,response.text
 assert summary(response.json())['confirmed'] and not response.json().get('conflict_decisions')


def test_missing_one_of_two_material_sources_is_eligible(client):
 task,material=prepared(client)
 second='退款说明：退款期限为 45 天；其他规则保留。'
 response=client.post(f"/api/tasks/{task['id']}/materials",files={'file':('policy2.md',second.encode('utf-8'),'text/markdown')})
 assert response.status_code==200,response.text
 task=response.json();material2=task['materials'][-1]
 sources=[{'kind':'requirement','id':'rules','quote':task['requirements']['rules']},
          {'kind':'material','id':material['id'],'quote':POLICY_QUOTE},
          {'kind':'material','id':material2['id'],'quote':'退款期限为 45 天；其他规则保留。'}]
 candidate={'schema_version':1,'conflicts':[row('C1',sources)],'notes':'固定资料中的期限差异，不按上传顺序判真。'}
 response=save(client,task,candidate);assert response.status_code==200,response.text
 changed=remove(client,response.json(),material)
 state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 assert state['dismissal_candidates']==[{'conflict_id':'C1','missing_material_ids':[material['id']]}]
 response=dismiss(client,changed);assert response.status_code==200,response.text
 assert response.json()['conflict_dismissals'][-1]['missing_material_ids']==[material['id']]


def test_dismissing_one_of_two_conflicts_keeps_remaining_stale_and_blocked(client):
 task,material=prepared(client)
 value=save(client,task,review(task,material,2)).json()
 changed=remove(client,value,material)
 state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 assert {item['conflict_id'] for item in state['dismissal_candidates']}=={'C1','C2'}
 response=dismiss(client,changed,conflict_id='C1');assert response.status_code==200,response.text
 updated=response.json()
 assert [r['id'] for r in updated['conflict_review']['review']['conflicts']]==['C2']
 assert updated['conflict_review']['context_digest']==state['record']['context_digest']
 current=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 assert current['stale'] is True and current['confirmed'] is False and current['blockers']
 assert current['dismissal_candidates']==[{'conflict_id':'C2','missing_material_ids':[material['id']]}]
 response=client.post(f"/api/tasks/{task['id']}/conflicts/confirm",json={'revision':updated['revision'],'review_token':current['review_token'],'acknowledge_review':True})
 assert response.status_code==409


@pytest.mark.parametrize('change',['active','mode_only','requirement_change'])
def test_only_removed_material_ids_are_eligible(client,change):
 task,material=prepared(client)
 value=save(client,task,review(task,material)).json()
 if change=='mode_only':
  response=client.patch(f"/api/tasks/{task['id']}/materials/{material['id']}",json={'revision':value['revision'],'reference_mode':'preserve','preserve_items':'保留退款规则'})
  assert response.status_code==200,response.text;changed=response.json();assert summary(changed)['stale']
 elif change=='requirement_change':
  response=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':'退款期限为 90 天；其他规则保留。'}})
  assert response.status_code==200,response.text;changed=response.json();assert summary(changed)['stale']
 else:changed=value
 before=copy.deepcopy(main.get_task(task['id']))
 assert summary(main.get_task(task['id']))['dismissal_candidates']==[]
 assert dismiss(client,changed).status_code==422
 assert main.get_task(task['id'])==before


@pytest.mark.parametrize('patch,status',[
 ({'conflict_id':'C9'},422),
 ({'review_token':'old'},409),
 ({'revision':1},409),
 ({'acknowledge_review':False},422),
 ({'acknowledge_dismissal':False},422),
 ({'acknowledge_review':1},422),
 ({'reason':''},422),
 ({'reason':'   '},422),
 ({'reason':'示'*3001},422),
 ({'extra':'not-allowed'},422),
])
def test_invalid_dismissals_do_not_mutate(client,patch,status):
 task,material=prepared(client)
 value=save(client,task,review(task,material)).json()
 changed=remove(client,value,material)
 before=copy.deepcopy(main.get_task(task['id']));budget=copy.deepcopy(main.budgets.get(task['id']))
 response=dismiss(client,changed,**patch)
 assert response.status_code==status,response.text
 assert main.get_task(task['id'])==before and main.budgets.get(task['id'])==budget


def test_lone_surrogate_reason_is_rejected_without_mutation(client):
 task,material=prepared(client)
 value=save(client,task,review(task,material)).json()
 changed=remove(client,value,material)
 state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 before=copy.deepcopy(main.get_task(task['id']))
 payload={'revision':changed['revision'],'review_token':state['review_token'],'conflict_id':'C1','reason':chr(0xd800),'acknowledge_review':True,'acknowledge_dismissal':True}
 response=client.post(f"/api/tasks/{task['id']}/conflicts/dismiss",content=json.dumps(payload,ensure_ascii=True),headers={'Content-Type':'application/json'})
 assert response.status_code==422,response.text
 assert '孤立代理字符' in response.text and chr(0xd800) not in response.text
 assert main.get_task(task['id'])==before


def eligible_removed_source(client):
 task,material=prepared(client)
 value=save(client,task,review(task,material)).json()
 return remove(client,value,material)


@pytest.mark.parametrize('patch',[
 {'reason':[chr(0xd800)]},
 {'reason':{'bad':chr(0xd800)}},
 {'extra':chr(0xd800)},
],ids=['reason_list','reason_dict','extra'])
def test_bad_text_anywhere_is_controlled_422_before_task_lookup(client,patch):
 changed=eligible_removed_source(client);task_id=changed['id']
 body=dismiss_body(client,changed,**patch)
 before=copy.deepcopy(main.get_task(task_id));budget=copy.deepcopy(main.budgets.get(task_id))
 with TestClient(main.app,raise_server_exceptions=False) as safe:
  response=safe.post(f"/api/tasks/{task_id}/conflicts/dismiss",content=json.dumps(body,ensure_ascii=True),headers={'Content-Type':'application/json'})
 assert response.status_code==422,response.text
 assert '孤立代理字符' in response.text
 assert chr(0xd800) not in response.text and 'ud800' not in response.text.lower()
 assert main.get_task(task_id)==before and main.budgets.get(task_id)==budget


def test_nonfinite_payload_is_controlled_422_before_task_lookup(client):
 changed=eligible_removed_source(client);task_id=changed['id']
 body=dismiss_body(client,changed,extra=float('nan'))
 before=copy.deepcopy(main.get_task(task_id));budget=copy.deepcopy(main.budgets.get(task_id))
 with TestClient(main.app,raise_server_exceptions=False) as safe:
  response=safe.post(f"/api/tasks/{task_id}/conflicts/dismiss",content=json.dumps(body,ensure_ascii=True),headers={'Content-Type':'application/json'})
 assert response.status_code==422,response.text
 assert '数值或结构' in response.text and 'NaN' not in response.text
 assert main.get_task(task_id)==before and main.budgets.get(task_id)==budget


def test_dismissal_history_survives_save_restore_and_store_reopen(client):
 from app.storage import Store
 task,material=prepared(client)
 value=save(client,task,review(task,material)).json()
 changed=remove(client,value,material)
 updated=dismiss(client,changed).json()
 audit=copy.deepcopy(updated['conflict_dismissals'])
 empty={'schema_version':1,'conflicts':[],'notes':'资料移除并撤销失效条目后，重新检查当前范围。'}
 response=client.post(f"/api/tasks/{task['id']}/conflicts",json={'revision':updated['revision'],'review':empty})
 assert response.status_code==200,response.text
 saved=response.json()
 assert saved['conflict_dismissals']==audit and saved['conflict_review']['review']==empty

 main.store=Store(main.DATA_ROOT)
 persisted=client.get(f"/api/tasks/{task['id']}").json()
 assert persisted['conflict_dismissals']==audit
 assert client.get(f"/api/tasks/{task['id']}/conflicts").json()['dismissals']==audit

 version_id=updated['versions'][-1]['id']
 response=client.post(f"/api/tasks/{task['id']}/restore",json=restore_payload(client,task['id'],version_id))
 assert response.status_code==200,response.text
 restored=response.json()
 assert restored['conflict_dismissals']==audit
 assert [r['id'] for r in restored['conflict_review']['review']['conflicts']]==['C1']
 assert summary(restored)['dismissal_candidates']==[{'conflict_id':'C1','missing_material_ids':[material['id']]}]
