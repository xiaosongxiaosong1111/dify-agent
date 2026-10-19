import copy
import pytest,yaml
from test_api import client
from test_container_retrieval import plan as retrieval_plan
from test_container_http_read import plan as http_plan
from test_preserved_loop import review
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest


def plan(owner='iteration'):
    p=retrieval_plan(owner);p['nodes'][0]['config']['variables']=[];p['nodes'][-1].update(type='answer',config={'answer':'处理结果已返回'})
    if owner=='iteration':p['nodes'][1]['config']['variables'][0]['value_selector']=['sys','query']
    p['conversation_variables']=[{'name':'query','var_type':'string','initial_value':'开发问题','description':'本会话查询','persistence_policy':'per_conversation','unwritten_policy':'retain_current'}]
    cfg=next(n for n in p['nodes'] if n['type']==owner)['config'];cfg['nodes'][0]['config']['query_variable_selector']=['conversation','query']
    return p


def task(p):return {'app_type':'advanced-chat','configuration':{},'workflow_plan':p}


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_container_retrieval_reads_current_declared_string_and_keeps_native_selector(owner):
    p=plan(owner);before=copy.deepcopy(p);content,checked=compile_workflow_plan(task(p));assert checked['valid'],checked
    root=yaml.safe_load(content);search=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='search')
    assert search['data']['query_variable_selector']==['conversation','query'] and p==before
    stamp=digest(root);checked=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None)
    assert checked['valid'],checked
    assert digest(root)==stamp


@pytest.mark.parametrize('owner',['iteration','loop'])
@pytest.mark.parametrize('fault',['unknown','number','boolean','nested_name','body_write'])
def test_body_state_reads_require_real_declared_type_and_never_allow_shared_writes(owner,fault):
    p=plan(owner);parent=next(n for n in p['nodes'] if n['type']==owner);cfg=parent['config']
    if fault=='unknown':cfg['nodes'][0]['config']['query_variable_selector']=['conversation','missing']
    elif fault in ('number','boolean'):p['conversation_variables'][0].update(var_type=fault,initial_value=0 if fault=='number' else False)
    elif fault=='nested_name':cfg['nodes'][-1]['id']='conversation'
    else:cfg['nodes'][0]={'id':'shared-write','type':'assigner','config':{'items':[{'variable_selector':['conversation','query'],'input_type':'constant','operation':'over-write','value':'不要共享写'}]}}
    before=copy.deepcopy(p);checked=validate_plan(task(p),p);assert not checked['valid'] and p==before


def test_loop_initializer_reads_matching_conversation_number_without_changing_original_reference():
    p=plan('loop');p['conversation_variables'].append({'name':'count','var_type':'number','initial_value':0,'description':'本会话计数','persistence_policy':'per_conversation','unwritten_policy':'retain_current'})
    cfg=next(n for n in p['nodes'] if n['type']=='loop')['config'];cfg['loop_variables'][0].update(value_type='variable',value=['conversation','count'])
    content,checked=compile_workflow_plan(task(p));assert checked['valid'],checked
    root=yaml.safe_load(content);parent=next(n for n in root['workflow']['graph']['nodes'] if n['data']['type']=='loop');assert parent['data']['loop_variables'][0]['value']==['conversation','count']
    checked=validate_preserved(root,loop_reviews=review(root));assert checked['valid'],checked
    p['conversation_variables'][-1].update(var_type='boolean',initial_value=False);assert not validate_plan(task(p),p)['valid']


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_template_body_cv_binding_uses_exact_boolean_type_instead_of_virtual_paragraph(owner):
    p,parent,http=http_plan(owner,'advanced-chat');p['conversation_variables']=[{'name':'flag','var_type':'boolean','initial_value':False,'description':'布尔条件','persistence_policy':'per_conversation','unwritten_policy':'retain_current'}]
    cfg=parent['config'];template={'id':'cv-template','type':'template-transform','config':{'template':'{{ flag }}','variables':[{'variable':'flag','value_selector':['conversation','flag'],'value_type':'boolean'}]}};cfg['nodes'].insert(1,template)
    content,checked=compile_workflow_plan(task(p));assert checked['valid'],checked
    root=yaml.safe_load(content);node=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='cv-template');assert node['data']['variables'][0]['value_selector']==['conversation','flag']
    template['config']['variables'][0]['value_type']='string';checked=validate_plan(task(p),p);assert not checked['valid']
