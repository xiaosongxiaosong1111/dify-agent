import ast,copy
import pytest,yaml
from test_api import client,approved
from app import main
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.loop import guard_specs,condition_expression,valid_scalar,PRIVATE_STAGNANT
from app.planning import normalize_draft,preserves_scope
from app.dsl_roundtrip import validate_preserved


def loop_plan():
    return {'schema_version':1,'nodes':[
        {'id':'start','type':'start','config':{'variables':[]}},
        {'id':'repeat','type':'loop','config':{
            'loop_count':3,'loop_variables':[{'label':'count','var_type':'number','value_type':'constant','value':0}],
            'nodes':[{'id':'increment','type':'code','config':{'code_language':'python3','code':'def main(count: float) -> dict:\n    return {"next_count": count + 1}\n','variables':[{'variable':'count','value_selector':['repeat','count']}],'outputs':{'next_count':{'type':'number','children':None}}}}],
            'updates':[{'variable':'count','value_selector':['increment','next_count']}],
            'break_conditions':[{'variable_selector':['repeat','count'],'varType':'number','comparison_operator':'≥','value':'3'}],
            'logical_operator':'and','failure_policy':'terminate','limit_policy':'fail_if_unmet','no_progress_limit':2,'progress_variables':['count'],'progress_reason':'计数每轮增加，代表固定三次技术处理进度；不是客户业务验收。'}},
        {'id':'end','type':'end','config':{'outputs':[{'variable':'count','value_selector':['repeat','count']}]}}
    ],'edges':[{'source':'start','target':'repeat'},{'source':'repeat','target':'end'}]}


def task(plan=None,**config):return {'app_type':'workflow','configuration':config,'workflow_plan':plan or loop_plan()}
def cfg(plan):return plan['nodes'][1]['config']


def test_loop_emits_actual_parent_scope_state_update_and_mandatory_stop_guard():
    p=loop_plan();before=copy.deepcopy(p);text,result=compile_workflow_plan(task(p));assert result['valid'],result['errors']
    graph=yaml.safe_load(text)['workflow']['graph'];nodes={n['id']:n for n in graph['nodes']};parent=nodes['repeat']['data']
    assert parent['type']=='loop' and parent['loop_count']==3 and parent['start_node_id']=='repeat__loop_start'
    assert parent['loop_variables'][0]['label']=='count' and parent['loop_variables'][1]['label']==PRIVATE_STAGNANT
    assert all(k not in parent for k in ('progress_reason','limit_policy','updates','nodes','no_progress_limit'))
    update=nodes['repeat__loop_update']['data'];assert update['type']=='assigner' and update['version']=='2'
    assert update['items'][0]=={'variable_selector':['repeat','count'],'input_type':'variable','operation':'over-write','value':['increment','next_count']}
    edges={(e['source'],e['target']) for e in graph['edges']}
    assert ('repeat','end') not in edges and ('repeat','repeat__loop_limit') in edges and ('repeat__loop_limit','end') in edges
    assert ('increment','repeat__loop_progress') in edges and ('repeat__loop_progress','repeat__loop_update') in edges
    assert ('repeat__loop_start','repeat__loop_input') in edges and ('repeat__loop_input','increment') in edges
    assert nodes['increment']['data']['loop_id']=='repeat' and nodes['repeat__loop_progress']['parentId']=='repeat'
    assert not nodes['repeat__loop_limit'].get('parentId') and p==before
    assert not validate_preserved(yaml.safe_load(text))['valid']


def test_generated_guards_are_syntax_checked_not_executed_and_goal_has_priority():
    progress,limit=guard_specs(loop_plan()['nodes'][1])
    for guard in (progress,limit):ast.parse(guard['config']['code'])
    code=progress['config']['code']
    assert 'completed or not same' in code and 'next_stagnant >= 2' in code
    assert '停止条件尚未满足' in limit['config']['code']
    assert [v['value_selector'] for v in progress['config']['variables']]==[['repeat','count'],['increment','next_count'],['repeat',PRIVATE_STAGNANT]]


@pytest.mark.parametrize('value',[None,True,0,101,'3',3.5])
def test_loop_count_requires_explicit_supported_integer(value):
    p=loop_plan();cfg(p)['loop_count']=value;assert not validate_plan(task(p),p)['valid']


