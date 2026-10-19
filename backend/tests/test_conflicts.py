from test_api import restore_payload
import copy,json
import pytest
from test_api import client,approved
from app import main
from app.conflicts import summary,validate_review,sources

def prepared(client):
 task=approved(client)
 task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':'退款期限为 7 天；其他规则保留。','knowledge':'资料说退款期限为 30 天。'}}).json()
 return task

def review(task,count=1):
 rows=[]
 for i in range(count):
  rows.append({'id':'C'+str(i+1),'title':'退款期限分歧','sources':[{'kind':'requirement','id':'rules','quote':task['requirements']['rules']},{'kind':'requirement','id':'knowledge','quote':task['requirements']['knowledge']}],'question':'本次按什么规则处理退款？','recommended_option_id':'A','recommendation_reason':'请用户决定，不自动判真。','options':[{'id':'A','label':'保留 7 天规则','requirements_patch':{'rules':'退款期限为 7 天；其他规则保留。'},'experience':'采用 7 天窗口','cost':'无','manual_work':'需要核对资料'}, {'id':'B','label':'采用 30 天规则','requirements_patch':{'rules':'退款期限为 30 天；其他规则保留。'},'experience':'延长期限','cost':'可能增加退款成本，待核对','manual_work':'需更新资料'}]})
 return {'schema_version':1,'conflicts':rows,'notes':'仅检查提供的技术样例，不证明事实正确。'}

def save(client,task,value):
 return client.post(f"/api/tasks/{task['id']}/conflicts",json={'revision':task['revision'],'review':value})

def choose(client,task,**patch):
 state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 return client.post(f"/api/tasks/{task['id']}/conflicts/decide",json={'revision':task['revision'],'review_token':state['review_token'],'conflict_id':'C1','option_id':'B','acknowledge_review':True,'acknowledge_replacement':True,**patch})

def confirm(client,task,**patch):
 state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 return client.post(f"/api/tasks/{task['id']}/conflicts/confirm",json={'revision':task['revision'],'review_token':state['review_token'],'acknowledge_review':True,**patch})

def test_unresolved_conflicts_block_requirement_confirmation(client):
 task=prepared(client);value=save(client,task,review(task)).json()
 assert not value['requirements_confirmed'] and not value['configuration_confirmed'] and value['revision']==task['revision']+1
 assert confirm(client,value).status_code==422
 assert client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':value['revision'],'kind':'requirements'}).status_code==422
 for action in ('build','import','run'):assert client.post(f"/api/tasks/{task['id']}/{action}",json={'revision':value['revision']}).status_code==422

def test_explicit_choice_writes_exact_requirement_and_preserves_history(client):
 task=prepared(client);task['workflow_plan']={'schema_version':1,'nodes':[],'edges':[]};main.save_task(task)
 value=save(client,task,review(task)).json();response=choose(client,value);assert response.status_code==200,response.text
 updated=response.json();assert updated['requirements']['rules']=='退款期限为 30 天；其他规则保留。' and updated['plan_stale']
 assert not updated['requirements_confirmed'] and not updated['configuration_confirmed'] and not updated['artifact']
 decision=updated['conflict_decisions'][-1];assert decision['before']['rules']==task['requirements']['rules'] and decision['after']['rules']==updated['requirements']['rules']
 assert not summary(updated)['confirmed'] and confirm(client,updated).status_code==200
 assert client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':updated['revision'],'kind':'requirements'}).status_code==200
 report=client.get(f"/api/tasks/{task['id']}/report");assert '分歧与用户裁定' in report.text

@pytest.mark.parametrize('patch',[{'acknowledge_review':False},{'acknowledge_replacement':False},{'option_id':'invented'},{'review_token':'old'},{'revision':True},{'extra':'not-allowed'}])
def test_choice_requires_current_explicit_acknowledgements(client,patch):
 task=prepared(client);value=save(client,task,review(task)).json();response=choose(client,value,**patch);assert response.status_code in (409,422)
 assert main.get_task(task['id'])['requirements']['rules']==task['requirements']['rules']

@pytest.mark.parametrize('mutate',[
 lambda r:r['conflicts'][0]['sources'][0].update(quote='伪造来源'),
 lambda r:r['conflicts'][0]['sources'][0].update(kind='material',id='another-task'),
 lambda r:r['conflicts'][0].update(sources=[r['conflicts'][0]['sources'][0]]*2),
 lambda r:r['conflicts'][0].update(sources=[None,None]),
 lambda r:r['conflicts'][0].update(recommended_option_id='other'),
 lambda r:r['conflicts'][0]['options'][0].update(requirements_patch={'app_type':'agent'}),
 lambda r:r['conflicts'][0]['options'][0].update(requirements_patch={}),
 lambda r:r['conflicts'][0]['options'][0].update(cost=''),
 lambda r:r['conflicts'][0]['options'][1].update(id='A'),
 lambda r:r['conflicts'][0].update(options='bad'),
 lambda r:r['conflicts'][0].update(id=[]),
 lambda r:r.update(schema_version=True),
 lambda r:r.update(notes=''),
])
def test_invalid_or_fabricated_sources_options_and_impacts_are_rejected(client,mutate):
 task=prepared(client);candidate=review(task);mutate(candidate)
 assert save(client,task,candidate).status_code==422
 assert main.get_task(task['id'])['revision']==task['revision']

