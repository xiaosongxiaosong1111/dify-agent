import copy,json,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.storage import Store


def task(name='public'):
    return {'id':'public-task','name':name,'revision':1,'state_sequence':999}


@pytest.mark.parametrize('method',['put','put_many','put_with_secrets','put_many_with_secrets','put_many_with_secret_sets'])
def test_every_task_write_path_allocates_and_returns_committed_state(tmp_path,method):
    store=Store(tmp_path)
    for sequence in (1,2):
        value=task();other={'public':True}
        if method=='put':store.put('task',value['id'],value)
        elif method=='put_many':store.put_many([('task',value['id'],value),('receipt','public',other)])
        elif method=='put_with_secrets':store.put_with_secrets('task',value['id'],value,{'test':'public-synthetic-only'})
        elif method=='put_many_with_secrets':store.put_many_with_secrets([('task',value['id'],value),('receipt','public',other)],'test-connection',{'test':'public-synthetic-only'})
        else:store.put_many_with_secret_sets([('task',value['id'],value),('receipt','public',other)],{'test-connection':{'test':'public-synthetic-only'}})
        assert value['state_sequence']==sequence
        assert store.get('task',value['id'])==value and value['revision']==1
        assert 'state_sequence' not in other


def test_legacy_reads_do_not_backfill_and_first_write_starts_one(tmp_path):
    store=Store(tmp_path);legacy={'id':'public-task','name':'legacy','revision':7}
    raw=json.dumps(legacy)
    with store.connect() as conn:conn.execute('INSERT INTO objects(kind,id,value) VALUES(?,?,?)',('task',legacy['id'],raw))
    assert store.get('task',legacy['id'])==legacy and store.list('task')==[legacy]
    with store.connect() as conn:assert conn.execute('SELECT value FROM objects WHERE kind=? AND id=?',('task',legacy['id'])).fetchone()[0]==raw
    store.put('task',legacy['id'],legacy)
    assert legacy['state_sequence']==1 and legacy['revision']==7


def test_atomic_failure_does_not_publish_sequence_or_partial_records(tmp_path):
    store=Store(tmp_path);before=task();store.put('task',before['id'],before)
    incoming={**before,'name':'attempted'};original=copy.deepcopy(incoming)
    with pytest.raises(TypeError):store.put_many([('task',incoming['id'],incoming),('receipt','bad',{'invalid':object()})])
    assert incoming==original and store.get('task',incoming['id'])==before and store.get('receipt','bad') is None
    store.put('task',incoming['id'],incoming);assert incoming['state_sequence']==2


def test_duplicate_task_records_in_one_transaction_get_distinct_sequences(tmp_path):
    store=Store(tmp_path);a,b=task('first'),task('second')
    store.put_many([('task',a['id'],a),('task',b['id'],b)])
    assert a['state_sequence']==1 and b['state_sequence']==2 and store.get('task',b['id'])==b


def test_two_store_instances_allocate_unique_committed_order(tmp_path):
    first,second=Store(tmp_path),Store(tmp_path);initial=task();first.put('task',initial['id'],initial)
    def writes(store):
        result=[]
        for _ in range(12):
            value=task();store.put('task',value['id'],value);result.append(value['state_sequence'])
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(writes,first);b=pool.submit(writes,second);values=a.result()+b.result()
    assert sorted(values)==list(range(2,26)) and first.get('task',initial['id'])['state_sequence']==25


@pytest.mark.parametrize('invalid',[True,-1,None,'private-marker',9007199254740991])
def test_invalid_existing_sequence_is_not_silently_reset(tmp_path,invalid):
    store=Store(tmp_path);existing={**task(),'state_sequence':invalid};raw=json.dumps(existing)
    with store.connect() as conn:conn.execute('INSERT INTO objects(kind,id,value) VALUES(?,?,?)',('task',existing['id'],raw))
    incoming=task();original=copy.deepcopy(incoming)
    with pytest.raises(ValueError) as error:store.put('task',incoming['id'],incoming)
    assert 'private-marker' not in str(error.value) and incoming==original and store.get('task',existing['id'])==existing
