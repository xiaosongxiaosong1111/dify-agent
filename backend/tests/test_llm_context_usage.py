import copy,json
import pytest,yaml
from test_workflow_plan import base_plan,plan_task
from test_api import client,approved,planning_provider,forbid_api_external_calls
from app import main
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.planning import normalize_draft


def retrieval_plan(mode='workflow'):
    p=base_plan(mode);p['nodes'].insert(1,{'id':'retrieve','type':'knowledge-retrieval','config':{'dataset_source':'node','dataset_ids':['public-faq'],'query_variable_selector':['sys','query'] if mode=='advanced-chat' else ['start','query']}})
    p['nodes'][2]['config']['context_variable_selector']=['retrieve','result']
    p['edges'].insert(0,{'source':'start','target':'retrieve'});p['edges'][1]['source']='retrieve'
    return p


@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_bound_retrieval_without_prompt_placeholder_cannot_emit_dsl(mode):
    p=retrieval_plan(mode);before=copy.deepcopy(p);content,v=compile_workflow_plan(plan_task(p,mode))
    assert not v['valid'] and content=='' and any('{{#context#}}' in e for e in v['errors']) and p==before


@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_placeholder_without_context_binding_is_not_silently_empty(mode):
    p=base_plan(mode);p['nodes'][1]['config']['user_prompt']+=' {{#context#}}'
    content,v=compile_workflow_plan(plan_task(p,mode))
    assert content=='' and not v['valid'] and any('context_variable_selector' in e for e in v['errors'])


@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
@pytest.mark.parametrize('field',['system_prompt','user_prompt'])
def test_explicit_placeholder_in_either_actual_prompt_keeps_exact_text(mode,field):
    p=retrieval_plan(mode);cfg=p['nodes'][2]['config'];cfg[field]+=' 资料：{{#context#}}';before=copy.deepcopy(p)
    text,v=compile_workflow_plan(plan_task(p,mode));assert v['valid'],v['errors']
    node=next(n['data'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='llm')
    role='system' if field=='system_prompt' else 'user';message=next(m for m in node['prompt_template'] if m['role']==role)
    assert message['text']==cfg[field] and node['context']=={'enabled':True,'variable_selector':['retrieve','result']} and p==before


def test_normalization_does_not_invent_context_text_or_binding():
    p=retrieval_plan();normalized,_=normalize_draft(p)
    assert normalized==p and not validate_plan(plan_task(p),normalized)['valid']


@pytest.mark.parametrize('owner',['iteration','loop'])
@pytest.mark.parametrize('bound',[True,False])
def test_supported_body_llm_reuses_same_context_gate(owner,bound):
    from test_container_retrieval import plan,task
    p=plan(owner);cfg=next(n for n in p['nodes'] if n['type']==owner)['config']
    node={'id':'respond','type':'llm','config':{'system_prompt':'只按资料回答' if bound else '{{#context#}}','user_prompt':'当前问题','model':{'provider':'fixture/provider','name':'fixture-model','mode':'chat','completion_params':{'temperature':0,'max_tokens':64}}}}
    if bound:node['config']['context_variable_selector']=['search','result']
    if owner=='iteration':cfg['nodes']=[cfg['nodes'][0],node];cfg['output_selector']=['respond','text']
    else:cfg['nodes'].insert(1,node)
    before=copy.deepcopy(p);content,v=compile_workflow_plan(task(p))
    assert not v['valid'] and content=='' and any('respond' in e and ('{{#context#}}' in e if bound else 'context_variable_selector' in e) for e in v['errors']) and p==before


def test_manual_invalid_plan_is_rejected_without_overwriting_saved_source(client):
    task=approved(client);path='/api/tasks/'+task['id'];task=client.patch(path,json={'configuration':{'dataset_ids':['public-faq']}}).json();before=copy.deepcopy(main.get_task(task['id']))
    response=client.post(path+'/plan',json={'revision':task['revision'],'plan':retrieval_plan()})
    assert response.status_code==422 and '{{#context#}}' in response.text and main.get_task(task['id'])==before


def test_controlled_model_candidate_preserves_diagnostic_usage_and_never_applies_or_retries(client,monkeypatch):
    planning_provider(client);task=approved(client);path='/api/tasks/'+task['id'];task=client.patch(path,json={'configuration':{'dataset_ids':['public-faq']}}).json();calls=[]
    async def model(*args,**kwargs):calls.append(1);return json.dumps(retrieval_plan()),{'prompt_tokens':20,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(path+'/plan/generate',json={'revision':task['revision']})
    assert response.status_code==422 and calls==[1]
    saved=main.get_task(task['id']);assert saved['workflow_plan'] is None and saved['revision']==task['revision'] and saved['artifact'] is None
    operation=saved['planning_runs'][-1]
    assert operation['last_candidate']==retrieval_plan() and any('{{#context#}}' in e for e in operation['diagnostics']) and len(operation['attempts'])==1
    assert operation['attempts'][0]['usage']['completion_tokens']==30 and len(main.budgets.get(task['id'])['entries'])==1
