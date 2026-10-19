import copy
import pytest
import yaml

from test_iteration import batch_plan, iteration, task
from test_api import client, approved
from app.workflow_plan import validate_plan, compile_workflow_plan
from app.planning import preserves_scope
from app import main


def parallel_plan(count=3):
    plan=batch_plan()
    iteration(plan).update(is_parallel=True, parallel_nums=count, parallel_safe=True, parallel_reason='每项独立文本转换，不访问外部接口或共享可写数据，不依赖其他项顺序。')
    return plan


@pytest.mark.parametrize('count',[2,3,10])
def test_parallel_parameters_native_and_no_private_declaration(count):
    plan=parallel_plan(count); original=copy.deepcopy(plan)
    text, result=compile_workflow_plan(task(plan))
    assert result['valid'],result['errors']
    graph=yaml.safe_load(text)['workflow']['graph'];node=next(n for n in graph['nodes'] if n['id']=='batch')
    assert node['data']['is_parallel'] is True and node['data']['parallel_nums']==count
    assert node['data']['error_handle_mode']=='terminated' and node['data']['flatten_output'] is False
    assert 'parallel_safe' not in node['data'] and 'parallel_reason' not in node['data']
    assert plan==original
    assert any('已派发' in w and '费用' in w for w in result['warnings'])


@pytest.mark.parametrize('patch',[{'parallel_nums':1},{'parallel_nums':0},{'parallel_nums':11},{'parallel_nums':True},{'parallel_nums':3.0},{'parallel_nums':'3'},{'parallel_nums':None},{'parallel_safe':False},{'parallel_safe':1},{'parallel_safe':'true'},{'parallel_reason':''},{'parallel_reason':' '},{'parallel_reason':300},{'parallel_reason':'x'*2001}])
def test_invalid_concurrency_or_missing_declaration_not_silently_sequential(patch):
    plan=parallel_plan();iteration(plan).update(patch)
    assert not validate_plan(task(plan),plan)['valid']
    text, result=compile_workflow_plan(task(plan));assert not text and not result['valid']


@pytest.mark.parametrize('missing',['parallel_nums','parallel_safe','parallel_reason','is_parallel'])
def test_all_parallel_choices_explicit(missing):
    plan=parallel_plan();iteration(plan).pop(missing)
    assert not validate_plan(task(plan),plan)['valid']


@pytest.mark.parametrize('patch',[{'parallel_nums':3},{'parallel_nums':True},{'parallel_safe':True},{'parallel_reason':'stale'}])
def test_sequential_does_not_ignore_parallel_configuration(patch):
    plan=batch_plan();iteration(plan).update(patch)
    assert not validate_plan(task(plan),plan)['valid']


def test_legacy_sequential_and_explicit_one_remain_valid():
    plan=batch_plan();assert validate_plan(task(plan),plan)['valid']
    iteration(plan)['parallel_nums']=1
    text,result=compile_workflow_plan(task(plan));assert result['valid']
    data=next(n for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='batch')['data']
    assert not data['is_parallel'] and data['parallel_nums']==1


def test_item_scope_and_inside_sequence_kept():
    plan=parallel_plan()
    iteration(plan)['nodes'].append({'id':'formatted','type':'template-transform','config':{'template':'{{ index }}:{{ value }}','variables':[{'variable':'index','value_type':'number','value_selector':['batch','index']},{'variable':'value','value_type':'string','value_selector':['clean','result']}]}})
    iteration(plan)['output_selector']=['formatted','output']
    text,result=compile_workflow_plan(task(plan));assert result['valid'],result['errors']
    graph=yaml.safe_load(text)['workflow']['graph'];edges=[e for e in graph['edges'] if e['data'].get('isInIteration')]
    assert [(e['source'],e['target']) for e in edges]==[('batch__iteration_start','clean'),('clean','formatted')]
    assert next(n for n in graph['nodes'] if n['id']=='formatted')['parentId']=='batch'
    iteration(plan)['nodes'][0]['config']['variables'][0]['value_selector']=['formatted','output']
    assert not validate_plan(task(plan),plan)['valid']


@pytest.mark.parametrize('field,value',[('parallel_nums',4),('parallel_safe',False),('parallel_reason','依赖先前项目'),('is_parallel',False)])
def test_automatic_repair_cannot_change_parallel_choices(field,value):
    before=parallel_plan();after=copy.deepcopy(before);iteration(after)[field]=value
    assert not preserves_scope(before,after)


def test_api_saves_parallel_candidate_only_then_requires_confirmation(client):
    t=approved(client)
    response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':parallel_plan()})
    assert response.status_code==200,response.text
    t=response.json();assert t['requirements_confirmed'] and not t['configuration_confirmed']
    assert not t['dify_app_id'] and not t['runs']
    assert client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).status_code==422
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind})
        assert response.status_code==200,response.text
        t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    t=response.json();assert t['artifact']['verification']=='static_only'
    assert not t['runs'] and not t['dify_app_id']


def test_chatflow_parallel_llm_does_not_read_history_per_item():
    plan=parallel_plan();t=task(plan,dify_model_provider='test/provider',dify_model='test',conversation_memory=True,memory_turns=5);t['app_type']='advanced-chat'
    plan['nodes'][0]['config']['variables']=[]
    plan['nodes'][1]['config']['variables'][0]['value_selector']=['sys','query']
    iteration(plan)['nodes']=[{'id':'body_llm','type':'llm','config':{'system_prompt':'独立转换本项，其他项目不作为历史。','user_prompt':'{{#batch.item#}}'}}]
    iteration(plan)['output_selector']=['body_llm','text'];plan['nodes'][-1]={'id':'answer','type':'answer','config':{'answer':'{{#batch.output#}}'}};plan['edges'][-1]['target']='answer'
    text,result=compile_workflow_plan(t);assert result['valid'],result['errors']
    node=next(n for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='body_llm')
    assert 'memory' not in node['data'] and node['data']['model']['name']=='test'
