"""Clarification is persisted as unverified questions, never an adopted plan."""
import copy
import json
import pytest
from test_api import client, approved, planning_provider
from app.planning_decisions import summarize, FIELDS
from test_planning import run, USAGE
from test_workflow_plan import base_plan
from app import main


def test_rich_decision_survives_pause_without_another_call_or_validation():
    row={k:'已明确的'+k for k in FIELDS}
    value={'error':'还缺检索范围', 'needs_decision':[{'id':'resource',**row},'是否接受模拟？']}
    def forbidden(candidate):raise AssertionError('澄清不能被当成计划校验')
    result,op,calls,error=run([(json.dumps(value,ensure_ascii=False),USAGE)],validate=forbidden)
    assert result is None and error=='needs_decision' and len(calls)==1
    report=op['decision_report']
    assert report['verification']=='model_clarification_only' and report['format_valid'] and not report['incomplete']
    assert report['questions'][0]==row and 'id' not in report['questions'][0]
    assert report['questions'][1]['question']=='是否接受模拟？' and report['questions'][1]['recommendation']==''
    assert 'last_candidate' not in op and op['attempts'][0]['status']=='needs_decision'


@pytest.mark.parametrize('error',[None,False,{},[],0,'',' '*2,'x'*2001],ids=['null','bool','dict','list','number','empty','space','long'])
def test_invalid_error_does_not_coerce_or_apply(error):
    _,op,calls,reason=run([(json.dumps({'error':error}),USAGE)])
    assert reason=='needs_decision' and len(calls)==1
    assert not op['decision_report']['format_valid'] and op['decision_report']['incomplete']
    assert 'last_candidate' not in op


@pytest.mark.parametrize('row',[False,1,{},[],{'question':'x','action':'auto_confirm'},{'question':None},{'question':'x','cost':3},{'id':False,'question':'x'},{'question':'x'*2001}],ids=['bool','num','empty','list','action','no-question','typed-cost','typed-id','long'])
def test_bad_question_is_flagged_without_converting_it_to_text(row):
    r=summarize({'error':'条件待补齐','needs_decision':[row,'仍可阅读的独立问题']})
    assert not r['format_valid'] and r['incomplete']
    assert len(r['questions'])==1 and r['questions'][0]['question']=='仍可阅读的独立问题'


def test_unrecognized_top_level_fields_never_hide_the_incomplete_response():
    r=summarize({'type':'json_object','error':'缺库','details':{'missing':['真实ID']},'needs_decision':['请提供真实ID']})
    assert r['message']=='缺库' and r['questions'][0]['question']=='请提供真实ID'
    assert r['incomplete'] and not r['format_valid']


def test_question_limit_is_explicit_and_empty_error_only_remains_compatible():
    assert summarize({'error':'缺模型'})['format_valid']
    r=summarize({'error':'缺条件','needs_decision':[str(i) for i in range(21)]})
    assert len(r['questions'])==20 and r['incomplete'] and not r['format_valid']
    assert summarize({'error':'缺条件','needs_decision':{}})['incomplete']


def test_secret_like_or_invalid_unicode_is_not_expanded():
    for value in ({'error':'sk-'+'A'*32},{'error':'条件待补','needs_decision':['\ud800']}):
        r=summarize(value)
        assert r['incomplete'] and not r['format_valid'] and not r['questions']
        assert 'sk-' not in json.dumps(r) and '\\ud800' not in json.dumps(r)


def test_error_mixed_with_plan_stops_and_marks_incomplete():
    _,op,calls,reason=run([(json.dumps({'error':'请确认','nodes':[{'type':'end'}]}),USAGE)])
    assert reason=='needs_decision' and len(calls)==1 and 'last_candidate' not in op
    assert op['decision_report']['incomplete']


def test_api_persists_questions_keeps_revision_configuration_and_previous_plan(client,monkeypatch):
    planning_provider(client);task=approved(client);calls=[]
    response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':base_plan('workflow')})
    assert response.status_code==200,response.text
    task=response.json()
    before=copy.deepcopy(task)
    async def controlled(provider,key,messages,**kwargs):
        calls.append(messages);ctx=json.loads(messages[1]['content'])
        assert set(ctx['coverage_scope'])=={'enabled','confirmed','stale','blockers','items'}
        summary=main.coverage_summary(before)
        assert {k:ctx['coverage_scope'][k] for k in ('enabled','confirmed','stale','blockers')}=={k:summary[k] for k in ('enabled','confirmed','stale','blockers')}
        assert 'coverage_scope.enabled=false' in messages[0]['content']
        assert 'needs_decision' in messages[0]['content'] and '不能只写引用而漏节点' in messages[0]['content']
        return json.dumps({'error':'缺库和明确分支','needs_decision':[{'question':'使用哪个库？','recommendation':'请先选库','reason':'避免虚构ID','cost':'费用待核对'}]},ensure_ascii=False),USAGE
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert response.status_code==422 and len(calls)==1
    saved=client.get('/api/tasks/'+task['id']).json()
    for field in ('revision','requirements','configuration','workflow_plan','configuration_confirmed','artifact','runs'):
        assert saved[field]==before[field]
    record=client.get(f"/api/tasks/{task['id']}/planning").json()['runs'][-1]
    assert record['status']=='paused' and record['revision']==task['revision'] and record['stop_reason']=='needs_decision'
    assert record['decision_report']['questions'][0]['recommendation']=='请先选库'
    assert record['attempts'][0]['usage']==USAGE and record['estimated_cost_usd']>0


def test_documented_txt_example_contains_the_extractor_and_compiles_without_running_it(client):
    from pathlib import Path
    from app.workflow_plan import validate_plan, compile_workflow_plan
    import yaml
    from app.dsl_roundtrip import validate_preserved
    text=(Path(__file__).parents[2]/'docs/workflow-plan-contract.md').read_text('utf-8')
    block=text.split('Complete single local TXT draft example',1)[1].split('```json\n',1)[1].split('```',1)[0]
    plan=json.loads(block);task=approved(client);task['workflow_plan']=plan
    assert validate_plan(task,plan)['valid']
    assert next(n for n in plan['nodes'] if n['id']=='extract')['type']=='document-extractor'
    assert validate_preserved(yaml.safe_load(compile_workflow_plan(task)[0]))['valid']
