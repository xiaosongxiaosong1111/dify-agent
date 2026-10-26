import copy,json
import pytest
from test_api import client,create,approved,forbid_api_external_calls
from test_planning import plan
from app import main
from app import task_workspace_view


def setup(client):
    task=create(client);task['messages']=[{'role':'user','content':f'原话{i}'} for i in range(123)]
    task['versions']=[{'id':f'version-{i}','revision':i+1,'label':f'公开快照{i}','kind':'saved','created_at':'2026-10-26T01:00:00Z','requirements':{'goal':'ONLY_OLD_PRIVATE_GOAL'},'workflow_plan':{'body':'ONLY_OLD_PRIVATE_PLAN'*4000},'materials':[{'text':'ONLY_OLD_PRIVATE_MATERIAL'}]} for i in range(20)]
    main.save_task(task);return main.get_task(task['id'])


def compact(client,task):return client.get(f"/api/tasks/{task['id']}?workspace_view=compact")


def test_compact_view_omits_all_snapshot_bodies_but_preserves_legacy_modes(client,monkeypatch):
    task=setup(client);before=main.store.get('task',task['id'])
    monkeypatch.setattr(main.store,'put',lambda *a,**k:pytest.fail('只读不能写入'))
    monkeypatch.setattr(main.store,'secret',lambda *a,**k:pytest.fail('只读不能解密'))
    response=compact(client,task);assert response.status_code==200,response.text
    value=response.json();assert value['workspace_view']['mode']=='compact' and value['message_count']==123 and len(value['messages'])==50
    assert value['version_summary']['state']=='ready' and value['version_summary']['returned_versions']==20
    assert all(set(row)=={'id','revision','label','kind','created_at'} for row in value['versions'])
    assert 'ONLY_OLD_PRIVATE' not in response.text and response.headers['cache-control']=='no-store'
    full=client.get('/api/tasks/'+task['id']);recent=client.get(f"/api/tasks/{task['id']}?message_window=recent")
    assert 'ONLY_OLD_PRIVATE_PLAN' in full.text and 'ONLY_OLD_PRIVATE_PLAN' in recent.text
    assert len(response.content)*50<len(full.content)
    assert main.store.get('task',task['id'])==before and 'workspace_view' not in before and 'version_summary' not in before


def test_compact_keeps_current_task_business_fields_exact(client):
    task=setup(client);value=compact(client,task).json()
    ignore={'messages','versions','message_count','message_window','workspace_view','version_summary'}
    assert {k:v for k,v in value.items() if k not in ignore}=={k:v for k,v in task.items() if k not in ignore}


@pytest.mark.parametrize('condition,reason',[('not_list','invalid_history'),('too_many','version_count_limit'),('missing_id','version_id_invalid'),('duplicate','version_id_ambiguous'),('wrong_row','metadata_invalid'),('bad_field','metadata_invalid'),('long_label','metadata_limit'),('large_index','index_bytes_limit')])
def test_unavailable_index_is_explicit_complete_history_retained(client,condition,reason):
    task=setup(client)
    if condition=='not_list':task['versions']={'private':'DO_NOT_ECHO'}
    if condition=='too_many':task['versions']=[{'id':str(i)} for i in range(5001)]
    if condition=='missing_id':task['versions'][2].pop('id')
    if condition=='duplicate':task['versions'][2]['id']=task['versions'][0]['id']
    if condition=='wrong_row':task['versions'][2]='DO_NOT_ECHO'
    if condition=='bad_field':task['versions'][2]['label']={'private':'DO_NOT_ECHO'}
    if condition=='long_label':task['versions'][2]['label']='DO_NOT_ECHO'*201
    if condition=='large_index':task['versions']=[{'id':str(i),'label':'x'*1999} for i in range(1000)]
    main.save_task(task);before=main.store.get('task',task['id']);response=compact(client,task);assert response.status_code==200
    value=response.json();assert value['versions']==[] and value['version_summary']['state']=='unavailable'
    assert value['version_summary']['reason']==reason and value['version_summary']['returned_versions']==0
    assert value['version_summary']['total_versions']==(None if condition=='not_list' else len(before['versions']))
    assert '不能当作没有历史' in value['version_summary']['note'] and 'DO_NOT_ECHO' not in response.text
    assert main.store.get('task',task['id'])==before


