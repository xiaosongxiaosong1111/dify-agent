import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import copy,uuid
import pytest
from app import main
from app.agent_environment_mapping import DRAFT_KIND
from app.environment_mapping_copy import COPY_KIND
from test_api import client
from test_environment_mapping_drafts import setup,save
from test_agent_environment_mapping import state,prepared,body,request,A,B
from test_agent_preservation import soul
from app.dsl_roundtrip import parse


def ready(client):
    task,inputs,preview,target=setup(client)
    saved=save(client,task,inputs,preview).json()
    scope=client.get(f"/api/tasks/{task['id']}/environment-mapping/copy-scope");assert scope.status_code==200,scope.text
    payload={'revision':task['revision'],'draft_revision':saved['draft_revision'],'preview_token':preview['preview_token'],
             'scope_token':scope.json()['scope_token'],'operation_id':str(uuid.uuid4()),'name':'独立公开目标',
             'acknowledge_local_copy':True,'acknowledge_scope':True}
    return task,inputs,preview,target,scope.json(),payload


def create(client,task,payload):return client.post(f"/api/tasks/{task['id']}/environment-mapping/copy-task",json=payload)


def test_scope_readonly_and_local_copy_preserves_source_and_complete_manual_dsl(client,monkeypatch):
    task,inputs,p,target,scope,payload=ready(client);source=copy.deepcopy(main.get_task(task['id']));baseline=state()
    assert client.get(f"/api/tasks/{task['id']}/environment-mapping/copy-scope").json()==scope
    assert state()==baseline
    monkeypatch.setattr(main.store,'secret',lambda *args:pytest.fail('copy must not decrypt credentials'))
    response=create(client,task,payload);assert response.status_code==201,response.text
    value=response.json();new=value['task'];assert value['created'] and value['source_unchanged']
    assert main.get_task(task['id'])==source and new['id']!=task['id']
    assert new['revision']==1 and new['app_type']=='agent' and new['environment_id']==target['id']
    assert not new['requirements_confirmed'] and not new['configuration_confirmed'] and new['intake_required']
    assert new['requirements']==source['requirements'] and new['configuration']==p['configuration']
    assert new['artifact'] is None and new['dify_app_id'] is None
    for field in ('materials','test_cases','runs','versions','planning_runs'):assert new[field]==[]
    assert 'confirmations' not in new and 'dsl_overlay' not in new
    ref=main.reference_for(new);assert ref['source']=='mapping_draft' and ref['current']==parse(p['content'],'agent')
    assert soul(ref['current'])['prompt']['system_prompt']=='保留人工职责与信息不足处理'
    merged=client.get(f"/api/tasks/{new['id']}/dsl-merge");assert merged.status_code==200,merged.text
    assert merged.json()['validation']['valid'] and not merged.json()['unresolved']
    assert parse(merged.json()['content'],'agent')==ref['current']
    assert client.post(f"/api/tasks/{new['id']}/build",json={'revision':1}).status_code==422


def test_repeat_same_operation_returns_one_task_and_conflicting_replay_rejected(client):
    task,_,_,_,_,payload=ready(client)
    first=create(client,task,payload);assert first.status_code==201
    baseline=state();second=create(client,task,payload);assert second.status_code==201
    assert not second.json()['created'] and second.json()['task']['id']==first.json()['task']['id'] and state()==baseline
    bad=create(client,task,{**payload,'name':'different'});assert bad.status_code==409 and state()==baseline
    assert len(main.store.list(COPY_KIND))==1


@pytest.mark.parametrize('patch',[{'acknowledge_scope':False},{'acknowledge_local_copy':False},{'revision':True},{'draft_revision':True},{'name':' '},{'scope_token':'e'*64},{'preview_token':'e'*64},{'draft_revision':9},{'name':'x','configuration':{}},{'operation_id':'../../other'}])
def test_invalid_or_stale_copy_no_partial_writes(client,patch):
    task,_,_,_,_,payload=ready(client);before=state()
    r=create(client,task,{**payload,**patch});assert r.status_code in {409,422},r.text
    assert state()==before


@pytest.mark.parametrize('change',['source','target','counts','busy'])
def test_source_target_scope_changes_and_busy_refuse_without_writes(client,change):
    task,_,_,target,_,payload=ready(client)
    if change=='source':
        row=main.get_task(task['id']);row['revision']+=1;main.save_task(row)
    if change=='target':
        target['connection_revision']='new-connection';main.store.put('environment',target['id'],target)
    if change=='counts':
        row=main.get_task(task['id']);row['materials']=[{'id':'public','filename':'not-copied.txt'}];main.save_task(row)
    if change=='busy':
        row=main.get_task(task['id']);row['status']='running';main.save_task(row)
    before=state();r=create(client,task,payload);assert r.status_code in {409,422},r.text
    assert state()==before


