from test_api import restore_payload
import copy,json
import httpx
import pytest
from test_api import client,approved
from app import main
from app.conflicts import summary,validate_review,sources

@pytest.fixture(autouse=True)
def forbid_conflict_external_calls(monkeypatch):
 def forbidden(*args, **kwargs):
  pytest.fail('冲突隔离检查不得访问真实 HTTP 或调用真实模型')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)

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


def document_and_reference(client):
 """Real local upload/adoption APIs; the DSL is a fixed, unexecuted fixture."""
 from test_planning import plan
 from app.workflow_plan import compile_workflow_plan
 task=prepared(client)
 document='退款政策：退款期限为 7 天；其他规则保留。'
 response=client.post(f"/api/tasks/{task['id']}/materials",files={'file':('退款政策.md',document.encode('utf-8'),'text/markdown')})
 assert response.status_code==200,response.text
 task=response.json();doc=task['materials'][-1]
 response=client.patch(f"/api/tasks/{task['id']}/materials/{doc['id']}",json={'reference_mode':'borrow'})
 assert response.status_code==200,response.text
 task=response.json();fixture=copy.deepcopy(task)
 fixture['workflow_plan']=plan("def main(query):\n    # 退款期限为 30 天；其他规则保留。\n    return {'result': query}\n")
 dsl=compile_workflow_plan(fixture)[0]
 response=client.post(f"/api/tasks/{task['id']}/reference-dsl/preview",json={'revision':task['revision'],'content':dsl,'filename':'退款参考.yaml'})
 assert response.status_code==200,response.text
 record=response.json()['record']
 assert record['summary']['verification']=='local_structure_only'
 response=client.post(f"/api/tasks/{task['id']}/reference-dsl/adopt",json={'revision':task['revision'],'preview_id':record['id'],'preview_token':record['preview_token'],'reference_mode':'borrow','acknowledge_limits':True})
 assert response.status_code==200,response.text
 task=response.json();reference=task['materials'][-1]
 assert reference['source_kind']=='reference_dsl' and reference['status']=='parsed'
 candidate=review(task)
 candidate['conflicts'][0]['sources']=[
  {'kind':'material','id':doc['id'],'quote':'退款期限为 7 天；其他规则保留。'},
  {'kind':'material','id':reference['id'],'quote':'退款期限为 30 天；其他规则保留。'},
 ]
 candidate['notes']='仅针对本地文档及参考 DSL 摘要中的固定退款规则，不证明完整语义识别或真实运行。'
 return task,candidate,document,dsl


@pytest.mark.parametrize('option_id,days',[('A',7),('B',30)])
def test_at03_document_reference_choice_is_explicit_and_persisted(client,option_id,days):
 from app.storage import Store
 task,candidate,document,dsl=document_and_reference(client)
 original=copy.deepcopy(task)
 response=save(client,task,candidate);assert response.status_code==200,response.text
 task=response.json();state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 assert state['record']['review']==candidate and state['verification']=='source_quote_and_user_decision_only'
 assert task['requirements']==original['requirements'] and not task.get('conflict_decisions')
 assert not task['requirements_confirmed'] and not task['configuration_confirmed']
 before=main.get_task(task['id'])
 assert confirm(client,task).status_code==422
 assert client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':'requirements'}).status_code==422
 for action in ('build','import','run'):
  assert client.post(f"/api/tasks/{task['id']}/{action}",json={'revision':task['revision']}).status_code==422
 assert main.get_task(task['id'])==before
 response=choose(client,task,option_id=option_id);assert response.status_code==200,response.text
 selected=response.json();decision=selected['conflict_decisions'][-1]
 assert decision['conflict']==candidate['conflicts'][0]
 assert decision['selected_option']==candidate['conflicts'][0]['options'][0 if option_id=='A' else 1]
 assert decision['source_revision']==task['revision'] and decision['result_revision']==selected['revision']==task['revision']+1
 assert decision['before']=={'rules':original['requirements']['rules']}
 assert decision['after']=={'rules':f'退款期限为 {days} 天；其他规则保留。'}
 assert selected['requirements']=={**original['requirements'],**decision['after']}
 assert selected['materials']==original['materials'] and selected['app_type']==original['app_type']
 assert not selected['requirements_confirmed'] and not selected['configuration_confirmed'] and not summary(selected)['confirmed']
 assert client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':selected['revision'],'kind':'requirements'}).status_code==422
 assert choose(client,selected,review_token=state['review_token']).status_code==409
 assert client.post(f"/api/tasks/{task['id']}/conflicts/decide",json={'revision':task['revision'],'review_token':state['review_token'],'conflict_id':'C1','option_id':option_id,'acknowledge_review':True,'acknowledge_replacement':True}).status_code==409
 assert confirm(client,selected).status_code==200
 response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':selected['revision'],'kind':'requirements'})
 assert response.status_code==200,response.text
 confirmed=response.json()
 main.store=Store(main.DATA_ROOT)
 persisted=client.get(f"/api/tasks/{task['id']}").json()
 assert persisted==confirmed and summary(persisted)['confirmed'] and persisted['requirements_confirmed']
 assert persisted['conflict_decisions']==[decision]
 folder=main.DATA_ROOT/task['id']/'materials'
 assert (folder/(task['materials'][0]['id']+'.md')).read_text(encoding='utf-8')==document
 assert (folder/(task['materials'][1]['id']+'.yaml')).read_text(encoding='utf-8')==dsl
 report=client.get(f"/api/tasks/{task['id']}/report")
 assert '分歧与用户裁定' in report.text
 assert all(ref['id'] in report.text for ref in candidate['conflicts'][0]['sources'])
 assert not persisted['artifact'] and not persisted['dify_app_id'] and not persisted['runs'] and not persisted.get('workflow_plan')


