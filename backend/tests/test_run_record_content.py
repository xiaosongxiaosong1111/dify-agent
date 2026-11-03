import copy,json,hashlib
import pytest
from test_api import client,approved,forbid_api_external_calls
from app import main

def seed(client):
    task=approved(client);task['runs']=[{'id':'public-run','kind':'run','status':'success','revision':1,'input':{'n':1.0,'id':9007199254740993},'test_case':{'id':'public-case','input':{'n':1.0}},'result':{'answer':{'n':1.0,'id':9007199254740993}},'evaluation':{'status':'failed','details':'旧规则记录，不自动复算'}}];main.store.put('task',task['id'],task);return task
def index(client,task,run='public-run'):return client.get(f"/api/tasks/{task['id']}/runs/{run}/content-index",params={'revision':task['revision']})
def page(client,task,meta,part='result',**extra):return client.get(f"/api/tasks/{task['id']}/runs/public-run/content",params={'revision':task['revision'],'source_token':meta['source_token'],'part':part,**extra})

def test_exact_saved_run_values_do_not_round_or_re_evaluate(client):
    task=seed(client);response=index(client,task);assert response.status_code==200,response.text
    meta=response.json();assert len(meta['parts'])==5 and meta['run_revision']==1
    result=page(client,task,meta);assert result.status_code==200,result.text
    data=result.json();assert '1.0' in data['text'] and '9007199254740993' in data['text']
    assert data['page_sha256']==hashlib.sha256(data['text'].encode('utf-8')).hexdigest()
    assert all(data[k] is False for k in ['task_changed','model_called','network_requested','platform_checked','business_verified'])
    assert main.get_task(task['id'])==task

@pytest.mark.parametrize('change',['revision','result','status','foreign','duplicate'])
def test_stale_or_foreign_record_never_returns_old_part(client,change):
    task=seed(client);meta=index(client,task).json()
    if change=='revision':task['revision']+=1
    elif change=='result':task['runs'][0]['result']['answer']['n']=2
    elif change=='status':task['runs'][0]['status']='unknown'
    elif change=='duplicate':task['runs'].append(copy.deepcopy(task['runs'][0]))
    else:
        other=approved(client);other['runs']=task['runs'];task=other
    main.store.put('task',task['id'],task);before=copy.deepcopy(task)
    response=page(client,task,meta);assert response.status_code==409,response.text
    assert 'text' not in response.json() and main.get_task(task['id'])==before

@pytest.mark.parametrize('bad',['secret','oversize','encoding'])
def test_unreadable_part_has_no_hash_or_partial_value_but_other_parts_remain_readable(client,bad):
    task=seed(client)
    value={'api_key':'sk-SYNTHETIC-ONLY-PRIVATE-0123456789'} if bad=='secret' else {'value':'x'*2_000_001} if bad=='oversize' else {'value':'PRIVATE\ud800'}
    task['runs'][0]['result']=value
    with main.store.connect() as db:db.execute('UPDATE objects SET value=? WHERE kind=? AND id=?',(json.dumps(task,ensure_ascii=True),'task',task['id']))
    meta_response=index(client,task);assert meta_response.status_code==200,meta_response.text
    meta=meta_response.json();entry=next(p for p in meta['parts'] if p['key']=='result');assert entry['state']=='unavailable' and entry['content_sha256'] is None and 'PRIVATE' not in meta_response.text
    result=page(client,task,meta);assert result.status_code==422 and 'PRIVATE' not in result.text and 'text' not in result.json()
    assert page(client,task,meta,'input').status_code==200

def test_null_and_missing_are_not_replaced_by_another_part(client):
    task=seed(client);task['runs'][0]['result']=None;main.store.put('task',task['id'],task)
    meta=index(client,task).json();assert page(client,task,meta).json()['text']=='null'
    entry=next(p for p in meta['parts'] if p['key']=='output');assert entry['state']=='missing'
    assert page(client,task,meta,'output').status_code==404

def test_unicode_paging_preserves_codepoint_offsets_and_one_full_source(client):
    task=seed(client);task['runs'][0]['result']={'text':'🙂𠀀e\u0301'*1300};main.store.put('task',task['id'],task)
    meta=index(client,task).json();first=page(client,task,meta).json();second=page(client,task,meta,offset=first['next_offset']).json()
    assert first['content_sha256']==second['content_sha256'] and len(first['text'])==4000
    assert json.loads(first['text']+second['text'])==task['runs'][0]['result']

@pytest.mark.parametrize('extra',[{'part':'unknown'},{'offset':-1},{'limit':4001},{'source_token':'bad'}])
def test_invalid_page_request_has_fixed_safe_error(client,extra):
    task=seed(client);meta=index(client,task).json();part=extra.pop('part','result')
    result=page(client,task,meta,part,**extra);assert result.status_code==422,result.text
    assert 'text' not in result.json()

def test_busy_task_reading_and_old_import_record_do_not_touch_budget_or_network(client):
    task=seed(client);task['status']='planning';task['runs'][0]['kind']='import';main.store.put('task',task['id'],task)
    before=main.store.get('task_budget',task['id']);meta=index(client,task).json()
    assert page(client,task,meta).status_code==200
    assert main.get_task(task['id'])==task and main.store.get('task_budget',task['id'])==before
