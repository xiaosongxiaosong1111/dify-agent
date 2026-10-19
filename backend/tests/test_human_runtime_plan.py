import copy,json,uuid
import pytest,yaml
from test_api import client,approved,create_env
from test_human_review import plan
from app import main


def setup(client):
    env=create_env(client);task=approved(client,env_id=env['id']);task['workflow_plan']=plan();main.store.put('task',task['id'],task)
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200,response.text
    return response.json(),env


def prepare(client,task,**patch):return client.post(f"/api/tasks/{task['id']}/human-runtime/prepare",json={'revision':task['revision'],'input':{'query':'仅本机技术审核对象'},**patch})


def test_local_concrete_plan_frozen_input_scope_no_calls_or_implicit_approval(client,monkeypatch):
    task,env=setup(client);before=copy.deepcopy(main.get_task(task['id']))
    async def forbidden(*a,**kw):pytest.fail('准备不能调用模型、平台或创建资源')
    monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
    response=prepare(client,task);assert response.status_code==200,response.text;p=response.json()
    assert p['state']=='prepared_unapproved' and p['execution_available'] and not p['role_restriction_enforced']
    assert p['resource_counts']=={'new_apps':1,'publish_attempts':1,'new_app_keys':1,'workflow_run_attempts':1,'expected_human_forms':1,'human_submissions':0}
    assert p['environment_id']==env['id'] and p['input']=={'query':'仅本机技术审核对象'} and len(p['resource_token'])==64
    assert not p['review']['rendered_form_available'] and p['review']['object_template']=='请审核：\n{{#start.query#}}'
    assert main.get_task(task['id'])==before
    assert client.post(f"/api/tasks/{task['id']}/human-runtime/{p['id']}/execute",json={'revision':task['revision'],'resource_token':p['resource_token'],'approve_resource_plan':False}).status_code==422


@pytest.mark.parametrize('value',[{}, {'query':123},{'query':'sk-fake-private-key-0123456789'},{'query':'valid','extra':'unused'},{'query':['unsupported']}])
def test_invalid_input_credentials_unknown_fields_never_recorded(client,value):
    task,env=setup(client);response=prepare(client,task,input=value);assert response.status_code==422
    assert not main.store.list('human_runtime_plan') and 'sk-fake-private' not in response.text


@pytest.mark.parametrize('change',['template','feature','variable','second_review','extra_channel','numeric_input'])
def test_unadapted_scope_never_silently_omitted_or_claimed_free(client,change):
    task,env=setup(client);path=main.artifact_path(task);root=yaml.safe_load(path.read_text(encoding='utf-8'));nodes=root['workflow']['graph']['nodes']
    if change=='template':nodes[2]['data'].update(template='{{message}}',variables=[{'variable':'message','value_selector':['start','query'],'value_type':'string'}])
    elif change=='feature':root['workflow']['features']['speech_to_text']['enabled']=True
    elif change=='variable':root['workflow']['environment_variables']=[{'id':str(uuid.uuid4()),'name':'state','value_type':'string','value':'extra'}]
    elif change=='second_review':nodes.append({**copy.deepcopy(nodes[1]),'id':'other-review'})
    elif change=='extra_channel':nodes[1]['data']['delivery_methods'].append({'id':str(uuid.uuid4()),'type':'email','enabled':False,'config':{}})
    else:nodes[0]['data']['variables'][0]['type']='number'
    path.write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8')
    response=prepare(client,task);assert response.status_code==422 and not main.store.list('human_runtime_plan')


def test_revision_confirmation_and_type_not_bypassed(client):
    task,env=setup(client);assert prepare(client,task,revision=task['revision']+1).status_code==409
    row=main.get_task(task['id']);row['configuration_confirmed']=False;main.store.put('task',row['id'],row)
    assert prepare(client,task).status_code==409 and not main.store.list('human_runtime_plan')


def test_public_history_bound_to_task_and_no_private_future_fields(client):
    task,env=setup(client);p=prepare(client,task).json();row=main.store.get('human_runtime_plan',p['id']);row['private_future_field']='fake-private-secret';main.store.put('human_runtime_plan',p['id'],row)
    response=client.get(f"/api/tasks/{task['id']}/human-runtime");assert response.json()['records'][0]['artifact_sha256']==p['artifact_sha256'] and 'fake-private-secret' not in response.text
    other=approved(client);assert client.get(f"/api/tasks/{other['id']}/human-runtime").json()['records']==[]


def test_frozen_plan_remains_history_when_artifact_changed_and_new_plan_differs(client):
    task,env=setup(client);p=prepare(client,task).json();path=main.artifact_path(task);root=yaml.safe_load(path.read_text(encoding='utf-8'));root['workflow']['graph']['nodes'][2]['data']['template']='新批准结果';path.write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8')
    newer=prepare(client,task).json();assert newer['artifact_sha256']!=p['artifact_sha256'] and newer['resource_token']!=p['resource_token']
    rows=client.get(f"/api/tasks/{task['id']}/human-runtime").json()['records'];assert rows[1]['artifact_sha256']==p['artifact_sha256']


@pytest.mark.parametrize('kind,value,default',[
    ('text-input','too long',None),('select','foreign','allowed'),('select',None,'allowed')])
def test_native_string_length_choice_and_required_not_defaulted(client,kind,value,default):
    task,_=setup(client);path=main.artifact_path(task);root=yaml.safe_load(path.read_text(encoding='utf-8'))
    row=root['workflow']['graph']['nodes'][0]['data']['variables'][0];row.update(type=kind,max_length=3)
    if kind=='select':row.update(options=['allowed'],default=default)
    path.write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8')
    assert prepare(client,task,input={} if value is None else {'query':value}).status_code==422
    assert not main.store.list('human_runtime_plan')

def test_yaml_escaped_environment_credential_rejected_without_echo(client):
    task,env=setup(client);path=main.artifact_path(task);text=path.read_text(encoding='utf-8').replace('已批准','"\\u0074est-console"');path.write_text(text,encoding='utf-8')
    response=prepare(client,task);assert response.status_code==422 and 'test-console' not in response.text and main.store.list('human_runtime_plan')==[]
