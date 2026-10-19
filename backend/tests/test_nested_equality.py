import copy
import pytest
from test_acceptance import task,record
from test_api import client,approved
from app import main
from app.evaluation import evaluate_output
from app.acceptance import summarize_acceptance

@pytest.mark.parametrize('actual,expected',[
 ({'ok':False},{'ok':0}),({'ok':True},{'ok':1}),([False],[0]),([True],[1]),({'n':1},{'n':1.0}),({'items':[{'ok':0}]},{'items':[{'ok':False}]}),([1,2],[2,1]),([1,1],[1]),({'a':None},{}),({'a':1},{'a':1,'b':2})
])
def test_equality_checks_types_at_every_depth_and_preserves_order(actual,expected):
 before=copy.deepcopy(actual);result=evaluate_output({'result':actual},{'mode':'equals','target':'result','expected':expected})
 assert result['status']=='failed' and result['comparison_version']==2 and actual==before

@pytest.mark.parametrize('actual,expected',[
 ({'a':0,'b':False},{'b':False,'a':0}),([{'a':True},False,0,None],[{'a':True},False,0,None]),({},{}),([],[]),({'nested':{'list':[1.0]}},{'nested':{'list':[1.0]}})
])
def test_equal_json_retains_key_order_independence_and_exact_types(actual,expected):
 assert evaluate_output({'result':actual},{'mode':'equals','target':'result','expected':expected})['status']=='passed'

@pytest.mark.parametrize('version',[None,1,'2',2.0,3])
def test_old_object_result_not_reused_as_current_strict_pass_or_mutated(version):
 t=task();t['test_cases'][0]['expectation']={'mode':'equals','target':'result','expected':{'ok':False}};r=record(t,evaluation={'mode':'equals','status':'passed','details':'旧结论'})
 if version is not None:r['evaluation']['comparison_version']=version
 t['runs']=[r];before=copy.deepcopy(t);summary=summarize_acceptance(t)
 assert summary['cases'][0]['status']=='needs_review' and not summary['all_required_passed'] and t==before
 assert '没有自动重跑' in summary['cases'][0]['details']


def test_new_result_stamp_and_ordinary_string_history_remain_usable():
 t=task();c=t['test_cases'][0];c['expectation']={'mode':'equals','target':'result','expected':[False,0]};r=record(t,evaluation=evaluate_output({'result':[False,0]},c['expectation']));t['runs']=[r]
 assert summarize_acceptance(t)['all_required_passed']
 c['expectation']['expected']='plain';t['runs']=[record(t,evaluation={'mode':'equals','status':'passed','details':'原字符串核对'})]
 assert summarize_acceptance(t)['all_required_passed']


def test_manual_stamp_cannot_override_old_automatic_type_check():
 t=task();t['test_cases'][0]['expectation']={'mode':'equals','target':'result','expected':{'ok':False}}
 t['runs']=[record(t,evaluation={'mode':'equals','status':'passed'},manual_review={'source':'user','decision':'passed','reason':'旧人工标记'})]
 assert not summarize_acceptance(t)['all_required_passed']


def test_point_path_nested_equality_uses_same_strict_types():
 result=evaluate_output({'result':{'data':{'ok':0}}},{'mode':'equals','target':'result.data','expected':{'ok':False}})
 assert result['status']=='failed'


def test_readonly_api_and_report_mark_legacy_object_result_without_task_write(client,monkeypatch):
 t=approved(client);c={'id':'old-object','name':'旧对象结果','required':True,'input':{'query':'x'},'expectation':{'mode':'equals','target':'result','expected':{'ok':False}}};t['test_cases']=[c]
 t['runs']=[{'id':'old-equality-run','kind':'run','revision':t['revision'],'environment_id':t['environment_id'],'status':'success','input':copy.deepcopy(c['input']),'test_case':copy.deepcopy(c),'evaluation':{'mode':'equals','status':'passed','details':'历史通过'},'result':{'data':{'outputs':{'result':{'ok':0}}}}}];main.save_task(t);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('读取摘要不得保留费用或重新运行')
 monkeypatch.setattr(main.execution_limits,'require_start',forbidden);monkeypatch.setattr(main.DifyClient,'run_workflow',forbidden)
 response=client.get(f"/api/tasks/{t['id']}/acceptance");assert response.status_code==200
 assert response.json()['cases'][0]['status']=='needs_review' and not response.json()['all_required_passed']
 response=client.get(f"/api/tasks/{t['id']}/report");assert response.status_code==200 and '早期对象' in response.text
 assert main.get_task(t['id'])==before
