import copy
import httpx
import pytest
from test_run_diagnostics import client,recorded,diagnose,mock_reader,REMOTE,APP
from app import main
from app.run_diagnostics import findings_for_display,classify

def legacy():
    return {'id':'legacy','source_hash':'unchanged','saved_status':'success','saved_error':'','trace_state':'read','remote_status':'succeeded','remote_error':'','nodes':[{'id':'one','node_id':'end','node_type':'end','status':'succeeded','error':''}],'node_count':1,'truncated':False,'findings':[classify('')]}

def success(client):
    task,run=recorded(client,'success');run['error']='';run['result']={'workflow_run_id':REMOTE,'data':{'id':REMOTE,'status':'succeeded','error':None,'outputs':{'result':'ok'}}};run['evaluation']={'status':'passed'};main.save_task(task);return task,run

def test_legacy_full_success_view_is_explicit_and_immutable():
    report=legacy();before=copy.deepcopy(report);shown=findings_for_display(report)
    assert shown[0]['category']=='execution_trace_success' and '业务验收' in shown[0]['recommendation']
    assert report==before

@pytest.mark.parametrize('patch',[
    {'saved_status':'unknown'},{'saved_status':'failed'},{'saved_error':'previous failure'},
    {'saved_result_status':'failed'},{'remote_status':'failed'},{'remote_error':'failure'},
    {'trace_state':'read_failed'},{'trace_state':'unavailable'},{'trace_error':'bad read'},
    {'nodes':[],'node_count':0},{'node_count':2},{'node_count':True},{'truncated':True},
    {'nodes':[{'status':'failed','error':''}]},{'nodes':[{'status':'succeeded','error':'problem'}]},
    {'nodes':[{'status':'running','error':''}]},{'nodes':[{'status':'succeeded','observations':{'extraction_status':'not_extracted'}}]},
    {'nodes':[{'status':'succeeded','observations':{'http_status_class':'non_2xx'}}]},
    {'findings':[{'category':'expectation_mismatch','basis':'saved_evaluation'}]},
    {'findings':[{'category':'extraction_not_extracted','basis':'native_extraction_flag'}]},
    {'findings':[classify('')|{'node_id':'failed_node','evidence':'unknown failure'}]},
])
def test_uncertain_failed_or_observed_issues_never_become_success(patch):
    report=legacy()|patch;before=copy.deepcopy(report)
    assert findings_for_display(report)==report['findings'] and report==before

def test_only_local_success_has_separate_limited_message():
    report=legacy()|{'trace_state':'local_only','nodes':[],'node_count':0,'remote_status':None}
    shown=findings_for_display(report)
    assert shown[0]['category']=='saved_execution_success' and '尚未读取' in shown[0]['recommendation']

def test_new_local_and_remote_reports_have_correct_info_without_changing_evaluation(client,monkeypatch):
    task,run=success(client);before=copy.deepcopy(run);calls=mock_reader(monkeypatch,detail={'id':REMOTE,'status':'succeeded'},nodes={'data':[{'id':'one','node_id':'end','node_type':'end','status':'succeeded'}]})
    local=diagnose(client,task).json();assert local['findings'][0]['category']=='saved_execution_success' and not calls
    remote=diagnose(client,task,True).json();assert remote['findings'][0]['category']=='execution_trace_success' and len(calls)==2
    saved=main.get_task(task['id'])['runs'][-1];assert {k:v for k,v in saved.items() if k!='diagnostics'}==before
    run=main.get_task(task['id']);run['runs'][-1]['evaluation']={'status':'failed'};main.save_task(run)
    mismatch=diagnose(client,task,True).json();assert mismatch['findings'][0]['category']=='expectation_mismatch'

def test_cached_presentation_get_and_report_are_local_readonly_and_source_bound(client,monkeypatch):
    task,run=success(client);report=legacy();report.update(source_revision=task['revision'],captured_at_revision=task['revision'],current_source=False,remote_run_id=REMOTE,app_id=APP,notes=[],created_at='2026-10-25T00:00:00Z')
    run['diagnostics']=[report];main.save_task(task);before=copy.deepcopy(main.get_task(task['id']))
    def forbidden(*a,**kw):pytest.fail('Cached presentation must not decrypt, call model or contact Dify')
    monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden);monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)
    url=f"/api/tasks/{task['id']}/runs/failed-run/diagnostics/legacy/presentation"
    response=client.get(url);assert response.status_code==200,response.text
    value=response.json();assert value['diagnostic_id']=='legacy' and value['source_hash']=='unchanged' and value['presentation_adjusted'] and value['findings'][0]['category']=='execution_trace_success'
    markdown=client.get(f"/api/tasks/{task['id']}/report").text
    assert '采集轨迹未发现执行失败' in markdown and '原始采集记录（保留原文）' in markdown and '尚不能可靠归因' in markdown
    assert client.get(url.replace('/legacy/','/missing/')).status_code==404
    assert client.get(url.replace('/failed-run/','/other-run/')).status_code==404
    assert main.get_task(task['id'])==before
