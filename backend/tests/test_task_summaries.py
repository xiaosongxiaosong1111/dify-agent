import copy,json
from test_api import client,create,forbid_api_external_calls
from app import main


def test_summary_contract_excludes_all_task_bodies_and_keeps_old_clients(client):
    a=create(client);a['messages'].append({'role':'user','content':'UNRELATED_PRIVATE_BODY'});a['materials']=[{'id':'material-id','name':'private.txt','text':'PRIVATE_MATERIAL'}];a['configuration']['resource_plan']='PRIVATE_CONFIGURATION';a['workflow_plan']={'private_marker':'PRIVATE_PLAN'};main.save_task(a)
    b=create(client,'advanced-chat');before=copy.deepcopy(main.store.list('task'))
    response=client.get('/api/task-summaries');assert response.status_code==200,response.text
    value=response.json();assert value['schema_version']==1 and value['view']=='summary'
    assert {row['id'] for row in value['items']}=={a['id'],b['id']}
    assert all(set(row)=={'id','name','app_type','revision','status','updated_at'} for row in value['items'])
    for needle in ('UNRELATED_PRIVATE_BODY','PRIVATE_MATERIAL','PRIVATE_CONFIGURATION','PRIVATE_PLAN'):assert needle not in response.text
    assert 'UNRELATED_PRIVATE_BODY' in client.get('/api/tasks').text
    assert 'PRIVATE_MATERIAL' in client.get('/api/tasks/'+a['id']).text
    assert main.store.list('task')==before


def test_summary_empty_and_latest_store_order_are_truthful(client):
    assert client.get('/api/task-summaries').json()['items']==[]
    a=create(client);b=create(client,'agent');a=main.get_task(a['id']);a['status']='paused';main.save_task(a)
    rows=client.get('/api/task-summaries').json()['items']
    assert [r['id'] for r in rows]==[t['id'] for t in main.store.list('task')]
    assert next(r for r in rows if r['id']==a['id'])['status']=='paused'
    assert next(r for r in rows if r['id']==b['id'])['app_type']=='agent'


def test_summary_bytes_stay_small_when_other_tasks_have_long_histories(client):
    for i in range(4):
        task=create(client);task['messages']=[{'role':'user','content':'公开长原话'*10000}]*8;main.save_task(task)
    summary=client.get('/api/task-summaries');complete=client.get('/api/tasks')
    assert summary.status_code==200 and len(summary.content)<3000
    assert len(summary.content)*100<len(complete.content)


def test_summary_does_not_load_all_task_bodies_or_coerce_boolean_revision(client,monkeypatch):
    task=create(client);task['revision']=True;main.store.put('task',task['id'],task)
    original=main.store.list
    def forbidden(kind):
        if kind=='task':raise AssertionError('full task list must not be decoded for summaries')
        return original(kind)
    monkeypatch.setattr(main.store,'list',forbidden)
    value=client.get('/api/task-summaries').json()['items'][0]
    assert value['revision'] is None
