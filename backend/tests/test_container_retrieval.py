import copy
import pytest
import yaml
from test_api import client
from test_iteration import batch_plan
from test_loop import loop_plan
from test_preserved_loop import review
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved


def plan(owner='iteration',mode='workflow'):
    p=batch_plan() if owner=='iteration' else loop_plan()
    parent=next(n for n in p['nodes'] if n['type']==owner);cfg=parent['config']
    if owner=='loop':
        p['nodes'][0]['config']['variables']=[{'variable':'query','type':'paragraph','required':True}]
    query=[parent['id'],'item'] if owner=='iteration' else ['start','query']
    retrieval={'id':'search','type':'knowledge-retrieval','config':{'query_variable_selector':query,'dataset_source':'node','dataset_ids':['fixture-dataset'],'top_k':4,'score_threshold':0.5,'reranking_enable':False}}
    child=cfg['nodes'][0];cfg['nodes']=[retrieval,child]
    # Bind a typed array into the final code, without executing code on this host.
    child['config']['variables'].append({'variable':'hits','value_selector':['search','result']})
    return p


def task(p):return {'name':'本机知识正文技术夹具','app_type':'workflow','configuration':{},'workflow_plan':p}


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_retrieval_in_body_emits_scoped_query_actual_settings_and_preserves_raw_edits(owner):
    p=plan(owner);before=copy.deepcopy(p)
    content,result=compile_workflow_plan(task(p));assert result['valid'],result['errors']
    root=yaml.safe_load(content);raw=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='search');data=raw['data']
    assert raw['parentId']==('batch' if owner=='iteration' else 'repeat')
    assert data['query_variable_selector']==(['batch','item'] if owner=='iteration' else ['start','query'])
    assert data['dataset_ids']==['fixture-dataset'] and data['multiple_retrieval_config']['top_k']==4
    assert data['multiple_retrieval_config']['score_threshold']==0.5
    assert 'memory' not in data and p==before
    raw['position']['x']=888;data['multiple_retrieval_config']['top_k']=7
    reviews=review(root) if owner=='loop' else None
    checked=validate_preserved(root,loop_reviews=reviews);assert checked['valid'],checked['errors']
    assert raw['position']['x']==888 and data['multiple_retrieval_config']['top_k']==7


@pytest.mark.parametrize('owner,selector',[('iteration',['batch','index']),('loop',['repeat','count'])])
def test_scoped_numeric_query_is_rejected_instead_of_using_virtual_paragraph_type(owner,selector):
    p=plan(owner);parent=next(n for n in p['nodes'] if n['type']==owner)
    parent['config']['nodes'][0]['config']['query_variable_selector']=selector
    checked=validate_plan(task(p),p);assert not checked['valid']
    assert any('非文字类型' in error for error in checked['errors'])


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_body_query_cannot_fall_back_to_application_default(owner):
    p=plan(owner);parent=next(n for n in p['nodes'] if n['type']==owner)
    del parent['config']['nodes'][0]['config']['query_variable_selector']
    checked=validate_plan(task(p),p);assert not checked['valid']
    assert any('不继承应用默认问题' in error for error in checked['errors'])


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_invalid_or_unconfirmed_retrieval_settings_are_not_removed(owner):
    p=plan(owner);parent=next(n for n in p['nodes'] if n['type']==owner);cfg=parent['config']['nodes'][0]['config']
    cfg['reranking_enable']=True;cfg['reranking_model']={'provider':'','model':''};cfg['metadata_filtering_mode']='manual'
    before=copy.deepcopy(p);checked=validate_plan(task(p),p)
    assert not checked['valid'] and p==before


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_body_llm_binds_real_retrieval_context_without_history(owner):
    p=plan(owner);cfg=next(n for n in p['nodes'] if n['type']==owner)['config']
    prompt={'id':'respond','type':'llm','config':{'system_prompt':'资料无命中时明确说明，按开发样例规则回答。{{#context#}}','user_prompt':'处理本项或本轮问题','context_variable_selector':['search','result'],'model':{'provider':'fixture/provider','name':'fixture-model','mode':'chat','completion_params':{'temperature':0,'max_tokens':64}}}}
    if owner=='iteration':
        cfg['nodes']=[cfg['nodes'][0],prompt];cfg['output_selector']=['respond','text']
    else:cfg['nodes'].insert(1,prompt)
    text,checked=compile_workflow_plan(task(p));assert checked['valid'],checked['errors']
    root=yaml.safe_load(text);raw=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='respond')
    assert raw['data']['context']['variable_selector']==['search','result']
    assert 'memory' not in raw['data']


