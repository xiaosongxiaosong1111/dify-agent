import copy
import pytest
import yaml
from test_api import client, approved
from test_dsl_roundtrip import prepared, capture, apply
from app import main
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest


def plan(**retrieval):
    return {'schema_version':1,'nodes':[
        {'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'paragraph'}]}},
        {'id':'retrieve','type':'knowledge-retrieval','config':{'query_variable_selector':['start','query'],'dataset_source':'node','dataset_ids':['actual-library'],**retrieval}},
        {'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['retrieve','result']}]}}
    ],'edges':[{'source':'start','target':'retrieve'},{'source':'retrieve','target':'end'}]}


def task(p=None, **config):return {'app_type':'workflow','configuration':config,'workflow_plan':p or plan()}


def native(p=None, **config):
    text,checked=compile_workflow_plan(task(p,**config));assert checked['valid'],checked['errors']
    root=yaml.safe_load(text)
    data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='retrieve')
    return root,data


def test_node_threshold_and_rerank_native_fields_preserved_without_execution():
    p=plan(score_threshold=.65,reranking_enable=True,reranking_model={'provider':'actual/rerank','model':'actual-reranker'},top_k=7)
    before=copy.deepcopy(p);root,data=native(p)
    assert data['multiple_retrieval_config']=={'top_k':7,'score_threshold':.65,'reranking_enable':True,'reranking_mode':'reranking_model','reranking_model':{'provider':'actual/rerank','model':'actual-reranker'}}
    assert data['dataset_ids']==['actual-library'] and 'dataset_source' not in data
    assert p==before and validate_preserved(root)['valid']


def test_explicit_independent_empty_library_does_not_fall_back_to_task():
    p=plan(dataset_ids=[])
    result=validate_plan(task(p,dataset_ids=['global-library']),p)
    assert not result['valid'] and any('不会回退' in e for e in result['errors'])


def test_task_library_source_and_legacy_behavior_are_distinct():
    p=plan(dataset_source='task');p['nodes'][1]['config'].pop('dataset_ids')
    _,data=native(p,dataset_ids=['global-library']);assert data['dataset_ids']==['global-library']
    p['nodes'][1]['config']['dataset_ids']=['ignored']
    assert not validate_plan(task(p,dataset_ids=['global-library']),p)['valid']
    p['nodes'][1]['config'].pop('dataset_source');p['nodes'][1]['config']['dataset_ids']=[]
    _,data=native(p,dataset_ids=['global-library']);assert data['dataset_ids']==['global-library']


@pytest.mark.parametrize('changes', [
    {'score_threshold':True},{'score_threshold':float('nan')},{'score_threshold':-.1},{'score_threshold':1.01},{'score_threshold':'0.5'},
    {'reranking_enable':1},{'reranking_enable':'true'},{'reranking_enable':True},{'reranking_enable':True,'reranking_model':{}},
    {'reranking_enable':True,'reranking_model':{'provider':'p','model':''}},
    {'reranking_enable':True,'reranking_model':{'provider':'p','model':'m','api_key':'synthetic-private-value'}},
    {'reranking_enable':False,'reranking_model':{'provider':'p','model':'m'}},
    {'dataset_source':None},{'dataset_source':{}},{'dataset_ids':['same','same']},
    {'metadata_filtering_mode':'manual'},{'retrieval_mode':'single'},{'weights':{}},{'search_method':'hybrid_search'},
])
def test_invalid_or_unadapted_choices_are_not_silently_ignored(changes):
    p=plan(**changes);result=validate_plan(task(p),p)
    assert not result['valid'] and not compile_workflow_plan(task(p))[0]
    assert 'synthetic-private-value' not in str(result)


@pytest.mark.parametrize('threshold',[None,0,1])
def test_threshold_boundary_and_disabled_rerank_compile(threshold):
    root,data=native(plan(score_threshold=threshold,reranking_enable=False))
    assert data['multiple_retrieval_config']['score_threshold']==threshold
    assert not data['multiple_retrieval_config']['reranking_enable'] and validate_preserved(root)['valid']


@pytest.mark.parametrize('mutation',['single','metadata','metadata_model','conditions','weights','rerank_mode','missing_model','disabled_model','attachment','vision'])
def test_preservation_rejects_unadapted_native_semantics_without_mutating_file(mutation):
    root,data=native()
    multi=data['multiple_retrieval_config']
    if mutation=='single':data['retrieval_mode']='single'
    elif mutation=='metadata':data['metadata_filtering_mode']='manual'
    elif mutation=='metadata_model':data['metadata_model_config']={'provider':'p','name':'m'}
    elif mutation=='conditions':data['metadata_filtering_conditions']={'conditions':[]}
    elif mutation=='weights':multi['weights']={'vector_setting':{}}
    elif mutation=='rerank_mode':multi['reranking_mode']='weighted_score'
    elif mutation=='missing_model':multi['reranking_enable']=True
    elif mutation=='disabled_model':multi['reranking_model']={'provider':'p','model':'m'}
    elif mutation=='attachment':data['query_attachment_selector']=['start','query']
    else:data['vision']={'enabled':True}
    before=copy.deepcopy(root);checked=validate_preserved(root)
    assert not checked['valid'] and root==before


def test_retained_native_threshold_change_confirms_into_final_artifact(client):
    t,_=prepared(client);p=plan(score_threshold=.3)
    response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':p});assert response.status_code==200,response.text
    t=response.json()
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert response.status_code==200,response.text;t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text;t=response.json()
    root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'))
    data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='retrieve');data['multiple_retrieval_config']['score_threshold']=.75
    t=capture(client,t,root);response,preview=apply(client,t);assert response.status_code==200,(response.text,preview['validation']);t=response.json()
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert response.status_code==200,response.text;t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    final=yaml.safe_load(main.artifact_path(response.json()).read_text(encoding='utf-8'));assert digest(final)==digest(root)


def test_rerank_impact_and_no_hit_warnings_are_visible_in_validation():
    p=plan(score_threshold=.5,reranking_enable=True,reranking_model={'provider':'p','model':'m'})
    result=validate_plan(task(p),p)
    assert result['valid'] and any('无命中行为' in w for w in result['warnings']) and any('可能的费用' in w for w in result['warnings'])


def test_global_configuration_proposal_explains_node_retrieval_is_unchanged():
    value=task(plan(score_threshold=.5),dify_model='',dify_model_provider='',dataset_ids=[])
    result=main.configuration_proposals.warnings(value,{'configuration':{}},{'models':[],'datasets':[]})
    assert any('节点独立选库、阈值及重排保持流程配置' in w and 'retrieve' in w for w in result)
