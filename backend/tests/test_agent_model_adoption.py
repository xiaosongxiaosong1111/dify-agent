import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,yaml
from app import main
from app.dsl_roundtrip import parse,digest
from test_agent_plan import runtime_task
from test_agent_preservation import soul
from test_dsl_roundtrip import capture,prepared
from test_api import client


def setup(client,*,kind='normal'):
    task=runtime_task(client);task['dify_app_id']=None
    task['configuration']['model_parameters']['presence_penalty']=.3
    main.save_task(task);current=parse(main.compile_current(task)[0],'agent')
    model=soul(current)['model'];model['model']='public-file-model'
    model['model_settings'].pop('presence_penalty',None);model['model_settings'].update(temperature=.6,max_tokens=512,thinking=True)
    if kind=='stop':model['model_settings']['stop']=['END']
    if kind=='tool':soul(current)['tools']['cli_tools']=[{'name':'keep-original-tool'}]
    task=capture(client,task,current)
    preview=client.get(f"/api/tasks/{task['id']}/dsl-merge").json()
    return task,current,preview


def body(task,p,**patch):
    data={'revision':task['revision'],'reference_id':p['reference_id'],'merge_token':p['merge_token'],'document_token':p['document_token'],'draft_revision':0,'choices':{},'acknowledge_pending_resource_review':True}
    data.update(patch);return data


def adopt(client,task,p,**patch):return client.post(f"/api/tasks/{task['id']}/dsl-merge/model-configuration",json=body(task,p,**patch))


def test_explicit_adoption_preserves_source_and_history_replaces_whole_model_extras_and_rebuilds(client):
    task,current,p=setup(client);before=copy.deepcopy(main.get_task(task['id']));ref=copy.deepcopy(main.store.get('dsl_reference',p['reference_id']))
    result=adopt(client,task,p);assert result.status_code==200,result.text
    updated=result.json();assert updated['revision']==before['revision']+1 and not updated['configuration_confirmed']
    assert updated['dify_app_id'] is None and updated['artifact'] is None and not updated['plan_stale']
    assert updated['configuration']['dify_model']=='public-file-model'
    assert updated['configuration']['temperature']==.6 and updated['configuration']['max_tokens']==512
    assert 'presence_penalty' not in updated['configuration']['model_parameters']
    for key in before['configuration']:
        if key not in {'dify_model_provider','dify_model','temperature','max_tokens','model_parameters'}:assert updated['configuration'][key]==before['configuration'][key]
    assert updated['agent_plan']==before['agent_plan'] and updated['environment_id']==before['environment_id']
    assert main.store.get('dsl_reference',p['reference_id'])==ref
    assert updated['versions'][-1]['configuration']==before['configuration']
    audit=updated['model_configuration_adoptions'][-1];assert audit['verification']=='local_configuration_only' and audit['pending_resource_review']
    assert audit['document_token']==p['document_token'] and audit['previous_revision']==before['revision']
    assert len(updated['runs'])==len(before['runs'])
    next_preview=client.get(f"/api/tasks/{task['id']}/dsl-merge").json();assert next_preview['validation']['valid'] and next_preview['agent_model_comparison'] is None
    assert client.post(f"/api/tasks/{task['id']}/build",json={'revision':updated['revision']}).status_code==422
    response=client.post(f"/api/tasks/{task['id']}/dsl-merge/apply",json={'revision':updated['revision'],'reference_id':next_preview['reference_id'],'merge_token':next_preview['merge_token'],'choices':{}});assert response.status_code==200,response.text
    updated=response.json()
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':updated['revision'],'kind':kind});assert response.status_code==200,response.text
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':updated['revision']});assert response.status_code==200,response.text
    assert digest(parse(main.artifact_path(response.json()).read_text('utf-8'),'agent'))==digest(current)
    assert adopt(client,task,p).status_code==409


@pytest.mark.parametrize('patch',[
    {'acknowledge_pending_resource_review':False},{'acknowledge_pending_resource_review':1},
    {'acknowledge_pending_resource_review':'true'},{'revision':True},{'revision':'1'},
    {'draft_revision':True},{'draft_revision':-1},{'document_token':'bad'},
    {'configuration':{'dify_model':'injected-model'}},
],ids=[f'strict{i}' for i in range(9)])
def test_missing_review_or_coerced_and_extra_fields_never_write_task(client,patch):
    task,current,p=setup(client);before=copy.deepcopy(main.get_task(task['id']))
    response=adopt(client,task,p,**patch);assert response.status_code==422,response.text
    assert main.get_task(task['id'])==before


