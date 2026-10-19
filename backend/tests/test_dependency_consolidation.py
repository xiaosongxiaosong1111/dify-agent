import copy,json,sys,yaml
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app.workflow_environment_mapping import build,WorkflowMappingRequest
from app.dsl_roundtrip import digest,parse,validate_preserved
from test_workflow_environment_mapping import setup
from test_api import client,create_env
from test_dsl_roundtrip import prepared,capture
from test_workflow_mapping_drafts import ready,save,changed
from app import main
from app.workflow_mapping_drafts import KIND,HISTORY


def two_plugins():
    task,root,source,target,request=setup()
    root['dependencies'].append({'type':'marketplace','value':{'marketplace_plugin_unique_identifier':'public/other:1@src','version':None},'current_identifier':'other-source-local'})
    next(n for n in root['workflow']['graph']['nodes'] if n['id']=='two')['data']['model']['provider']='public/other/provider'
    source.update(content=yaml.safe_dump(root,allow_unicode=True),document_token=digest(root),validation=validate_preserved(root))
    assert source['validation']['valid']
    request.document_token=digest(root);request.dependency_mapping['public/other:1@src']='public/target:2@dst'
    return task,root,source,target,request


def test_identical_target_versions_require_explicit_new_choice_and_keep_source():
    task,root,source,target,request=two_plugins();before=copy.deepcopy((task,root,source))
    with pytest.raises(ValueError,match='明确接受合并'):build(task,source,target,request)
    assert (task,root,source)==before
    request.acknowledge_dependency_consolidation=True
    result=build(task,source,target,request);output=parse(result['content'],'workflow')
    assert result['can_download'] and len(output['dependencies'])==2  # One chat plugin and the independent reranker.
    assert [d['value']['marketplace_plugin_unique_identifier'] for d in output['dependencies']]==['public/target:2@dst','public/reranktarget:3@dst']
    assert result['dependency_consolidation']==[{'target_identifier':'public/target:2@dst','source_identifiers':['public/source:1@src','public/other:1@src']}]
    assert any(c['kind']=='dependency_consolidation' and c['acknowledged'] is True for c in result['changes'])
    assert (task,root,source)==before and not result['task_modified'] and not result['target_resources_verified']


@pytest.mark.parametrize('change',['conflicting_version','duplicate_additional','blank_identifier'])
def test_confirmation_does_not_allow_conflicting_or_unnecessary_dependencies(change):
    task,root,source,target,request=two_plugins();request.acknowledge_dependency_consolidation=True
    if change=='conflicting_version':request.dependency_mapping['public/other:1@src']='public/target:9@different'
    elif change=='duplicate_additional':request.additional_dependencies.append('public/target:2@dst')
    else:request.dependency_mapping={key:'' for key in request.dependency_mapping}
    with pytest.raises(ValueError):build(task,source,target,request)


def test_legacy_saved_payload_hash_and_idempotence_do_not_gain_new_default_keys(client):
    task,env,path,payload=ready(client)
    first=save(client,path,payload);record=first['record'];assert 'acknowledge_dependency_consolidation' not in record['payload']
    assert digest(record['payload'])==record['payload_token'] and first['restorable']
    assert first['restore_inputs']['acknowledge_dependency_consolidation'] is False
    read=client.get(path+'/draft').json();assert read['record']==record and read['restorable']
    assert save(client,path,{**payload,'draft_revision':1})['draft_revision']==1
    assert save(client,path,{**payload,'draft_revision':1,'acknowledge_dependency_consolidation':False})['draft_revision']==1
    assert main.store.get(KIND,task['id'])==record and main.store.get(HISTORY,task['id']+':1') is None
    second=save(client,path,{**changed(client,path,{**payload,'draft_revision':1}),'acknowledge_dependency_consolidation':False})
    assert second['draft_revision']==2 and main.store.get(HISTORY,task['id']+':1')==record
    historical=client.get(path+'/draft/history/1').json();assert historical['record']==record and historical['restorable']


def test_new_consolidated_mapping_saved_as_inputs_but_restore_clears_consolidation_choice(client):
    task,_=prepared(client);_,root,_,_,request=two_plugins();task['workflow_plan']=setup()[0]['workflow_plan'];task['dify_app_id']=None;main.save_task(task);task=capture(client,task,root)
    p=client.get(f"/api/tasks/{task['id']}/dsl-merge").json();assert p['validation']['valid'] and not p['unresolved']
    env=create_env(client);body=request.model_dump();body.update(revision=task['revision'],reference_id=p['reference_id'],merge_token=p['merge_token'],document_token=p['document_token'],target_environment_id=env['id'],expected_target_connection_revision=env.get('connection_revision'),acknowledge_dependency_consolidation=True)
    path=f"/api/tasks/{task['id']}/workflow-environment-mapping";before=copy.deepcopy(main.store.get('task',task['id']))
    response=client.post(path+'/preview',json=body);assert response.status_code==200,response.text;preview=response.json();assert preview['dependency_consolidation']
    stored=save(client,path,{**body,'draft_revision':0,'preview_token':preview['preview_token']})
    assert stored['record']['payload']['acknowledge_dependency_consolidation'] is True and stored['restore_inputs']['acknowledge_dependency_consolidation'] is False
    assert not stored['confirmed'] and main.store.get('task',task['id'])==before
    old_confirmation={**body,'acknowledge_dependency_consolidation':False};assert client.post(path+'/preview',json=old_confirmation).status_code==422
