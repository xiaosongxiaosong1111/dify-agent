import copy,hashlib,json
from uuid import uuid4
from pathlib import Path
import pytest
from test_api import client,approved
from test_workflow_plan import base_plan
from app import main
from app.plan_inspection import inspect

def task(mode='workflow'):
    return {'app_type':mode,'configuration':{'dataset_ids':[]},'revision':1}

def test_missing_node_is_reported_without_adopting_or_repairing():
    context=task();before=copy.deepcopy(context);plan=base_plan();plan['nodes']=[n for n in plan['nodes'] if n['id']!='llm'];text=json.dumps(plan,ensure_ascii=False)
    value=inspect(context,text)
    assert not value['valid'] and any('不存在节点' in e for e in value['errors'])
    assert value['source_text_sha256']==hashlib.sha256(text.encode()).hexdigest() and context==before
    assert value['verification']=='local_plan_structure_only'
    assert not any(value[k] for k in ('task_changed','network_requested','code_executed','platform_checked','business_verified'))

@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_actual_app_validator_used_without_inheriting_another_app_scope(mode):
    plan={'schema_version':1,'scope':'text','system_prompt':'只润色文字，不编造事实。'} if mode=='agent' else base_plan(mode)
    value=inspect(task(mode),json.dumps(plan,ensure_ascii=False))
    assert value['valid'] and not value['errors'] and value['json_location'] is None
    if mode=='agent':assert value['nodes']==0 and any('内建' in w for w in value['warnings'])

def test_json_line_column_and_no_source_echo():
    text='{\n"nodes": [\nprivate-source'
    value=inspect(task(),text)
    assert not value['valid'] and value['json_location']=={'line':3,'column':1}
    assert 'private-source' not in json.dumps(value)

@pytest.mark.parametrize('text',['{}\n{}','[]','{"a":1,"a":2}','{"a":NaN}','{"a":1e999}','{"a":"\\ud800"}',''],ids=['extra','array','duplicate','nan','overflow','unicode','empty'])
def test_invalid_complete_input_not_repaired_or_coerced(text):
    value=inspect(task(),text)
    assert not value['valid'] and value['errors']

def test_credentials_bad_encoding_and_size_are_not_echoed():
    for text in ('{"password":"do-not-show-password"}','{"note":"sk-'+'A'*32+'"}','\ud800','字'*700000):
        value=inspect(task(),text);output=json.dumps(value)
        assert not value['valid'] and 'do-not-show' not in output and 'A'*32 not in output
    assert inspect(task(),'\ud800')['source_text_sha256'] is None

def test_generated_code_is_only_parsed_not_executed(tmp_path):
    marker=tmp_path/'must-not-exist';plan=base_plan();plan['nodes'][1]={'id':'llm','type':'code','config':{'code_language':'python3','code':f'def main():\n    open({str(marker)!r}, "w").write("executed")\n    return {{"text":"ok"}}','variables':[],'outputs':{'text':{'type':'string','children':None}}}}
    value=inspect(task(),json.dumps(plan));assert value['valid'],value['errors'];assert not marker.exists()

def test_manual_llm_json_field_transport_matches_save_without_rounding():
    from test_plan_field_text import draft,HUGE
    plan=draft();plan['nodes'][2]['config']['structured_output']=json.dumps(plan['nodes'][2]['config']['structured_output']);before=copy.deepcopy(plan);text=json.dumps(plan)
    value=inspect(task(),text)
    assert value['valid'],value['errors']
    assert str(HUGE) in text and plan==before and value['source_text_sha256']==hashlib.sha256(text.encode()).hexdigest()

def test_invalid_llm_json_field_is_not_silently_replaced_or_echoed():
    from test_plan_field_text import draft
    plan=draft();plan['nodes'][2]['config']['structured_output']='{private-unfinished';value=inspect(task(),json.dumps(plan))
    assert not value['valid'] and 'private-unfinished' not in json.dumps(value)

@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_api_checks_without_storage_model_compile_or_confirmation_changes(client,monkeypatch,mode):
    t=approved(client)
    if mode!='workflow':t['app_type']=mode;main.store.put('task',t['id'],t)
    before=client.get('/api/tasks/'+t['id']).json();nonce=str(uuid4());plan={'schema_version':1,'scope':'text','system_prompt':'只按明确事实回答。'} if mode=='agent' else base_plan(mode);text=json.dumps(plan)
    def forbidden(*a,**k):raise AssertionError('不得写存储、调用模型或编译/执行')
    monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
    import app.workflow_plan,app.agent_plan
    monkeypatch.setattr(app.workflow_plan,'compile_workflow_plan',forbidden);monkeypatch.setattr(app.agent_plan,'compile_agent_plan',forbidden)
    response=client.post(f"/api/tasks/{t['id']}/plan-check",json={'revision':t['revision'],'plan_text':text,'request_nonce':nonce})
    assert response.status_code==200,response.text;value=response.json()
    assert value['valid'] and value['task_id']==t['id'] and value['revision']==t['revision'] and value['request_nonce']==nonce
    assert client.get('/api/tasks/'+t['id']).json()==before

@pytest.mark.parametrize('field,value',[('revision',True),('revision',0),('plan_text',{}),('plan_text','\ud800'),('request_nonce','not-a-uuid'),('extra','private-request')],ids=['bool-rev','zero','object-text','bad-unicode','nonce','extra'])
def test_request_validation_does_not_echo_input(client,field,value):
    t=approved(client);body={'revision':t['revision'],'plan_text':'PRIVATE-TEXT','request_nonce':str(uuid4()),field:value}
    response=client.post(f"/api/tasks/{t['id']}/plan-check",content=json.dumps(body,ensure_ascii=True),headers={'Content-Type':'application/json'})
    if field=='plan_text' and value=='\ud800' and response.status_code==200:
        assert not response.json()['valid'] and response.json()['source_text_sha256'] is None
        return
    assert response.status_code==422 and 'PRIVATE-TEXT' not in response.text and 'private-request' not in response.text

def test_duplicate_envelope_key_is_refused_before_check(client):
    t=approved(client);body='{"revision":'+str(t['revision'])+',"plan_text":"PRIVATE-TEXT","plan_text":"{}","request_nonce":"'+str(uuid4())+'"}'
    response=client.post(f"/api/tasks/{t['id']}/plan-check",content=body,headers={'Content-Type':'application/json'})
    assert response.status_code==422 and 'PRIVATE-TEXT' not in response.text

def test_stale_revision_and_change_during_check_refuse_result(client,monkeypatch):
    import app.plan_inspection as module
    t=approved(client);url=f"/api/tasks/{t['id']}/plan-check";body={'revision':t['revision']-1,'plan_text':'{}','request_nonce':str(uuid4())}
    assert client.post(url,json=body).status_code==409
    original=module.inspect;calls=[]
    def changed(context,text):
        calls.append(1);stored=main.store.get('task',t['id']);stored['revision']+=1;main.store.put('task',t['id'],stored);return original(context,text)
    monkeypatch.setattr(module,'inspect',changed);body['revision']=t['revision']
    assert client.post(url,json=body).status_code==409 and calls==[1]
    saved=client.get('/api/tasks/'+t['id']).json();assert saved['workflow_plan']==t['workflow_plan'] and saved['configuration_confirmed']==t['configuration_confirmed']