@pytest.mark.parametrize('key',['reference_id','merge_token','document_token'])
def test_stale_source_or_preview_tokens_never_write_task(client,key):
    task,current,p=setup(client);before=copy.deepcopy(main.get_task(task['id']))
    response=adopt(client,task,p,**{key:'f'*64});assert response.status_code==409,response.text
    assert main.get_task(task['id'])==before


@pytest.mark.parametrize('kind',['stop','tool'])
def test_unexpressible_model_refused_but_local_model_fix_does_not_drop_unsupported_tools(client,kind):
    task,current,p=setup(client,kind=kind);before=copy.deepcopy(main.get_task(task['id']))
    result=adopt(client,task,p)
    if kind=='stop':
        assert result.status_code==422 and main.get_task(task['id'])==before
    else:
        assert result.status_code==200,result.text
        next_p=client.get(f"/api/tasks/{task['id']}/dsl-merge").json()
        assert not next_p['validation']['valid'] and next_p['agent_model_comparison'] is None
        assert main.store.get('dsl_reference',p['reference_id'])['current']==current
        assert 'keep-original-tool' in next_p['content']


def test_all_conflicts_must_be_chosen_saved_and_bound_before_adoption(client):
    task,current,p=setup(client)
    task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'dify_model':'public-generated-model'}}).json()
    p=client.get(f"/api/tasks/{task['id']}/dsl-merge").json();assert p['unresolved']
    before=copy.deepcopy(main.get_task(task['id']));assert adopt(client,task,p).status_code==422
    choices={c['path']:'current' for c in p['conflicts']}
    p=client.post(f"/api/tasks/{task['id']}/dsl-merge/preview",json={'revision':task['revision'],'choices':choices}).json();assert not p['unresolved']
    response=adopt(client,task,p,choices=choices);assert response.status_code==422 and '先保存' in response.text
    assert main.get_task(task['id'])==before
    response=client.put(f"/api/tasks/{task['id']}/dsl-merge/draft",json={'revision':task['revision'],'draft_revision':0,'reference_id':p['reference_id'],'document_token':p['document_token'],'choices':choices});assert response.status_code==200,response.text
    saved=copy.deepcopy(main.store.get('merge_draft',task['id']))
    assert adopt(client,task,p,choices=choices,draft_revision=0).status_code==409
    response=adopt(client,task,p,choices=choices,draft_revision=1);assert response.status_code==200,response.text
    assert response.json()['configuration']['dify_model']=='public-file-model'
    assert main.store.get('merge_draft',task['id'])==saved
    state=client.get(f"/api/tasks/{task['id']}/dsl-merge/draft").json();assert state['stale'] and state['record']['choices']==choices
    assert response.json()['model_configuration_adoptions'][-1]['choices']==choices


@pytest.mark.parametrize('state',['busy','plan_stale','origin_changed'])
def test_active_stale_or_changed_origin_cannot_adopt(client,state):
    task,current,p=setup(client)
    if state=='busy':task['status']='running';main.save_task(task)
    elif state=='plan_stale':task['plan_stale']=True;main.save_task(task)
    else:
        env=main.store.get('environment',task['environment_id']);env['base_url']='http://127.0.0.1:8999';main.store.put('environment',env['id'],env)
    before=copy.deepcopy(main.get_task(task['id']));response=adopt(client,task,p)
    assert response.status_code==(409 if state=='busy' else 422),response.text
    assert main.get_task(task['id'])==before


def test_workflow_is_not_converted_to_agent_by_adoption(client):
    task,current=prepared(client);before=copy.deepcopy(main.get_task(task['id']))
    response=client.post(f"/api/tasks/{task['id']}/dsl-merge/model-configuration",json={'revision':task['revision'],'reference_id':'not-used','merge_token':'f'*64,'document_token':'f'*64,'draft_revision':0,'acknowledge_pending_resource_review':True})
    assert response.status_code==422 and main.get_task(task['id'])==before


def test_equal_model_cannot_be_repeatedly_adopted_as_new_configuration(client):
    task=runtime_task(client);task['dify_app_id']=None;main.save_task(task)
    current=parse(main.compile_current(task)[0],'agent');task=capture(client,task,current)
    p=client.get(f"/api/tasks/{task['id']}/dsl-merge").json();before=copy.deepcopy(main.get_task(task['id']))
    assert adopt(client,task,p).status_code==422 and main.get_task(task['id'])==before
