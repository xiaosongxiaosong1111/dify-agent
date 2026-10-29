"""Diagnose only an explicitly chosen saved turn; all transports are local doubles."""
import copy
import json
import pytest
from test_chatflow_diagnostic_source import client, no_real_external, recorded, APP, MESSAGE, CONVERSATION, REMOTE, OTHER
from app import main
from app.dify import DifyClient
from app.dsl_roundtrip import parse

SECOND='819709de-0003-4410-85c8-b0c3a2c621bc'


def conversation(client):
    task,run=recorded(client)
    turns=[{'input':{'query':'查询订单但没有单号'},'expectation':{'mode':'equals','target':'answer','expected':'请补单号'}},
           {'input':{'query':'ORD-104'},'expectation':{'mode':'equals','target':'answer','expected':'模拟：待发货'}}]
    run['test_case']={'id':'order-conversation','name':'公开两轮订单','required':True,**turns[0],'followups':turns[1:]}
    run['input']=turns[0]['input']
    results=[]
    for i,t in enumerate(turns):
        actual={**copy.deepcopy(run['result']),'id':MESSAGE if i==0 else OTHER,'message_id':MESSAGE if i==0 else OTHER,'answer':t['expectation']['expected']}
        results.append({'index':i+1,'status':'success',**copy.deepcopy(t),'source_conversation_id':None if i==0 else CONVERSATION,'result':actual,'evaluation':{'status':'passed'}})
    run['result']={'conversation_case':True,'complete':True,'conversation_id':CONVERSATION,'answer':results[-1]['result']['answer'],'turns':results}
    run['evaluation']={'status':'passed','mode':'conversation'}
    main.save_task(task)
    return task,run


def transport(monkeypatch,task,on_read=None):
    graph=parse(main.artifact_path(task).read_text('utf-8'),'advanced-chat')['workflow']['graph']
    node=next(n for n in graph['nodes'] if n['data']['type']=='llm');calls=[]
    async def read(self,method,path,**kwargs):
        assert method=='GET' and kwargs['credential']=='console_token'
        assert path.startswith('/console/api/apps/'+APP+'/');calls.append(path)
        if on_read:on_read(path)
        if '/messages/' in path:
            msg=path.rsplit('/',1)[-1];assert msg in {MESSAGE,OTHER}
            return {'id':msg,'conversation_id':CONVERSATION,'workflow_run_id':REMOTE if msg==MESSAGE else SECOND}
        if path.endswith('/node-executions'):
            return {'data':[{'id':OTHER,'node_id':node['id'],'node_type':'llm','title':'首轮节点' if REMOTE in path else '补号轮节点','status':'succeeded','error':None}]}
        if path.endswith('/workflows/publish'):return {'id':OTHER,'graph':graph}
        rid=path.rsplit('/',1)[-1];assert rid in {REMOTE,SECOND}
        return {'id':rid,'status':'succeeded','graph':graph}
    monkeypatch.setattr(DifyClient,'request',read)
    return calls


def request(client,task,index=None,remote=False,**kwargs):
    body={'revision':task['revision'],'read_remote':remote,**kwargs}
    if index is not None:body['turn_index']=index
    return client.post(f"/api/tasks/{task['id']}/runs/chat-run/diagnose",json=body)


def test_first_then_second_are_exact_separate_sources_and_old_results_kept(client,monkeypatch):
    task,run=conversation(client);before=copy.deepcopy(run);budget=copy.deepcopy(main.store.get('task_budget',task['id']))
    calls=transport(monkeypatch,task)
    for index,msg,rid in [(1,MESSAGE,REMOTE),(2,OTHER,SECOND)]:
        response=request(client,task,index,True);assert response.status_code==200,response.text
        r=response.json();assert r['selected_turn']==index and r['selection_mode']=='explicit_turn'
        assert r['remote_run_id']==rid and r['trace_state']=='read' and r['source_graph']['matched']
        assert calls[-4]==f'/console/api/apps/{APP}/messages/{msg}'
        assert calls[-3].endswith('/workflow-runs/'+rid) and calls[-2].endswith('/'+rid+'/node-executions')
    assert len(calls)==8
    current=main.get_task(task['id']);assert {k:v for k,v in current['runs'][0].items() if k!='diagnostics'}==before
    assert current['revision']==task['revision'] and main.store.get('task_budget',task['id'])==budget


def test_default_still_chooses_last_or_failed_without_explicit_mode(client):
    task,run=conversation(client)
    assert request(client,task).json()['selected_turn']==2
    run['result']['turns'][0]['evaluation']['status']='failed';main.save_task(task)
    r=request(client,task).json();assert r['selected_turn']==1 and 'selection_mode' not in r


