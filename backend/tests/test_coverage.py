from test_api import restore_payload
import copy,json
import pytest
from test_api import client,approved,create_env
from app import main
from app.coverage import validate_items,summary,evidence,digest

def items(task,status='planned'):
 return [{'id':'R_'+field,'requirement':text,'source':{'kind':'requirement','id':field,'quote':text},'status':status,'evidence_ids':['config:dify_model'] if status=='planned' else [],'case_ids':[],'explanation':'配置已明确，仍需运行核对；这里只是技术清单。','impact':'无','cost':'无','manual_work':'无'} for field,text in task['requirements'].items()]

def save(client,task,rows):
 return client.post(f"/api/tasks/{task['id']}/coverage",json={'revision':task['revision'],'items':rows})

def confirm(client,task,**patch):
 state=client.get(f"/api/tasks/{task['id']}/coverage").json()
 return client.post(f"/api/tasks/{task['id']}/coverage/confirm",json={'revision':task['revision'],'review_token':state['review_token'],'acknowledge_review':True,'acknowledge_exclusions':False,**patch})

def test_unresolved_gate_does_not_change_business_or_fake_completion(client):
 task=approved(client);response=save(client,task,items(task,'unresolved'));assert response.status_code==200,response.text
 value=response.json();assert value['revision']==task['revision']+1 and value['requirements']==task['requirements'] and not value['configuration_confirmed']
 state=client.get(f"/api/tasks/{task['id']}/coverage").json();assert state['enabled'] and not state['confirmed'] and '未解决' in ' '.join(state['blockers'])
 assert confirm(client,value).status_code==422
 cfg=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':value['revision'],'kind':'configuration'});assert cfg.status_code==422 and '覆盖' in cfg.text
 for path in ('build','import','run'):
  assert client.post(f"/api/tasks/{task['id']}/{path}",json={'revision':value['revision']}).status_code==422

def test_current_confirmation_allows_static_build_and_report(client):
 task=approved(client);value=save(client,task,items(task)).json();response=confirm(client,value);assert response.status_code==200,response.text
 state=client.get(f"/api/tasks/{task['id']}/coverage").json();assert state['confirmed'] and state['verification']=='declared_plan_mapping_only'
 assert client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':value['revision'],'kind':'configuration'}).status_code==200
 response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':value['revision']});assert response.status_code==200,response.text
 assert response.json()['artifact']['verification']=='static_only'
 report=client.get(f"/api/tasks/{task['id']}/report");assert '需求与方案覆盖' in report.text and '不等于完整业务验证' in report.text

@pytest.mark.parametrize('change',[{'requirements':{'rules':'新规则'}},{'configuration':{'temperature':.3}},{'name':'新名称'}])
def test_changes_require_fresh_review(client,change):
 task=approved(client);value=save(client,task,items(task)).json();assert confirm(client,value).status_code==200
 changed=client.patch(f"/api/tasks/{task['id']}",json=change).json();assert changed['revision']>value['revision']
 state=client.get(f"/api/tasks/{task['id']}/coverage").json();assert state['stale'] and not state['confirmed']
 assert confirm(client,changed).status_code==409

def test_exclusion_is_explicit_and_model_cannot_choose(client):
 task=approved(client);rows=items(task);rows[0]['status']='excluded'
 assert not validate_items(task,{'schema_version':1,'items':rows},model=True)['valid']
 value=save(client,task,rows).json();assert confirm(client,value).status_code==422
 response=confirm(client,value,acknowledge_exclusions=True);assert response.status_code==200
 assert response.json()['coverage_review']['confirmation']['excluded_ids']==['R_goal']

@pytest.mark.parametrize('field,value',[('impact',''),('cost',''),('manual_work',''),('explanation',''),('evidence_ids',['node:made-up']),('case_ids',['unknown']),('source',{'kind':'requirement','id':'rules','quote':'虚构引文'}),('source',{'kind':'material','id':'missing','quote':'资料'}),('id','bad id'),('status','passed'),('status',[]),('evidence_ids',[{}]),('case_ids',{}),('requirement',True)])
def test_invalid_or_fabricated_values_are_rejected(client,field,value):
 task=approved(client);rows=items(task);rows[0]['status']='excluded' if field in ('impact','cost','manual_work') else 'planned';rows[0][field]=value
 response=save(client,task,rows);assert response.status_code==422,response.text
 assert client.get(f"/api/tasks/{task['id']}").json()['revision']==task['revision']

def test_no_silent_deletion_or_missing_requirement_categories(client):
 task=approved(client);rows=items(task);value=save(client,task,rows).json()
 assert save(client,value,rows[1:]).status_code==422
 assert not validate_items(task,{'schema_version':1,'items':rows[:1]},model=True)['valid']
 partial=approved(client);saved=save(client,partial,items(partial)[:1]).json();assert confirm(client,saved).status_code==422

def test_stale_token_and_nonexplicit_ack_are_rejected(client):
 task=approved(client);value=save(client,task,items(task)).json()
 assert confirm(client,value,review_token='wrong').status_code==409
 assert confirm(client,value,acknowledge_review=False).status_code==422
 assert confirm(client,value,acknowledge_exclusions='true').status_code==422

def test_restore_keeps_enabled_gate_without_restoring_old_approval(client):
 task=approved(client);value=save(client,task,items(task)).json();assert confirm(client,value).status_code==200
 version=value['versions'][-1]['id'];restored=client.post(f"/api/tasks/{task['id']}/restore",json=restore_payload(client, task['id'], version)).json()
 assert restored['coverage_enabled'] and restored['coverage_review'] is None
 assert not summary(restored)['confirmed'] and summary(restored)['blockers']

