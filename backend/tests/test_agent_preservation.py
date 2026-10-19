import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,yaml
from app.agent_preservation import validate,SOUL_DEFAULTS,FILE_DEFAULTS
from app.dsl_roundtrip import preview,digest,parse
from app.agent_plan import compile_agent_plan
from test_agent_plan import fixture_task,runtime_task,knowledge_task
from test_api import client
from test_dsl_roundtrip import capture,apply
from app import main


def root():return yaml.safe_load(compile_agent_plan(fixture_task())[0])
def soul(doc):return doc['agent_packages'][doc['agent']['package_ref']]['soul']
def record(base,current):return {'id':'ref','mode':'agent','base':base,'current':current,'source':'uploaded_file','created_at':'now','baseline_note':'文件未在线核对'}

def test_native_defaults_preserve_original_and_null_model_parameters():
    proposal=root();current=copy.deepcopy(proposal);state=soul(current)
    state.update(copy.deepcopy(SOUL_DEFAULTS));state['model']['model_settings'].update(top_p=None,stop=None,presence_penalty=None,frequency_penalty=None)
    state['app_features']['file_upload']={**copy.deepcopy(FILE_DEFAULTS),'enabled':False}
    state['app_features'].update(speech_to_text=None,text_to_speech=None,suggested_questions_after_answer=None,retriever_resource=None,sensitive_word_avoidance=None)
    state['prompt']['system_prompt']='人工保留的指令';state['app_features']['opening_statement']='欢迎';state['app_features']['suggested_questions']=['如何开始？']
    before=copy.deepcopy(current);result=preview(record(proposal,current),yaml.safe_dump(proposal),7)
    assert result['validation']['valid'],result
    assert parse(result['content'],'agent')==before==current
    assert result['parallel_candidates']==[] and result['loop_candidates']==[] and result['unresolved']==0
    assert result['validation']['verification']=='static_only' and 'workflow' not in parse(result['content'],'agent')

@pytest.mark.parametrize('path,value',[
    (['tools','cli_tools'],[{'name':'run'}]),(['tools','dify_tools'],[{'tool_name':'search'}]),
    (['knowledge','sets'],[{'id':'kb'}]),(['config_files'],[{'name':'x'}]),(['config_skills'],[{'name':'x'}]),
    (['human'],{'contacts':[{'name':'someone'}],'tools':[]}),(['env'],{'variables':[{'name':'x'}]}),
    (['app_variables'],[{'name':'x'}]),(['sandbox'],{'provider':'custom'}),(['memory'],{'scope':'global'}),
    (['config_note'],'执行额外指令'),(['misc_legacy'],{'opening_statement':'旧行为'}),
    (['app_features','file_upload'],{'enabled':True}),(['app_features','file_upload'],{'enabled':0}),
    (['app_features','speech_to_text'],{'enabled':True}),(['app_features','suggested_questions'],['']),
    (['unknown'],False),(['schema_version'],True),(['prompt','system_prompt'],'{{#workflow.input#}}'),
    (['model','model'],'other-model'),(['model','model_settings','temperature'],.8),
    (['model','credential_ref'],{'type':'provider','id':'credential'}),
    (['model','model_settings','thinking'],0),(['tools'],[]),(['memory'],[]),
],ids=[f'guard{i}' for i in range(25)])
def test_unadapted_behavior_is_retained_but_refused(path,value):
    proposal=root();current=copy.deepcopy(proposal);target=soul(current)
    for key in path[:-1]:target=target.setdefault(key,{})
    target[path[-1]]=value;before=copy.deepcopy(current)
    result=preview(record(proposal,current),yaml.safe_dump(proposal),7)
    assert not result['validation']['valid'] and result['validation']['errors']
    assert parse(result['content'],'agent')==before==current

@pytest.mark.parametrize('kind',['extra_package','asset','workspace','wrong_mode','workflow','root_extra','dependencies','github','bad_plugin'])
def test_package_and_root_guards(kind):
    proposal=root();current=copy.deepcopy(proposal);pkg=current['agent_packages']['agent_1']
    if kind=='extra_package':current['agent_packages']['extra']=copy.deepcopy(pkg)
    elif kind=='asset':pkg['omitted_assets']=[{'kind':'file','name':'missing.txt'}]
    elif kind=='workspace':pkg['workspace_skills']=[{'name':'skill'}]
    elif kind=='wrong_mode':current['app']['mode']='workflow'
    elif kind=='workflow':current['workflow']={'graph':{'nodes':[],'edges':[]}}
    elif kind=='root_extra':current['extra']=None
    elif kind=='dependencies':current['dependencies']=[{'type':'package','value':{'plugin_unique_identifier':'x'}}]
    else:current['dependencies']=[{'type':'github' if kind=='github' else 'marketplace','value':{'marketplace_plugin_unique_identifier':'other/plugin:1@abcd'}}]
    assert not validate(current,proposal)['valid']