def test_successful_first_turn_does_not_borrow_later_auth_error_or_failed_evaluation(client):
    task,run=conversation(client);run.update(status='failed',error='Dify HTTP 401 later',http_status=401,evaluation={'status':'failed'})
    main.save_task(task);r=request(client,task,1).json()
    assert r['saved_status']=='failed' and r['selected_turn_status']=='success' and not r['saved_error']
    assert r['findings'][0]['category']=='saved_execution_success'
    assert main.get_task(task['id'])['runs'][0]['status']=='failed'


def test_first_turn_own_rule_mismatch_not_hidden_by_other_turn(client):
    task,run=conversation(client);run['result']['turns'][0]['evaluation']={'status':'failed'};main.save_task(task)
    r=request(client,task,1).json();assert r['findings'][0]['category']=='expectation_mismatch'
    assert request(client,task,2).json()['findings'][0]['category']=='saved_execution_success'


@pytest.mark.parametrize('index',[0,11,True,'1',1.0])
def test_invalid_request_index_cannot_dispatch_or_save(client,monkeypatch,index):
    task,run=conversation(client);before=copy.deepcopy(task)
    response=request(client,task,index,True);assert response.status_code==422
    assert main.get_task(task['id'])==before


@pytest.mark.parametrize('bad',['missing','duplicate','bool_index','bad_list','pending_duplicate','outside_case','single','no_case','workflow'])
def test_missing_or_ambiguous_saved_turn_never_falls_back_or_decrypts(client,monkeypatch,bad):
    task,run=conversation(client);index=1
    if bad=='missing':run['result']['turns']=run['result']['turns'][1:]
    if bad=='duplicate':run['result']['turns'].append(copy.deepcopy(run['result']['turns'][0]))
    if bad=='bool_index':run['result']['turns'][0]['index']=True
    if bad=='bad_list':run['result']['turns']=None
    if bad=='pending_duplicate':run['result']['pending_turn']=copy.deepcopy(run['result']['turns'][0])
    if bad=='outside_case':index=3
    if bad=='single':run['result']=run['result']['turns'][0]['result']
    if bad=='no_case':run.pop('test_case')
    if bad=='workflow':run['app_type']='workflow'
    main.save_task(task);before=copy.deepcopy(task)
    monkeypatch.setattr(main.store,'secret',lambda *a:pytest.fail('Invalid turn must fail before decrypt'))
    response=request(client,task,index,True);assert response.status_code==422,response.text
    assert main.get_task(task['id'])==before


def test_not_dispatched_second_turn_is_rejected_not_replaced_with_first(client):
    task,run=conversation(client);run['result']['turns']=run['result']['turns'][:1];run['result']['complete']=False;main.save_task(task)
    assert request(client,task,2).status_code==422
    assert request(client,task,1).json()['selected_turn']==1


def test_unknown_pending_turn_can_be_selected_without_erasing_unknown(client,monkeypatch):
    task,run=conversation(client);second=run['result']['turns'].pop();run['result'].update(complete=False,pending_turn=second)
    run.update(status='unknown',error='后续连接中断');main.save_task(task);calls=transport(monkeypatch,task)
    response=request(client,task,2,True);assert response.status_code==200,response.text
    assert response.json()['remote_run_id']==SECOND and len(calls)==4
    saved=main.get_task(task['id'])['runs'][0];assert saved['status']=='unknown' and saved['result']['pending_turn']==second


def test_missing_selected_result_does_not_use_another_turn_message(client):
    task,run=conversation(client);run['result']['turns'][0]['result']=None;main.save_task(task)
    r=request(client,task,1,True).json();assert r['trace_state']=='unavailable' and r['remote_run_id'] is None


def test_agent_turn_is_local_only_not_sent_to_workflow_endpoints(client):
    task,run=conversation(client);run['app_type']='agent';main.save_task(task)
    r=request(client,task,1,True).json();assert r['selected_turn']==1 and r['trace_state']=='unavailable'


def test_late_read_source_change_refuses_save_and_preserves_old_results(client,monkeypatch):
    task,run=conversation(client)
    def change(path):
        if '/messages/' in path:
            current=main.get_task(task['id']);current['runs'][0]['result']['turns'][0]['result']['answer']='changed';main.save_task(current)
    transport(monkeypatch,task,change)
    assert request(client,task,1,True).status_code==409
    assert not main.get_task(task['id'])['runs'][0].get('diagnostics')
