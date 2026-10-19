import copy,hashlib,json
from uuid import uuid4
import pytest
from fastapi import HTTPException
from test_api import client,approved
from app import main
from app.missing_extractor import prepare
from app.workflow_plan import validate_plan

HUGE=9007199254740993
def source():
    return {'schema_version':1,'nodes':[{'id':'entry','type':'start','title':'用户原入口','config':{'variables':[{'variable':'doc','label':'原文档','type':'file','required':True,'hide':False,'allowed_file_types':['custom'],'allowed_file_extensions':['.txt'],'allowed_file_upload_methods':['local_file']},{'variable':'doc_ext','type':'paragraph','required':False},{'variable':'count','type':'number','required':False,'default':HUGE}]}},{'id':'finish','type':'end','title':'用户原输出','config':{'outputs':[{'variable':'original_text','value_selector':['missing_extract','text']}]}}],'edges':[{'source':'entry','target':'missing_extract'},{'source':'missing_extract','target':'finish'}]}

def context():return {'app_type':'workflow','configuration':{}}

def test_only_one_node_added_with_all_original_nodes_edges_inputs_and_integer_preserved():
    plan=source();before=copy.deepcopy(plan);task=context();text=json.dumps(plan,ensure_ascii=False);value=prepare(task,text,'missing_extract','doc');result=json.loads(value['plan_text'])
    assert validate_plan(task,result)['valid'] and len(result['nodes'])==3
    inserted=result['nodes'].pop(1);assert inserted['id']=='missing_extract' and inserted['type']=='document-extractor'
    assert inserted['config']=={'variable_selector':['entry','doc'],'input_type':'file','empty_policy':'fail_if_missing'}
    assert result==before and plan==before and '9007199254740993' in value['plan_text']
    assert value['source_text_sha256']==hashlib.sha256(text.encode()).hexdigest()
    assert value['proposal_sha256']==hashlib.sha256(value['plan_text'].encode()).hexdigest()
    assert value['original_nodes_preserved'] and value['original_edges_preserved']
    assert not any(value[k] for k in ('task_changed','network_requested','code_executed','platform_checked','business_verified'))

def test_original_node_and_edge_order_are_not_rebuilt():
    plan=source();plan['nodes'].reverse();plan['edges'].reverse();value=prepare(context(),json.dumps(plan),'missing_extract','doc');result=json.loads(value['plan_text']);result['nodes']=[n for n in result['nodes'] if n['id']!='missing_extract'];assert result==plan

@pytest.mark.parametrize('mode',['advanced-chat','agent'])
def test_application_type_not_changed(mode):
    task=context();task['app_type']=mode
    with pytest.raises(ValueError):prepare(task,json.dumps(source()),'missing_extract','doc')

@pytest.mark.parametrize('case',['extra-node','extra-edge','list','optional','multiple-files','wrong-type','wrong-output','multiple-outputs','wrong-source','wrong-variable','existing-id','bad-edge','bad-filter'])
def test_ambiguous_or_different_scope_is_not_partially_repaired(case):
    plan=source();node_id='missing_extract';variable='doc';entry=plan['nodes'][0]
    if case=='extra-node':plan['nodes'].append({'id':'other','type':'code','config':{}})
    if case=='extra-edge':plan['edges'].append({'source':'entry','target':'finish'})
    if case=='list':entry['config']['variables'][0]['type']='file-list'
    if case=='optional':entry['config']['variables'][0]['required']=False
    if case=='multiple-files':entry['config']['variables'].append({**copy.deepcopy(entry['config']['variables'][0]),'variable':'another'})
    if case=='wrong-type':entry['type']='trigger-schedule'
    if case=='wrong-output':plan['nodes'][1]['config']['outputs'][0]['value_selector']=['missing_extract','body']
    if case=='multiple-outputs':plan['nodes'][1]['config']['outputs'].append({'variable':'another','value_selector':['entry','doc_ext']})
    if case=='wrong-source':plan['edges'][0]['source']='another'
    if case=='wrong-variable':variable='other'
    if case=='existing-id':node_id='entry'
    if case=='bad-edge':plan['edges'][0]['source']=[]
    if case=='bad-filter':entry['config']['variables'][0]['allowed_file_types']=['image']
    before=copy.deepcopy(plan)
    with pytest.raises(ValueError):prepare(context(),json.dumps(plan),node_id,variable)
    assert plan==before

@pytest.mark.parametrize('text',['{"schema_version":1,"schema_version":1}','{"private":"sk-'+'A'*32+'"}','{private-unfinished'],ids=['duplicate','secret','unfinished'])
def test_bad_text_not_echoed_or_repaired(text):
    with pytest.raises((ValueError,HTTPException)) as caught:prepare(context(),text,'missing_extract','doc')
    assert 'A'*32 not in str(caught.value) and 'private-unfinished' not in str(caught.value)

def payload(task):return {'revision':task['revision'],'plan_text':json.dumps(source()),'missing_node_id':'missing_extract','input_variable':'doc','acknowledge_extraction':True,'request_nonce':str(uuid4())}

def test_api_prepares_only_no_storage_model_compile_or_resource_changes(client,monkeypatch):
    task=approved(client);before=client.get('/api/tasks/'+task['id']).json();body=payload(task)
    def forbidden(*a,**k):raise AssertionError('不得写存储、编译或调用模型')
    monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
    import app.workflow_plan
    monkeypatch.setattr(app.workflow_plan,'compile_workflow_plan',forbidden)
    response=client.post(f"/api/tasks/{task['id']}/missing-document-extractor",json=body)
    assert response.status_code==200,response.text;v=response.json()
    assert v['task_id']==task['id'] and v['revision']==task['revision'] and v['request_nonce']==body['request_nonce']
    assert client.get('/api/tasks/'+task['id']).json()==before

@pytest.mark.parametrize('field,value',[('acknowledge_extraction',False),('acknowledge_extraction','true'),('revision',True),('input_variable','other'),('missing_node_id','entry'),('extra','PRIVATE-REQUEST')],ids=['unconfirmed','coerced','bool-revision','wrong-input','collision','extra'])
def test_required_explicit_choices_and_safe_errors(client,field,value):
    task=approved(client);body=payload(task);body[field]=value
    response=client.post(f"/api/tasks/{task['id']}/missing-document-extractor",json=body)
    assert response.status_code==422 and 'PRIVATE-REQUEST' not in response.text

def test_revision_change_during_preparation_rejects_old_proposal(client,monkeypatch):
    import app.missing_extractor as module
    task=approved(client);body=payload(task);url=f"/api/tasks/{task['id']}/missing-document-extractor";old=module.prepare;calls=[]
    def changed(*args):
        calls.append(1);stored=main.store.get('task',task['id']);stored['revision']+=1;main.store.put('task',task['id'],stored);return old(*args)
    monkeypatch.setattr(module,'prepare',changed)
    assert client.post(url,json=body).status_code==409 and calls==[1]
    assert client.get('/api/tasks/'+task['id']).json()['workflow_plan']==task['workflow_plan']
