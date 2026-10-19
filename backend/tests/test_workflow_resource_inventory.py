import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app.workflow_resource_inventory import inventory
from app.dsl_roundtrip import digest,preview

A='a1111111-1111-4111-8111-111111111111'
B='b2222222-2222-4222-8222-222222222222'


def root():
    return {'kind':'app','version':'0.7.0','app':{'mode':'workflow'},'workflow':{'graph':{'nodes':[
        {'id':'s','data':{'type':'start'}},
        {'id':'m1','parentId':'batch','data':{'type':'llm','model':{'provider':'public/provider','name':'public-model','mode':'chat','completion_params':{'temperature':.2,'max_tokens':512}},'prompt_template':'PRIVATE-PROMPT'}},
        {'id':'m2','data':{'type':'question-classifier','model':{'provider':'public/provider','name':'public-model','mode':'chat'}}},
        {'id':'r','data':{'type':'knowledge-retrieval','dataset_ids':[A,B],'retrieval_mode':'multiple','multiple_retrieval_config':{'reranking_enable':True,'reranking_model':{'provider':'public/reranker','model':'public-rerank'}}}},
        {'id':'h','data':{'type':'http-request','url':'https://private.example.invalid/path','body':'PRIVATE-BODY'}},
        {'id':'c','data':{'type':'code','code':'PRIVATE-CODE'}},
    ],'edges':[]},'environment_variables':[{'name':'PRIVATE_ENV_NAME','value_type':'string','value':'PRIVATE-VALUE'},{'name':'TARGET_AUTH','value_type':'secret','value':''}]},
    'dependencies':[{'type':'marketplace','value':{'marketplace_plugin_unique_identifier':'public/provider:1@hash'}}]}


def check(value):
    token=digest(value);before=copy.deepcopy(value);result=inventory(value,token);assert value==before
    if result['available']:
        assert result['document_token']==token and result['verification']=='source_resource_inventory_only'
        assert all(result[k] is False for k in ('target_resources_verified','platform_verified','business_verified','task_modified'))
    return result


def test_all_occurrences_and_container_location_preserved_without_bodies_or_values():
    value=check(root());assert value['available'] and value['nodes_scanned']==6 and not value['blockers']
    models=[e for e in value['entries'] if e['category']=='chat_model'];assert len(models)==2
    assert 'batch' in models[0]['location'] and models[0]['identifiers']==models[1]['identifiers']
    raw=json.dumps(value);assert all(text not in raw for text in ('PRIVATE-PROMPT','PRIVATE-BODY','PRIVATE-CODE','PRIVATE-VALUE','private.example.invalid','completion_params'))
    assert 'PRIVATE_ENV_NAME' in raw and 'TARGET_AUTH' in raw
    assert next(e for e in value['entries'] if e['category']=='datasets')['identifiers']==[A,B]
    assert any(e['category']=='reranking_model' for e in value['entries'])


@pytest.mark.parametrize('kind',['llm','question-classifier','parameter-extractor'])
def test_model_nodes_are_independent_and_missing_identifier_is_explicit(kind):
    doc=root();doc['workflow']['graph']['nodes']=[{'id':'m','data':{'type':kind,'model':{'provider':'known','mode':'chat'}}}]
    result=check(doc);assert result['available'] and result['blockers'] and not any(e['category']=='chat_model' for e in result['entries'])


@pytest.mark.parametrize('field,value',[('dataset_ids',[]),('dataset_ids',[A,A]),('dataset_ids',['source-label']),('retrieval_mode','single'),('single_retrieval_config',{}),('metadata_model_config',{}),('metadata_filtering_mode','automatic')])
def test_unsupported_retrieval_resource_cannot_silently_disappear(field,value):
    doc=root();doc['workflow']['graph']['nodes'][3]['data'][field]=value
    result=check(doc);assert result['available'] and result['blockers']


@pytest.mark.parametrize('patch',[{'weights':{}},{'reranking_mode':'weighted_score'},{'reranking_enable':'true'},{'reranking_model':{}},{'reranking_enable':False}])
def test_unknown_rerank_or_stale_disabled_config_requires_review(patch):
    doc=root();doc['workflow']['graph']['nodes'][3]['data']['multiple_retrieval_config'].update(patch)
    assert check(doc)['blockers']


