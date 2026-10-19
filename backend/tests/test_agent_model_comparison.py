import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,yaml
from app import main
from app.agent_plan import compile_agent_plan
from app.agent_model_comparison import compare,configuration
from app.dsl_roundtrip import parse,preview
from test_agent_plan import fixture_task,runtime_task
from test_agent_preservation import record,soul
from test_dsl_roundtrip import capture
from test_api import client


def base():return yaml.safe_load(compile_agent_plan(fixture_task())[0])

def changed():
    doc=base();model=soul(doc)['model'];model['model']='public-new-model';model['model_settings'].update(temperature=.7,max_tokens=512,thinking=True,response_format={'type':'json_object'})
    return doc


def test_unchanged_or_known_null_export_defaults_need_no_comparison():
    selected=base();current=copy.deepcopy(selected)
    soul(current)['model']['model_settings'].update(top_p=None,stop=None,presence_penalty=None)
    assert compare(current,selected) is None


def test_complete_difference_and_configuration_mapping_without_mutating_documents():
    selected=base();current=changed();a=copy.deepcopy(current);b=copy.deepcopy(selected)
    result=compare(current,selected)
    assert result['available'] and result['verification']=='local_model_comparison_only'
    assert result['current']['name']=='public-new-model' and result['current']['temperature']==.7
    cfg=result['current_configuration'];assert cfg['model_parameters']=={'thinking':True,'response_format':'json_object'}
    assert cfg['temperature']==.7 and cfg['max_tokens']==512
    assert {v['name'] for v in result['parameter_differences']}=={'temperature','max_tokens','thinking','response_format'}
    assert current==a and selected==b and '没有核对' in result['note'] and '不自动采用' in result['note']
    task=fixture_task();task['configuration'].update(cfg)
    again=yaml.safe_load(compile_agent_plan(task)[0]);assert soul(again)['model']==soul(current)['model']


def test_missing_parameter_is_distinct_from_false_no_hidden_inheritance():
    current=changed();selected=base();del soul(current)['model']['model_settings']['thinking']
    result=compare(current,selected);row=next(v for v in result['parameter_differences'] if v['name']=='thinking')
    assert row['current']=={'present':False} and row['selected']=={'present':True,'value':False}
    assert 'thinking' not in result['current_configuration']['model_parameters']


@pytest.mark.parametrize('field,value',[
    ('stop',['END']),('response_format',{'type':'json_object','schema':{}}),
    ('response_format',{'type':[]}),('thinking',None),('max_tokens',True),
    ('temperature',float('inf')),('seed',9007199254740993),('seed',10**600),('seed',1e20),
    ('top_p',{'nested':True}),('authorization','not-a-credential'),
],ids=[f'unsupported{i}' for i in range(11)])
def test_unrepresentable_parameters_never_become_partial_suggestion(field,value):
    current=changed();soul(current)['model']['model_settings'][field]=value
    result=compare(current,base())
    assert result['available'] is False and result['reason']
    assert 'current_configuration' not in result and 'current' not in result


@pytest.mark.parametrize('field',['temperature','max_tokens'])
def test_missing_explicit_numeric_parameter_cannot_take_selected_default(field):
    current=changed();del soul(current)['model']['model_settings'][field]
    result=compare(current,base());assert not result['available'] and '缺少明确' in result['reason']


@pytest.mark.parametrize('kind',['no_model','bad_ref','multi','other_mode','credential','plugin_mismatch'])
def test_unknown_model_structure_gives_unavailable_instead_of_crashing(kind):
    current=changed()
    if kind=='no_model':del soul(current)['model']
    elif kind=='bad_ref':current['agent']['package_ref']='missing'
    elif kind=='multi':current['agent_packages']['extra']=copy.deepcopy(current['agent_packages']['agent_1'])
    elif kind=='other_mode':current['app']['mode']='workflow'
    elif kind=='credential':soul(current)['model']['credential_ref']={'type':'private'}
    else:soul(current)['model']['plugin_id']='other/plugin'
    result=compare(current,base());assert not result['available']


def test_preview_remains_invalid_until_model_is_explicitly_selected_elsewhere():
    selected=base();current=changed();result=preview(record(selected,current),yaml.safe_dump(selected),9)
    assert not result['validation']['valid'] and result['agent_model_comparison']['available']
    assert result['unresolved']==0 and 'public-new-model' in result['content']
    task=fixture_task();task['configuration'].update(result['agent_model_comparison']['current_configuration'])
    configured=yaml.safe_load(compile_agent_plan(task)[0])
    next_preview=preview(record(selected,current),yaml.safe_dump(configured),10)
    assert next_preview['validation']['valid'] and next_preview['agent_model_comparison'] is None
    assert next_preview['merge_token']!=result['merge_token']


def test_actual_api_preview_only_reports_difference_without_adopting_or_creating_run(client):
    task=runtime_task(client);task['dify_app_id']=None;main.save_task(task)
    current=parse(main.compile_current(task)[0],'agent');soul(current)['model']['model']='public-new-model'
    task=capture(client,task,current);before=copy.deepcopy(main.get_task(task['id']))
    response=client.get(f"/api/tasks/{task['id']}/dsl-merge");assert response.status_code==200,response.text
    result=response.json();assert result['agent_model_comparison']['available'] and not result['validation']['valid']
    assert main.get_task(task['id'])==before and not result['agent_model_comparison'].get('adopted')
    assert result['revision']==task['revision'] and result['reference_id']==task['dsl_reference']['id']
