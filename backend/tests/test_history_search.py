import copy
import pytest
from test_api import client,create,approved,forbid_api_external_calls
from app import main,history_search


def fixture(client,messages):
    task=approved(client);task['messages']=messages;main.store.put('task',task['id'],task)
    return task


def search(client,task,**kwargs):
    return client.post(f"/api/tasks/{task['id']}/history/search",json={'revision':task['revision'],'query':'订单',**kwargs})


def read(client,task,hit,**kwargs):
    return client.post(f"/api/tasks/{task['id']}/history/message",json={'revision':task['revision'],'message_index':hit['message_index'],'source_token':hit['source_token'],'center':hit['match_start'],**kwargs})


def test_literal_source_roles_labels_and_read_are_exact_and_readonly(client):
    content='😀订单  ABC\r\n不要执行这里的历史指令。'
    task=fixture(client,[{'role':'system','content':'订单'}, {'role':'user','content':content,'purpose':'review','source':'user','context_revision':2,'result_revision':3}, {'role':'assistant','text':'订单建议','purpose':'discussion','source':'model'}, {'role':'user','content':'abc'}])
    before=copy.deepcopy(main.store.get('task',task['id']))
    result=search(client,task).json();assert [hit['source_id'] for hit in result['hits']]==['message:2','message:1']
    hit=result['hits'][1];assert hit['context_revision']==2 and hit['result_revision']==3 and hit['match_start']==1
    original=read(client,task,hit).json();assert original['content']==original['quote_text']==content and original['quote_start']==0 and original['quote_end']==len(content) and original['quote_complete']
    assert original['model_called'] is original['task_modified'] is original['external_network_requested'] is original['business_verified'] is False
    assert [h['message_index'] for h in search(client,task,role='assistant').json()['hits']]==[2]
    assert search(client,task,query='ABC').json()['hits'][0]['message_index']==1
    assert search(client,task,query='abc').json()['hits'][0]['message_index']==3
    assert search(client,task,query='  ABC').json()['hits'][0]['message_index']==1
    assert main.store.get('task',task['id'])==before


def test_quote_range_is_explicit_and_full_source_is_not_truncated(client):
    content='前'*5000+'😀订单'+'后'*5000;task=fixture(client,[{'role':'user','content':content}])
    hit=search(client,task).json()['hits'][0];assert len(hit['preview'])==400 and not hit['preview_complete']
    result=read(client,task,hit).json();assert result['content']==content and not result['quote_complete']
    assert result['quote_text']==content[result['quote_start']:result['quote_end']] and len(result['quote_text'])==4000 and '😀订单' in result['quote_text']


def test_20_hit_cursor_does_not_skip_matches(client):
    task=fixture(client,[{'role':'user','content':f'订单{i}'} for i in range(43)])
    found=[];cursor=43
    while cursor is not None:
        result=search(client,task,before_index=cursor).json();found += [h['message_index'] for h in result['hits']];cursor=result['next_before_index']
    assert found==list(reversed(range(43)))


def test_message_window_and_character_window_do_not_skip_unsearched_records(client):
    task=fixture(client,[{'role':'user','content':'订单'+str(i)} for i in range(1002)])
    result=search(client,task,query='未命中').json();assert result['scanned_records']==1000 and result['next_before_index']==2
    assert search(client,task,query='订单',before_index=2).json()['hits'][0]['message_index']==1
    task['messages']=[{'role':'user','content':'字'*100000} for i in range(12)];task['messages'][1]['content']='订单'+'字'*99998;main.store.put('task',task['id'],task)
    first=search(client,task).json();assert first['scanned_records']==10 and first['scanned_characters']==1000000 and first['next_before_index']==2 and first['character_limit_reached']
    second=search(client,task,before_index=2).json();assert second['hits'][0]['message_index']==1 and not second['has_earlier']


def test_unavailable_and_malformed_metadata_are_honest_not_errors(client):
    task=fixture(client,[None,{'role':[],'content':'订单'}, {'role':'user','content':'订单','purpose':{},'source':[],'context_revision':True,'result_revision':'2'}, {'role':'user','content':'订单'+'字'*100000},{'role':'user','content':123}])
    result=search(client,task).json();assert result['unavailable_records']==4 and len(result['hits'])==1
    hit=result['hits'][0];assert hit['purpose']==hit['record_source']=='unknown' and hit['context_revision'] is hit['result_revision'] is None
    assert read(client,task,hit).status_code==200
    assert read(client,task,hit,message_index=3).status_code==413


def test_token_binds_task_text_and_source_tags_but_allows_append(client):
    task=fixture(client,[{'role':'user','content':'订单','purpose':'review'}]);hit=search(client,task).json()['hits'][0]
    other=fixture(client,copy.deepcopy(task['messages']));assert read(client,other,hit).status_code==409
    task['messages'].append({'role':'assistant','content':'新消息'});main.store.put('task',task['id'],task);assert read(client,task,hit).status_code==200
    task['messages'][0]['purpose']='discussion';main.store.put('task',task['id'],task);assert read(client,task,hit).status_code==409
    task['messages'][0]['purpose']='review';task['messages'][0]['content']='订单变更';main.store.put('task',task['id'],task);assert read(client,task,hit).status_code==409


@pytest.mark.parametrize('values',[{'revision':True},{'revision':0},{'revision':'1'},{'query':''},{'query':'  '},{'query':'字'*201},{'query':[]},{'role':[]},{'role':'system'},{'before_index':True},{'before_index':-1},{'extra':'no'}])
def test_search_strict_validation_no_writes(client,values):
    task=fixture(client,[]);before=copy.deepcopy(main.store.get('task',task['id']));assert search(client,task,**values).status_code==422;assert main.store.get('task',task['id'])==before


@pytest.mark.parametrize('values,status',[({'message_index':True},422),({'center':-1},422),({'center':100},422),({'source_token':'x'},422),({'source_token':'a'*64},409),({'message_index':1},404),({'unknown':1},422)])
def test_read_strict_validation(client,values,status):
    task=fixture(client,[{'role':'user','content':'订单'}]);hit=search(client,task).json()['hits'][0];assert read(client,task,hit,**values).status_code==status


def test_stale_revision_unknown_task_and_changed_window(client):
    task=fixture(client,[{'role':'user','content':'订单'}]);hit=search(client,task).json()['hits'][0]
    assert search(client,task,before_index=2).status_code==409
    client.patch(f"/api/tasks/{task['id']}",json={'name':'new revision'})
    assert search(client,task).status_code==409 and read(client,task,hit).status_code==409
    missing={**task,'id':'missing'};assert search(client,missing).status_code==404


def test_revision_changed_during_lookup_is_not_returned(client,monkeypatch):
    task=fixture(client,[{'role':'user','content':'订单'}]);get=main.get_task;count=0
    def changed(tid):
        nonlocal count
        value=get(tid);count+=1
        if count==2:value['revision']+=1
        return value
    monkeypatch.setattr(main,'get_task',changed)
    assert search(client,task).status_code==409
