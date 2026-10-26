import copy,hashlib,json
import pytest
from test_api import client,create,forbid_api_external_calls
from app import main
from app.history_search import _describe


def setup(client,text=None):
    task=create(client);message={'role':'user','purpose':'discussion','source':'user','content':text if text is not None else ('前🙂\r\n'*2500)+'完整原话结尾','context_revision':1}
    task['messages']=[message];main.store.put('task',task['id'],task)
    source=_describe(task,0,message,message['content'])
    body={'revision':task['revision'],'message_index':0,'content_sha256':source['content_sha256'],'labels':{key:source[key] for key in ('role','purpose','record_source','context_revision','result_revision')},'source_token':None,'offset':0}
    return main.get_task(task['id']),body


def post(client,task,body):return client.post(f"/api/tasks/{task['id']}/history/message-page",json=body)


def test_pages_reassemble_exact_unicode_crlf_and_are_read_only(client,monkeypatch):
    task,body=setup(client);before=main.get_task(task['id']);parts=[];token=None;offset=0
    monkeypatch.setattr(main.store,'put',lambda *a,**kw:pytest.fail('分页不得写入'))
    monkeypatch.setattr(main.store,'secret',lambda *a,**kw:pytest.fail('分页不得解密'))
    while True:
        response=post(client,task,{**body,'offset':offset,'source_token':token});assert response.status_code==200,response.text
        assert response.headers['cache-control']=='no-store'
        value=response.json();parts.append(value['content_chunk']);token=token or value['source_token']
        assert value['source_token']==token and value['page_start']==offset and len(value['content_chunk'])<=4000
        assert value['content_chunk']==task['messages'][0]['content'][offset:value['page_end']]
        assert not value['task_modified'] and not value['model_called'] and not value['external_network_requested']
        assert value['complete_message'] is False
        offset=value['page_end']
        if not value['has_next']:break
    assert ''.join(parts)==task['messages'][0]['content'] and main.get_task(task['id'])==before


def test_short_message_is_explicitly_complete(client):
    task,body=setup(client,'完整🙂\r\n原话');value=post(client,task,body).json()
    assert value['complete_message'] and not value['has_previous'] and not value['has_next']
    assert value['source_bytes']==len('完整🙂\r\n原话'.encode())


@pytest.mark.parametrize('change',['content','role','purpose','record_source','context_revision','result_revision','revision','foreign_task','token'])
def test_changed_or_foreign_source_rejected_not_replaced(client,change):
    task,body=setup(client);first=post(client,task,body).json();body.update(offset=4000,source_token=first['source_token'])
    current=main.get_task(task['id']);message=current['messages'][0]
    if change=='content':message['content']+='CHANGED'
    if change=='role':message['role']='assistant'
    if change=='purpose':message['purpose']='review'
    if change=='record_source':message['source']='model'
    if change=='context_revision':message['context_revision']=2
    if change=='result_revision':message['result_revision']=2
    if change=='revision':current['revision']+=1
    if change=='token':body['source_token']='0'*64
    if change=='foreign_task':
        other,other_body=setup(client);task=other
    else:main.store.put('task',current['id'],current)
    response=post(client,task,body);assert response.status_code==409
    assert '完整原话结尾' not in response.text and 'CHANGED' not in response.text


def test_appending_keeps_original_token_and_next_page_valid(client):
    task,body=setup(client);first=post(client,task,body).json();task['messages'].append({'role':'assistant','content':'新消息'});main.store.put('task',task['id'],task)
    before=main.get_task(task['id']);response=post(client,task,{**body,'offset':4000,'source_token':first['source_token']});assert response.status_code==200
    assert response.json()['source_token']==first['source_token'] and main.get_task(task['id'])==before


@pytest.mark.parametrize('change',['negative','bool_index','bool_offset','missing_token','bad_hash','extra','wrong_labels','bool_revision_label','out_of_range','missing_record'])
def test_bad_positions_or_contract_do_not_guess(client,change):
    task,body=setup(client)
    if change=='negative':body['offset']=-1
    if change=='bool_index':body['message_index']=False
    if change=='bool_offset':body['offset']=False
    if change=='missing_token':body['offset']=4000
    if change=='bad_hash':body['content_sha256']='private invalid'
    if change=='extra':body['private']='DO_NOT_ECHO'
    if change=='wrong_labels':body['labels']['extra']='DO_NOT_ECHO'
    if change=='bool_revision_label':body['labels']['context_revision']=True
    if change=='out_of_range':body['offset']=len(task['messages'][0]['content']);body['source_token']=post(client,task,{**body,'offset':0}).json()['source_token']
    if change=='missing_record':body['message_index']=9
    response=post(client,task,body);assert response.status_code in (422,404)
    assert 'DO_NOT_ECHO' not in response.text and main.get_task(task['id'])==task


@pytest.mark.parametrize('raw',['{"revision":1,"revision":2,"private":"HIDDEN"}','{"revision":NaN}','[]','{"bad":"'+('x'*8200)+'"}'],ids=['duplicate','nonfinite','array','large_request'])
def test_strict_request_json_no_echo(client,raw):
    task,_=setup(client);response=client.post(f"/api/tasks/{task['id']}/history/message-page",content=raw,headers={'Content-Type':'application/json'})
    assert response.status_code==422 and 'HIDDEN' not in response.text
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('text',['a'*2_000_000,'a'*2_000_001,'🙂'*500_001],ids=['exact_utf8_limit','ascii_over','multibyte_over'])
def test_complete_source_byte_limit_is_not_silent_truncation(client,text):
    task,body=setup(client,text);response=post(client,task,body)
    assert response.status_code==(200 if len(text.encode())<=2_000_000 else 413)
    assert main.get_task(task['id'])==task


def test_bad_saved_unicode_rejected_without_replacement(client,monkeypatch):
    task,body=setup(client);task['messages'][0]['content']='bad\ud800';monkeypatch.setattr(main,'get_task',lambda _:copy.deepcopy(task))
    response=post(client,task,body);assert response.status_code==422 and '\\ud800' not in response.text
