"""Regression from the approved public 0.240 interview; no live supplier calls."""
import copy,json
from pathlib import Path
import pytest
from test_api import client
from test_task_budget import provider
from app import main
from app.intake import ReviewContractError,model_review_outline,topics,validate_review

FIXTURE=Path(__file__).parent/'fixtures/after_sales_intake_240.json'

def recorded():return json.loads(FIXTURE.read_text('utf-8'))

def test_recorded_extra_topics_are_rejected_with_actionable_safe_reason():
 f=recorded();t=f['task'];v=f['response']['intake_review']
 assert len(topics(t))==11 and len(v['checks'])==14
 with pytest.raises(ReviewContractError,match='当前标准为 11 项'):
  validate_review(t,v,evidence_task=t)

def test_outline_uses_exact_topic_and_material_identifiers_only():
 t=recorded()['task'];t['materials'][0]['unused_sensitive_field']='must-not-enter-outline'
 outline=model_review_outline(t)
 assert outline['required_check_topics']==[r['id'] for r in topics(t)]
 assert outline['material_sources']==[{'id':m['id'],'name':m['name']} for m in t['materials']]
 assert 'must-not-enter-outline' not in json.dumps(outline)
 assert 'materials' not in outline['required_check_topics'] and 'human_input' not in outline['required_check_topics']

def test_extra_topics_are_not_silently_discarded_and_bad_sources_still_fail():
 f=recorded();t=f['task'];v=copy.deepcopy(f['response']['intake_review'])
 v['checks']=[r for r in v['checks'] if r['topic'] in {t['id'] for t in topics(t)}]
 # Removing extras cannot make the inconsistent completed/questions pair valid.
 with pytest.raises(ReviewContractError,match='已齐全时不能仍有待答问题'):
  validate_review(t,v,evidence_task=t)
 v['questions']=[]
 v['checks'][0]['evidence']=[{'kind':'material','id':t['materials'][0]['name'],'quote':t['materials'][0]['text'][:20]}]
 with pytest.raises(ReviewContractError,match='来源引文不存在'):
  validate_review(t,v,evidence_task=t)

def test_failed_live_response_replay_reports_reason_and_never_applies_or_retries(client,monkeypatch):
 f=recorded();t=client.post('/api/tasks',json={'name':'公开访谈回归','app_type':'workflow'}).json()
 p=provider(client)
 t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':f['task']['requirements'],'configuration':{'assistant_provider_id':p['id']}}).json()
 t['materials']=f['task']['materials'];main.save_task(t)
 before=copy.deepcopy(main.get_task(t['id']));calls=[]
 async def model(*args,**kwargs):
  context=json.loads(args[2][1]['content'].split('当前任务资料：',1)[1])
  assert context['intake_response_outline']['required_check_topics']==[r['id'] for r in topics(before)]
  calls.append(1)
  return json.dumps(f['response'],ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
 monkeypatch.setattr(main,'call_model',model)
 r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'按既定公开合成需求核对。'})
 assert r.status_code==200,r.text
 result=r.json();assert calls==[1]
 assert result['requirements']==before['requirements'] and result['revision']==before['revision']
 assert not result['requirements_confirmed'] and result.get('intake_review') is None
 note=result['messages'][-1]['content'];assert '当前标准为 11 项' in note and '未自动重试' in note
 assert result['interview_attempts'][-1]['applied'] is False
 operation=client.get(f"/api/tasks/{t['id']}/interviews").json()['operations'][0]
 assert operation['status']=='failed' and operation['note']==note and operation['applied'] is False
 ledger=client.get(f"/api/tasks/{t['id']}/budget").json()
 assert len(ledger['entries'])==1 and ledger['entries'][0]['status']=='settled'

def test_diagnostic_never_reflects_unknown_model_authored_topic(client,monkeypatch):
 f=recorded();t=client.post('/api/tasks',json={'name':'未知主题脱敏','app_type':'workflow'}).json();provider(client)
 t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':f['task']['requirements']}).json()
 response=f['response'];response['intake_review']['checks'][0]['topic']='sk-must-not-appear-in-diagnostic'
 async def model(*a,**kw):return json.dumps(response),{'prompt_tokens':10,'completion_tokens':10}
 monkeypatch.setattr(main,'call_model',model)
 result=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'核对公开规则'}).json()
 assert 'sk-must-not-appear-in-diagnostic' not in result['messages'][-1]['content']
 assert '当前标准为 11 项' in result['messages'][-1]['content']
