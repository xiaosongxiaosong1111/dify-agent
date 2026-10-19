import copy,json,sqlite3,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import main
from app.dsl_roundtrip import parse,digest
from app.agent_environment_mapping import MARKER,MODEL_MOCK,DATASET_MOCK
from test_agent_plan import runtime_task
from test_agent_preservation import soul
from test_dsl_roundtrip import capture
from test_api import client,create_env

A='a1111111-1111-4111-8111-111111111111'
B='b2222222-2222-4222-8222-222222222222'
MODEL={'provider':'langgenius/deepseek/deepseek','name':'target-model','mode':'chat','completion_params':{'temperature':.4,'max_tokens':512,'response_format':'text'}}


def prepared(client,*,knowledge=False,dependency=False,unsupported=False,source_ids=None):
    task=runtime_task(client);task['dify_app_id']=None
    task['configuration']['mock_dependencies']=['保留原有未解决条件']
    if knowledge:
        libraries=source_ids or ['source-a','source-b']
        task['configuration']['dataset_ids']=libraries
        task['agent_plan'].update(scope='knowledge',knowledge_sets=[
            {'name':'第一组','description':'按公开政策答复','dataset_ids':libraries,'query_mode':'generated_query','top_k':3},
            {'name':'第二组','description':'补充公开说明','dataset_ids':[libraries[1]],'query_mode':'generated_query','top_k':4}])
    main.save_task(task);root=parse(main.compile_current(task)[0],'agent')
    root['app']['description']='完整源说明';soul(root)['prompt']['system_prompt']='保留人工职责与信息不足处理'
    soul(root)['app_features']['opening_statement']='保留人工开场'
    if knowledge:
        rows=soul(root)['knowledge']['sets'];rows[0]['id']='manual-set';rows[0]['name']='人工资料组';rows[0]['retrieval']['top_k']=7
        rows[0]['datasets'][0].update(name='源库显示名称',description='源库说明')
    if dependency:root['dependencies']=[{'type':'marketplace','value':{'marketplace_plugin_unique_identifier':'langgenius/deepseek:1.0@abc','version':None},'current_identifier':None}]
    if unsupported:soul(root)['tools']['cli_tools']=[{'name':'never-drop-tool'}]
    task=capture(client,task,root)
    source=client.get(f"/api/tasks/{task['id']}/dsl-merge").json()
    target=create_env(client)
    return task,root,source,target


def body(task,p,target,**patch):
    value={'revision':task['revision'],'reference_id':p['reference_id'],'merge_token':p['merge_token'],'document_token':p['document_token'],
        'target_environment_id':target['id'],'target_model_json':json.dumps(MODEL),'dataset_mapping':{},'acknowledge_unverified_target':True}
    value.update(patch);return value


def request(client,task,p,target,**patch):return client.post(f"/api/tasks/{task['id']}/environment-mapping/preview",json=body(task,p,target,**patch))


