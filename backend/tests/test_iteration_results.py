import copy,hashlib,json
import pytest
from test_api import client,approved
from app import main
from app.iteration_results import outcomes

def records(n=45,chain=False):
 result=[]
 for i in range(n):
  ok=i%3!=1;row={'index':i,'ok':ok,'value':{'text':'公开结果','n':i,'duplicate':'保留'} if ok else None,'error_category':None if ok else 'ValueError'}
  if chain:row['failed_stage']=None if ok else 2
  result.append(row)
 return result

def setup(client,n=45,value=None,**patch):
 task=approved(client);run={'id':'batch-run','kind':'run','status':'success','app_type':'workflow','revision':task['revision'],'app_id':'public-app','environment_id':'public-environment','result':{'data':{'outputs':{'result.items':records(n) if value is None else value}}},**patch};task['runs']=[run];main.save_task(task);return main.get_task(task['id'])
def path(task):return f"/api/tasks/{task['id']}/runs/batch-run/iteration-results"
def get(client,task,**params):return client.get(path(task),params={'revision':task['revision'],'field':'result.items',**params})

def test_full_field_counts_pages_and_failed_original_indices_no_changes(client,monkeypatch):
 task=setup(client);before=copy.deepcopy(main.get_task(task['id']))
 def forbidden(*a,**kw):pytest.fail('Read must not decrypt, execute or contact model/platform')
 monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 response=get(client,task);assert response.status_code==200,response.text;v=response.json();assert v['total']==45 and v['failed']==15 and len(v['rows'])==20 and v['rows'][0]['index']==0
 assert response.headers['cache-control']=='no-store' and all(v[k] is False for k in ['task_changed','network_requested','business_verified'])
 more=get(client,task,source=v['source_sha256'],offset=20).json();assert [r['index'] for r in more['rows']]==list(range(20,40))
 tail=get(client,task,source=v['source_sha256'],offset=40).json();assert len(tail['rows'])==5
 failed=get(client,task,source=v['source_sha256'],state='failed').json();assert [r['index'] for r in failed['rows']]==list(range(1,45,3))
 assert main.get_task(task['id'])==before

def test_export_selected_full_values_and_source_hash_not_preview(client):
 rows=records(3,chain=True);rows[0]['value']={'large':'x'*4000,'amount':-2.5};task=setup(client,value=rows);before=copy.deepcopy(main.get_task(task['id']));v=get(client,task).json();assert v['rows'][0]['value_truncated'] and v['rows'][0]['value_characters']>4000
 query={'revision':task['revision'],'field':'result.items','source':v['source_sha256'],'state':'all'};response=client.get(path(task)+'/export',params=query);assert response.status_code==200,response.text;assert response.json()['items']==rows
 assert response.headers['x-sierra-content-sha256']==hashlib.sha256(response.content).hexdigest()
 query['state']='failed';response=client.get(path(task)+'/export',params=query);assert response.json()['items']==[rows[1]] and response.json()['items'][0]['index']==1
 assert main.get_task(task['id'])==before

@pytest.mark.parametrize('rows',[[],records(1)])
def test_empty_or_no_failures_have_explicit_zero_filtered_results(client,rows):
 task=setup(client,value=rows);response=get(client,task,state='failed');assert response.status_code==200,response.text;v=response.json();assert v['selected_total']==0 and v['rows']==[]

@pytest.mark.parametrize('patch',[{'index':True},{'index':1},{'ok':1},{'error_category':'PrivateSentinel'}, {'value':None}, {'value':True},{'value':9007199254740993},{'value':float('inf')},{'value':{'password':'PrivateSentinel'}},{'unknown':'PrivateSentinel'},{'failed_stage':2}])
def test_bad_complete_protocol_or_sensitive_data_rejected_without_echo(client,patch):
 rows=records(2);rows[0].update(patch);task=setup(client,value=rows);r=get(client,task);assert r.status_code==422,r.text;assert 'PrivateSentinel' not in r.text

@pytest.mark.parametrize('value',['[{"index":0,"index":0,"ok":true,"value":"x","error_category":null}]','[{"index":0,"ok":true,"value":0.10000000000000001,"error_category":null}]','{}','null','[],"extra":123',records(1001)])
def test_raw_string_duplicate_numeric_loss_nonarrays_and_limits_rejected(client,value):
 task=setup(client,value=value);r=get(client,task);assert r.status_code==422,r.text

def test_raw_array_string_is_explicitly_supported_without_changing_original(client):
 raw=json.dumps(records(3),ensure_ascii=False,indent=3);task=setup(client,value=raw);v=get(client,task);assert v.status_code==200,v.text;assert main.get_task(task['id'])['runs'][0]['result']['data']['outputs']['result.items']==raw

@pytest.mark.parametrize('patch',[{'kind':'import'},{'status':'unknown'},{'status':'error'},{'app_type':None},{'revision':True},{'revision':999},{'conversation_context':{}},{'file_case':{}},{'test_case':{'followups':[{}]}},{'test_case':[]},{'result':'PrivateSentinel'}])
def test_unsupported_record_not_flattened_to_completed_batch(client,patch):
 task=setup(client,**patch);r=get(client,task);assert r.status_code==422,r.text;assert 'PrivateSentinel' not in r.text

def test_source_change_stale_revision_duplicate_run_and_query_guards(client):
 task=setup(client);v=get(client,task).json();run=main.get_task(task['id']);run['runs'][0]['result']['data']['outputs']['result.items'][0]['value']='changed';main.save_task(run)
 assert get(client,task,source=v['source_sha256'],offset=20).status_code==409
 assert client.get(path(task)+'/export',params={'revision':task['revision'],'field':'result.items','source':v['source_sha256']}).status_code==409
 assert get(client,task,offset=20).status_code==422
 for params in [{'revision':task['revision']+1},{'field':'missing'},{'offset':1},{'offset':'1e2'},{'state':'success'},{'extra':'x'}]:assert get(client,task,**params).status_code in (409,422)
 assert client.get(path(task),params=[('revision',str(task['revision'])),('field','result.items'),('field','different')]).status_code==422
 run['runs']*=2;main.save_task(run);assert get(client,task).status_code==404

def test_root_result_size_and_nested_bound_fail_closed():
 value=records(1);value[0]['value']='x'*2_000_000
 with pytest.raises(main.HTTPException):outcomes(value)
 value=records(1);nested={};value[0]['value']=nested
 for _ in range(18):nested['child']={};nested=nested['child']
 with pytest.raises(main.HTTPException):outcomes(value)