def test_cannot_silently_drop_unresolved_conflict(client):
 task=prepared(client);value=save(client,task,review(task,2)).json();candidate=review(task)
 assert save(client,value,candidate).status_code==422

def test_other_conflicts_need_recheck_after_changing_rule(client):
 task=prepared(client);value=save(client,task,review(task,2)).json();updated=choose(client,value).json()
 assert summary(updated)['stale'] and len(updated['conflict_review']['review']['conflicts'])==1
 assert choose(client,updated,conflict_id='C2').status_code==409
 refreshed=review(updated);refreshed['conflicts'][0]['id']='C2'
 assert save(client,updated,refreshed).status_code==200

def test_source_changes_and_restore_do_not_revive_old_confirmation(client):
 task=prepared(client);value=save(client,task,review(task,0)).json();assert confirm(client,value).status_code==200
 changed=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':'新规则'}}).json();assert summary(changed)['stale']
 reverted=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'rules':task['requirements']['rules']}}).json();assert not summary(reverted)['confirmed']
 historical=next(v for v in reverted['versions'] if v.get('conflict_review') and v['conflict_review'].get('confirmation'))
 restored=client.post(f"/api/tasks/{task['id']}/restore",json=restore_payload(client, task['id'], historical['id'])).json();assert restored['conflict_enabled'] and not summary(restored)['confirmed']

def test_metadata_only_revision_does_not_create_review_loop(client):
 task=prepared(client);value=save(client,task,review(task,0)).json();assert confirm(client,value).status_code==200
 changed=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'temperature':.3}}).json();assert summary(changed)['confirmed'] and not summary(changed)['stale']

def test_confirmed_history_source_is_real_and_task_local(client):
 task=approved(client);assert sources(task)
 version=task['versions'][-1]
 # Only versions whose revision has a matching requirement confirmation count.
 text=version['requirements']['rules'];found=('version',version['id']+':rules') in sources(task)
 assert found==any(c.get('kind')=='requirements' and c.get('revision')==version['revision'] for c in task.get('confirmations',[]))
 task['versions'].append({'id':'fake-version','revision':999,'requirements':{'rules':'未确认草稿'}})
 assert ('version','fake-version:rules') not in sources(task)

def test_conflict_and_coverage_confirmations_can_both_reach_build(client):
 from test_coverage import items
 task=prepared(client);value=save(client,task,review(task,0)).json();assert confirm(client,value).status_code==200
 value=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':value['revision'],'kind':'requirements'}).json()
 response=client.post(f"/api/tasks/{task['id']}/coverage",json={'revision':value['revision'],'items':items(value)});assert response.status_code==200,response.text
 value=response.json();assert summary(value)['confirmed']
 state=client.get(f"/api/tasks/{task['id']}/coverage").json();assert client.post(f"/api/tasks/{task['id']}/coverage/confirm",json={'revision':value['revision'],'review_token':state['review_token'],'acknowledge_review':True,'acknowledge_exclusions':False}).status_code==200
 assert client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':value['revision'],'kind':'configuration'}).status_code==200
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':value['revision']});assert response.status_code==200,response.text

@pytest.mark.parametrize('response_kind',['valid','omitted','missing_price','paused'])
def test_bounded_model_proposals_do_not_decide_or_apply_business_rules(client,monkeypatch,response_kind):
 task=prepared(client)
 if response_kind=='omitted':task=save(client,task,review(task)).json()
 provider={'name':'mock','provider':'openai-compatible','base_url':'https://api.deepseek.com','model':'model','api_key':'test-key'}
 if response_kind!='missing_price':provider['pricing']={'input_per_million_usd':1,'output_per_million_usd':1}
 p=client.post('/api/providers',json=provider).json();task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json();calls=[]
 async def model(*args,**kwargs):
  calls.append(args[2])
  if response_kind=='paused':main.pause(task['id'])
  return json.dumps(review(task,0 if response_kind=='omitted' else 1)),{'prompt_tokens':50,'completion_tokens':80}
 monkeypatch.setattr(main,'call_model',model)
 response=client.post(f"/api/tasks/{task['id']}/conflicts/generate",json={'revision':task['revision']})
 current=main.get_task(task['id']);assert current['requirements']['rules']==task['requirements']['rules'] and not current.get('conflict_decisions')
 if response_kind=='valid':assert response.status_code==200 and current['conflict_review']['source']=='model' and not current['conflict_review']['confirmation']
 else:
  assert response.status_code==422 and current['status']=='paused'
  assert current['planning_runs'][-1]['stop_reason']=={'omitted':'needs_decision','missing_price':'pricing_unknown','paused':'user_pause'}[response_kind]
 if response_kind=='missing_price':assert not calls
 else:assert len(calls)==1