def test_query_semantics_and_scope_eleven_require_new_explicit_acknowledgement(client):
    from app.case_dsl_semantics import summary
    from test_assistant_routing import setup,enable,state
    from app import main
    p=plan();content,checked=compile_workflow_plan(task(p));assert checked['valid']
    node=next(n for n in summary(yaml.safe_load(content))['nodes'] if n['id']=='search')
    assert node['parent_id']=='batch' and node['config']['query_variable_selector']==['batch','item']
    saved,provider,light=setup(client)
    assert enable(client,saved,light,scope_version=10).status_code==409
    assert enable(client,saved,light).status_code==200
    old=main.routing.get(saved['id']);old['scope_version']=10;main.store.put('assistant_routing',saved['id'],old)
    current=state(client,saved)
    assert current['required_scope_version']==18 and current['blocker'] and '知识检索的实际问题来源' in current['scope_note']


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_explicit_dag_query_cannot_read_future_or_sibling_output(owner):
    p=plan(owner);cfg=next(n for n in p['nodes'] if n['type']==owner)['config'];last=cfg['nodes'][1]
    cfg.update(entry_node_id='search',edges=[{'source':'search','target':last['id']}])
    assert validate_plan(task(p),p)['valid']
    cfg['nodes'][0]['config']['query_variable_selector']=[last['id'],next(iter(last['config']['outputs']))]
    assert not validate_plan(task(p),p)['valid']


def test_object_item_needs_explicit_text_conversion_before_retrieval():
    p=plan();cfg=p['nodes'][2]['config'];cfg['iterator_input_type']='array[object]'
    p['nodes'][1]['config']['outputs']['items']['type']='array[object]'
    checked=validate_plan(task(p),p)
    assert not checked['valid'] and any('非文字类型' in error for error in checked['errors'])


def test_parallel_retrieval_retains_explicit_concurrency_and_independence():
    p=plan();cfg=p['nodes'][2]['config']
    cfg.update(is_parallel=True,parallel_nums=4,parallel_safe=True,parallel_reason='技术夹具逐项检索，不更改库；实际限流／收费须确认。')
    text,checked=compile_workflow_plan(task(p));assert checked['valid'],checked['errors']
    parent=next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='batch')
    assert parent['is_parallel'] is True and parent['parallel_nums']==4 and parent['error_handle_mode']=='terminated'
    del cfg['parallel_reason'];assert not validate_plan(task(p),p)['valid']


def test_loop_actual_string_state_query_and_complete_rerank_remain_declared():
    p=plan('loop');cfg=p['nodes'][1]['config'];search=cfg['nodes'][0]
    cfg['loop_variables'].append({'label':'query','var_type':'string','value_type':'constant','value':'开发用明确问题'})
    echo={'id':'echo','type':'template-transform','config':{'template':'{{ query }}','variables':[{'variable':'query','value_selector':['repeat','query'],'value_type':'string'}]}}
    cfg['nodes'].insert(1,echo);cfg['updates'].append({'variable':'query','value_selector':['echo','output']})
    search['config'].update(query_variable_selector=['repeat','query'],reranking_enable=True,reranking_model={'provider':'fixture/rerank','model':'fixture-rerank'},score_threshold=0)
    text,checked=compile_workflow_plan(task(p));assert checked['valid'],checked['errors']
    data=next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='search')
    assert data['query_variable_selector']==['repeat','query'] and data['multiple_retrieval_config']['score_threshold']==0
    assert data['multiple_retrieval_config']['reranking_model']=={'provider':'fixture/rerank','model':'fixture-rerank'}


@pytest.mark.parametrize('owner',['iteration','loop'])
@pytest.mark.parametrize('kind,field',[('knowledge-retrieval','result'),('llm','usage'),('code','unknown')])
def test_external_array_object_or_unknown_query_type_does_not_become_virtual_text(owner,kind,field):
    p=plan(owner);parent=next(n for n in p['nodes'] if n['type']==owner)
    query=['start','items_json' if owner=='iteration' else 'query']
    if kind=='knowledge-retrieval':cfg={'query_variable_selector':query,'dataset_source':'node','dataset_ids':['fixture-library']}
    elif kind=='llm':cfg={'system_prompt':'开发样例','user_prompt':'明确问题','model':{'provider':'fixture/provider','name':'fixture-model','mode':'chat','completion_params':{'temperature':0,'max_tokens':64}}}
    else:cfg={'code_language':'python3','code':'def main() -> dict:\n    return {"unknown": "开发样例"}\n','variables':[],'outputs':{'unknown':{'type':None}}}
    p['nodes'].insert(p['nodes'].index(parent),{'id':'outer','type':kind,'config':cfg})
    entrance=next(edge for edge in p['edges'] if edge['target']==parent['id']);previous=entrance['source'];entrance['source']='outer';p['edges'].append({'source':previous,'target':'outer'})
    parent['config']['nodes'][0]['config']['query_variable_selector']=['outer',field]
    checked=validate_plan(task(p),p)
    assert not checked['valid']
    assert any('非文字类型' in error or '须明确文字问题来源类型' in error for error in checked['errors'])
