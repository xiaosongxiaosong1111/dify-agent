import copy
import hashlib
import pytest
import yaml
from test_api import client,approved
from test_start_inputs import root
from app import main
from app.start_inputs import form_schema


def test_schema_reads_final_artifact_not_old_plan_and_no_task_mutation(client):
    saved=approved(client);tid=saved['id']
    saved=client.post(f'/api/tasks/{tid}/build',json={'revision':saved['revision']}).json()
    native=root();native['workflow']['graph']['nodes'][0]['data']['variables'][1].update(options=['__unset','退款'],default='__unset')
    content=yaml.safe_dump(native,allow_unicode=True);main.artifact_path(saved).write_text(content,encoding='utf-8')
    before=copy.deepcopy(main.get_task(tid))
    response=client.get(f'/api/tasks/{tid}/run-input-schema');assert response.status_code==200,response.text;value=response.json()
    assert value['revision']==saved['revision'] and value['verification']=='static_only'
    assert value['source_sha256']==hashlib.sha256(content.encode()).hexdigest()
    assert value['fields'][0]['type']=='number' and value['fields'][0]['default']==0
    assert value['fields'][1]['options']==['__unset','退款']
    assert not any(key in value for key in ('nodes','edges','code','runs','environment_id'))
    assert main.get_task(tid)==before


def test_schema_missing_artifact_and_stale_revision_refused(client):
    saved=approved(client);tid=saved['id'];assert client.get(f'/api/tasks/{tid}/run-input-schema').status_code==404
    saved=client.post(f'/api/tasks/{tid}/build',json={'revision':saved['revision']}).json()
    changed=client.patch(f'/api/tasks/{tid}',json={'requirements':{'goal':'新的明确目标'}}).json()
    assert changed['revision']>saved['revision']
    assert client.get(f'/api/tasks/{tid}/run-input-schema').status_code==404


@pytest.mark.parametrize('patch',[
 {'type':'file'}, {'type':'number','required':False}, {'label':{'object':'wrong'}}, {'type':'select','options':['a'],'default':'b'},
])
def test_unknown_or_invalid_actual_fields_block_whole_form(patch):
    native=root();row=native['workflow']['graph']['nodes'][0]['data']['variables'][0]
    row.pop('default',None);row.update(patch);before=copy.deepcopy(native)
    with pytest.raises(ValueError):form_schema(native)
    assert native==before


def test_empty_inputs_valid_but_duplicate_or_oversize_not_truncated():
    native=root();start=native['workflow']['graph']['nodes'][0]['data'];start['variables']=[]
    assert form_schema(native)['fields']==[]
    start['variables']=[{'variable':'query','type':'text-input'}]*2
    with pytest.raises(ValueError):form_schema(native)
    start['variables']=[{'variable':f'x{i}','type':'text-input'} for i in range(101)]
    with pytest.raises(ValueError):form_schema(native)


def test_chatflow_type_not_changed_for_run_form():
    native=root();native['app']['mode']='advanced-chat'
    before=copy.deepcopy(native);schema=form_schema(native)
    assert schema['app_mode']=='advanced-chat' and schema['fields'][0]['variable']=='query'
    assert native==before
    assert native['app']['mode']=='advanced-chat'