def test_material_source_and_iteration_ids(client):
 task=approved(client);task['materials']=[{'id':'doc','status':'parsed','text':'资料中的可追溯事实'}];main.save_task(task)
 rows=items(task);rows.append({**copy.deepcopy(rows[0]),'id':'R_doc','source':{'kind':'material','id':'doc','quote':'可追溯事实'}})
 assert save(client,task,rows).status_code==200
 task['workflow_plan']={'nodes':[{'id':'batch','type':'iteration','config':{'nodes':[{'id':'body','type':'code'}]}}]}
 assert 'node:body' in evidence(task)

def test_generated_suggestions_save_without_auto_confirmation(client,monkeypatch):
 task=approved(client)
 provider=client.post('/api/providers',json={'name':'mock','provider':'openai-compatible','base_url':'https://api.deepseek.com','model':'model','api_key':'test-key','pricing':{'input_per_million_usd':1,'output_per_million_usd':1}}).json()
 task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':provider['id']}}).json()
 calls=[]
 async def model(*args,**kwargs):
  calls.append(args[2]);return json.dumps({'schema_version':1,'items':items(task)}),{'prompt_tokens':100,'completion_tokens':100}
 monkeypatch.setattr(main,'call_model',model)
 response=client.post(f"/api/tasks/{task['id']}/coverage/generate",json={'revision':task['revision']});assert response.status_code==200,response.text
 value=response.json();assert value['coverage_review']['source']=='model' and not value['coverage_review']['confirmation']
 assert value['planning_runs'][-1]['kind']=='coverage' and value['planning_runs'][-1]['status']=='succeeded' and len(calls)==1
 assert not summary(value)['confirmed']

def test_model_omission_pauses_preserving_candidate(client,monkeypatch):
 task=approved(client);provider=client.post('/api/providers',json={'name':'mock','provider':'openai-compatible','base_url':'https://api.deepseek.com','model':'model','api_key':'test-key','pricing':{'input_per_million_usd':1,'output_per_million_usd':1}}).json()
 task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':provider['id']}}).json()
 async def model(*args,**kwargs):return json.dumps({'schema_version':1,'items':items(task)[:1]}),{'prompt_tokens':50,'completion_tokens':50}
 monkeypatch.setattr(main,'call_model',model)
 assert client.post(f"/api/tasks/{task['id']}/coverage/generate",json={'revision':task['revision']}).status_code==422
 current=client.get(f"/api/tasks/{task['id']}").json();assert current['status']=='paused' and not current.get('coverage_review')
 assert current['planning_runs'][-1]['last_candidate']['items'] and current['planning_runs'][-1]['stop_reason']=='needs_decision'

def test_final_dsl_evidence_and_overlay_carry_are_consistent(client):
 from test_dsl_roundtrip import prepared,changed
 from app.dsl_roundtrip import digest as dsl_digest
 task,root=prepared(client);root=changed(root);root['workflow']['graph']['nodes'][1]['id']='actual_code'
 for edge in root['workflow']['graph']['edges']:
  if edge['source']=='code':edge['source']='actual_code'
  if edge['target']=='code':edge['target']='actual_code'
 root['workflow']['graph']['nodes'][-1]['data']['outputs'][0]['value_selector']=['actual_code','result']
 import yaml
 folder=main.DATA_ROOT/task['id'];(folder/'preserved.yaml').write_text(yaml.safe_dump(root),encoding='utf-8')
 task.update(dsl_reference={'id':'fixture'},dsl_overlay={'revision':task['revision'],'filename':'preserved.yaml','digest':dsl_digest(root)})
 main.save_task(task)
 refs=evidence(task);assert 'node:actual_code' in refs and 'node:code' not in refs and 'config:dify_model' not in refs
 rows=items(task)
 for row in rows:row['evidence_ids']=['node:actual_code']
 value=save(client,task,rows).json();assert value['dsl_overlay']['revision']==value['revision']
 assert confirm(client,value).status_code==200
 (folder/'preserved.yaml').write_text('changed file',encoding='utf-8')
 assert not summary(value)['confirmed'] and '无法读取' in ' '.join(summary(value)['blockers'])


@pytest.mark.parametrize('mutation',['new_revision','pause','missing_price'])
def test_model_checks_stop_without_applying_old_or_unpriced_candidate(client,monkeypatch,mutation):
 task=approved(client);payload={'name':'mock','provider':'openai-compatible','base_url':'https://api.deepseek.com','model':'model','api_key':'test-key'}
 if mutation!='missing_price':payload['pricing']={'input_per_million_usd':1,'output_per_million_usd':1}
 provider=client.post('/api/providers',json=payload).json()
 task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'assistant_provider_id':provider['id']}}).json()
 calls=[]
 async def model(*args,**kwargs):
  calls.append(True);current=main.get_task(task['id'])
  if mutation=='new_revision':current['revision']+=1;current['status']='configuration';main.save_task(current)
  elif mutation=='pause':main.pause(task['id'])
  return json.dumps({'schema_version':1,'items':items(task)}),{'prompt_tokens':50,'completion_tokens':50}
 monkeypatch.setattr(main,'call_model',model)
 assert client.post(f"/api/tasks/{task['id']}/coverage/generate",json={'revision':task['revision']}).status_code==422
 current=main.get_task(task['id']);assert not current.get('coverage_review')
 assert current['status']==('configuration' if mutation=='new_revision' else 'paused')
 if mutation=='missing_price':assert not calls and current['planning_runs'][-1]['stop_reason']=='pricing_unknown'
 else:assert len(calls)==1 and current['planning_runs'][-1]['attempts'][0]['usage']
