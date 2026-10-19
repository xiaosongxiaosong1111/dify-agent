import json,math
import pytest
from test_api import client
from test_run_diagnostics import recorded,mock_reader,diagnose,trace
from app.node_metrics import extract
from app.run_diagnostics import safe_text


def test_actual_zero_is_preserved_and_missing_is_unknown():
    zero=extract({'elapsed_time':0,'retry_index':0,'execution_metadata':{'total_tokens':0,'total_price':'0','currency':'USD','loop_index':0}},safe_text)
    assert zero['elapsed_seconds']=='0' and zero['total_tokens']==0 and zero['cost_known'] and zero['context']['loop_index']==0 and zero['context']['retry_index']==0
    absent=extract({},safe_text);assert absent['elapsed_seconds'] is None and absent['total_tokens'] is None and not absent['cost_known']


@pytest.mark.parametrize('bad',[True,-1,float('nan'),float('inf'),'invalid',{},1e20])
def test_invalid_numeric_measurements_do_not_become_zero_or_escape(bad):
    s=extract({'elapsed_time':bad,'retry_index':bad,'execution_metadata':{'total_tokens':bad,'total_price':bad,'iteration_index':bad}},safe_text)
    assert s['elapsed_seconds'] is None and s['total_tokens'] is None and s['reported_price'] is None and not s['context'] and s['notes']
    json.dumps(s,allow_nan=False)


def test_unknown_metadata_values_and_runtime_inputs_are_not_copied():
    row={'inputs':{'password':'private-data'},'outputs':{'secret':'private-output'},'execution_metadata':{'unknown':'private-unknown','tool_info':{'api_key':'private-tool-key'},'loop_variable_map':{'business':'private-state'},'total_tokens':8,'loop_id':'current-loop','loop_index':2}}
    s=extract(row,safe_text);assert s['context']=={'loop_id':'current-loop','loop_index':2} and s['total_tokens']==8
    assert 'private-' not in json.dumps(s)


def test_currency_and_context_are_strict_and_secret_identifiers_sanitized():
    s=extract({'execution_metadata':{'currency':'usd','total_price':'.02','iteration_id':'sk-fake-secret-1234567890123456','loop_id':9,'loop_index':True}},safe_text)
    assert not s['cost_known'] and s['currency'] is None and s['reported_price']=='0.02'
    assert s['context']=={'iteration_id':'[已脱敏]'} and len(s['notes'])==3


def test_parent_and_child_measurements_kept_separate_not_summed(client,monkeypatch):
    t,run=recorded(client);nodes=trace();nodes['data'][0].update(elapsed_time=2.5,execution_metadata={'total_tokens':10,'total_price':'.01','currency':'USD','iteration_id':'parent','iteration_index':0})
    nodes['data'].append({'id':'parent-execution','node_id':'parent','node_type':'iteration','status':'succeeded','elapsed_time':2.6,'execution_metadata':{'total_tokens':10,'total_price':'.01','currency':'USD'}})
    mock_reader(monkeypatch,nodes=nodes);response=diagnose(client,t,True);assert response.status_code==200
    report=response.json();assert [n['metrics']['total_tokens'] for n in report['nodes']]==[10,10]
    assert 'total_price' not in report and report['verification']=='diagnostic_evidence_only'


def test_bad_metadata_container_remains_unknown_and_does_not_destroy_trace(client,monkeypatch):
    t,run=recorded(client);nodes=trace();nodes['data'][0]['execution_metadata']=['private-value'];mock_reader(monkeypatch,nodes=nodes)
    response=diagnose(client,t,True);assert response.status_code==200
    metrics=response.json()['nodes'][0]['metrics'];assert metrics['notes'] and metrics['total_tokens'] is None and 'private-value' not in json.dumps(metrics)
