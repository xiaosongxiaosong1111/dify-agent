import copy
import pytest
import yaml
from test_api import client, approved
from test_iteration import batch_plan, llm_body, iteration
from app import main
from app.workflow_plan import compile_workflow_plan, validate_plan
from app.model_parameters import needs_task_model
from app.dsl_roundtrip import validate_preserved


def chosen(provider='actual/provider',name='small-model',**params):
    return {'provider':provider,'name':name,'mode':'chat','completion_params':{'temperature':.1,'max_tokens':256,**params}}


def plan():
    return {'schema_version':1,'nodes':[
        {'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'paragraph'}]}},
        {'id':'classify','type':'llm','config':{'user_prompt':'{{#start.query#}}','model':chosen()}},
        {'id':'answer','type':'llm','config':{'user_prompt':'{{#classify.text#}}','model':chosen('other/provider','large-model',temperature=.3,max_tokens=1024)}},
        {'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['answer','text']}]}}
    ],'edges':[{'source':'start','target':'classify'},{'source':'classify','target':'answer'},{'source':'answer','target':'end'}]}


def task(p=None, **cfg):
    return {'app_type':'workflow','configuration':cfg,'workflow_plan':p or plan()}


def test_distinct_node_models_compile_without_a_global_model_or_hidden_params():
    p=plan();before=copy.deepcopy(p)
    text,result=compile_workflow_plan(task(p,model_parameters={'top_p':.9}))
    assert result['valid'],result['errors']
    nodes={n['id']:n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes']}
    assert nodes['classify']['model']==p['nodes'][1]['config']['model']
    assert nodes['answer']['model']==p['nodes'][2]['config']['model']
    assert all('top_p' not in nodes[key]['model']['completion_params'] for key in ('classify','answer'))
    assert p==before and not needs_task_model(p)
    assert any('实际供应商／型号' in w for w in result['warnings'])


def test_mixed_inherited_and_independent_models_use_only_the_selected_parameters():
    p=plan();p['nodes'][2]['config'].pop('model')
    assert needs_task_model(p) and not compile_workflow_plan(task(p))[0]
    text,result=compile_workflow_plan(task(p,dify_model_provider='global/provider',dify_model='global-model',temperature=.7,max_tokens=500,model_parameters={'top_p':.9}))
    assert result['valid'],result['errors']
    nodes={n['id']:n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes']}
    assert nodes['classify']['model']==chosen()
    assert nodes['answer']['model']['name']=='global-model' and nodes['answer']['model']['completion_params']['top_p']==.9


@pytest.mark.parametrize('mutation', [
    'null','string','empty','partial','unknown_field','no_provider','no_name','whitespace',
    'completion_mode','missing_params','params_string','missing_temperature','missing_max',
    'bool_temperature','nan_temperature','temperature_range','bool_max','max_range','nested_params','secret_field'
])
def test_incomplete_or_invalid_node_models_block_save_and_compile(mutation):
    p=plan();m=p['nodes'][1]['config']['model']
    if mutation=='null':p['nodes'][1]['config']['model']=None
    elif mutation=='string':p['nodes'][1]['config']['model']='incomplete'
    elif mutation=='empty':p['nodes'][1]['config']['model']={}
    elif mutation=='partial':m.pop('name')
    elif mutation=='unknown_field':m['reason']='未适配字段'
    elif mutation=='no_provider':m['provider']=''
    elif mutation=='no_name':m['name']=''
    elif mutation=='whitespace':m['name']=' actual-model '
    elif mutation=='completion_mode':m['mode']='completion'
    elif mutation=='missing_params':m['completion_params']={}
    elif mutation=='params_string':m['completion_params']='{'
    elif mutation=='missing_temperature':m['completion_params'].pop('temperature')
    elif mutation=='missing_max':m['completion_params'].pop('max_tokens')
    elif mutation=='bool_temperature':m['completion_params']['temperature']=True
    elif mutation=='nan_temperature':m['completion_params']['temperature']=float('nan')
    elif mutation=='temperature_range':m['completion_params']['temperature']=3
    elif mutation=='bool_max':m['completion_params']['max_tokens']=True
    elif mutation=='max_range':m['completion_params']['max_tokens']=1000001
    elif mutation=='nested_params':m['completion_params']['thinking']={'type':'disabled'}
    else:m['completion_params']['api_key']='synthetic-private-value'
    checked=validate_plan(task(p),p)
    assert not checked['valid'] and not compile_workflow_plan(task(p))[0]
    assert 'synthetic-private-value' not in str(checked)


def test_flat_extra_settings_are_emitted_as_given():
    p=plan();p['nodes'][1]['config']['model']['completion_params'].update(thinking=False,top_p=.5,seed=9)
    text,result=compile_workflow_plan(task(p))
    assert result['valid'] and 'thinking: false' in text and 'seed: 9' in text


def test_inner_iteration_models_override_individually_without_task_model():
    p=batch_plan();llm_body(p)
    child=iteration(p)['nodes'][0]
    child['config']['model']=chosen()
    assert not needs_task_model(p)
    text,result=compile_workflow_plan(task(p))
    assert result['valid'],result['errors']
    data=next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']==child['id'])
    assert data['model']==chosen() and 'memory' not in data
    child['config']['model']['completion_params']['temperature']=True
    assert not validate_plan(task(p),p)['valid']


def test_chatflow_memory_policy_still_comes_from_task_configuration():
    p=plan();p['nodes'][0]['config']['variables']=[]
    p['nodes'][1]['config']['user_prompt']='{{#sys.query#}}'
    p['nodes'][-1]={'id':'end','type':'answer','config':{'answer':'{{#answer.text#}}'}}
    value={**task(p,conversation_memory=True,memory_turns=3),'app_type':'advanced-chat'}
    text,result=compile_workflow_plan(value)
    assert result['valid'],result['errors']
    root=yaml.safe_load(text)
    assert all(n['data'].get('memory') for n in root['workflow']['graph']['nodes'] if n['data']['type']=='llm')
    assert validate_preserved(root)['valid']


def test_invalid_config_does_not_crash_model_gate():
    p=plan();p['nodes'][1]['config']=None
    assert needs_task_model(p) and not validate_plan(task(p),p)['valid']


def test_api_configuration_gate_accepts_complete_node_choices_and_invalidates_approval_on_change(client):
    t=approved(client)
    t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'dify_model_provider':'','dify_model':''}}).json()
    response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':plan()})
    assert response.status_code==200,response.text
    t=response.json()
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind})
        assert response.status_code==200,response.text
        t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']})
    assert response.status_code==200,response.text
    t=response.json();previous=t['revision']
    p=copy.deepcopy(t['workflow_plan']);p['nodes'][1]['config']['model']['name']='new-model'
    response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':p})
    assert response.status_code==200,response.text
    changed=response.json()
    assert changed['revision']>previous and not changed['configuration_confirmed'] and not changed['artifact']
    assert client.post(f"/api/tasks/{t['id']}/build",json={'revision':previous}).status_code==409


def test_invalid_override_cannot_be_saved_just_because_global_model_exists(client):
    t=approved(client);p=plan();p['nodes'][1]['config']['model'].pop('provider')
    response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':p})
    assert response.status_code==422 and not main.get_task(t['id'])['workflow_plan']


def test_global_configuration_proposal_does_not_imply_changing_independent_nodes():
    value={'app_type':'workflow','configuration':{'dify_model':'','dify_model_provider':'','dataset_ids':[]},'workflow_plan':plan()}
    warnings=main.configuration_proposals.warnings(value,{'configuration':{}},{'models':[],'datasets':[]})
    assert any('独立模型节点保持其流程配置' in text and 'classify' in text and 'answer' in text for text in warnings)
