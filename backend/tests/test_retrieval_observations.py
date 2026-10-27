"""Native retrieval evidence; no retrieval/model request is dispatched."""
import copy,json,math
import httpx,pytest
from test_api import client
from test_run_diagnostics import recorded,mock_reader,diagnose,REMOTE
from app import main
from app.node_observations import extract
from app.run_diagnostics import parse_trace,findings_for_display

DATASET='d12cf081-5c52-41e3-b869-e94e6f8d37b1'
DOC='3688a74c-d2e2-48a6-a183-235f24145733'
SEGMENT='714ceb37-130e-4037-af7f-62ecc713fe96'

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
 def forbidden(*a,**kw):raise AssertionError('No physical model/Dify/HTTP in retrieval evidence checks')
 monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
 monkeypatch.setattr(main.DifyClient,'request',forbidden)
 monkeypatch.setattr(main,'call_model',forbidden)

def row(results=None,**patch):
 value={'id':'retrieval-execution','node_id':'kb','node_type':'knowledge-retrieval','status':'succeeded','outputs':{'result':[] if results is None else results},'inputs':{'query':'PRIVATE_QUERY'},'process_data':{'secret':'PRIVATE_PROCESS'}}
 value.update(patch);return value

def item(score=0):
 return {'metadata':{'dataset_id':DATASET,'document_id':DOC,'segment_id':SEGMENT,'score':score,'doc_metadata':{'password':'PRIVATE_PASSWORD'},'dataset_name':'PRIVATE_NAME','child_chunks':[{'content':'PRIVATE_CHILD'}]},'title':'PRIVATE_TITLE','content':'PRIVATE_CONTENT','summary':'PRIVATE_SUMMARY','files':['PRIVATE_FILE']}

def parsed(raw):return parse_trace({'id':REMOTE,'status':'succeeded'},{'data':[raw]},REMOTE,[])

def test_successful_empty_is_explicit_no_match_without_changing_execution():
 report=parsed(row());node=report['nodes'][0]
 assert node['observations']['retrieval_status']=='empty' and node['observations']['result_count']==0
 assert report['findings'][0]['category']=='retrieval_empty' and node['status']=='succeeded'
 assert '无命中' in report['findings'][0]['title']
 assert 'PRIVATE_' not in json.dumps(report)

@pytest.mark.parametrize('patch',[{'outputs':None},{'outputs':{}},{'outputs':'{"result":[]}'},{'outputs':{'result':None}},{'outputs':{'result':'[]'}},{'outputs':{'result':[None]}},{'outputs_truncated':True},{'outputs_truncated':'false'},{'outputs_truncated':0},{'status':'running'},{'status':None}])
def test_absent_malformed_truncated_or_nonterminal_is_unknown_not_no_match(patch):
 report=parsed(row(**patch));obs=report['nodes'][0]['observations']
 assert obs['retrieval_status']=='unknown' and obs['result_count'] is None and obs['sources']==[]
 assert any(f['category']=='retrieval_unknown' for f in report['findings'])

@pytest.mark.parametrize('patch',[{'status':'failed'},{'status':'exception'},{'error':'Query variable is not string type.'},{'status':'failed','outputs_truncated':True}])
def test_failed_retrieval_never_becomes_empty(patch):
 report=parsed(row(**patch));obs=report['nodes'][0]['observations']
 assert obs['retrieval_status']=='technical_failure' and obs['result_count'] is None and obs['sources']==[]
 assert any(f['category']=='retrieval_technical_failure' for f in report['findings'])
 assert not any(f['category']=='retrieval_empty' for f in report['findings'])

