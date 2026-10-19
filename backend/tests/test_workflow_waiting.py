import copy,json,uuid
import pytest
from test_api import client,approved,create_env,example_case
from app import main
from app.workflow_waiting import receipt
from app.dify import DifyError

APP=str(uuid.uuid4());RUN=str(uuid.uuid4());WORKFLOW=str(uuid.uuid4());TOKEN='fake-form-submission-secret-never-save'


def raw():return {'workflow_run_id':RUN,'task_id':'native-task','data':{'id':RUN,'workflow_id':WORKFLOW,'status':'paused','outputs':{'form_token':TOKEN,'result':'private unfinished text'},'paused_nodes':['review'],'reasons':[{'form_token':TOKEN,'form_content':'private review text','TYPE':'human_input_required'}],'error':TOKEN,'extra_private':TOKEN}}


def setup(client,monkeypatch):
    env=create_env(client);client.patch(f"/api/environments/{env['id']}",json={'service_app_id':APP,'service_api_key':'fixture-only'})
    task=approved(client,env_id=env['id']);task=client.post(f"/api/tasks/{task['id']}/test-cases",json={'revision':task['revision'],'cases':[example_case('contains')]}).json()
    for kind in ('requirements','configuration'):assert client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).status_code==200
    assert client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']}).status_code==200
    task=main.get_task(task['id']);task['dify_app_id']=APP;main.save_task(task);calls=[]
    async def paused(self,inputs):calls.append(1);return raw()
    monkeypatch.setattr(main.DifyClient,'run_workflow',paused)
    response=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'case_id':'warranty'});assert response.status_code==200,response.text
    return response.json(),env,calls


def check(client,task):return client.get(f"/api/tasks/{task['id']}/runs/{task['runs'][-1]['id']}/waiting-state")


def test_paused_response_no_credentials_raw_body_or_business_pass_and_repeat_blocked(client,monkeypatch):
    task,env,calls=setup(client,monkeypatch);record=task['runs'][-1]
    assert record['status']=='waiting_platform' and task['status']=='waiting_platform' and 'evaluation' not in record
    assert TOKEN not in json.dumps(task) and 'private review text' not in json.dumps(task) and TOKEN.encode() not in main.store.path.read_bytes()
    summary=client.get(f"/api/tasks/{task['id']}/acceptance").json();assert not summary['all_required_passed'] and summary['cases'][0]['status']=='needs_review'
    report=client.get(f"/api/tasks/{task['id']}/report");assert TOKEN not in report.text
    assert client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'case_id':'warranty'}).status_code==409 and calls==[1]
    main.recover_external_actions();assert main.get_task(task['id'])['runs'][-1]['status']=='waiting_platform' and calls==[1]


@pytest.mark.parametrize('status',['succeeded','failed','stopped','partial-succeeded','running','paused'])
def test_read_only_original_run_status_no_result_adoption_or_submit(client,monkeypatch,status):
    task,env,original_calls=setup(client,monkeypatch);reads=[];before=copy.deepcopy(main.get_task(task['id']))
    async def native(self,method,path,**kwargs):
        reads.append((method,path));assert method=='GET' and path.endswith('/'+RUN) and self.env['id']==env['id']
        return {'id':RUN,'status':status,'outputs':{'result':'保修一年','form_token':TOKEN},'graph':{'private':TOKEN},'error':TOKEN}
    monkeypatch.setattr(main.DifyClient,'request',native)
    response=check(client,task);assert response.status_code==200,response.text
    updated=main.get_task(task['id']);record=updated['runs'][-1]
    assert record['status']==('platform_finished' if status in {'succeeded','failed','stopped','partial-succeeded'} else 'waiting_platform')
    assert record['waiting_state']['platform_status']==status and not record['waiting_state']['business_verified']
    assert 'evaluation' not in record and TOKEN not in json.dumps(updated) and len(reads)==1 and original_calls==[1]
    assert all(updated[k]==before[k] for k in ('revision','requirements','configuration','requirements_confirmed','configuration_confirmed','artifact'))
    assert not client.get(f"/api/tasks/{task['id']}/acceptance").json()['all_required_passed']


def test_connection_rotation_after_read_does_not_save_stale_observation(client,monkeypatch):
    task,env,calls=setup(client,monkeypatch);before=copy.deepcopy(main.get_task(task['id']))
    async def read(self,*a,**kw):main.store.set_secret(env['id'],'console_token','fixture-rotated');return {'id':RUN,'status':'succeeded'}
    monkeypatch.setattr(main.DifyClient,'request',read)
    assert check(client,task).status_code==409 and main.get_task(task['id'])==before and calls==[1]


def test_task_environment_switch_keeps_original_waiting_target(client,monkeypatch):
    task,env,calls=setup(client,monkeypatch);row=main.get_task(task['id']);row['environment_id']=str(uuid.uuid4());row['status']='configuration';main.store.put('task',row['id'],row)
    async def read(self,method,path,**kw):assert self.env['id']==env['id'];assert method=='GET';return {'id':RUN,'status':'succeeded'}
    monkeypatch.setattr(main.DifyClient,'request',read)
    assert check(client,task).status_code==200
    updated=main.get_task(task['id']);assert updated['environment_id']==row['environment_id'] and updated['status']=='configuration' and calls==[1]


@pytest.mark.parametrize('patch',[{'id':'wrong'},{'id':str(uuid.uuid4())},{'status':'unexpected-secret-status'},{'status':{}}])
def test_untrusted_native_read_rejects_without_saving_raw_response(client,monkeypatch,patch):
    task,env,calls=setup(client,monkeypatch);before=copy.deepcopy(main.get_task(task['id']))
    async def read(*a,**kw):return {'id':RUN,'status':'succeeded','private':TOKEN,**patch}
    monkeypatch.setattr(main.DifyClient,'request',read)
    response=check(client,task);assert response.status_code==502 and TOKEN not in response.text and main.get_task(task['id'])==before


def test_malformed_paused_identifiers_never_preserve_private_body():
    value=raw();value['workflow_run_id']=str(uuid.uuid4())
    with pytest.raises(DifyError) as captured:receipt(value)
    assert TOKEN not in json.dumps(captured.value.result) and 'private review text' not in json.dumps(captured.value.result)


def test_unknown_paused_record_stays_blocked_across_new_revision(client,monkeypatch):
    task,env,calls=setup(client,monkeypatch);row=main.get_task(task['id']);record=row['runs'][-1]
    record['status']='unknown';row['revision']+=1;row['status']='imported';main.store.put('task',row['id'],row)
    built=client.post(f"/api/tasks/{row['id']}/build",json={'revision':row['revision']});assert built.status_code==200,built.text
    result=client.post(f"/api/tasks/{row['id']}/run",json={'revision':row['revision'],'case_id':'warranty'})
    assert result.status_code==409 and calls==[1]
