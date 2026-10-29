import copy
import json
from uuid import uuid4

import pytest
import yaml

from test_api import client, forbid_api_external_calls
from test_plan_review import ready
from app import main
from app.after_sales_starter import prepare, COLLECT_CODE, digest
from app.workflow_plan import compile_workflow_plan


def inputs():
    return {'source_text':'','dependency':'订单查询模拟','records_text':'{"DEMO-001":"合成样例：已发货。"}',
        'no_hit_reply':'知识库暂无相关信息，请联系人工客服。','missing_order_reply':'请提供订单号。','clarify_reply':'请明确咨询资料还是查询订单。'}


def context():
    return {'id':'local','revision':3,'name':'公开售后草稿','app_type':'advanced-chat',
        'requirements':{k:'公开合成售后范围，模型效果待验证' for k in main.REQ_KEYS},
        'configuration':{'dify_model_provider':'test/provider','dify_model':'chosen-model','temperature':.2,'max_tokens':512,
            'model_parameters':{},'dataset_ids':['existing-faq'],'retrieval_top_k':3,'mock_dependencies':['订单查询模拟']}}


def test_full_graph_has_grounded_faq_no_hit_order_success_failure_and_clarification_paths():
    task=context();original=copy.deepcopy(task);text,validation=prepare(task,inputs());plan=json.loads(text)
    assert validation['valid'] and task==original
    content,checked=compile_workflow_plan({**task,'workflow_plan':plan});root=yaml.safe_load(content)
    assert checked['valid'] and root['app']['mode']=='advanced-chat'
    native={n['id']:n['data'] for n in root['workflow']['graph']['nodes']}
    edges={(e['source'],e['sourceHandle'],e['target']) for e in root['workflow']['graph']['edges']}
    assert {('intent','clarify','clarify'),('intent','faq','retrieve'),('intent','order','extract_order'),
        ('check_hit','found','grounded_answer'),('check_hit','false','no_hit'),
        ('check_order','extracted','validate_order'),('check_order','false','missing_order'),
        ('validate_order','source','check_order_value'),('check_order_value','has_order','order_lookup'),
        ('check_order_value','false','missing_order')}<=edges
    assert len(native)==19 and len(edges)==19
    assert native['retrieve']['dataset_ids']==['existing-faq'] and native['retrieve']['multiple_retrieval_config']['top_k']==3
    for node_id in ['intent','extract_order','grounded_answer']:
        assert native[node_id]['model']['name']=='chosen-model' and native[node_id]['model']['provider']=='test/provider'
    assert native['grounded_answer']['context']['variable_selector']==['retrieve','result']
    assert native['check_hit']['cases'][0]['conditions'][0]['value'] is True
    assert native['check_order']['cases'][0]['conditions'][0]['variable_selector']==['extract_order','__is_success']
    assert native['check_order']['cases'][0]['conditions'][0]['value']=='1'
    assert native['order_lookup']['variables']==[{'variable':'order_id','value_selector':['extract_order','order_no']}]
    assert '【模拟订单查询，非真实订单】' in native['order_lookup']['code'] and '合成样例：已发货。' in native['order_lookup']['code']
    for node_id,key in [('no_hit','no_hit_reply'),('missing_order','missing_order_reply'),('clarify','clarify_reply')]:
        assert native[node_id]['template']==inputs()[key]


def test_collector_distinguishes_empty_result_from_invalid_transport_data():
    scope={};exec(COLLECT_CODE,scope)
    assert scope['main']([])=={'has_result':False} and scope['main']([{'content':'公开FAQ'}])=={'has_result':True}
    with pytest.raises(ValueError):scope['main'](None)


def test_retrieved_public_facts_reach_compiled_answer_messages():
    """Dify graphon0.7.0 substitutes context only at its dedicated placeholder."""
    task=context();text,_=prepare(task,inputs())
    content,checked=compile_workflow_plan({**task,'workflow_plan':json.loads(text)})
    answer=next(n['data'] for n in yaml.safe_load(content)['workflow']['graph']['nodes'] if n['id']=='grounded_answer')
    assert checked['valid'] and answer['context']=={'enabled':True,'variable_selector':['retrieve','result']}
    public_context='公开政策ZXRET715：签收七天内且未拆封可退货。'
    query='ZXRET715在签收后七天内且未拆封，能否退货？'
    # The tagged engine replaces {{#context#}} before normal variable expansion;
    # merely enabling node.context does not append it to any prompt message.
    rendered=[p['text'].replace('{{#context#}}',public_context).replace('{{#sys.query#}}',query) for p in answer['prompt_template']]
    assert any(public_context in p for p in rendered), 'Bound retrieval was omitted from actual prompt messages'
    assert any(query in p for p in rendered)
    assert inputs()['no_hit_reply'] in '\n'.join(rendered)
    assert public_context not in text  # No policy facts hardcoded into the template.
    instructions='\n'.join(p['text'] for p in answer['prompt_template'] if p['role']=='system')
    assert all(term in instructions for term in ('适用条件','政策编号','结论')), 'Policy answer omits the required completeness instruction'


