from test_planning import run, USAGE
import json,sys
import pytest
from app.providers import extract_json,JSONStructureLimitError
from test_api import client,approved,planning_provider,forbid_api_external_calls
from app import main
from test_workflow_plan import base_plan


def test_deep_model_json_stops_once_as_format_without_internal_exception():
    raw = '{"x":' + '[' * 3000 + '0' + ']' * 3000 + '}'
    result, op, calls, reason = run([(raw, USAGE)], settings={'max_retries':3,'max_minutes':1,'max_cost_usd':1})
    assert result is None and reason == 'invalid_plan_format' and len(calls) == 1
    assert op['last_response_excerpt'] == raw and op['attempts'][0]['usage'] == USAGE
    assert '60' in '\n'.join(op['diagnostics']) and not op.get('last_candidate')


@pytest.mark.parametrize('levels',[60,150,3000])
@pytest.mark.parametrize('wrapper',['{}','```json\n{}\n```','公开前置说明\n{}\n公开后置说明'])
def test_excess_depth_rejected_before_model_objects_can_reach_recursive_consumers(levels,wrapper):
    raw='{"private_field":'+'['*levels+'0'+']'*levels+'}'
    with pytest.raises(JSONStructureLimitError) as caught:extract_json(wrapper.format(raw))
    assert 'private_field' not in str(caught.value) and '60' in str(caught.value)


def test_root_zero_limit_includes_leaf_and_bracket_text_is_not_structure():
    limit=sys.getrecursionlimit()
    raw='{"x":'+'['*59+'0'+']'*59+'}'
    assert isinstance(extract_json(raw),dict)
    text='['*3000+']'*3000
    assert extract_json(json.dumps({'code':text}))=={'code':text}
    assert sys.getrecursionlimit()==limit


@pytest.mark.parametrize('retries',[0,3])
def test_parseable_but_over_limit_candidate_stops_once_without_normalization(retries):
    raw='{"schema_version":1,"nodes":[],"edges":[],"extra":'+'['*150+'0'+']'*150+'}'
    result,op,calls,reason=run([(raw,USAGE)],settings={'max_retries':retries,'max_minutes':1,'max_cost_usd':1})
    assert result is None and reason=='invalid_plan_format' and len(calls)==1
    assert op['last_response_excerpt']==raw and op['attempts'][0]['usage']==USAGE
    assert not op.get('last_candidate') and not op.get('decision_report')


def test_api_deep_plan_returns_format_failure_not_internal_error_and_keeps_old_state(client,monkeypatch):
    planning_provider(client);t=approved(client);url='/api/tasks/'+t['id']
    response=client.post(url+'/plan',json={'revision':t['revision'],'plan':base_plan()});assert response.status_code==200
    before=response.json();raw='{"x":'+'['*3000+'0'+']'*3000+'}';calls=[]
    async def fake(*args,**kwargs):calls.append(args[2]);return raw,USAGE
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(url+'/plan/generate',json={'revision':before['revision']})
    assert response.status_code==422 and '60' in response.text
    saved=client.get(url).json();op=saved['planning_runs'][-1]
    assert len(calls)==1 and op['stop_reason']=='invalid_plan_format'
    assert op['last_response_excerpt']==raw and op['attempts'][0]['usage']==USAGE
    for key in ('revision','requirements','configuration','workflow_plan','requirements_confirmed','configuration_confirmed','artifact','runs'):
        assert saved.get(key)==before.get(key),key
    assert len(main.budgets.get(t['id'])['entries'])==1


def test_interview_depth_failure_keeps_requirements_confirmation_and_known_usage(client,monkeypatch):
    planning_provider(client);t=approved(client);url='/api/tasks/'+t['id'];before=main.get_task(t['id']);calls=[]
    raw='{"x":'+'['*3000+'0'+']'*3000+'}'
    async def fake(*args,**kwargs):calls.append(args[2]);return raw,USAGE
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(url+'/messages',json={'content':'请核对需求','revision':before['revision']})
    assert response.status_code==200,response.text
    saved=client.get(url).json()
    assert len(calls)==1 and saved['revision']==before['revision'] and saved['requirements']==before['requirements']
    assert saved['requirements_confirmed']==before['requirements_confirmed'] and saved['configuration_confirmed']==before['configuration_confirmed']
    assert not saved.get('active_interview_id')
    assert saved['interview_attempts'][-1]['response_excerpt']==raw and saved['interview_attempts'][-1]['applied'] is False
    assert len(main.budgets.get(t['id'])['entries'])==1
