import copy,json
import pytest
from uuid import uuid4
from test_api import client,forbid_api_external_calls
from test_mock_order_read import saved_after_sales
from app import main
from app.after_sales_cases import propose
from app.after_sales_starter import prepare as starter
from app.mock_order import PREFIX,NOT_FOUND_REPLY
from app.plan_text_codec import render


def built(client):
    task=saved_after_sales(client);url='/api/tasks/'+task['id']
    assert client.post(url+'/confirm',json={'revision':task['revision'],'kind':'configuration'}).status_code==200
    assert client.post(url+'/build',json={'revision':task['revision']}).status_code==200
    return main.get_task(task['id'])


def call(client,task,**extra):return client.post('/api/tasks/'+task['id']+'/after-sales-cases-preview',json={'revision':task['revision'],'dependency':'订单查询模拟','request_nonce':str(uuid4()),**extra})


def test_current_template_rows_exact_expected_mock_results_no_writes_or_calls(client,monkeypatch):
    task=built(client);original=copy.deepcopy(task);budget=main.store.get('task_budget',task['id'])
    def forbid(*args,**kwargs):pytest.fail('Case draft must not write/decrypt')
    monkeypatch.setattr(main.store,'put',forbid);monkeypatch.setattr(main.store,'secret',forbid)
    response=call(client,task);assert response.status_code==200,response.text
    value=response.json();rows=value['rows'];assert len(rows)==3
    assert rows[0]['input']=={'query':'查询订单 DEMO-001'} and rows[0]['expectation']['expected']==PREFIX+'合成样例：已发货。'
    assert rows[1]['expectation']['expected']==NOT_FOUND_REPLY and rows[2]['expectation']['expected']=='请提供订单号。'
    assert value['artifact_sha256']==task['artifact']['sha256']
    assert all(value[k] is False for k in ['task_changed','network_requested','model_called','code_executed','business_verified'])
    assert main.get_task(task['id'])==original and main.store.get('task_budget',task['id'])==budget


@pytest.mark.parametrize('change',['title','route','reply','unprotected'])
def test_any_non_template_change_is_preserved_and_not_inferred(change,client):
    task=built(client);plan=task['workflow_plan']
    if change=='title':plan['nodes'][0]['title']='手改标题'
    if change=='route':plan['edges'][1]['target']='retrieve'
    if change=='reply':next(n for n in plan['nodes'] if n['id']=='no_hit')['config']['variables']=[{'variable':'x','value_selector':['sys','query']}]
    if change=='unprotected':next(e for e in plan['edges'] if e['source']=='extract_order')['target']='order_lookup'
    with pytest.raises((ValueError,main.HTTPException)):propose(task,'订单查询模拟')


def test_all_table_rows_and_noncolliding_miss_identifier(client):
    task=built(client);task['workflow_plan']=None;task['artifact']=None
    from test_after_sales_starter import inputs
    data=inputs();data['records_text']=json.dumps({'UNLISTED-DEMO':'合成一','UNLISTED-DEMO_1':'合成二','DEMO':'合成三'})
    text,_=starter(task,data);task['workflow_plan']=json.loads(text)
    rows,_=propose(task,'订单查询模拟')
    assert len(rows)==5 and rows[-2]['input']['query']=='查询订单 UNLISTED-DEMO_2'


@pytest.mark.parametrize('key,value',[('requirements_confirmed',False),('configuration_confirmed',False),('plan_stale',True),('artifact',None),('dsl_reference',{'id':'manual-source'})])
def test_missing_confirmation_or_preserved_dsl_not_assumed_current(client,key,value):
    task=built(client);task[key]=value;main.store.put('task',task['id'],task)
    assert call(client,task).status_code==422


def test_changed_artifact_bytes_stale_revision_unknown_dependency_and_duplicate_body(client):
    task=built(client)
    assert call(client,task,revision=task['revision']+1).status_code==409
    assert call(client,task,dependency='未声明').status_code==422
    payload={'revision':task['revision'],'dependency':'订单查询模拟','request_nonce':str(uuid4())}
    raw=json.dumps(payload)[:-1]+',"dependency":"订单查询模拟"}'
    assert client.post('/api/tasks/'+task['id']+'/after-sales-cases-preview',content=raw,headers={'Content-Type':'application/json'}).status_code==422
    path=main.artifact_path(task);path.write_bytes(path.read_bytes()+b'\n# manual artifact edit\n')
    assert call(client,task).status_code==409


def test_selected_rows_can_save_as_new_unverified_cases_without_old_result_reuse(client):
    task=built(client);budget=copy.deepcopy(main.store.get('task_budget',task['id']));value=call(client,task).json();rows=[{k:v for k,v in r.items() if k!='scenario'}|{'id':str(uuid4())} for r in value['rows']]
    saved=client.post('/api/tasks/'+task['id']+'/test-cases',json={'revision':task['revision'],'cases':rows});assert saved.status_code==200,saved.text
    result=saved.json();assert result['revision']>task['revision'] and not result['requirements_confirmed'] and not result['configuration_confirmed']
    assert result['artifact'] is None and not result['runs']
    assert main.store.get('task_budget',task['id'])==budget