@pytest.mark.parametrize('key,value',[('workflow_plan',{'nodes':[]}),('artifact',{'revision':3}),('dsl_reference',{'id':'original'}),('dify_app_id','existing'),('agent_plan',{'scope':'text'})])
def test_saved_sources_are_never_replaced(key,value):
    task=context();task[key]=value;original=copy.deepcopy(task)
    with pytest.raises(main.HTTPException):prepare(task,inputs())
    assert task==original


@pytest.mark.parametrize('mode',['workflow','agent'])
def test_user_app_type_is_never_changed(mode):
    task=context();task['app_type']=mode
    with pytest.raises(main.HTTPException):prepare(task,inputs())
    assert task['app_type']==mode


@pytest.mark.parametrize('key,value',[('dataset_ids',[]),('dify_model',''),('mock_dependencies',[])])
def test_no_resource_or_mock_choice_is_invented(key,value):
    task=context();task['configuration'][key]=value
    with pytest.raises(main.HTTPException):prepare(task,inputs())


def test_foreign_mock_binding_is_not_silently_reassigned():
    task=context();task['configuration']['mock_dependency_bindings']=[{'dependency':'订单查询模拟','node_id':'other-node','replacement_todo':'真实接入待办'}]
    with pytest.raises(ValueError):prepare(task,inputs())
    assert task['configuration']['mock_dependency_bindings'][0]['node_id']=='other-node'


@pytest.mark.parametrize('key,value',[('source_text','{"nodes":[]}'),('no_hit_reply',''),('missing_order_reply','{{ hidden }}'),('clarify_reply','Bearer SYNTHETICPRIVATEVALUE12345')])
def test_existing_drafts_dynamic_replies_and_credentials_are_refused(key,value):
    data=inputs();data[key]=value
    with pytest.raises(main.HTTPException):prepare(context(),data)


def prepared(client):
    task=ready(client,'advanced-chat')
    response=client.patch('/api/tasks/'+task['id'],json={'configuration':{'dataset_ids':['existing-faq'],'mock_dependencies':['订单查询模拟']}})
    assert response.status_code==200,response.text
    return response.json()


def body(task):return {**inputs(),'revision':task['revision'],'request_nonce':str(uuid4()),'acknowledge_scope':True}


def test_actual_preview_readonly_then_explicit_save_confirm_and_static_download(client,monkeypatch):
    task=prepared(client);path='/api/tasks/'+task['id'];payload=body(task);original=copy.deepcopy(task);budget=main.store.get('task_budget',task['id'])
    def forbid(*args,**kwargs):pytest.fail('Preview must not write or decrypt')
    with monkeypatch.context() as patch:
        patch.setattr(main.store,'put',forbid);patch.setattr(main.store,'secret',forbid)
        response=client.post(path+'/after-sales-plan-preview',json=payload)
    assert response.status_code==200,response.text
    value=response.json();assert value['input_sha256']==digest(inputs()) and value['request_nonce']==payload['request_nonce']
    assert value['node_count']==len(json.loads(value['plan_text'])['nodes'])==19
    assert all(value[k] is False for k in ['task_changed','model_called','network_requested','code_executed','platform_checked','business_verified'])
    assert main.get_task(task['id'])==original and main.store.get('task_budget',task['id'])==budget
    saved=client.post(path+'/plan',json={'revision':task['revision'],'plan_text':value['plan_text']})
    assert saved.status_code==200,saved.text
    task=saved.json();assert not task['configuration_confirmed'] and task['plan_source']=='manual'
    assert client.post(path+'/confirm',json={'revision':task['revision'],'kind':'configuration'}).status_code==200
    result=client.post(path+'/build',json={'revision':task['revision']});assert result.status_code==200,result.text
    artifact=client.get(path+'/artifact');assert artifact.status_code==200 and '模拟' in artifact.text
    assert client.get(path+'/report').status_code==200


def test_nonce_revision_ack_duplicates_and_invalid_records_fail_without_task_changes(client):
    task=prepared(client);path='/api/tasks/'+task['id']+'/after-sales-plan-preview';payload=body(task)
    for patch in [{'revision':task['revision']+1},{'acknowledge_scope':False},{'acknowledge_scope':'true'},
        {'records_text':'{"DEMO-001":"a","DEMO-001":"b"}'},{'records_text':'{"DEMO-001":123}'},
        {'records_text':'{"DEMO-001":"app-SYNTHETICPRIVATEVALUE12345"}'}]:
        response=client.post(path,json={**payload,**patch});assert response.status_code in {409,422}
        assert 'SYNTHETICPRIVATEVALUE' not in response.text
    raw=json.dumps(payload)[:-1]+',"acknowledge_scope":true}'
    assert client.post(path,content=raw,headers={'Content-Type':'application/json'}).status_code==422
    assert main.get_task(task['id'])==task
