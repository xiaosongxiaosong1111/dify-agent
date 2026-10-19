import json
import pytest
import yaml
from test_api import client, create_env, approved, code_only_plan
from app import main
from app.resources import models_metadata, parameter_metadata, datasets_metadata
from app.dsl import compile_dsl
from app.workflow_plan import compile_workflow_plan


def catalog(status='active',mode='chat'):
    return {'data':[{'provider':'langgenius/test/test','label':{'zh_Hans':'测试供应商'},'credentials':{'api_key':'PRIVATE'},'models':[{'model':'exact-model','label':{'en_US':'Test'},'status':status,'model_properties':{'mode':mode,'context_size':10000,'api_key':'PRIVATE'},'features':['tool-call'],'credentials':'PRIVATE'}]}]}


def test_models_are_allowlisted_and_unavailable_never_selectable():
    rows=models_metadata(catalog(),'llm')
    assert rows[0]['selectable'] and rows[0]['context_size']==10000
    assert 'PRIVATE' not in json.dumps(rows)
    for status in ('disabled','no-configure','no-permission','quota-exceeded','credential-removed','future-status'):
        assert not models_metadata(catalog(status),'llm')[0]['selectable']
    assert not models_metadata(catalog(mode='completion'),'llm')[0]['selectable']


@pytest.mark.parametrize('payload',[{}, {'data':None},{'data':[{}]},{'data':[{'provider':'p','models':[{'model':'m'}]}]}])
def test_invalid_catalog_is_not_reported_empty(payload):
    with pytest.raises(main.DifyError):models_metadata(payload,'llm')


def test_models_endpoint_actual_adapter_and_no_secret_fields(client,monkeypatch):
    env=create_env(client)
    async def read(self,model_type):
        assert model_type=='llm'
        return catalog()
    monkeypatch.setattr(main.DifyClient,'models',read)
    result=client.get(f"/api/environments/{env['id']}/models")
    assert result.status_code==200 and 'PRIVATE' not in result.text
    assert result.json()['environment_id']==env['id'] and result.json()['source']=='console'
    assert client.get(f"/api/environments/{env['id']}/models?model_type=not-a-type").status_code==422


def test_model_rules_require_fresh_available_selection(client,monkeypatch):
    env=create_env(client)
    async def models(self,model_type):return catalog()
    async def rules(self,path,model):
        assert path=='langgenius/test/test' and model=='exact-model'
        return {'data':[{'name':'temperature','label':{'zh_Hans':'温度'},'type':'float','min':0,'max':1,'default':.7,'credentials':'PRIVATE'}]}
    monkeypatch.setattr(main.DifyClient,'models',models)
    monkeypatch.setattr(main.DifyClient,'model_parameters',rules)
    result=client.get(f"/api/environments/{env['id']}/model-parameters",params={'provider':'langgenius/test/test','model':'exact-model'})
    assert result.status_code==200 and result.json()['data'][0]['max']==1 and 'PRIVATE' not in result.text
    result=client.get(f"/api/environments/{env['id']}/model-parameters",params={'provider':'langgenius/test/test','model':'unknown-model'})
    assert result.status_code==422
    for path in ('../test','a/../b','https://target','bad?query'):
        assert client.get(f"/api/environments/{env['id']}/model-parameters",params={'provider':path,'model':'m'}).status_code==422


def test_resources_reject_response_from_changed_connection(client,monkeypatch):
    env=create_env(client)
    async def models(self,model_type):
        record=main.store.get('environment',env['id']);record['base_url']='https://changed.example';main.store.put('environment',env['id'],record)
        return catalog()
    monkeypatch.setattr(main.DifyClient,'models',models)
    assert client.get(f"/api/environments/{env['id']}/models").status_code==409


