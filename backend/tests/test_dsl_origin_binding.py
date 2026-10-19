import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,yaml
from app import main,dsl_roundtrip
from app.dify import DifyClient
from test_api import client
from test_dsl_roundtrip import prepared,capture,changed,apply


def alter_env(task,key,value):
    env=main.store.get('environment',task['environment_id']);env[key]=value;main.store.put('environment',env['id'],env)


@pytest.mark.parametrize('key,value',[('base_url','http://127.0.0.1:8999'),('version','1.16.0')],ids=['address','version'])
def test_uploaded_dsl_freezes_origin_and_cannot_preview_against_changed_profile(client,key,value):
    task,root=prepared(client);task=capture(client,task,changed(root));ref=main.store.get('dsl_reference',task['dsl_reference']['id'])
    env=main.store.get('environment',task['environment_id']);assert ref['environment_fingerprint']==[env['base_url'],env['version']]
    before=copy.deepcopy(main.get_task(task['id']));alter_env(task,key,value)
    response=client.get(f"/api/tasks/{task['id']}/dsl-merge")
    assert response.status_code==422 and '源环境地址或版本变化' in response.text
    assert main.get_task(task['id'])==before and main.store.get('dsl_reference',ref['id'])==ref


@pytest.mark.parametrize('key,value',[('base_url','http://127.0.0.1:8999'),('version','1.16.0')],ids=['address','version'])
def test_accepted_overlay_cannot_be_rebuilt_for_same_id_new_origin(client,key,value):
    task,root=prepared(client);task=capture(client,task,changed(root));response,p=apply(client,task);assert response.status_code==200
    task=response.json()
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind});assert response.status_code==200,response.text
    before=copy.deepcopy(main.get_task(task['id']));alter_env(task,key,value)
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']})
    assert response.status_code==422 and '源环境地址或版本变化' in response.text
    assert main.get_task(task['id'])==before


def test_legacy_missing_origin_requires_recapture_but_explicit_discard_remains_possible(client):
    task,root=prepared(client);task=capture(client,task,changed(root));ref=main.store.get('dsl_reference',task['dsl_reference']['id'])
    ref['environment_fingerprint']=None;main.store.put('dsl_reference',ref['id'],ref)
    response=client.get(f"/api/tasks/{task['id']}/dsl-merge")
    assert response.status_code==422 and '旧 DSL 引用未固定' in response.text
    assert main.store.get('dsl_reference',ref['id'])==ref
    response=client.post(f"/api/tasks/{task['id']}/dsl-reference/discard",json={'revision':task['revision'],'acknowledge_loss':True})
    assert response.status_code==200 and main.store.get('dsl_reference',ref['id'])==ref


def test_profile_change_during_upload_parse_does_not_save_reference(client,monkeypatch):
    task,root=prepared(client);current=changed(root);current['app']['description']='origin-read-race-marker'
    original=dsl_roundtrip.parse
    def racing(content,mode):
        result=original(content,mode)
        if 'origin-read-race-marker' in content:alter_env(task,'base_url','http://127.0.0.1:8999')
        return result
    monkeypatch.setattr(dsl_roundtrip,'parse',racing)
    before=copy.deepcopy(main.get_task(task['id']))
    response=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision'],'content':yaml.safe_dump(current)})
    assert response.status_code==409 and '本次未保存引用' in response.text
    assert main.get_task(task['id'])==before and not main.store.list('dsl_reference')


def test_profile_change_during_online_export_does_not_save_reference(client,monkeypatch):
    task,root=prepared(client);calls=[]
    async def racing(self,app_id):
        calls.append(app_id);alter_env(task,'base_url','http://127.0.0.1:8999');return yaml.safe_dump(changed(root))
    monkeypatch.setattr(DifyClient,'export_dsl',racing);before=copy.deepcopy(main.get_task(task['id']))
    response=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision']})
    assert response.status_code==409 and len(calls)==1
    assert main.get_task(task['id'])==before and not main.store.list('dsl_reference')


def test_no_selected_environment_still_allows_local_agent_preservation(client):
    from test_agent_plan import prepare
    task=prepare(client);assert task['environment_id'] is None
    current=dsl_roundtrip.parse(main.compile_current(task)[0],'agent')
    task=capture(client,task,current);ref=main.store.get('dsl_reference',task['dsl_reference']['id'])
    assert ref['environment_fingerprint'] is None
    response,p=apply(client,task);assert response.status_code==200,response.text
    assert p['validation']['valid']