def test_unknown_revision_is_not_rounded_and_empty_index_is_known_empty(client):
    task=setup(client);task['versions']=[{'id':'legacy-bool','revision':True},{'id':'legacy-large','revision':2**53},{'id':'legacy-missing'},{'id':'valid','revision':3,'label':'🙂'*1000}];main.save_task(task)
    value=compact(client,task).json();assert value['version_summary']['unknown_revision_count']==3
    assert all('revision' not in row for row in value['versions'][:3]) and value['versions'][3]['revision']==3
    task['versions']=[];main.save_task(task);value=compact(client,task).json()
    assert value['version_summary']['state']=='ready' and value['version_summary']['total_versions']==0


def test_index_byte_boundary_counts_json_exactly_without_silent_partial(client,monkeypatch):
    task=setup(client);task['versions']=[{'id':'one','label':'公开🙂'},{'id':'two'}];main.save_task(task)
    size=len(json.dumps(task['versions'],ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    monkeypatch.setattr(task_workspace_view,'MAX_INDEX_BYTES',size)
    assert compact(client,task).json()['version_summary']['state']=='ready'
    monkeypatch.setattr(task_workspace_view,'MAX_INDEX_BYTES',size-1)
    value=compact(client,task).json();assert value['versions']==[] and value['version_summary']['reason']=='index_bytes_limit'


def test_unencodable_index_text_does_not_replace_history(client,monkeypatch):
    task=setup(client);task['versions'][0]['label']='bad\ud800';monkeypatch.setattr(main,'get_task',lambda _:copy.deepcopy(task))
    value=compact(client,task).json();assert value['version_summary']['reason']=='metadata_encoding' and value['versions']==[]


@pytest.mark.parametrize('query',['workspace_view=PRIVATE_MODE','workspace_view=compact&message_window=recent','workspace_view=compact&message_window=PRIVATE_MODE'])
def test_modes_not_silently_mixed_or_echoed(client,query):
    task=setup(client);response=client.get(f"/api/tasks/{task['id']}?{query}")
    assert response.status_code==422 and 'PRIVATE_MODE' not in response.text


def test_restore_preview_and_restoration_use_actual_full_snapshot_after_projection(client):
    task=approved(client);old=plan("def main(query):\n    return {'result': 'HISTORY_ONLY_MARKER' + query}\n")
    response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':old});assert response.status_code==200;task=response.json()
    response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan()});assert response.status_code==200;task=response.json()
    version=task['versions'][-1];path=f"/api/tasks/{task['id']}/versions/{version['id']}/restore-preview?revision={task['revision']}"
    before=client.get(path);assert before.status_code==200,before.text
    view=compact(client,task);assert view.status_code==200 and 'HISTORY_ONLY_MARKER' not in view.text
    after=client.get(path);assert after.status_code==200 and after.json()['review_token']==before.json()['review_token']
    restored=client.post(f"/api/tasks/{task['id']}/restore",json={'revision':task['revision'],'version_id':version['id'],'review_token':after.json()['review_token'],'acknowledge_restore':True})
    assert restored.status_code==200,restored.text
    value=restored.json();assert value['workflow_plan']==old and value['revision']>task['revision']
    assert not value['requirements_confirmed'] and not value['configuration_confirmed'] and value['artifact'] is None and value['dify_app_id'] is None
    assert 'version_summary' not in value and 'workspace_view' not in value and 'HISTORY_ONLY_MARKER' in restored.text
    assert main.get_task(task['id'])['versions'][:-1]==task['versions']