def test_console_datasets_use_explicit_source_without_dataset_key(client,monkeypatch):
    env=create_env(client)
    async def console(self,page,limit):
        assert page==2 and limit==10
        return {'data':[{'id':'dataset','name':'资料','document_count':1,'credentials':'PRIVATE'}],'has_more':False}
    async def service(*args,**kwargs):pytest.fail('Console source must not call service dataset API')
    monkeypatch.setattr(main.DifyClient,'console_datasets',console)
    monkeypatch.setattr(main.DifyClient,'datasets',service)
    result=client.get(f"/api/environments/{env['id']}/datasets?page=2&limit=10&source=console")
    assert result.status_code==200 and result.json()['source']=='console' and 'PRIVATE' not in result.text
    assert client.get(f"/api/environments/{env['id']}/datasets?source=automatic").status_code==422


def test_resource_metadata_rejects_malformed_rules_and_datasets():
    for payload in ({},{'data':None},{'data':[{}]}):
        with pytest.raises(main.DifyError):parameter_metadata(payload)
    with pytest.raises(main.DifyError):datasets_metadata({'data':[]})
    assert datasets_metadata({'data':[],'has_more':False})=={'data':[],'has_more':False}


def test_extra_model_parameters_compile_in_both_paths(client):
    task=approved(client)
    task['configuration']['model_parameters']={'thinking':False,'reasoning_effort':'low','top_p':1,'response_format':'text'}
    text,validation=compile_dsl(task)
    params=next(n['data']['model']['completion_params'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['data']['type']=='llm')
    assert params['thinking'] is False and params['max_tokens']==2048 and params['reasoning_effort']=='low'
    plan=code_only_plan();plan['nodes'][1]={'id':'code','type':'llm','config':{'system_prompt':'回答','user_prompt':'{{#start.query#}}'}};plan['nodes'][2]['config']['outputs'][0]['value_selector']=['code','text']
    task['workflow_plan']=plan
    text,validation=compile_workflow_plan(task)
    params=next(n['data']['model']['completion_params'] for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['data']['type']=='llm')
    assert validation['valid'] and params['thinking'] is False and params['response_format']=='text'


@pytest.mark.parametrize('params',[{'api_key':'PRIVATE'},{'temperature':.5},{'thinking':[]},{'nested':{}},{'extra':float('inf')},{'bad name':True}])
def test_invalid_extra_parameters_rejected(params):
    with pytest.raises(main.HTTPException):main.validate_config({'model_parameters':params})


@pytest.mark.parametrize("app_type", ["workflow", "advanced-chat"])
def test_opening_and_suggestions_survive_template_and_plan_compilers(client, app_type):
    task=approved(client,app_type=app_type)
    task['configuration'].update({'opening_statement':'这是技术联调，不是客户政策。','suggested_questions':['退货期限多久？']})
    content,validation=compile_dsl(task)
    features=yaml.safe_load(content)['workflow']['features']
    assert features['opening_statement']=='这是技术联调，不是客户政策。' and features['suggested_questions']==['退货期限多久？']
    if app_type=='advanced-chat':
        task['workflow_plan']={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[]}},{'id':'answer','type':'answer','config':{'answer':'测试'}}],'edges':[{'source':'start','target':'answer'}]}
    else:
        task['workflow_plan']=code_only_plan()
    content,validation=compile_workflow_plan(task)
    assert yaml.safe_load(content)['workflow']['features']==features


@pytest.mark.parametrize("configuration", [{'opening_statement':123},{'suggested_questions':['']},{'suggested_questions':['a']*7}])
def test_invalid_opening_configuration_rejected(configuration):
    with pytest.raises(main.HTTPException):main.validate_config(configuration)


def test_scoped_dataset_catalog_denial_is_not_fake_empty_success(client,monkeypatch):
    env=create_env(client)
    async def denied(*args,**kwargs):raise main.DifyError('Dify 返回 HTTP 403。')
    monkeypatch.setattr(main.DifyClient,'datasets',denied)
    response=client.get(f"/api/environments/{env['id']}/datasets?source=service")
    assert response.status_code==502 and '无权读取全局目录' in response.text and '不会自动扩大' in response.text
    assert 'data' not in response.json()
