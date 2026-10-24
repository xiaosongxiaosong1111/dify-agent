import copy,json,asyncio,threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_api import client,forbid_api_external_calls
from test_dsl_roundtrip import prepared
from test_execution_limits import configure_service,save
from app import main
from app.dify import DifyError
from app.storage import Store


def ready(client):
    task,_=prepared(client);configure_service(task)
    task['test_cases']=[{'id':str(i),'name':'合成样例'+str(i),'required':True,'input':{'query':'q'+str(i)},'expectation':{'mode':'equals','target':'result','expected':'q'+str(i)}} for i in range(2)]
    main.save_task(task);assert save(client,task,count=2).status_code==200
    return main.get_task(task['id'])


def preview(client,t,ids=None):return client.post('/api/tasks/'+t['id']+'/case-sequence-preview',json={'revision':t['revision'],'case_ids':ids or ['0','1']})
def send(client,t,p,index=0,**extra):
    return client.post('/api/tasks/'+t['id']+'/run',json={'revision':t['revision'],'case_id':p['case_ids'][index],
        'sequence':{k:p[k] for k in ('case_ids','start_count','token')}|{'index':index},**extra})


def fake(monkeypatch,answer=None):
    calls=[]
    async def run(self,values):
        calls.append(copy.deepcopy(values))
        if isinstance(answer,Exception):raise answer
        return {'data':{'status':'succeeded','outputs':{'result':values['query'] if answer is None else answer}}}
    monkeypatch.setattr(main.DifyClient,'run_workflow',run);return calls


def test_preview_readonly_no_decrypt_no_store_writes(client,monkeypatch):
    t=ready(client);before=copy.deepcopy(t);budget=main.store.get('task_budget',t['id'])
    def forbid(*a,**kw):pytest.fail('preview must not write/decrypt')
    monkeypatch.setattr(main.store,'secret',forbid);monkeypatch.setattr(main.store,'put',forbid)
    r=preview(client,t);assert r.status_code==200,r.text
    p=r.json();assert p['requested_runs']==2 and p['max_started_runs']==2 and p['start_count']==len(t['runs'])
    assert p['network_requested'] is False and p['task_changed'] is False and p['resource_permission_granted'] is False
    assert main.get_task(t['id'])==before and main.store.get('task_budget',t['id'])==budget


def test_two_ordered_passes_each_new_record_and_old_request_rejected(client,monkeypatch):
    t=ready(client);calls=fake(monkeypatch);p=preview(client,t).json()
    assert send(client,t,p,1).status_code==409
    for i in range(2):
        r=send(client,t,p,i);assert r.status_code==200,r.text
        last=r.json()['runs'][-1];assert last['evaluation']['status']=='passed' and last['test_case']==t['test_cases'][i]
        assert send(client,t,p,i).status_code==409
    assert len(calls)==2 and main.get_task(t['id'])['runs'][:p['start_count']]==t['runs']


@pytest.mark.parametrize('mode',['failed','manual','unknown','waiting'])
def test_first_nonpass_blocks_later_even_reloaded_store(mode,client,monkeypatch):
    t=ready(client)
    if mode=='manual':t['test_cases'][0]['expectation']={'mode':'manual','description':'需业务判断'};main.save_task(t)
    answer=DifyError('结果可能未知，停止。') if mode=='unknown' else main.DifyPaused('等待平台',result={'waiting_state':{'platform_status':'paused'}}) if mode=='waiting' else 'wrong' if mode=='failed' else None
    calls=fake(monkeypatch,answer)
    p=preview(client,t).json();r=send(client,t,p)
    assert r.status_code==(502 if mode=='unknown' else 200)
    main.store=Store(main.DATA_ROOT)
    assert send(client,t,p,1).status_code==409 and len(calls)==1
    assert len(main.get_task(t['id'])['runs'])==p['start_count']+1


