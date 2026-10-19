import copy
import pytest,yaml
from test_api import client
from test_container_conversation_read import plan as body_plan,task
from test_scalar_conversation_state import scalar_plan
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,digest
from test_preserved_loop import review


def consumers(owner='root'):
    p=scalar_plan('number',0) if owner=='root' else body_plan(owner)
    name='topic' if owner=='root' else 'count'
    if owner!='root':
        cv=p['conversation_variables'][0];p['conversation_variables'] += [{**cv,'name':'count','var_type':'number','initial_value':0},{**cv,'name':'flag','var_type':'boolean','initial_value':False}]
    code={'id':'cv-code','type':'code','config':{'code_language':'python3','code':'def main(count):\n    return {"result": str(count)}','variables':[{'variable':'count','value_selector':['conversation',name]}],'outputs':{'result':{'type':'string'}}}}
    template={'id':'cv-template','type':'template-transform','config':{'template':'{{ count }}','variables':[{'variable':'count','value_type':'number','value_selector':['conversation',name]}]}}
    if owner=='root':
        gate={'id':'cv-limit','type':'if-else','config':{'cases':[{'case_id':'over','logical_operator':'and','conditions':[{'variable_selector':['conversation',name],'varType':'number','comparison_operator':'≥','value':'3'}]}]}}
        p['nodes']=[p['nodes'][0],code,template,gate,{'id':'over','type':'answer','config':{'answer':'达到阈值'}},{'id':'keep','type':'answer','config':{'answer':'继续'}}]
        p['edges']=[{'source':'start','target':'cv-code'},{'source':'cv-code','target':'cv-template'},{'source':'cv-template','target':'cv-limit'},{'source':'cv-limit','target':'over','source_handle':'over'},{'source':'cv-limit','target':'keep','source_handle':'false'}]
    else:
        cfg=next(n for n in p['nodes'] if n['type']==owner)['config'];child=cfg['nodes'][-1]
        child['config']['variables']=[v for v in child['config']['variables'] if v['variable']!='hits'];cfg['nodes']=[code,template,child]
    return p


@pytest.mark.parametrize('owner',['root','iteration','loop'])
def test_code_and_typed_template_read_state_without_rewriting_defaults_or_controls(owner):
    p=consumers(owner);before=copy.deepcopy(p);text,result=compile_workflow_plan(task(p));assert result['valid'],result
    root=yaml.safe_load(text);template=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='cv-template')
    assert template['data']['variables'][0]['value_type']=='number'
    assert template['data']['variables'][0]['value_selector']==['conversation','topic' if owner=='root' else 'count']
    stamp=digest(root);checked=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None)
    assert checked['valid'],checked
    assert digest(root)==stamp and p==before


@pytest.mark.parametrize('owner',['root','iteration','loop'])
@pytest.mark.parametrize('wrong',['string','boolean',None])
def test_template_binding_declared_type_must_match_real_cv_in_all_scopes(owner,wrong):
    p=consumers(owner);nodes=p['nodes'] if owner=='root' else next(n for n in p['nodes'] if n['type']==owner)['config']['nodes']
    binding=next(n for n in nodes if n['id']=='cv-template')['config']['variables'][0]
    if wrong is None:binding.pop('value_type')
    else:binding['value_type']=wrong
    before=copy.deepcopy(p);checked=validate_plan(task(p),p)
    assert not checked['valid'] and p==before and any('value_type' in e for e in checked['errors'])


def test_root_condition_state_type_mismatch_is_not_a_virtual_numeric_source():
    p=consumers();p['nodes'][3]['config']['cases'][0]['conditions'][0]['varType']='boolean'
    checked=validate_plan(task(p),p);assert not checked['valid']
