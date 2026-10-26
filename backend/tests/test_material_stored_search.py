import copy,hashlib
import pytest
from test_api import client,forbid_api_external_calls
from test_material_stored_text import setup,request
from app import main

def search(client,task,meta,**extra):
    material=task['materials'][0]
    return client.post(f"/api/tasks/{task['id']}/materials/{material['id']}/stored-text/search",json={'revision':task['revision'],'source_sha256':material['sha256'],'source_token':meta['source_token'],'field':'partial_text','offset':0,'query':'公开',**extra})

def test_search_all_results_and_preview_offsets_are_exact_and_readonly(client,monkeypatch):
    task=setup(client);text='🙂\r\n'+('公开Aa 规则\r\n🙂'*48)+'最后';task['materials'][0]['partial_text']=text;main.save_task(task);meta=request(client,task).json();before=main.store.get('task',task['id'])
    monkeypatch.setattr(main.store,'put',lambda *a,**k:pytest.fail('不能保存'))
    monkeypatch.setattr(main.store,'secret',lambda *a,**k:pytest.fail('不能解密'))
    found=[];offset=0
    while True:
        response=search(client,task,meta,offset=offset);assert response.status_code==200,response.text
        value=response.json();assert len(value['matches'])<=20 and value['source_token']==meta['source_token']
        assert value['case_sensitive'] and value['non_overlapping'] and not value['regular_expression'] and value['partial_extraction']
        for row in value['matches']:
            assert text[row['start']:row['end']]=='公开' and row['preview']==text[row['preview_start']:row['preview_end']]
            assert len(row['preview'])<=242 and row['preview_sha256']==hashlib.sha256(row['preview'].encode()).hexdigest()
            found.append(row['start'])
        if not value['has_more']:assert value['next_offset'] is None;break
        assert value['next_offset']>offset;offset=value['next_offset']
    assert len(found)==48 and len(set(found))==48 and main.store.get('task',task['id'])==before

@pytest.mark.parametrize('query,expected',[('公开',1700),('公.',0),('公开\r\n🙂',1700),('AAA',0),('🙂',1700)])
def test_literal_query_does_not_regex_casefold_or_normalize(client,query,expected):
    task=setup(client);meta=request(client,task).json();value=search(client,task,meta,query=query).json()
    assert len(value['matches'])==min(expected,20) and value['has_more']==(expected>20)
    assert value['query']==query and value['query_sha256']==hashlib.sha256(query.encode()).hexdigest()

@pytest.mark.parametrize('extra',[{'query':''},{'query':' '},{'query':'x'*101},{'query':[]},{'offset':True},{'offset':-1},{'offset':999999},{'field':[]},{'source_token':None}])
def test_invalid_search_never_mutates_or_guesses(client,extra):
    task=setup(client);meta=request(client,task).json();before=main.store.get('task',task['id'])
    assert search(client,task,meta,**extra).status_code==422 and main.store.get('task',task['id'])==before

def test_source_change_foreign_task_and_partial_vs_body(client):
    task=setup(client);task['materials'][0].update(text='用户新正文',source_kind='user_supplied_text',source_coverage_note='原件未知');main.save_task(task);meta=request(client,task).json()
    assert search(client,task,meta,field='text',query='用户').json()['partial_extraction'] is False
    assert search(client,task,meta).json()['partial_extraction'] is True
    other=setup(client);assert search(client,other,meta).status_code==409
    task['materials'][0]['partial_text']='相同修订改变原文';main.save_task(task)
    assert search(client,task,meta).status_code==409

def test_non_overlapping_and_end_position_are_explicit(client):
    task=setup(client);task['materials'][0]['partial_text']='aaaaa';main.save_task(task);meta=request(client,task).json()
    value=search(client,task,meta,query='aa').json();assert [x['start'] for x in value['matches']]==[0,2] and not value['has_more']
    value=search(client,task,meta,offset=5,query='aa').json();assert value['matches']==[] and value['next_offset'] is None
