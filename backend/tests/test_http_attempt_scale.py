import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app.execution_scale import estimate
from test_container_http_read import plan,task
from test_preservation_extensions import http_plan
from test_aggregation import task as root_task
from test_iteration import batch_plan,task as batch_task


@pytest.mark.parametrize('enabled,count,expected',[(False,3,1),(True,1,2),(True,2,3),(True,10,11)])
def test_root_http_declared_attempts_do_not_change_logical_visits_or_plan(enabled,count,expected):
    p=http_plan();p['nodes'][1]['config']['retry_config']={'retry_enabled':enabled,'max_retries':count,'retry_interval':1200};before=copy.deepcopy(p)
    result=estimate(root_task(),p,{})
    assert result['max_resource_node_visits']['http_nodes']==1 and result['http_attempts']['total']==expected
    row=result['http_attempts']['nodes'][0];assert row['logical_visits']==1 and row['attempts_per_visit']==expected and row['retry_enabled'] is enabled
    assert row['scope_id'] is None and row['retry_interval_ms']==1200 and p==before
    assert not result['http_attempts']['actual_http_requests_known'] and not result['http_attempts']['internal_requests_counted'] and result['cost_usd'] is None


@pytest.mark.parametrize('items,total',[(None,None),(0,0),(1,3),(20,60),(100000,300000)])
def test_iteration_unknown_and_zero_are_distinct_and_retry_factor_applies_per_item(items,total):
    p,parent,node=plan();node['config']['retry_config']={'retry_enabled':True,'max_retries':2,'retry_interval':500}
    value=estimate(task(p),p,{} if items is None else {parent['id']:items});assert value['http_attempts']['total']==total
    row=value['http_attempts']['nodes'][0];assert row['scope_id']==parent['id'] and row['logical_visits']==items and row['max_attempts']==total
    assert value['max_resource_node_visits']['http_nodes']==items


def test_loop_uses_declared_round_cap_without_treating_parallel_or_early_stop_as_discount():
    p,parent,node=plan('loop');node['config']['retry_config']={'retry_enabled':True,'max_retries':1,'retry_interval':0}
    value=estimate(task(p),p,{});assert value['http_attempts']['total']==parent['config']['loop_count']*2


def test_unknown_non_http_items_do_not_make_zero_http_count_unknown_or_free():
    p=batch_plan();value=estimate(batch_task(p),p,{})
    assert value['has_unknown_item_count'] and value['http_attempts']['total']==0 and value['http_attempts']['nodes']==[]
    assert value['cost_usd'] is None and not value['cost_estimate_available'] and not value['actual_api_calls_known']


def test_unknown_container_does_not_erase_known_root_attempt_details():
    p,parent,node=plan();root={'id':'root_http','type':'http-request','config':{'method':'GET','url':'https://httpbin.org/get','headers':'','params':'','body':{'type':'none','data':[]}}}
    edge=next(e for e in p['edges'] if e['target']==parent['id']);edge['target']=root['id'];p['edges'].append({'source':root['id'],'target':parent['id']});p['nodes'].insert(-1,root)
    value=estimate(task(p),p,{})['http_attempts'];assert value['total'] is None
    known=next(r for r in value['nodes'] if r['scope_id'] is None);assert known['node_id']=='root_http' and known['max_attempts']==1 and known['max_retries']==0 and known['attempts_per_visit']==1


@pytest.mark.parametrize('bad',[None,{'retry_enabled':True,'max_retries':0,'retry_interval':0},{'retry_enabled':True,'max_retries':2.5,'retry_interval':0},{'retry_enabled':True,'max_retries':2,'retry_interval':True}])
def test_invalid_policy_never_returns_partial_attempt_counts(bad):
    p=http_plan();p['nodes'][1]['config']['retry_config']=bad
    with pytest.raises(ValueError):estimate(root_task(),p,{})