@pytest.mark.parametrize('invalid_source',['foreign_task','unparsed','fabricated_quote'])
def test_at03_document_reference_sources_must_be_read_and_task_local(client,invalid_source):
 task,candidate,_,_=document_and_reference(client)
 ref=candidate['conflicts'][0]['sources'][1]
 if invalid_source=='foreign_task':
  other,other_candidate,_,_=document_and_reference(client)
  ref['id']=other_candidate['conflicts'][0]['sources'][1]['id']
  assert ref['id']!=task['materials'][1]['id']
 elif invalid_source=='unparsed':
  response=client.post(f"/api/tasks/{task['id']}/materials",files={'file':('未解析.bin',b'not-readable','application/octet-stream')})
  assert response.status_code==200,response.text
  task=response.json();assert task['materials'][-1]['status']=='needs_input'
  ref['id']=task['materials'][-1]['id']
 else:ref['quote']='退款期限为 90 天。'
 before=main.get_task(task['id']);response=save(client,task,candidate)
 assert response.status_code==422 and '引文不是本任务当前资料或已确认历史中的原文' in response.text
 assert main.get_task(task['id'])==before


@pytest.mark.parametrize('change',['document_added','reference_mode'])
def test_at03_material_changes_invalidate_confirmed_resolution(client,change):
 task,candidate,_,_=document_and_reference(client)
 task=save(client,task,candidate).json();task=choose(client,task).json()
 assert confirm(client,task).status_code==200
 response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':'requirements'})
 assert response.status_code==200,response.text
 task=response.json();old_state=client.get(f"/api/tasks/{task['id']}/conflicts").json()
 if change=='document_added':
  response=client.post(f"/api/tasks/{task['id']}/materials",files={'file':('政策补充.md','退款期限重新待定。'.encode('utf-8'),'text/markdown')})
 else:
  response=client.patch(f"/api/tasks/{task['id']}/materials/{task['materials'][1]['id']}",json={'reference_mode':'preserve','preserve_items':'保留退款规则'})
 assert response.status_code==200,response.text
 changed=response.json();before=copy.deepcopy(changed)
 assert changed['revision']==task['revision']+1 and not changed['requirements_confirmed']
 assert summary(changed)['stale'] and not summary(changed)['confirmed']
 assert changed['conflict_decisions']==task['conflict_decisions']
 assert confirm(client,changed).status_code==409
 assert choose(client,changed,review_token=old_state['review_token']).status_code==409
 assert client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':changed['revision'],'kind':'requirements'}).status_code==422
 assert client.post(f"/api/tasks/{task['id']}/build",json={'revision':changed['revision']}).status_code==422
 assert main.get_task(task['id'])==before


def test_at03_model_sees_document_and_reference_but_cannot_choose(client,monkeypatch):
 task,candidate,_,_=document_and_reference(client)
 response=client.post('/api/providers',json={'name':'隔离模型替身','provider':'openai-compatible','base_url':'https://model.invalid/v1','model':'fixture-model','api_key':'fixture-only','pricing':{'input_per_million_usd':1,'output_per_million_usd':1}})
 assert response.status_code==201,response.text
 task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':response.json()['id']}}).json()
 calls=[]
 async def model(*args,**kwargs):
  calls.append(copy.deepcopy(args[2]))
  return json.dumps(candidate,ensure_ascii=False),{'prompt_tokens':50,'completion_tokens':80}
 monkeypatch.setattr(main,'call_model',model)
 response=client.post(f"/api/tasks/{task['id']}/conflicts/generate",json={'revision':task['revision']})
 assert response.status_code==200,response.text
 proposed=response.json();assert len(calls)==1
 prompt=json.loads(calls[0][-1]['content'])
 available={(s['kind'],s['id']):s for s in prompt['sources']}
 for ref in candidate['conflicts'][0]['sources']:
  snippet=available[(ref['kind'],ref['id'])]
  assert ref['quote'] in snippet['text'] and not snippet['excerpt_truncated']
 assert proposed['conflict_review']['source']=='model' and proposed['conflict_review']['review']==candidate
 assert proposed['requirements']==task['requirements'] and proposed['materials']==task['materials']
 assert proposed['app_type']==task['app_type'] and not proposed.get('conflict_decisions')
 assert not proposed['conflict_review']['confirmation'] and not proposed['requirements_confirmed']
 assert not proposed['artifact'] and not proposed['dify_app_id'] and not proposed['runs']