def test_copy_knowledge_uses_mapped_ids_preserves_grouping_names_topk_and_mock_conditions(client):
    task,root,p,target=prepared(client,knowledge=True,source_ids=[A,B])
    mapping={A:'c3333333-3333-4333-8333-333333333333',B:'d4444444-4444-4444-8444-444444444444'}
    inputs=body(task,p,target,dataset_mapping=mapping);preview=request(client,task,p,target,dataset_mapping=mapping).json()
    save(client,task,inputs,preview)
    scope=client.get(f"/api/tasks/{task['id']}/environment-mapping/copy-scope").json()
    payload={'revision':task['revision'],'draft_revision':1,'preview_token':preview['preview_token'],'scope_token':scope['scope_token'],
             'operation_id':str(uuid.uuid4()),'name':'明确目标知识集','acknowledge_local_copy':True,'acknowledge_scope':True}
    r=create(client,task,payload);assert r.status_code==201,r.text
    new=r.json()['task'];assert set(new['configuration']['dataset_ids'])==set(mapping.values())
    assert set(new['configuration']['mock_dependencies'])>=set(task['configuration']['mock_dependencies'])
    current=main.reference_for(new)['current'];sets=soul(current)['knowledge']['sets'];before=soul(root)['knowledge']['sets']
    assert len(sets)==len(before) and sets[0]['id']==before[0]['id'] and sets[0]['name']==before[0]['name']
    assert sets[0]['retrieval']['top_k']==7
    assert {d['id'] for group in sets for d in group['datasets']}==set(mapping.values())
    result=client.get(f"/api/tasks/{new['id']}/dsl-merge");assert result.status_code==200 and result.json()['validation']['valid']


def test_scope_without_saved_mapping_cannot_create(client):
    task,_,_,_=setup(client);before=state()
    r=client.get(f"/api/tasks/{task['id']}/environment-mapping/copy-scope");assert r.status_code==422 and state()==before


def test_replay_corrupt_owner_never_returns_foreign_task(client):
    task,_,_,_,_,payload=ready(client);r=create(client,task,payload);assert r.status_code==201
    key=task['id']+':'+payload['operation_id'];receipt=main.store.get(COPY_KIND,key);receipt['source_task_id']='foreign';main.store.put(COPY_KIND,key,receipt)
    baseline=state();bad=create(client,task,payload);assert bad.status_code==409 and state()==baseline


def test_transaction_failure_cannot_leave_target_task_or_reference(client,monkeypatch):
    task,_,_,_,_,payload=ready(client);before=state()
    original_put=main.store.put_many
    def fail(rows):return original_put([*rows,('invalid',object(),{})])
    monkeypatch.setattr(main.store,'put_many',fail)
    with pytest.raises(Exception):create(client,task,payload)
    assert state()==before


def test_read_receipt_does_not_write_or_create_and_handles_invalid_ids(client):
    task,_,_,_,_,payload=ready(client)
    path=f"/api/tasks/{task['id']}/environment-mapping/copies/{payload['operation_id']}"
    baseline=state();assert client.get(path).status_code==404 and state()==baseline
    created=create(client,task,payload).json()['task'];baseline=state()
    value=client.get(path);assert value.status_code==200 and value.json()['task']['id']==created['id']
    assert not value.json()['created'] and state()==baseline
    malformed=client.get(path.rsplit('/',1)[0]+'/private-invalid-operation')
    assert malformed.status_code==422 and 'private-invalid-operation' not in malformed.text and state()==baseline


def test_scope_counts_do_not_inherit_real_history_or_approvals(client):
    task,_,_,_,_,_=ready(client);row=main.get_task(task['id'])
    row['materials']=[{'id':'local-material','filename':'public.txt'}];row['test_cases']=[{'id':'case','confirmed':True}]
    row['confirmations']=[{'kind':'configuration','revision':row['revision']}];main.save_task(row)
    scope=client.get(f"/api/tasks/{task['id']}/environment-mapping/copy-scope").json()
    assert scope['not_copied']['materials']==1 and scope['not_copied']['test_cases']==1 and scope['not_copied']['confirmations']==1
    payload={'revision':row['revision'],'draft_revision':scope['draft_revision'],'preview_token':scope['preview_token'],'scope_token':scope['scope_token'],
             'operation_id':str(uuid.uuid4()),'name':'明确有限复制','acknowledge_local_copy':True,'acknowledge_scope':True}
    result=create(client,task,payload);assert result.status_code==201,result.text
    new=result.json()['task'];assert new['materials']==new['test_cases']==[] and 'confirmations' not in new
    assert new['mapping_origin']['scope']['not_copied']==scope['not_copied']
    assert main.get_task(task['id'])==row


def test_copy_duplicate_json_key_rejected_no_echo_or_writes(client):
    import json
    task,_,_,_,_,payload=ready(client);baseline=state()
    raw=json.dumps(payload)[:-1]+',"name":"do-not-echo-private"}'
    result=client.post(f"/api/tasks/{task['id']}/environment-mapping/copy-task",content=raw,headers={'Content-Type':'application/json'})
    assert result.status_code==422 and 'do-not-echo-private' not in result.text and state()==baseline