@pytest.mark.parametrize('mutation',['missing_policy','skip_failure','return_unverified','progress_none','progress_repeat','progress_unknown','progress_reason','progress_limit','var_repeat','var_object','var_implicit','var_secret','var_reserved','wrong_initial_type','unknown_initial','missing_update','unknown_update','self_update','wrong_update_type','no_condition','wrong_condition_scope','wrong_condition_type','wrong_operator','numeric_expression','numeric_nan','wrong_boolean_value','unrelated_body','nested','branch','body_extra','sibling_future','leaked_body','reserved_node','loop_round','source_handle'])
def test_incomplete_unsupported_or_unsafe_loop_policy_does_not_compile(mutation):
    p=loop_plan();c=cfg(p);v=c['loop_variables'][0];step=c['nodes'][0];condition=c['break_conditions'][0]
    if mutation=='missing_policy':c.pop('limit_policy')
    elif mutation=='skip_failure':c['failure_policy']='continue'
    elif mutation=='return_unverified':c['limit_policy']='return_latest'
    elif mutation=='progress_none':c['progress_variables']=[]
    elif mutation=='progress_repeat':c['progress_variables']=['count','count']
    elif mutation=='progress_unknown':c['progress_variables']=['unknown']
    elif mutation=='progress_reason':c['progress_reason']=''
    elif mutation=='progress_limit':c['no_progress_limit']=1
    elif mutation=='var_repeat':c['loop_variables'].append(copy.deepcopy(v))
    elif mutation=='var_object':v['var_type']='object'
    elif mutation=='var_implicit':v.pop('value_type')
    elif mutation=='var_secret':v['label']='api_key'
    elif mutation=='var_reserved':v['label']=PRIVATE_STAGNANT
    elif mutation=='wrong_initial_type':v['value']='0'
    elif mutation=='unknown_initial':v.update(value_type='variable',value=['start','unknown'])
    elif mutation=='missing_update':c['updates']=[]
    elif mutation=='unknown_update':c['updates'][0]['variable']='unknown'
    elif mutation=='self_update':c['updates'][0]['value_selector']=['repeat','count']
    elif mutation=='wrong_update_type':step['config']['outputs']['next_count']['type']='string'
    elif mutation=='no_condition':c['break_conditions']=[]
    elif mutation=='wrong_condition_scope':condition['variable_selector']=['increment','next_count']
    elif mutation=='wrong_condition_type':condition['varType']='string'
    elif mutation=='wrong_operator':condition['comparison_operator']='contains'
    elif mutation=='numeric_expression':condition['value']='1 + 2'
    elif mutation=='numeric_nan':condition['value']='NaN'
    elif mutation=='wrong_boolean_value':v.update(var_type='boolean',value=False);condition.update(varType='boolean',comparison_operator='is',value='true')
    elif mutation=='unrelated_body':step['type']='http-request'
    elif mutation=='nested':step['type']='loop'
    elif mutation=='branch':step['type']='if-else'
    elif mutation=='body_extra':step['config']['retry_config']={}
    elif mutation=='sibling_future':step['config']['variables'][0]['value_selector']=['end','count']
    elif mutation=='leaked_body':p['nodes'][-1]['config']['outputs'][0]['value_selector']=['increment','next_count']
    elif mutation=='reserved_node':step['id']='repeat__loop_limit'
    elif mutation=='loop_round':step['config']['variables'][0]['value_selector']=['repeat','loop_round']
    else:p['edges'][-1]['source_handle']='failure'
    result=validate_plan(task(p),p);assert not result['valid'] and not compile_workflow_plan(task(p))[0]


@pytest.mark.parametrize('field,value',[('loop_variables',[None]),('loop_variables','bad'),('nodes',[None]),('nodes',[{'type':[]}]),('updates',[None]),('break_conditions',[None]),('logical_operator',{}),('progress_variables',[{}]),('loop_variables',[{'label':{},'var_type':'number','value_type':'constant','value':0}])])
def test_malformed_shape_returns_invalid_without_crashing(field,value):
    p=loop_plan();cfg(p)[field]=value;assert not validate_plan(task(p),p)['valid']


def test_literal_stop_text_cannot_become_guard_code():
    text='\"\n__import__(\"os\").system(\"not-executed\")\n'
    row={'variable_selector':['repeat','draft'],'varType':'string','comparison_operator':'is','value':text}
    expression=condition_expression([row],'and',{'draft':'v0'})
    tree=ast.parse(expression,mode='eval')
    assert not any(isinstance(n,ast.Call) for n in ast.walk(tree))


def test_numeric_and_boolean_initial_constants_are_strict_and_bounded():
    assert valid_scalar(0,'number') and valid_scalar(False,'boolean')
    assert not valid_scalar(True,'number') and not valid_scalar(10**500,'number') and not valid_scalar(float('inf'),'number')


