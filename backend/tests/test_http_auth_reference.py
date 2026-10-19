import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,yaml
from test_api import client,approved
from test_preservation_extensions import http_plan,native as document
from test_aggregation import task
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import load_document,validate_preserved
from app.dsl import _contains_secret_key
from app.case_dsl_semantics import summary
from app import main
from test_assistant_routing import setup,enable,state


def plan(kind='bearer',name='SERVICE_AUTH'):
    value=http_plan();value['nodes'][1]['config']['authentication']={'type':kind,'secret_variable':name,'description':'技术接口认证，导入后在 Dify 填写。','header':'X-Service-Key' if kind=='custom' else 'Authorization'}
    return value


def data(root):return next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='http')
def parse(root):return load_document(yaml.safe_dump(root,allow_unicode=True,sort_keys=False))


@pytest.mark.parametrize('kind',['bearer','basic','custom'])
def test_compile_read_and_preserve_exact_empty_native_secret_reference(kind):
    p=plan(kind);before=copy.deepcopy(p);root=document(p);variables=root['workflow']['environment_variables']
    assert len(variables)==1 and variables[0]['value_type']=='secret' and variables[0]['value']==''
    assert variables[0]['selector']==['env','SERVICE_AUTH']
    auth=data(root)['authorization'];assert auth['type']=='api-key' and auth['config']['type']==kind
    assert auth['config']['api_key']=='{{#env.SERVICE_AUTH#}}'
    assert not _contains_secret_key(root) and parse(root)==root
    original=copy.deepcopy(root);result=validate_preserved(root);assert result['valid'],result['errors'];assert root==original and p==before
    assert any('未补齐不可运行' in w for w in result['warnings'])


@pytest.mark.parametrize('change',['literal','concat','missing_variable','not_secret','nonempty_secret','mask_value','null_value','extra_auth','foreign_selector','duplicate_env','unknown_field','duplicate_header','wrong_header'])
def test_raw_secret_or_unadapted_native_reference_never_enters_reader(change):
    root=document(plan());auth=data(root)['authorization']['config'];env=root['workflow']['environment_variables'][0]
    if change=='literal':auth['api_key']='PRIVATE-KEY'
    elif change=='concat':auth['api_key']='prefix {{#env.SERVICE_AUTH#}}'
    elif change=='missing_variable':root['workflow']['environment_variables']=[]
    elif change=='not_secret':env['value_type']='string'
    elif change=='nonempty_secret':env['value']='PRIVATE-KEY'
    elif change=='mask_value':env['value']='********'
    elif change=='null_value':env['value']=None
    elif change=='extra_auth':auth['password']='PRIVATE'
    elif change=='foreign_selector':env['selector']=['other','SERVICE_AUTH']
    elif change=='duplicate_env':root['workflow']['environment_variables'].append(copy.deepcopy(env))
    elif change=='unknown_field':env['extra']='PRIVATE'
    elif change=='duplicate_header':data(root)['headers']='authorization: something'
    elif change=='wrong_header':auth['header']='X-Other'
    before=copy.deepcopy(root)
    with pytest.raises(ValueError):parse(root)
    assert root==before


@pytest.mark.parametrize('patch',[
 {'type':['bearer']},{'type':'oauth2'},{'secret_variable':'9bad'},{'secret_variable':'a.b'},
 {'description':''},{'description':'sk-'+'x'*32},{'header':'Cookie'}, {'header':'Authorization\r\nOther'},
 {'header':'X-Other'}, {'api_key':'PRIVATE'}, {'value':''},
])
def test_plan_cannot_smuggle_values_or_unknown_authentication(patch):
    p=plan();p['nodes'][1]['config']['authentication'].update(patch)
    result=validate_plan(task(),p);assert not result['valid']
    content,result=compile_workflow_plan({**task(),'workflow_plan':p});assert not content and not result['valid']


def test_same_variable_one_declaration_conflicting_description_is_rejected():
    p=plan();p['nodes'].insert(2,{'id':'second','type':'http-request','config':copy.deepcopy(p['nodes'][1]['config'])})
    p['edges']=[{'source':'start','target':'http'},{'source':'http','target':'second'},{'source':'second','target':'end'}]
    root=document(p);assert len(root['workflow']['environment_variables'])==1
    p['nodes'][2]['config']['authentication']['description']='另一个不兼容用途。'
    assert not validate_plan(task(),p)['valid']


def test_permission_does_not_extend_to_api_key_fields_in_other_contexts():
    root=document(plan())
    root['workflow']['graph']['nodes'][0]['data']['api_key']='{{#env.SERVICE_AUTH#}}'
    assert _contains_secret_key(root)
    with pytest.raises(ValueError):parse(root)
    assert _contains_secret_key({'api_key':'{{#env.SERVICE_AUTH#}}'})


def test_summary_exposes_dependency_names_and_missing_readiness_never_values():
    root=document(plan('custom'));out=summary(root)
    assert out['http_secret_dependencies']==[{'name':'SERVICE_AUTH','description':'技术接口认证，导入后在 Dify 填写。','value_included':False,'readiness':'user_must_configure_in_dify_not_verified'}]
    assert next(n['config'] for n in out['nodes'] if n['id']=='http')['authorization']['config']['api_key']=='{{#env.SERVICE_AUTH#}}'


def test_scope4_cannot_reuse_confirmation_for_new_auth_dependency_range(client):
    t,p,light=setup(client);assert enable(client,t,light).status_code==200
    policy=main.routing.get(t['id']);policy['scope_version']=4;main.store.put('assistant_routing',t['id'],policy)
    assert state(client,t)['required_scope_version']==18 and state(client,t)['blocker']
    assert enable(client,t,light,scope_version=4).status_code==409
    assert enable(client,t,light,scope_version=18).status_code==200


def test_api_build_keeps_secret_empty_and_claims_only_static_verification(client):
    original=approved(client);response=client.post(f"/api/tasks/{original['id']}/plan",json={'revision':original['revision'],'plan':plan()})
    assert response.status_code==200,response.text
    saved=response.json();assert saved['requirements_confirmed'] and not saved['configuration_confirmed']
    assert client.post(f"/api/tasks/{saved['id']}/confirm",json={'kind':'configuration','revision':saved['revision']}).status_code==200
    response=client.post(f"/api/tasks/{saved['id']}/build",json={'revision':saved['revision']});assert response.status_code==200,response.text
    built=response.json();assert built['artifact']['verification']=='static_only' and not built['dify_app_id'] and not built['runs']
    root=load_document(client.get(f"/api/tasks/{saved['id']}/artifact").text)
    assert root['workflow']['environment_variables'][0]['value']==''
    assert data(root)['authorization']['config']['api_key']=='{{#env.SERVICE_AUTH#}}'
    assert any('未补齐不可运行' in w for w in built['artifact']['validation']['warnings'])
