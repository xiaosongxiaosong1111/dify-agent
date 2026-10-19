import sys,json,copy,yaml,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app.workflow_environment_mapping import WorkflowMappingRequest,build,MARKER
from app.dsl_roundtrip import digest,validate_preserved,parse
from app.workflow_plan import compile_workflow_plan
from test_api import client,create_env

A='a1111111-1111-4111-8111-111111111111';B='b2222222-2222-4222-8222-222222222222'
MODEL={'provider':'public/target/provider','name':'target-model','mode':'chat','completion_params':{'temperature':.4,'max_tokens':512,'top_p':.8}}


def setup(mode='workflow'):
    model={'provider':'public/source/provider','name':'source-model','mode':'chat','completion_params':{'temperature':.2,'max_tokens':1024}}
    plan={'schema_version':1,'nodes':[
        {'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'paragraph','required':True}]}},
        {'id':'retrieve','type':'knowledge-retrieval','config':{'query_variable_selector':['start','query'],'dataset_source':'node','dataset_ids':[A],'top_k':3,'score_threshold':.6,'reranking_enable':True,'reranking_model':{'provider':'public/rerank/provider','model':'source-rerank'}}},
        {'id':'one','type':'llm','config':{'system_prompt':'原人工职责','user_prompt':'{{#start.query#}}','model':model}},
        {'id':'two','type':'llm','config':{'system_prompt':'独立模型职责','user_prompt':'{{#one.text#}}','model':model}},
        {'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['two','text']}]}}
    ],'edges':[{'source':'start','target':'retrieve'},{'source':'retrieve','target':'one'},{'source':'one','target':'two'},{'source':'two','target':'end'}]}
    if mode=='advanced-chat':
        plan['nodes'][0]['config']['variables']=[]
        plan['nodes'][1]['config']['query_variable_selector']=['sys','query']
        plan['nodes'][2]['config']['user_prompt']='{{#sys.query#}}'
        plan['nodes'][-1]={'id':'end','type':'answer','config':{'answer':'{{#two.text#}}'}}
    task={'id':'public-task','revision':4,'app_type':mode,'environment_id':'source','workflow_plan':plan,'configuration':{}}
    content,v=compile_workflow_plan(task);assert v['valid'],v['errors'];root=parse(content,mode)
    root['dependencies']=[{'type':'marketplace','value':{'marketplace_plugin_unique_identifier':'public/source:1@src','version':None},'current_identifier':'source-local-id'}]
    root['workflow']['graph']['nodes'][2]['position']['x']+=37
    source={'content':yaml.safe_dump(root,allow_unicode=True),'validation':validate_preserved(root),'unresolved':0,'reference_id':'ref','merge_token':'a'*64,'document_token':digest(root)}
    assert source['validation']['valid'],source['validation']['errors']
    target={'id':'target','name':'公开目标','base_url':'http://127.0.0.1:8080','version':'1.17.1','connection_revision':'target-rev'}
    request=WorkflowMappingRequest(revision=4,reference_id='ref',merge_token='a'*64,document_token=digest(root),target_environment_id='target',expected_target_connection_revision='target-rev',node_models_json={'one':json.dumps(MODEL),'two':json.dumps({**MODEL,'name':'second-target'})},dataset_mapping={A:B},node_rerankers={'retrieve':{'provider':'public/reranktarget/provider','model':'target-rerank'}},dependency_mapping={'public/source:1@src':'public/target:2@dst'},additional_dependencies=['public/reranktarget:3@dst'],acknowledge_unverified_target=True)
    return task,root,source,target,request


@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_exact_nodes_and_retrieval_parameters_graph_and_layout_preserved(mode):
    task,root,source,target,request=setup(mode);before=copy.deepcopy((task,root,source,target,request.model_dump()))
    result=build(task,source,target,request);output=parse(result['content'],mode)
    assert result['validation']['valid'] and result['can_download'] and not result['can_apply']
    assert (task,root,source,target,request.model_dump())==before
    expected=copy.deepcopy(root);nodes={n['id']:n for n in expected['workflow']['graph']['nodes']}
    nodes['one']['data']['model']=MODEL;nodes['two']['data']['model']={**MODEL,'name':'second-target'}
    nodes['retrieve']['data']['dataset_ids']=[B];nodes['retrieve']['data']['multiple_retrieval_config']['reranking_model']={'provider':'public/reranktarget/provider','model':'target-rerank'}
    expected['dependencies']=output['dependencies'];expected['app']['description']=output['app']['description'];assert expected==output
    assert output['app']['description'].endswith(MARKER) and all(d['current_identifier'] is None for d in output['dependencies'])
    assert all(result[k] is False for k in ('task_modified','platform_verified','business_verified','target_resources_verified'))


@pytest.mark.parametrize('patch',[{'node_models_json':{}},{'node_models_json':{'one':json.dumps(MODEL)}},{'dataset_mapping':{}},{'dataset_mapping':{A:'label'}},{'node_rerankers':{}},{'dependency_mapping':{}},{'additional_dependencies':[]},{'additional_dependencies':['public/target:other@hash']},{'acknowledge_unverified_target':False}])
def test_no_missing_or_ambiguous_resource_is_silently_dropped(patch):
    task,root,source,target,req=setup();req=WorkflowMappingRequest.model_validate({**req.model_dump(),**patch});before=copy.deepcopy(root)
    with pytest.raises(ValueError):build(task,source,target,req)
    assert root==before


@pytest.mark.parametrize('raw',['{"provider":"x","provider":"y"}',json.dumps({**MODEL,'completion_params':{'temperature':.4,'max_tokens':512,'api_key':'PRIVATE-INPUT'}}),json.dumps(MODEL).replace('0.4','0.40000000000000001')])
def test_model_raw_json_not_rewritten_or_secret_echoed(raw):
    task,root,source,target,req=setup();req.node_models_json['one']=raw
    with pytest.raises(ValueError) as exc:build(task,source,target,req)
    assert 'PRIVATE-INPUT' not in str(exc.value)


def test_external_settings_require_explicit_ack_and_keep_values_without_credentials():
    task,root,source,target,req=setup();root['workflow']['environment_variables']=[{'id':'public-var','name':'PUBLIC_HOST','value_type':'string','value':'private-original-setting'}]
    source['content']=yaml.safe_dump(root);source['document_token']=digest(root)
    with pytest.raises(ValueError,match='明确接受保留原值'):build(task,source,target,req)
    req.acknowledge_retained_external_settings=True;result=build(task,source,target,req)
    assert parse(result['content'],'workflow')['workflow']['environment_variables']==root['workflow']['environment_variables']
    assert 'private-original-setting' not in json.dumps(result['retained_conditions'])


def test_parallel_source_review_cannot_be_reused_for_target_but_fresh_target_review_can():
    from test_iteration import batch_plan,task as batch_task
    from test_preserved_iteration import native
    # Native source declarations and target declarations must bind different complete documents.
    p=batch_plan();root=native(p);n=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='batch');n['data'].update(is_parallel=True,parallel_nums=2)
    source_review={'batch':{'root_token':digest(root),'acknowledge_independence':True,'reason':'公开独立元素，无外部写入'}}
    task=batch_task(p);task.update(id='batch-task',revision=1,environment_id='source')
    source={'content':yaml.safe_dump(root),'reference_id':'ref','merge_token':'a'*64,'document_token':digest(root),'unresolved':0,'validation':validate_preserved(root,source_review)}
    assert source['validation']['valid'],source['validation']['errors']
    target={'id':'target','name':'目标','base_url':'http://127.0.0.1:8080','version':'1.17.1'}
    req=WorkflowMappingRequest(revision=1,reference_id='ref',merge_token='a'*64,document_token=digest(root),target_environment_id='target',parallel_reviews=source_review,acknowledge_unverified_target=True,acknowledge_retained_external_settings=True)
    draft=build(task,source,target,req);assert not draft['can_download'] and not draft['validation']['valid']
    req.target_document_token=draft['document_token'];req.target_parallel_reviews=source_review
    assert not build(task,source,target,req)['can_download']
    req.target_parallel_reviews={'batch':{**source_review['batch'],'root_token':draft['document_token']}}
    done=build(task,source,target,req);assert done['can_download'] and done['validation']['valid']
    req.additional_dependencies=['public/unused:1@new']
    with pytest.raises(ValueError,match='目标文件已变化'):build(task,source,target,req)


def test_live_api_is_local_only_and_connection_and_source_bound(client,monkeypatch):
    from test_dsl_roundtrip import prepared,capture
    from app import main
    task,root=prepared(client);task=capture(client,task,root);source=client.get(f"/api/tasks/{task['id']}/dsl-merge").json();target=create_env(client)
    request={'revision':task['revision'],'reference_id':source['reference_id'],'merge_token':source['merge_token'],'document_token':source['document_token'],'target_environment_id':target['id'],'expected_target_connection_revision':target.get('connection_revision'),'acknowledge_unverified_target':True,'acknowledge_retained_external_settings':True}
    path=f"/api/tasks/{task['id']}/workflow-environment-mapping/preview"
    before=copy.deepcopy(main.store.get('task',task['id']))
    def no_network(*args,**kwargs):raise AssertionError('No Dify adapter may be created')
    monkeypatch.setattr(main,'DifyClient',no_network)
    result=client.post(path,json=request);assert result.status_code==200,result.text
    assert result.json()['can_download'] and main.store.get('task',task['id'])==before
    for patch in ({'revision':task['revision']-1},{'document_token':'f'*64},{'expected_target_connection_revision':'changed'}):assert client.post(path,json={**request,**patch}).status_code==409
    response=client.post(path,content='{"revision":1,"revision":2,"private":"PRIVATE-INPUT"}',headers={'Content-Type':'application/json'});assert response.status_code==422 and 'PRIVATE-INPUT' not in response.text


def test_loop_target_requires_fresh_progress_and_stop_review():
    from test_preserved_loop import native,review
    from test_loop import task as loop_task
    root=native();task=loop_task();task.update(revision=1,environment_id='source')
    source={'content':yaml.safe_dump(root),'reference_id':'ref','merge_token':'a'*64,'document_token':digest(root),'unresolved':0,'validation':validate_preserved(root,loop_reviews=review(root))}
    target={'id':'target','name':'目标','base_url':'http://127.0.0.1:8080','version':'1.17.1'}
    request=WorkflowMappingRequest(revision=1,reference_id='ref',merge_token='a'*64,document_token=digest(root),target_environment_id='target',loop_reviews=review(root),acknowledge_unverified_target=True,acknowledge_retained_external_settings=True)
    draft=build(task,source,target,request);assert not draft['can_download'] and draft['target_loop_candidates']
    request.target_document_token=draft['document_token'];request.target_loop_reviews=review(root)
    assert not build(task,source,target,request)['can_download']
    output=parse(draft['content'],'workflow');request.target_loop_reviews=review(output)
    done=build(task,source,target,request);assert done['can_download'] and done['validation']['valid']
    source_nodes={n['id']:n for n in root['workflow']['graph']['nodes']};target_nodes={n['id']:n for n in output['workflow']['graph']['nodes']}
    assert source_nodes==target_nodes  # Actual guard code, AST, state updates and layout preserved.