def test_marketplace_model_dependency_is_preserved_but_not_verified():
    proposal=root();current=copy.deepcopy(proposal)
    current['dependencies']=[{'type':'marketplace','value':{'marketplace_plugin_unique_identifier':'langgenius/deepseek:1.0.0@abc','version':None},'current_identifier':None}]
    result=preview(record(proposal,current),yaml.safe_dump(proposal),7)
    assert result['validation']['valid'] and parse(result['content'],'agent')['dependencies']==current['dependencies']
    assert any('依赖可用性' in w for w in result['validation']['warnings'])


def test_knowledge_selected_in_generated_never_silently_removed():
    proposal=yaml.safe_load(compile_agent_plan(knowledge_task())[0]);current=copy.deepcopy(proposal)
    soul(current)['knowledge']['sets']=[]
    assert not validate(current,proposal)['valid']


def test_no_workflow_container_attestation_accepted():
    doc=root()
    assert not validate(doc,doc,{'iteration':{}},None)['valid']
    assert not validate(doc,doc,None,{'loop':{}})['valid']


def test_prompt_conflict_requires_choice_and_different_choices_invalidate_document():
    base=root();current=copy.deepcopy(base);generated=copy.deepcopy(base)
    soul(current)['prompt']['system_prompt']='手改指令';soul(generated)['prompt']['system_prompt']='新生成指令'
    item=record(base,current);result=preview(item,yaml.safe_dump(generated),9)
    assert result['unresolved']==1 and result['validation']['valid']
    path=result['conflicts'][0]['path'];assert path.endswith('/prompt/system_prompt')
    current_pick=preview(item,yaml.safe_dump(generated),9,{path:'current'})
    generated_pick=preview(item,yaml.safe_dump(generated),9,{path:'generated'})
    assert current_pick['document_token']!=generated_pick['document_token']
    assert soul(parse(current_pick['content'],'agent'))['prompt']['system_prompt']=='手改指令'
    assert soul(parse(generated_pick['content'],'agent'))['prompt']['system_prompt']=='新生成指令'
    assert preview(item,yaml.safe_dump(generated),10)['merge_token']!=result['merge_token']


def test_agent_api_apply_confirm_build_keeps_actual_manual_text(client):
    task=runtime_task(client);task['dify_app_id']=None;main.save_task(task)
    baseline=parse(main.compile_current(task)[0],'agent');current=copy.deepcopy(baseline)
    soul(current)['prompt']['system_prompt']='人工确认的新指令';soul(current)['app_features']['opening_statement']='人工开场白'
    task=capture(client,task,current);response,p=apply(client,task)
    assert response.status_code==200,response.text
    task=response.json();assert task['app_type']=='agent' and not task['configuration_confirmed'] and not task['dify_app_id']
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind})
        assert response.status_code==200,response.text
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']})
    assert response.status_code==200,response.text
    actual=parse(main.artifact_path(response.json()).read_text('utf-8'),'agent')
    assert digest(actual)==digest(current) and 'workflow' not in actual
    assert response.json()['artifact']['verification']=='static_only'
    changed=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'max_tokens':512}}).json()
    stale=client.post(f"/api/tasks/{task['id']}/dsl-merge/apply",json={'revision':changed['revision'],'reference_id':p['reference_id'],'merge_token':p['merge_token'],'choices':{}})
    assert stale.status_code==409


def test_agent_unsupported_tool_cannot_apply_or_build_and_reference_survives(client):
    task=runtime_task(client);task['dify_app_id']=None;main.save_task(task)
    current=parse(main.compile_current(task)[0],'agent');soul(current)['tools']['cli_tools']=[{'name':'original-tool'}]
    task=capture(client,task,current);response,p=apply(client,task)
    assert response.status_code==422 and not p['validation']['valid']
    saved=main.store.get('dsl_reference',task['dsl_reference']['id'])
    assert saved['current']==current and not main.get_task(task['id']).get('dsl_overlay')
