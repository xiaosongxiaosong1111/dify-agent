"""Model format failures remain invalid without inventing a business decision."""
import copy,json
import pytest
from test_planning import run,USAGE
from test_workflow_plan import base_plan,task as compiler_task
from app.workflow_plan import validate_plan
from test_api import client,approved,planning_provider,forbid_api_external_calls
from app import main


def test_json_syntax_diagnostic_locates_extracted_candidate_without_echo_or_repair():
    text = '{\n  "nodes": [],\n  "edges": []\n  "schema_version": 1\n}'
    raw = '公开前置说明\n' + text + '\n公开后置说明'
    result, op, calls, reason = run([(raw, USAGE)], settings={'max_retries':0,'max_minutes':1,'max_cost_usd':1})
    assert result is None and reason == 'retry_limit' and len(calls) == 1
    diagnostic = '\n'.join(op['diagnostics'])
    assert '第4行，第3列' in diagnostic and '候选片段' in diagnostic
    assert 'schema_version' not in diagnostic and '公开前置说明' not in diagnostic
    assert op['last_response_excerpt'] == raw and op['attempts'][0]['usage'] == USAGE
    assert not op.get('last_candidate') and not op.get('decision_report')


def test_different_json_error_locations_keep_existing_no_progress_stop_and_usage():
    one = '{"nodes": [] "edges": []}'
    two = '{\n  "nodes": []\n  "edges": []}'
    result, op, calls, reason = run([(one, USAGE), (two, USAGE)])
    assert result is None and reason == 'no_progress' and len(calls) == 2
    assert op['attempts'][0]['diagnostics'] != op['attempts'][1]['diagnostics']
    assert op['last_response_excerpt'] == two and not op.get('last_candidate')
    assert all(attempt['usage'] == USAGE for attempt in op['attempts'])


@pytest.mark.parametrize('text,hint', [('{"a":1 "b":2}', '应为逗号'),
                                     ('{"a" 1}', '缺少冒号'),
                                     ('{a:1}', '双引号'),
                                     ('{"a":}', '缺少有效JSON值'),
                                     ('{"a":"unclosed}', '字符串未闭合'),
                                     ('{"a":"x\ny"}', '控制字符'),
                                     ('{"a":"\\x"}', '字符串转义无效'),
                                     ('{"a":"\\uQQQQ"}', 'Unicode转义无效')])
def test_fixed_chinese_reason_never_contains_decoder_document_values(text,hint):
    from app.planning import _json_syntax_diagnostic
    with pytest.raises(json.JSONDecodeError) as caught:
        json.loads(text)
    diagnostic = _json_syntax_diagnostic(caught.value)
    assert hint in diagnostic and '从0计字符偏移' in diagnostic
    assert text not in diagnostic


def test_unknown_decoder_message_and_non_decoder_exception_are_not_echoed():
    from app.planning import _json_syntax_diagnostic
    error = json.JSONDecodeError('Bearer PRIVATE-SYNTHETIC-VALUE', 'PRIVATE-FIELD', 0)
    assert 'PRIVATE' not in _json_syntax_diagnostic(error)
    assert _json_syntax_diagnostic(ValueError('PRIVATE-FIELD')) is None


def test_api_json_error_keeps_original_response_old_plan_revision_and_budget(client,monkeypatch):
    planning_provider(client);t=approved(client);url='/api/tasks/'+t['id']
    response=client.post(url+'/plan',json={'revision':t['revision'],'plan':base_plan()});assert response.status_code==200
    before=response.json();raw='{"schema_version":1,"nodes":[] "edges":[]}';calls=[]
    response=client.patch('/api/settings',json={'max_retries':0});assert response.status_code==200
    async def fake(*args,**kwargs):calls.append(args[2]);return raw,USAGE
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(url+'/plan/generate',json={'revision':before['revision']});assert response.status_code==422
    saved=client.get(url).json();op=saved['planning_runs'][-1]
    assert len(calls)==1 and op['stop_reason']=='retry_limit' and '候选片段' in '\n'.join(op['diagnostics'])
    assert op['last_response_excerpt']==raw and op['attempts'][0]['usage']==USAGE
    for key in ('revision','requirements','configuration','workflow_plan','requirements_confirmed','configuration_confirmed','artifact','runs'):
        assert saved.get(key)==before.get(key),key
    assert len(main.budgets.get(t['id'])['entries'])==1