def test_explicitly_disabled_reranker_is_not_invented():
    doc=root();doc['workflow']['graph']['nodes'][3]['data']['multiple_retrieval_config']={'reranking_enable':False}
    result=check(doc);assert not result['blockers'] and not any(e['category']=='reranking_model' for e in result['entries'])


@pytest.mark.parametrize('mutation',['duplicate_node','invalid_node','invalid_parent','unknown_mode','oversize_nodes','bad_variables','duplicate_variable','nonempty_secret','invalid_dependencies'])
def test_bad_structure_is_not_returned_as_partial_inventory(mutation):
    doc=root();workflow=doc['workflow'];nodes=workflow['graph']['nodes']
    if mutation=='duplicate_node':nodes.append(copy.deepcopy(nodes[0]))
    if mutation=='invalid_node':nodes[0]=None
    if mutation=='invalid_parent':nodes[1]['parentId']={}
    if mutation=='unknown_mode':doc['app']['mode']='agent'
    if mutation=='oversize_nodes':workflow['graph']['nodes']=[{}]*1001
    if mutation=='bad_variables':workflow['environment_variables']={}
    if mutation=='duplicate_variable':workflow['environment_variables'].append(copy.deepcopy(workflow['environment_variables'][0]))
    if mutation=='nonempty_secret':workflow['environment_variables'][1]['value']='PRIVATE-SECRET'
    if mutation=='invalid_dependencies':doc['dependencies']={}
    result=check(doc);assert result['available'] is False and 'entries' not in result and 'PRIVATE-SECRET' not in json.dumps(result)


@pytest.mark.parametrize('kind',['human-input','trigger-schedule','unknown-plugin-node'])
def test_explicit_platform_and_unknown_node_conditions(kind):
    doc=root();doc['workflow']['graph']['nodes']=[{'id':'node','data':{'type':kind}}]
    result=check(doc);assert result['available']
    if kind=='unknown-plugin-node':assert result['blockers']
    else:assert result['entries'][0]['category'] in {'human_review','schedule'} and '发布' in result['entries'][0]['requirement']


def test_chatflow_and_empty_graph_never_claim_no_target_dependencies():
    doc=root();doc['app']['mode']='advanced-chat';doc['workflow']['graph']['nodes']=[];doc['workflow']['environment_variables']=[];doc['dependencies']=[]
    result=check(doc);assert result['mode']=='advanced-chat' and result['entries']==[] and result['warnings']


@pytest.mark.parametrize('name',['password','api_key','access-token'])
def test_credential_named_plain_variable_is_not_treated_as_safe_to_copy(name):
    doc=root();doc['workflow']['environment_variables']=[{'name':name,'value_type':'string','value':'PRIVATE-STRING-CREDENTIAL'}]
    result=check(doc);assert result['available'] and result['blockers'] and 'PRIVATE-STRING-CREDENTIAL' not in json.dumps(result)


@pytest.mark.parametrize('value',['constructor','public/plugin','public/plugin:bad version'])
def test_incomplete_marketplace_identifier_is_not_offered_as_a_supported_mapping(value):
    doc=root();doc['dependencies'][0]['value']['marketplace_plugin_unique_identifier']=value
    assert check(doc)['blockers']


def test_saved_preview_api_inventory_read_only_and_preserved_code(client):
    from test_dsl_roundtrip import prepared,capture
    from app import main
    task,doc=prepared(client);doc['workflow']['graph']['nodes'][1]['data']['code']+='\n# manual private code'
    task=capture(client,task,doc);before=main.store.get('task',task['id'])
    response=client.get(f"/api/tasks/{task['id']}/dsl-merge");assert response.status_code==200,response.text
    result=response.json();inv=result['workflow_resource_inventory']
    assert inv['available'] and inv['document_token']==result['document_token'] and inv['nodes_scanned']==3
    assert [e['category'] for e in inv['entries']]==['code_runtime']
    assert 'manual private code' in result['content'] and 'manual private code' not in json.dumps(inv)
    assert main.store.get('task',task['id'])==before


from test_api import client
