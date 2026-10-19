import copy,json,math
import pytest
from test_api import client
from test_run_diagnostics import recorded,mock_reader,diagnose,REMOTE
from app.run_diagnostics import parse_trace,classify
from app.node_observations import extract,finding
from app import main

def row(flag=0):return {'id':'execution','node_id':'extract','node_type':'parameter-extractor','status':'succeeded','outputs':{'__is_success':flag,'__reason':'private-reason','order':'private-order'},'inputs':{'query':'private-query'}}

@pytest.mark.parametrize('flag,state',[(0,'not_extracted'),(1,'extracted'),(0.0,'not_extracted'),(1.0,'extracted'),(True,'unknown'),(False,'unknown'),('0','unknown'),(None,'unknown'),(2,'unknown'),(float('nan'),'unknown'),(float('inf'),'unknown')])
def test_only_explicit_native_numeric_flags_are_observed_without_business_values(flag,state):
 value=extract(row(flag));assert value['extraction_status']==state and 'private-' not in json.dumps(value);json.dumps(value,allow_nan=False)

@pytest.mark.parametrize('patch',[{'outputs':'{"__is_success":0}'},{'outputs':None},{'outputs_truncated':True},{'outputs_truncated':'false'}])
def test_missing_serialized_or_truncated_output_does_not_become_failed_or_successful(patch):
 raw=row();raw.update(patch);assert extract(raw)['extraction_status']=='unknown'

def test_other_node_outputs_are_not_parsed_or_copied_and_flag_does_not_override_status():
 raw=row();raw['node_type']='code';assert extract(raw) is None
 raw=row();raw['status']='failed';raw['observations']=extract(raw);assert finding(raw) is None

def test_successful_execution_with_flag_zero_reports_business_warning_not_node_failure():
 report=parse_trace({'id':REMOTE,'status':'succeeded'},{'data':[row()]},REMOTE,[])
 assert report['remote_status']=='succeeded' and report['nodes'][0]['status']=='succeeded'
 assert report['findings'][0]['category']=='extraction_not_completed' and report['findings'][0]['basis']=='native_extraction_flag'
 assert 'private-' not in json.dumps(report) and 'outputs' not in report['nodes'][0]

def test_reading_native_flag_retains_original_success_and_saved_evaluation(client,monkeypatch):
 task,run=recorded(client,status='success');run['result']['data']['status']='succeeded';run['evaluation']={'status':'passed','mode':'manual'};main.save_task(task);before=copy.deepcopy(run)
 mock_reader(monkeypatch,detail={'id':REMOTE,'status':'succeeded'},nodes={'data':[row()]})
 response=diagnose(client,task,True);assert response.status_code==200,response.text
 current=main.get_task(task['id'])['runs'][-1];assert {k:v for k,v in current.items() if k!='diagnostics'}==before
 assert current['diagnostics'][-1]['findings'][0]['category']=='extraction_not_completed'
 assert 'private-' not in json.dumps(current['diagnostics'])

@pytest.mark.parametrize('error,category',[('Invalid serial index: must be <= 2, got 3','list_extract_index'),('Variable is not an array type','list_input_or_filter'),('Invalid filter value: incorrect','list_input_or_filter')])
def test_native_array_failure_has_configuration_specific_advice(error,category):
 assert classify(error,'list-operator')['category']==category
 assert classify(error,'code')['category']!=category
