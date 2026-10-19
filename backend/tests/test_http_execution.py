import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app.http_execution import validate, native, preserved
from app.workflow_plan import compile_workflow_plan, validate_plan
from app.dsl_roundtrip import validate_preserved
from app.case_dsl_semantics import summary
from test_preservation_extensions import http_plan, native as document
from test_aggregation import task
from test_assistant_routing import setup, enable, state
from test_api import client
from app import main


def request_data(root):
    return next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='http')


def test_default_never_enables_retry_and_inherits_timeout():
    data=request_data(document(http_plan()))
    assert data['retry_config']=={'retry_enabled':False,'max_retries':0,'retry_interval':0}
    assert data['timeout'] is None and data['ssl_verify'] is True


def test_custom_native_policy_is_exact_and_not_shared():
    plan=http_plan();cfg=plan['nodes'][1]['config']
    cfg.update(timeout={'connect':4,'read':45,'write':60},ssl_verify=False,
               retry_config={'retry_enabled':True,'max_retries':2,'retry_interval':1500})
    before=copy.deepcopy(plan);data=request_data(document(plan))
    assert all(data[k]==cfg[k] for k in ('timeout','ssl_verify','retry_config'))
    data['retry_config']['max_retries']=9;assert plan==before
    result=validate_plan(task(),plan)
    assert result['valid'] and any('重复提交' in w for w in result['warnings'])
    assert any('证书' in w for w in result['warnings'])


@pytest.mark.parametrize('patch',[
 {'timeout':{'max_connect_timeout':10}}, {'timeout':{'connect':True}},
 {'timeout':{'connect':11}}, {'timeout':{'read':601}}, {'timeout':{'write':-1}},
 {'timeout':{'read':1.5}}, {'timeout':[]}, {'ssl_verify':'false'},
 {'retry_config':{'retry_enabled':True}},
 {'retry_config':{'retry_enabled':'true','max_retries':2,'retry_interval':100}},
 {'retry_config':{'retry_enabled':True,'max_retries':0,'retry_interval':0}},
 {'retry_config':{'retry_enabled':True,'max_retries':11,'retry_interval':0}},
 {'retry_config':{'retry_enabled':True,'max_retries':True,'retry_interval':0}},
 {'retry_config':{'retry_enabled':True,'max_retries':2,'retry_interval':5001}},
 {'retry_config':{'retry_enabled':True,'max_retries':2,'retry_interval':1.2}},
 {'error_strategy':'default-value'}, {'default_value':[{'key':'body','value':'fake success'}]},
])
def test_invalid_execution_settings_block_compilation(patch):
    plan=http_plan();plan['nodes'][1]['config'].update(patch)
    assert not validate_plan(task(),plan)['valid']
    content,result=compile_workflow_plan({**task(),'workflow_plan':plan})
    assert not result['valid'] and not content


def test_null_zero_timeout_and_dormant_native_retry_are_not_normalized():
    config={'timeout':{'connect':0,'read':None,'write':600},'retry_config':{'retry_enabled':False,'max_retries':3,'retry_interval':100}}
    assert not validate(config)[0] and native(config)=={**config,'ssl_verify':True}


def test_preserved_actual_policy_and_metadata_remain_exact():
    root=document(http_plan());data=request_data(root)
    data.update(timeout={'connect':5,'read':30,'write':40,'max_connect_timeout':10,'max_read_timeout':600,'max_write_timeout':600},
                ssl_verify=False,retry_config={'retry_enabled':True,'max_retries':2,'retry_interval':120})
    before=copy.deepcopy(root);result=validate_preserved(root)
    assert result['valid'],result['errors']
    assert root==before
    assert any('上限元数据' in w for w in result['warnings'])
    assert preserved(data)['timeout']=={'connect':5,'read':30,'write':40}


@pytest.mark.parametrize('patch',[{'timeout':{'unknown_timeout':20}}, {'timeout':{'max_read_timeout':False}}, {'retry_config':{'retry_enabled':True}}, {'error_strategy':'fail-branch'}])
def test_preserved_unknown_or_unsupported_policy_not_silently_removed(patch):
    root=document(http_plan());request_data(root).update(patch);before=copy.deepcopy(root)
    assert not validate_preserved(root)['valid'] and root==before


def test_http_retry_and_ssl_are_visible_in_final_case_contract():
    root=document(http_plan());data=request_data(root)
    data.update(ssl_verify=False,retry_config={'retry_enabled':True,'max_retries':2,'retry_interval':200})
    out=next(n['config'] for n in summary(root)['nodes'] if n['id']=='http')
    assert out['retry_config']==data['retry_config'] and out['ssl_verify'] is False


def test_old_scope3_requires_reconfirmation_before_any_dispatch(client):
    t,p,light=setup(client);assert enable(client,t,light).status_code==200
    policy=main.routing.get(t['id']);policy['scope_version']=3;main.store.put('assistant_routing',t['id'],policy)
    current=state(client,t);assert current['required_scope_version']==18 and current['blocker']
    assert enable(client,t,light,scope_version=3).status_code==409
    assert enable(client,t,light,scope_version=18).status_code==200