def boolean_plan(value):
    plan=base_plan();plan['nodes'][0]['config']['variables'].append({'variable':'flag','type':'checkbox','required':True})
    plan['nodes'].append({'id':'check','type':'if-else','title':'检查','config':{'cases':[{'case_id':'yes','logical_operator':'and','conditions':[{'variable_selector':['start','flag'],'varType':'boolean','comparison_operator':'is','value':value}]}]}})
    plan['edges']=[{'source':'start','target':'check'},{'source':'check','target':'llm','source_handle':'yes'},{'source':'check','target':'llm','source_handle':'false'},{'source':'llm','target':'end'}]
    return plan


@pytest.mark.parametrize('value',['true','false'])
@pytest.mark.parametrize('retries',[0,3])
def test_string_boolean_stops_once_as_format_without_coercion(value,retries):
    plan=boolean_plan(value);before=copy.deepcopy(plan)
    validate=lambda candidate:validate_plan(compiler_task(),candidate)
    assert not validate(plan)['valid']
    fixed=copy.deepcopy(plan);fixed['nodes'][-1]['config']['cases'][0]['conditions'][0]['value']=value=='true'
    assert validate(fixed)['valid']
    result,op,calls,reason=run([(json.dumps(plan),USAGE)],settings={'max_retries':retries,'max_minutes':1,'max_cost_usd':1},validate=validate)
    assert result is None and reason=='invalid_plan_format' and len(calls)==1
    assert op['last_candidate']==before and plan==before and op['attempts'][0]['status']=='invalid'
    assert '不是新的业务选择' in op['message'] and 'decision_report' not in op


def test_mixed_graph_problem_stays_needs_decision_without_hiding_diagnostics():
    plan=boolean_plan('true');plan['edges']=[edge for edge in plan['edges'] if edge.get('source_handle')!='false']
    validate=lambda candidate:validate_plan(compiler_task(),candidate)
    result,op,calls,reason=run([(json.dumps(plan),USAGE)],validate=validate)
    assert result is None and reason=='needs_decision' and len(calls)==1 and len(op['diagnostics'])>1
    assert op['last_candidate']==plan


@pytest.mark.parametrize('value,operator',[('yes','is'),('true',{}),('false',[])])
def test_unrecognized_boolean_word_or_operator_remains_unresolved(value,operator):
    plan=boolean_plan(value);plan['nodes'][-1]['config']['cases'][0]['conditions'][0]['comparison_operator']=operator
    _,op,calls,reason=run([(json.dumps(plan),USAGE)],validate=lambda candidate:validate_plan(compiler_task(),candidate))
    assert reason=='needs_decision' and len(calls)==1 and op['last_candidate']==plan


def test_api_format_error_keeps_previous_plan_revision_confirmation_and_budget(client,monkeypatch):
    planning_provider(client);t=approved(client);url='/api/tasks/'+t['id']
    response=client.post(url+'/plan',json={'revision':t['revision'],'plan':base_plan()});assert response.status_code==200
    before=response.json();candidate=boolean_plan('true');calls=[]
    async def fake(*args,**kwargs):calls.append(args[2]);return json.dumps(candidate),USAGE
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(url+'/plan/generate',json={'revision':before['revision']});assert response.status_code==422 and '不是新的业务选择' in response.text
    saved=client.get(url).json();op=saved['planning_runs'][-1]
    assert len(calls)==1 and op['stop_reason']=='invalid_plan_format' and op['last_candidate']==candidate
    for key in ('revision','requirements','configuration','workflow_plan','requirements_confirmed','configuration_confirmed','artifact','runs'):
        assert saved.get(key)==before.get(key),key
    assert len(main.budgets.get(t['id'])['entries'])==1
