import copy
import httpx,pytest
from test_api import client
from test_knowledge import task_with_env,propose
from test_dify_reauth import expired,mock_login
from test_transports import transport_client
from app import main,dify
from app.console_reauth import EMAIL,PASSWORD,BINDING


@pytest.mark.parametrize('change',[None,'base_url','version','connection_revision'])
def test_knowledge_preparation_accepts_auth_only_refresh_but_not_changed_connection(client,monkeypatch,change):
    task,target=task_with_env(client);env=main.store.get('environment',target['id'])
    env[BINDING]={**{k:env[k] for k in ('base_url','version')},'workspace_id':'workspace-test'};env['console_workspace_id']='workspace-test'
    main.store.put_with_secrets('environment',env['id'],env,{EMAIL:'user@test.local',PASSWORD:'PASSWORD-PRIVATE','console_token':expired()})
    before=copy.deepcopy(main.get_task(task['id']));calls=mock_login(monkeypatch);seen=[]
    def handler(request):
        seen.append(request);assert request.method=='GET' and request.url.path=='/console/api/workspaces/current/summary'
        assert request.headers['authorization']=='Bearer new-access'
        if change:
            value=main.store.get('environment',env['id']);value[change]='changed';main.store.put('environment',env['id'],value)
        return httpx.Response(200,json={'id':'workspace-test','name':'隔离工作空间'})
    transport_client(monkeypatch,dify,handler)
    result=propose(client,task)
    assert result.status_code==(409 if change else 201),result.text
    assert len(calls)==len(seen)==1 and main.get_task(task['id'])==before
    if change:assert not main.store.list('knowledge_job')
    else:
        job=result.json();assert job['status']=='draft' and not job['operations'] and job['dataset_id'] is None
        assert job['connection']=={k:env[k] for k in ('base_url','version','connection_revision')}
        assert job['workspace']['id']=='workspace-test'
    assert 'PASSWORD-PRIVATE' not in result.text and 'user@test.local' not in result.text


@pytest.mark.parametrize('endpoint',['models','model-parameters?provider=langgenius%2Ftest%2Ftest&model=exact-model','datasets?source=console'])
@pytest.mark.parametrize('connection_changed',[False,True])
def test_resource_directory_accepts_only_auth_metadata_refresh(client,monkeypatch,endpoint,connection_changed):
    from test_resources import catalog
    from test_api import create_env
    target=create_env(client);env=main.store.get('environment',target['id']);env[BINDING]={**{k:env[k] for k in ('base_url','version')},'workspace_id':'workspace-test'};env['console_workspace_id']='workspace-test'
    main.store.put_with_secrets('environment',env['id'],env,{EMAIL:'user@test.local',PASSWORD:'PASSWORD-PRIVATE','console_token':expired()})
    calls=mock_login(monkeypatch);seen=[]
    def handler(request):
        seen.append(request);assert request.method=='GET' and request.headers['authorization']=='Bearer new-access'
        if connection_changed and len(seen)==1:
            changed=main.store.get('environment',env['id']);changed['connection_revision']='different';main.store.put('environment',env['id'],changed)
        if request.url.path.endswith('/parameter-rules'):return httpx.Response(200,json={'data':[]})
        if request.url.path.endswith('/datasets'):return httpx.Response(200,json={'data':[],'has_more':False})
        assert request.url.path.endswith('/model-types/llm');return httpx.Response(200,json=catalog())
    transport_client(monkeypatch,dify,handler)
    result=client.get(f"/api/environments/{env['id']}/"+endpoint)
    assert result.status_code==(409 if connection_changed else 200),result.text
    assert len(calls)==1 and len(seen)==(2 if endpoint.startswith('model-parameters') else 1)
    assert 'PRIVATE' not in result.text and 'user@test.local' not in result.text
