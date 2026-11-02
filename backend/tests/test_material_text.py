import copy,json,hashlib
from pathlib import Path
import pytest
from test_api import client,approved,planning_provider
from app import main


def unread(client):
    task=approved(client)
    task=client.post(f"/api/tasks/{task['id']}/materials",files={'file':('flow.png',b'isolated unread source','image/png')}).json()
    return task,task['materials'][-1]


def payload(task,material,**values):
    return {'revision':task['revision'],'source_sha256':material['sha256'],'text':'  这是用户说明：问题先检索，未命中时追问。\n','coverage_note':'仅说明主分支，截图右侧内容尚未补全。','acknowledge_manual_source':True,**values}


def test_manual_source_keeps_file_old_error_versions_and_unconfirmed_reference(client):
    task,material=unread(client);before=copy.deepcopy(task)
    path=main.DATA_ROOT/task['id']/'materials'/(material['id']+'.png');raw=path.read_bytes()
    response=client.post(f"/api/tasks/{task['id']}/materials/{material['id']}/text",json=payload(task,material))
    assert response.status_code==200,response.text
    saved=response.json();m=saved['materials'][-1]
    assert saved['revision']==task['revision']+1 and not saved['requirements_confirmed'] and not saved['configuration_confirmed']
    assert m['text']==payload(task,material)['text'] and m['status']=='parsed'
    assert m['source_kind']=='user_supplied_text' and m['source_file_parsed'] is False
    assert m['original_parse_error']==material['error'] and m['original_parse_status']=='needs_input'
    assert m['reference_mode'] is None and path.read_bytes()==raw
    assert saved['versions'][-1]['materials']==before['materials']
    assert client.post(f"/api/tasks/{task['id']}/confirm",json={'kind':'requirements','revision':saved['revision']}).status_code==422
    assert not saved['runs'] and not saved['artifact']


@pytest.mark.parametrize('patch',[{'acknowledge_manual_source':False},{'text':' '},{'coverage_note':' '},{'text':'x'*100001},{'revision':True},{'source_sha256':'bad'},{'unexpected':True}])
def test_unacknowledged_or_invalid_text_never_truncates_or_mutates_task(client,patch):
    task,m=unread(client);before=main.get_task(task['id'])
    response=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json=payload(task,m,**patch))
    assert response.status_code==422 and main.get_task(task['id'])==before


@pytest.mark.parametrize('fault',['stale_revision','wrong_hash','changed_file','missing_file'])
def test_stale_or_unreadable_binary_identity_rejects_text_before_invalidation(client,fault):
    task,m=unread(client);before=main.get_task(task['id']);data=payload(task,m)
    path=main.DATA_ROOT/task['id']/'materials'/(m['id']+'.png')
    if fault=='stale_revision':data['revision']-=1
    elif fault=='wrong_hash':data['source_sha256']='0'*64
    elif fault=='changed_file':path.write_bytes(b'changed isolated source')
    elif fault=='missing_file':path.unlink()
    response=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json=data)
    assert response.status_code==(422 if fault=='missing_file' else 409),response.text
    assert main.get_task(task['id'])==before


def test_already_parsed_text_is_not_overwritten_by_fallback(client):
    task=approved(client);task=client.post(f"/api/tasks/{task['id']}/materials",files={'file':('rules.txt','原始正文'.encode(),'text/plain')}).json();m=task['materials'][-1];before=main.get_task(task['id'])
    assert client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json=payload(task,m)).status_code==422
    assert main.get_task(task['id'])==before


def test_interview_receives_user_source_marker_not_a_claim_of_image_reading(client,monkeypatch):
    planning_provider(client);task,m=unread(client)
    task=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json=payload(task,m)).json()
    calls=[]
    async def controlled(provider,key,messages,**kwargs):
        calls.append(messages);context=json.loads(messages[1]['content'].removeprefix('当前任务资料：'))
        source=context['materials'][0]
        assert source['source_kind']=='user_supplied_text' and source['source_file_parsed'] is False
        assert source['source_coverage_note']==payload(task,m)['coverage_note']
        assert '不得声称已读取全图' in messages[0]['content']
        assert 'isolated unread source' not in json.dumps(messages)
        return json.dumps({'message':'仅根据用户文字讨论，右侧内容请补充。','requirements_patch':{}}),{'prompt_tokens':80,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'按我的文字说明继续讨论'})
    assert response.status_code==200 and len(calls)==1


def test_existing_preserve_decision_is_kept_and_blocks_automatic_borrow_planning(client):
    planning_provider(client);task,m=unread(client)
    task=client.patch(f"/api/tasks/{task['id']}/materials/{m['id']}",json={'revision':task['revision'],'reference_mode':'preserve','preserve_items':'指定主流程与右侧分支'}).json()
    task=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json=payload(task,m)).json()
    assert task['materials'][0]['reference_mode']=='preserve'
    assert task['materials'][0]['preserve_items']=='指定主流程与右侧分支'
    response=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert response.status_code==422 and '不会自动改为借鉴' in response.text


def test_report_marks_unread_original_and_excludes_original_binary(client):
    task,m=unread(client)
    task=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json=payload(task,m)).json()
    report=client.get(f"/api/tasks/{task['id']}/report")
    assert report.status_code==200,report.text
    assert 'user_supplied_text' in report.text and '"source_file_parsed": false' in report.text
    assert '仅说明主分支' in report.text and 'OCR成功' in report.text
    assert 'isolated unread source' not in report.text