@pytest.mark.parametrize('change',['case','artifact','key','env','policy','history','task'])
def test_same_revision_scope_changes_invalidate_proof_without_dispatch(change,client,monkeypatch):
    t=ready(client);calls=fake(monkeypatch);p=preview(client,t).json()
    if change=='case':t['test_cases'][1]['input']['query']='changed';main.save_task(t)
    elif change=='artifact':main.artifact_path(t).write_bytes(main.artifact_path(t).read_bytes()+b'\n# changed\n')
    elif change=='key':main.store.set_secret(t['environment_id'],'service_api_key','another-synthetic-key')
    elif change=='env':
        env=main.environment(t);env['base_url']='https://new.invalid';main.store.put('environment',env['id'],env)
    elif change=='policy':assert save(client,t,count=3).status_code==200
    elif change=='history':t['runs'][0]['error']='changed old record';main.save_task(t)
    else:t['configuration']['max_tokens']=1024;main.save_task(t)
    r=send(client,t,p);assert r.status_code==409,r.text
    assert calls==[] and len(main.get_task(t['id'])['runs'])==p['start_count']


def test_finite_whole_batch_capacity_required_without_adjustment(client):
    t=ready(client)
    assert save(client,t,count=None).status_code==200 and preview(client,t).status_code==422
    assert save(client,t,count=1).status_code==200 and preview(client,t).status_code==409
    assert main.execution_limits.state(t)['policy']['max_started_runs']==1


@pytest.mark.parametrize('change',['duplicate','unknown','multiturn','nested','conversation','input'])
def test_unsupported_selection_refused(client,change):
    t=ready(client);ids=['0','1']
    if change=='duplicate':ids=['0','0']
    elif change=='unknown':ids=['missing']
    elif change=='multiturn':t['test_cases'][0]['followups']=[copy.deepcopy(t['test_cases'][0])]
    elif change=='nested':t['test_cases'][0]['input']['query']={'file':'not-supported'}
    elif change=='conversation':t['test_cases'][0]['input']['conversation_id']='cid'
    else:t['test_cases'][0]['input']={'wrong':'q'}
    main.save_task(t);assert preview(client,t,ids).status_code in {404,422}


def test_no_free_input_or_conversation_mixed_with_sequence(client,monkeypatch):
    t=ready(client);p=preview(client,t).json();calls=fake(monkeypatch)
    assert send(client,t,p,input={'query':'q0'}).status_code==422
    assert send(client,t,p,conversation_from_run_id='source').status_code==422
    assert not calls


def test_concurrent_same_step_only_dispatches_once(client,monkeypatch):
    t=ready(client);p=preview(client,t).json();entered=threading.Event();release=threading.Event();calls=[]
    async def run(self,values):
        calls.append(values);entered.set()
        while not release.is_set():await asyncio.sleep(.01)
        return {'data':{'status':'succeeded','outputs':{'result':'q0'}}}
    monkeypatch.setattr(main.DifyClient,'run_workflow',run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(send,client,t,p)
        try:
            assert entered.wait(5)
            assert send(client,t,p).status_code==409
        finally:release.set()
        assert first.result(timeout=5).status_code==200
    assert len(calls)==1


def test_ambiguous_body_and_wrong_index_do_not_change_task(client):
    t=ready(client);p=preview(client,t).json();before=copy.deepcopy(main.get_task(t['id']))
    raw=json.dumps({'revision':t['revision'],'case_ids':['0']})[:-1]+',"case_ids":["1"]}'
    assert client.post('/api/tasks/'+t['id']+'/case-sequence-preview',content=raw).status_code==422
    r=client.post('/api/tasks/'+t['id']+'/run',json={'revision':t['revision'],'case_id':'1','sequence':{k:p[k] for k in ('case_ids','start_count','token')}|{'index':0}})
    assert r.status_code==409 and main.get_task(t['id'])==before


def test_pause_after_first_pass_blocks_next_without_dispatch(client,monkeypatch):
    t=ready(client);p=preview(client,t).json();calls=fake(monkeypatch)
    assert send(client,t,p).status_code==200
    current=main.get_task(t['id']);current['status']='paused';main.save_task(current)
    assert send(client,t,p,1).status_code==409 and len(calls)==1