def state():
    with sqlite3.connect((main.DATA_ROOT/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        return (db.execute('SELECT kind,id,value FROM objects ORDER BY kind,id').fetchall(),db.execute('SELECT id,value FROM secrets ORDER BY id').fetchall())


def test_text_preview_preserves_all_source_state_and_marks_target_unverified(client,monkeypatch):
    task,root,p,target=prepared(client);assert p['validation']['valid']
    main.store.set_secret(target['id'],'console_token','never-copy-target-connection')
    baseline=state();before=copy.deepcopy(main.get_task(task['id']))
    def no_decrypt(*args,**kwargs):pytest.fail('stateless mapping must not decrypt credentials')
    monkeypatch.setattr(main.store,'secret',no_decrypt)
    result=request(client,task,p,target);assert result.status_code==200,result.text
    value=result.json();assert not value['task_modified'] and not value['can_apply'] and not value['target_resources_verified']
    assert not value['platform_verified'] and not value['business_verified'] and value['verification']=='static_mapping_preview'
    mapped=parse(value['content'],'agent');assert mapped['app']['mode']=='agent' and 'workflow' not in mapped
    assert MARKER in mapped['app']['description'] and mapped['app']['description'].startswith('完整源说明')
    assert soul(mapped)['prompt']==soul(root)['prompt'] and soul(mapped)['app_features']==soul(root)['app_features']
    assert soul(mapped)['model']['model']=='target-model'
    assert value['agent_plan']['system_prompt']=='保留人工职责与信息不足处理'
    assert value['configuration']['dataset_ids']==[] and MODEL_MOCK in value['configuration']['mock_dependencies']
    assert '保留原有未解决条件' in value['configuration']['mock_dependencies']
    assert 'thinking' not in value['configuration']['model_parameters']
    assert 'never-copy-target-connection' not in json.dumps(value,ensure_ascii=False)
    assert set(value['target_environment'])=={'id','name','base_url','version'}
    assert state()==baseline and main.get_task(task['id'])==before
    second=request(client,task,p,target);assert second.json()==value and state()==baseline


def test_knowledge_groups_keep_purpose_order_topk_and_explicit_id_mapping(client):
    task,root,p,target=prepared(client,knowledge=True);baseline=state()
    response=request(client,task,p,target,dataset_mapping={'source-a':A,'source-b':B});assert response.status_code==200,response.text
    value=response.json();mapped=parse(value['content'],'agent');rows=soul(mapped)['knowledge']['sets']
    assert rows[0]['id']=='manual-set' and rows[0]['name']=='人工资料组' and rows[0]['retrieval']['top_k']==7
    assert rows[0]['datasets']==[{'id':A,'name':None,'description':None},{'id':B}]
    assert rows[1]['datasets']==[{'id':B}]
    assert value['configuration']['dataset_ids']==[A,B] and DATASET_MOCK in value['configuration']['mock_dependencies']
    assert value['changes']['datasets'][0]['source']['name']=='源库显示名称'
    assert value['changes']['datasets'][0]['target']['name'] is None
    assert value['validation']['valid'] and any('显示名／描述' in warning for warning in value['warnings']) and state()==baseline
    assert main.store.get('dsl_reference',p['reference_id'])['current']==root


@pytest.mark.parametrize('mapping',[
    {},{'source-a':A},{'source-a':A,'source-b':B,'foreign':str(uuid.uuid4())},
    {'source-a':A,'source-b':A},{'source-a':'copied-name-not-id','source-b':B},
    {'source-a':A.upper(),'source-b':B},
],ids=['empty','missing','extra','many_to_one','name','noncanonical'])
def test_incomplete_or_ambiguous_library_mapping_never_filters_or_inserts(client,mapping):
    task,root,p,target=prepared(client,knowledge=True);baseline=state()
    response=request(client,task,p,target,dataset_mapping=mapping);assert response.status_code==422,response.text
    assert state()==baseline


@pytest.mark.parametrize('model_text',[
    '{"provider":"x/y/z","provider":"other/plugin/provider"}',
    json.dumps({**MODEL,'mode':'completion'}),json.dumps({**MODEL,'provider':'short/provider'}),
    json.dumps({**MODEL,'completion_params':{'temperature':.4}}),
    json.dumps({**MODEL,'completion_params':{'temperature':True,'max_tokens':512}}),
    json.dumps({**MODEL,'completion_params':{'temperature':.4,'max_tokens':512,'seed':9007199254740993}}),
    '{"provider":"langgenius/deepseek/deepseek","name":"target-model","mode":"chat","completion_params":{"temperature":0.10000000000000001,"max_tokens":512}}',
    json.dumps({**MODEL,'completion_params':{'temperature':.4,'max_tokens':512,'api_key':'never-echo-target-key'}}),
],ids=[f'model{i}' for i in range(8)])
def test_full_model_required_and_ambiguous_numeric_or_secret_settings_are_not_echoed(client,model_text):
    task,root,p,target=prepared(client);baseline=state()
    response=request(client,task,p,target,target_model_json=model_text);assert response.status_code==422,response.text
    assert 'never-echo-target-key' not in response.text and state()==baseline


def test_changing_provider_does_not_silently_discard_fixed_plugin_dependency(client):
    task,root,p,target=prepared(client,dependency=True);baseline=state()
    other={**MODEL,'provider':'langgenius/openai/openai'}
    response=request(client,task,p,target,target_model_json=json.dumps(other));assert response.status_code==422 and '固定依赖' in response.text
    assert state()==baseline
    response=request(client,task,p,target,target_model_json=json.dumps(other),target_dependency='langgenius/openai:2.0@def');assert response.status_code==200,response.text
    value=response.json();mapped=parse(value['content'],'agent')
    assert mapped['dependencies'][0]['value']['marketplace_plugin_unique_identifier']=='langgenius/openai:2.0@def'
    assert value['changes']['dependencies']['source']==root['dependencies'] and state()==baseline


def test_same_plugin_dependency_is_preserved_but_not_claimed_installed(client):
    task,root,p,target=prepared(client,dependency=True)
    response=request(client,task,p,target);assert response.status_code==200,response.text
    assert parse(response.json()['content'],'agent')['dependencies']==root['dependencies']
    assert not response.json()['target_resources_verified']


@pytest.mark.parametrize('kind',['same_environment','wrong_version','wrong_record_id','busy','source_unsupported','source_origin_changed','stale_token','no_ack'])
def test_context_and_source_scope_block_preview_without_state_changes(client,kind):
    task,root,p,target=prepared(client,unsupported=kind=='source_unsupported');patch={}
    if kind=='same_environment':patch['target_environment_id']=task['environment_id']
    elif kind in {'wrong_version','wrong_record_id'}:
        row=main.store.get('environment',target['id']);row['version' if kind=='wrong_version' else 'id']='1.18.0' if kind=='wrong_version' else str(uuid.uuid4());main.store.put('environment',target['id'],row)
    elif kind=='busy':task['status']='running';main.save_task(task)
    elif kind=='source_origin_changed':
        row=main.store.get('environment',task['environment_id']);row['base_url']='http://127.0.0.1:8999';main.store.put('environment',row['id'],row)
    elif kind=='stale_token':patch['document_token']='f'*64
    elif kind=='no_ack':patch['acknowledge_unverified_target']=False
    baseline=state();response=request(client,task,p,target,**patch)
    assert response.status_code in {409,422},response.text
    assert state()==baseline


def test_target_connection_context_change_invalidates_the_preview_token(client):
    task,root,p,target=prepared(client);first=request(client,task,p,target).json()
    env=main.store.get('environment',target['id']);env['connection_revision']='new-connection';main.store.put('environment',target['id'],env)
    second=request(client,task,p,target).json()
    assert first['target_context_token']!=second['target_context_token'] and first['preview_token']!=second['preview_token']
    assert first['document_token']==second['document_token']


def test_unresolved_source_conflicts_require_an_explicit_choice_but_preview_does_not_save_it(client):
    task,root,p,target=prepared(client)
    plan=copy.deepcopy(task['agent_plan']);plan['system_prompt']='本次生成的新职责'
    task=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan}).json()
    p=client.get(f"/api/tasks/{task['id']}/dsl-merge").json();assert p['unresolved']
    assert request(client,task,p,target).status_code==422
    choices={c['path']:'current' for c in p['conflicts']}
    selected=client.post(f"/api/tasks/{task['id']}/dsl-merge/preview",json={'revision':task['revision'],'choices':choices}).json()
    baseline=state();response=request(client,task,selected,target,choices=choices);assert response.status_code==200,response.text
    assert response.json()['agent_plan']['system_prompt']=='保留人工职责与信息不足处理'
    assert state()==baseline and main.store.get('merge_draft',task['id']) is None


