import copy,json
import pytest
from test_api import client
from test_run_diagnostics import recorded,mock_reader,diagnose,REMOTE
from app.node_observations import extract
from app.run_diagnostics import parse_trace
from app import main


def row(code):return {'id':'http-exec','node_id':'fetch','node_type':'http-request','status':'succeeded','outputs':{'status_code':code,'body':'private-body','headers':{'secret':'private-header'},'files':['private-file']},'inputs':{'url':'private-url'}}


@pytest.mark.parametrize('code,state',[(200,'2xx'),(299,'2xx'),(304,'non_2xx'),(404,'non_2xx'),(500,'non_2xx'),(True,'unknown'),('404','unknown'),(404.0,'unknown'),(None,'unknown'),(99,'unknown'),(600,'unknown')])
def test_only_explicit_integer_response_codes_are_recorded_without_payload(code,state):
    value=extract(row(code));assert value['http_status_class']==state and 'private-' not in json.dumps(value)
    if state=='unknown':assert value['http_status_code'] is None


def test_truncated_response_does_not_prove_http_status():
    raw=row(404);raw['outputs_truncated']=True;assert extract(raw)['http_status_class']=='unknown'


def test_http_success_non2xx_is_business_warning_not_run_failure():
    report=parse_trace({'id':REMOTE,'status':'succeeded'},{'data':[row(404)]},REMOTE,[])
    assert report['remote_status']=='succeeded' and report['nodes'][0]['status']=='succeeded'
    assert report['findings'][0]['category']=='http_response_business_check'
    assert 'private-' not in json.dumps(report) and 'outputs' not in report['nodes'][0]


def test_diagnostic_save_does_not_override_saved_result_or_evaluation(client,monkeypatch):
    saved,run=recorded(client,status='success');run['result']['data']['status']='succeeded';run['evaluation']={'status':'passed','mode':'manual'};main.save_task(saved);before=copy.deepcopy(run)
    mock_reader(monkeypatch,detail={'id':REMOTE,'status':'succeeded'},nodes={'data':[row(404)]})
    response=diagnose(client,saved,True);assert response.status_code==200,response.text
    current=main.get_task(saved['id'])['runs'][-1];assert {k:v for k,v in current.items() if k!='diagnostics'}==before
    assert current['diagnostics'][-1]['findings'][0]['category']=='http_response_business_check'
    assert 'private-' not in json.dumps(current['diagnostics'])
