import copy
import yaml
import pytest

from test_api import client,approved
from test_dsl_roundtrip import prepared,capture,apply
from test_aggregation import merge_plan,task
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,digest
from app import main


def http_plan():
    return {'schema_version':1,'nodes':[
        {'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'paragraph','required':False,'default':''}]}},
        {'id':'http','type':'http-request','config':{'method':'POST','url':'https://service.company.internal/api/{{#start.query#}}','headers':'Content-Type: application/json','params':'input: {{#start.query#}}','body':{'type':'json','data':[{'type':'text','key':'','value':'{"input":"{{#start.query#}}"}'}]}}},
        {'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['http','body']}]}}
    ],'edges':[{'source':'start','target':'http'},{'source':'http','target':'end'}]}


def native(plan):
    text,result=compile_workflow_plan({**task(),'workflow_plan':plan});assert result['valid'],result['errors']
    return yaml.safe_load(text)


def test_noauth_http_preservation_keeps_native_fields_and_templates():
    root=native(http_plan());data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='http')
    data['retry_config']={'retry_enabled':False,'max_retries':0,'retry_interval':120}
    before=copy.deepcopy(root);result=validate_preserved(root)
    assert result['valid'],result['errors'];assert root==before


def test_aggregation_preservation_keeps_candidate_order():
    root=native(merge_plan());before=copy.deepcopy(root)
    assert validate_preserved(root)['valid'] and root==before
    data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='merge')
    data['variables'].reverse();assert validate_preserved(root)['valid']
    assert data['variables'][0]==['respond','output']


@pytest.mark.parametrize('change',['auth','header','placeholder_domain','files','missing_ref','malformed_ref','nested_ref'])
def test_http_unsupported_or_bad_preserved_fields_rejected(change):
    root=native(http_plan());data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='http')
    if change=='auth':data['authorization']={'type':'api-key','config':{'header':'Authorization'}}
    elif change=='header':data['headers']='Cookie: developer-test'
    elif change=='placeholder_domain':data['url']='https://example.org/'
    elif change=='files':data['body']={'type':'form-data','data':[{'type':'file','key':'upload','value_selector':['start','query']}]}
    elif change=='missing_ref':data['body']['data'][0]['value']='{{#ghost.output#}}'
    elif change=='malformed_ref':data['params']='input: {{#start.query'
    else:data['url']='https://service.company.internal/{{#start.query.field#}}'
    assert not validate_preserved(root)['valid']


@pytest.mark.parametrize('change',['group','missing_candidate','mismatch','missing_path'])
def test_bad_preserved_aggregation_rejected(change):
    root=native(merge_plan());data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='merge')
    if change=='group':data['advanced_settings']={'group_enabled':True,'groups':[]}
    elif change=='missing_candidate':data['variables']=[['unknown','output']]
    elif change=='mismatch':data['output_type']='number'
    else:data['variables']=[['ask','output']]
    assert not validate_preserved(root)['valid']


@pytest.mark.parametrize('field',['url','headers','params','body'])
def test_request_templates_cannot_read_sibling_branch(field):
    plan=merge_plan();plan['nodes'].insert(-1,{'id':'http','type':'http-request','config':{'url':'https://service.company.internal/api','method':'GET'}})
    plan['edges'][-1]['target']='http';plan['edges'].append({'source':'http','target':'end'})
    cfg=next(n['config'] for n in plan['nodes'] if n['id']=='http')
    bad='{{#ask.output#}}'
    if field=='url':cfg[field]='https://service.company.internal/'+bad
    elif field=='body':cfg[field]={'type':'raw-text','data':[{'type':'text','key':'','value':bad}]}
    else:cfg[field]='input: '+bad
    result=validate_plan(task(),plan);assert not result['valid'] and any('不保证在所有路径' in e for e in result['errors'])
    cfg[field]=str(cfg[field]).replace('ask.output','merge.output') if field!='body' else {'type':'raw-text','data':[{'type':'text','key':'','value':'{{#merge.output#}}'}]}
    assert validate_plan(task(),plan)['valid']


@pytest.mark.parametrize('kind',['http','aggregation'])
def test_actual_api_capture_merge_and_build_preserves_extended_node(client,kind):
    old,_=prepared(client);plan=http_plan() if kind=='http' else merge_plan()
    response=client.post(f"/api/tasks/{old['id']}/plan",json={'revision':old['revision'],'plan':plan});assert response.status_code==200,response.text
    t=response.json()
    for check in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':check});assert response.status_code==200,response.text;t=response.json()
    t=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).json();root=yaml.safe_load(main.artifact_path(t).read_text(encoding='utf-8'))
    node=next(n for n in root['workflow']['graph']['nodes'] if n['id']==('http' if kind=='http' else 'merge'))
    if kind=='http':node['data']['headers']='X-Source: manual-preservation';node['data']['retry_config']['retry_enabled']=False
    else:node['data']['variables'].reverse()
    t=capture(client,t,root);response,_=apply(client,t);assert response.status_code==200,response.text;t=response.json()
    for check in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':check});assert response.status_code==200,response.text;t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    final=yaml.safe_load(main.artifact_path(response.json()).read_text(encoding='utf-8'));assert digest(final)==digest(root)
    assert not response.json()['dify_app_id']


@pytest.mark.parametrize('field,value',[('headers','X-API-Key: synthetic-private-value'),('params','token: synthetic-private-value'),('url','https://user:synthetic-password@service.company.internal/api')])
def test_known_http_credentials_rejected_before_reference_is_saved(client,field,value):
    t=approved(client);root=native(http_plan());data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='http');data[field]=value
    response=client.post(f"/api/tasks/{t['id']}/reference-dsl/preview",json={'revision':t['revision'],'filename':'unsafe.yaml','content':yaml.safe_dump(root)})
    assert response.status_code==422 and 'synthetic-private-value' not in response.text and 'synthetic-password' not in response.text
    assert not main.store.list('reference_dsl_preview') and not main.get_task(t['id'])['materials']


@pytest.mark.parametrize('params',['token: synthetic-value','api_key=synthetic-value'])
def test_generated_http_params_do_not_emit_credentials(params):
    plan=http_plan();plan['nodes'][1]['config']['params']=params
    text,result=compile_workflow_plan({**task(),'workflow_plan':plan})
    assert not text and not result['valid'] and all('synthetic-value' not in e for e in result['errors'])