def test_returned_sources_are_whitelisted_not_business_relevance():
 raw=row([item(0),item(.9)]);before=copy.deepcopy(raw);report=parsed(raw);obs=report['nodes'][0]['observations']
 assert obs['retrieval_status']=='returned' and obs['result_count']==2
 assert obs['sources']==[{'position':i+1,'dataset_id':DATASET,'document_id':DOC,'segment_id':SEGMENT,'score':score} for i,score in enumerate([0,.9])]
 assert raw==before and 'PRIVATE_' not in json.dumps(report) and 'outputs' not in report['nodes'][0]
 assert report['findings'][0]['category']=='retrieval_returned' and '相关性' in obs['note']
 assert not any('低相关' in f['title'] or '高相关' in f['title'] for f in report['findings'])

@pytest.mark.parametrize('score',[True,False,'0.2',None,float('nan'),float('inf'),10**400])
def test_bad_score_is_unknown_not_zero_and_no_other_metadata_is_copied(score):
 part=item(score);part['metadata']['dataset_id']='app-PRIVATE_TOKEN';part['metadata']['document_id']='../PRIVATE_PATH';part['metadata']['segment_id']=None
 obs=extract(row([part]));assert obs['retrieval_status']=='returned'
 assert obs['sources']==[{'position':1,'dataset_id':None,'document_id':None,'segment_id':None,'score':None}]
 assert 'PRIVATE_' not in json.dumps(obs,allow_nan=False)

@pytest.mark.parametrize('part',[{}, {'metadata':None}, {'metadata':'PRIVATE_METADATA'}])
def test_missing_source_metadata_keeps_returned_count_but_no_fabricated_source(part):
 obs=extract(row([part]));assert obs['result_count']==1 and obs['sources'][0]=={'position':1,'dataset_id':None,'document_id':None,'segment_id':None,'score':None}

def test_bounded_sources_do_not_silently_claim_complete_preview():
 obs=extract(row([item(.2)]*21));assert obs['result_count']==21 and len(obs['sources'])==20 and obs['sources_truncated'] is True
 obs=extract(row([item(.2)]*1001));assert obs['retrieval_status']=='unknown' and obs['result_count'] is None

@pytest.mark.parametrize('status',['empty','unknown','technical_failure'])
def test_presentation_does_not_upgrade_legacy_generic_success_with_retrieval_warning(status):
 report={'saved_status':'success','saved_result_status':'succeeded','findings':[{'category':'unclassified','basis':'insufficient_evidence'}],'trace_state':'read','remote_status':'succeeded','nodes':[{'status':'succeeded','observations':{'retrieval_status':status}}],'node_count':1,'truncated':False}
 assert findings_for_display(report)==report['findings']

def test_saved_api_and_report_keep_original_run_revision_evaluation_and_private_output(client,monkeypatch):
 task,run=recorded(client,status='success');run['result']['data'].update(status='succeeded',error=None);run['error']=None;run['evaluation']={'status':'passed','mode':'manual'};main.save_task(task);before=copy.deepcopy(run)
 calls=mock_reader(monkeypatch,detail={'id':REMOTE,'status':'succeeded'},nodes={'data':[row([item(.2)])]})
 response=diagnose(client,task,True);assert response.status_code==200,response.text
 report=response.json();assert report['nodes'][0]['observations']['result_count']==1 and len(calls)==2
 saved=main.get_task(task['id']);assert saved['revision']==task['revision'] and saved['requirements_confirmed']==task['requirements_confirmed']
 assert {k:v for k,v in saved['runs'][-1].items() if k!='diagnostics'}==before
 exported=client.get(f"/api/tasks/{task['id']}/report");assert exported.status_code==200 and 'retrieval_returned' in exported.text and DATASET in exported.text
 assert 'PRIVATE_' not in exported.text


def test_whitelisted_uuid_matching_known_secret_is_not_copied():
 report=parse_trace({'id':REMOTE,'status':'succeeded'},{'data':[row([item(.2)])]},REMOTE,[DATASET,SEGMENT])
 obs=report['nodes'][0]['observations'];assert obs['sources'][0]['dataset_id'] is None and obs['sources'][0]['segment_id'] is None
 assert DATASET not in json.dumps(report) and SEGMENT not in json.dumps(report) and DOC in json.dumps(report)