def test_outer_duplicate_keys_and_schema_errors_do_not_echo_any_input(client):
    task,root,p,target=prepared(client);baseline=state();value=body(task,p,target)
    text=json.dumps(value)[:-1]+',"target_environment_id":"never-echo-body-marker"}'
    response=client.post(f"/api/tasks/{task['id']}/environment-mapping/preview",content=text,headers={'Content-Type':'application/json'})
    assert response.status_code==422 and '重复' in response.text and 'never-echo' not in response.text
    value['target_model_json']={'api_key':'never-echo-schema-marker'}
    response=client.post(f"/api/tasks/{task['id']}/environment-mapping/preview",json=value)
    assert response.status_code==422 and 'never-echo' not in response.text and state()==baseline



def test_identical_uuid_still_requires_explicit_mapping_and_never_means_target_verified(client):
    task,root,p,target=prepared(client,knowledge=True,source_ids=[A,B]);baseline=state()
    assert request(client,task,p,target).status_code==422
    response=request(client,task,p,target,dataset_mapping={A:A,B:B});assert response.status_code==200,response.text
    value=response.json();assert value['changes']['dataset_id_mapping']==[{'source_id':A,'target_id':A},{'source_id':B,'target_id':B}]
    assert value['source_environment_id']==task['environment_id'] and value['target_environment']['id']==target['id']
    assert not value['target_resources_verified'] and DATASET_MOCK in value['configuration']['mock_dependencies']
    assert state()==baseline


@pytest.mark.parametrize('url',['http://user:never-echo-target-url@localhost:8999','http://127.0.0.1:8999/?api_key=never-echo-target-url'])
def test_legacy_credential_bearing_target_urls_are_not_echoed_or_copied(client,url):
    task,root,p,target=prepared(client);env=main.store.get('environment',target['id']);env['base_url']=url;main.store.put('environment',target['id'],env)
    baseline=state();response=request(client,task,p,target)
    assert response.status_code==422 and 'never-echo-target-url' not in response.text and state()==baseline


@pytest.mark.parametrize('app_type',['workflow','advanced-chat'])
def test_user_selected_non_agent_type_is_not_converted_for_mapping(client,app_type):
    from test_api import create
    task=create(client,app_type);baseline=state()
    payload={'revision':task['revision'],'reference_id':'not-used','merge_token':'f'*64,'document_token':'f'*64,'target_environment_id':'not-used','target_model_json':json.dumps(MODEL),'acknowledge_unverified_target':True}
    response=client.post(f"/api/tasks/{task['id']}/environment-mapping/preview",json=payload)
    assert response.status_code==422 and state()==baseline and main.get_task(task['id'])['app_type']==app_type


def test_openapi_exposes_only_preview_with_complete_model_text_and_no_extra_fields(client):
    schema=client.get('/openapi.json').json();operation=schema['paths']['/api/tasks/{item_id}/environment-mapping/preview']['post']
    name=operation['requestBody']['content']['application/json']['schema']['$ref'].split('/')[-1]
    dto=schema['components']['schemas'][name]
    assert dto['additionalProperties'] is False and dto['properties']['target_model_json']['type']=='string'
    assert dto['properties']['target_model_json']['maxLength']==30000
    assert not any('/environment-mapping/apply' in path for path in schema['paths'])