def test_external_initial_reference_requires_known_matching_type():
    p=loop_plan();p['nodes'].insert(1,{'id':'seed','type':'code','config':{'code_language':'python3','code':'def main() -> dict:\n    return {"count": 1}\n','outputs':{'count':{'type':'number','children':None}}}})
    p['nodes'][2]['config']['loop_variables'][0].update(value_type='variable',value=['seed','count'])
    p['edges']=[{'source':'start','target':'seed'},{'source':'seed','target':'repeat'},{'source':'repeat','target':'end'}]
    assert compile_workflow_plan(task(p))[1]['valid']


def test_inner_llm_model_gate_and_history_exclusion():
    p=loop_plan();c=cfg(p)
    c['loop_variables']=[{'label':'draft','var_type':'string','value_type':'constant','value':'初始建议'}]
    c['nodes']=[{'id':'refine','type':'llm','config':{'user_prompt':'完善 {{#repeat.draft#}}'}}]
    c['updates']=[{'variable':'draft','value_selector':['refine','text']}];c['progress_variables']=['draft']
    c['break_conditions']=[{'variable_selector':['repeat','draft'],'varType':'string','comparison_operator':'contains','value':'完成'}]
    p['nodes'][-1]['config']['outputs']=[{'variable':'draft','value_selector':['repeat','draft']}]
    assert not compile_workflow_plan(task(p))[0]
    c['nodes'][0]['config']['model']={'provider':'actual/provider','name':'actual-model','mode':'chat','completion_params':{'temperature':.2,'max_tokens':256}}
    text,checked=compile_workflow_plan(task(p));assert checked['valid'],checked['errors']
    data=next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='refine')
    assert data['model']['name']=='actual-model' and 'memory' not in data
    p['nodes'][-1]={'id':'end','type':'answer','config':{'answer':'{{#repeat.draft#}}'}}
    value={**task(p,conversation_memory=True,memory_turns=3),'app_type':'advanced-chat'}
    text,checked=compile_workflow_plan(value);assert checked['valid'],checked['errors']
    data=next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='refine')
    assert 'memory' not in data


def test_loop_repair_cannot_change_stop_progress_or_update_contract():
    p=loop_plan();normalized,fixes=normalize_draft(p);assert normalized==p and not fixes and preserves_scope(p,normalized)
    changed=copy.deepcopy(p);cfg(changed)['loop_count']=4;assert not preserves_scope(p,changed)


def test_malformed_root_type_beside_loop_does_not_crash_normalization_or_validation():
    p=loop_plan();p['nodes'].append({'id':'bad','type':[],'config':{}})
    assert not validate_plan(task(p),p)['valid']
    assert normalize_draft(p)[0]==p


def test_loop_protection_error_is_a_hint_not_automatic_business_repair():
    from app.run_diagnostics import classify
    result=classify('Sierra 循环已达到最大轮数，但停止条件尚未满足')
    assert result['category']=='loop_control' and result['confidence']=='需核对' and '删除保护' in result['recommendation']


def test_api_loop_save_confirm_build_is_local_and_revision_bound(client):
    t=approved(client);response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':loop_plan()});assert response.status_code==200,response.text;t=response.json()
    assert not t['configuration_confirmed']
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert response.status_code==200,response.text;t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    assert not response.json()['dify_app_id'] and 'loop' in main.artifact_path(response.json()).read_text(encoding='utf-8')


def test_loop_requirements_add_specific_intake_topic_and_keep_new_task_gate(client):
    t=client.post('/api/tasks',json={'name':'循环准入技术样例','app_type':'workflow'}).json()
    req={key:'固定循环计数技术样例：初始0，每轮加1，≥3停止，最多3轮，无进展2轮失败，次数未达目标失败；仅技术计数。' for key in main.REQ_KEYS}
    t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':req}).json()
    state=client.get(f"/api/tasks/{t['id']}/intake").json()
    assert 'loop_policy' in {row['id'] for row in state['standard']}
    assert client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':'requirements'}).status_code==422
    answers={row['id']:req.get(row['id'],'计数是固定三次处理的明确技术进度；停止、类型、最大轮数与初始值按上述规则；非客户验收。') for row in state['standard']}
    response=client.post(f"/api/tasks/{t['id']}/intake/manual",json={'revision':t['revision'],'context_token':state['context_token'],'answers':answers,'acknowledge_review':True})
    assert response.status_code==200,response.text
