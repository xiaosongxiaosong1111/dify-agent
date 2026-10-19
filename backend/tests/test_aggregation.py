import copy
import yaml
import pytest

from test_api import client,approved
from app.workflow_plan import validate_plan,compile_workflow_plan as native_compile
from app import main
from app.reference_dsl import summarize


def merge_plan(app_type='workflow'):
    query=['sys','query'] if app_type=='advanced-chat' else ['start','query']
    return {'schema_version':1,'nodes':[
        {'id':'start','type':'start','config':{'variables':[] if app_type=='advanced-chat' else [{'variable':'query','type':'paragraph','required':False,'default':''}]}},
        {'id':'route','type':'if-else','config':{'cases':[{'case_id':'missing','logical_operator':'and','conditions':[{'variable_selector':query,'varType':'string','comparison_operator':'empty','value':''}]}]}},
        {'id':'ask','type':'template-transform','config':{'template':'请补充输入内容。','variables':[]}},
        {'id':'respond','type':'template-transform','config':{'template':'已收到输入。','variables':[]}},
        {'id':'merge','type':'variable-aggregator','config':{'variables':[['ask','output'],['respond','output']],'output_type':'string','selection_mode':'first_available'}},
        {'id':'answer','type':'answer','config':{'answer':'{{#merge.output#}}'}} if app_type=='advanced-chat' else {'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['merge','output']}]}}
    ],'edges':[{'source':'start','target':'route'},{'source':'route','target':'ask','source_handle':'missing'},{'source':'route','target':'respond','source_handle':'false'},{'source':'ask','target':'merge'},{'source':'respond','target':'merge'},{'source':'merge','target':'answer' if app_type=='advanced-chat' else 'end'}]}


def cfg(plan):return next(n['config'] for n in plan['nodes'] if n['id']=='merge')
def task(app_type='workflow'):return {'app_type':app_type,'configuration':{}}

def compile_workflow_plan(t,plan):return native_compile({**t,'workflow_plan':plan})


@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_branch_outputs_can_merge_without_relaxing_normal_refs(mode):
    plan=merge_plan(mode);text,result=compile_workflow_plan(task(mode),plan)
    assert result['valid'],result['errors'];root=yaml.safe_load(text)
    data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='merge')
    assert data['variables']==[['ask','output'],['respond','output']] and data['output_type']=='string'
    assert data['advanced_settings']=={'group_enabled':False,'groups':[]} and 'selection_mode' not in data
    assert any('0／false' in w for w in result['warnings'])
    # Ordinary terminal variables still must exist on every path.
    if mode=='workflow':plan['nodes'][-1]['config']['outputs'][0]['value_selector']=['ask','output']
    else:plan['nodes'][-1]['config']['answer']='{{#ask.output#}}'
    assert not validate_plan(task(mode),plan)['valid']


@pytest.mark.parametrize('patch',[{'variables':[]},{'variables':None},{'variables':[['ask','output']]*13},{'variables':[['ask','output'],['ask','output']]},{'variables':[['ask']]},{'variables':[None]},{'variables':[['ghost','output']]},{'variables':[['merge','output']]},{'variables':[['end','output']]},{'variables':[['ask','missing']]},{'output_type':'number'},{'output_type':None},{'output_type':{}},{'selection_mode':'first_nonempty'},{'selection_mode':None},{'groups':[]},{'extra':'silent'}])
def test_invalid_or_unknown_aggregation_configuration_rejected(patch):
    plan=merge_plan();cfg(plan).update(patch)
    text,result=compile_workflow_plan(task(),plan);assert not result['valid'] and not text


def test_missing_default_branch_candidate_rejected():
    plan=merge_plan();cfg(plan)['variables']=[['ask','output']]
    result=validate_plan(task(),plan);assert not result['valid'] and any('没有任何候选' in e for e in result['errors'])


def test_global_fallback_explicitly_covers_other_branch():
    plan=merge_plan();cfg(plan)['variables']=[['ask','output'],['start','query']]
    assert validate_plan(task(),plan)['valid']
    cfg(plan)['variables'].reverse();text,result=compile_workflow_plan(task(),plan);assert result['valid']
    assert next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='merge')['variables'][0]==['start','query']


def test_chatflow_sys_fallback_and_workflow_rejection():
    plan=merge_plan('advanced-chat');cfg(plan)['variables']=[['ask','output'],['sys','query']]
    assert validate_plan(task('advanced-chat'),plan)['valid']
    plan=merge_plan();cfg(plan)['variables']=[['ask','output'],['sys','query']]
    assert not validate_plan(task(),plan)['valid']


@pytest.mark.parametrize('output_type',['number','boolean','object','array[string]','array[number]','array[object]'])
def test_declared_code_types_must_match_on_both_paths(output_type):
    plan=merge_plan()
    for node in plan['nodes']:
        if node['id'] in {'ask','respond'}:node.update(type='code',config={'code_language':'python3','code':'def main() -> dict:\n    return {"result": None}\n','variables':[],'outputs':{'result':{'type':output_type,'children':None}}})
    cfg(plan).update(variables=[['ask','result'],['respond','result']],output_type=output_type)
    assert validate_plan(task(),plan)['valid']
    # The code above is only syntax checked; its declared type is not runtime proof.
    plan['nodes'][2]['config']['outputs']['result']['type']='string'
    assert not validate_plan(task(),plan)['valid']


def test_aggregation_chain_keeps_common_output_available():
    plan=merge_plan();plan['nodes'].insert(-1,{'id':'second','type':'variable-aggregator','config':{'variables':[['merge','output']],'output_type':'string','selection_mode':'first_available'}})
    plan['edges'][-1]['target']='second';plan['edges'].append({'source':'second','target':'end'});plan['nodes'][-1]['config']['outputs'][0]['value_selector']=['second','output']
    assert validate_plan(task(),plan)['valid']


def test_nonancestor_candidate_rejected_even_with_valid_fallback():
    plan=merge_plan();plan['nodes'].append({'id':'other_end','type':'end','config':{'outputs':[{'variable':'value','value_selector':['start','query']}]}});plan['edges'].append({'source':'start','target':'other_end'});cfg(plan)['variables']=[['other_end','value'],['start','query']]
    assert not validate_plan(task(),plan)['valid']


def test_saved_plan_confirmation_and_source_summary(client):
    t=approved(client);result=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':merge_plan()});assert result.status_code==200,result.text
    t=result.json();assert t['requirements_confirmed'] and not t['configuration_confirmed']
    assert not t['runs'] and not t['dify_app_id']
    result=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':'configuration'});assert result.status_code==200,result.text;t=result.json()
    result=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert result.status_code==200,result.text;t=result.json()
    text=main.artifact_path(t).read_text(encoding='utf-8');summary=summarize(text,'workflow','merge.yaml')
    assert next(n for n in summary['nodes'] if n['id']=='merge')['label']=='变量聚合'
    assert any('分组' in w for w in summary['warnings'])
