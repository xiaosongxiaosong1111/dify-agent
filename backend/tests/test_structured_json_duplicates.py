import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.providers import extract_json
from test_planning import run, USAGE, plan
from test_api import client, approved, planning_provider, forbid_api_external_calls
from app import main
import copy


def test_json_parser_rejects_duplicate_fields_without_echo():
    raw = '{"nodes":[{"id":"original_branch"}],"nodes":[]}'
    with pytest.raises(ValueError) as caught:
        extract_json(raw)
    assert 'original_branch' not in str(caught.value) and 'nodes' not in str(caught.value)


@pytest.mark.parametrize('raw', ['{"id":1,"id":1}',
                               '{"outer":{"secret_field":1,"secret_field":2}}',
                               '{"items":[{"id":1,"id":2}]}',
                               r'{"nodes":[],"\u006eodes":[1]}',
                               '{"Bearer PRIVATE-SYNTHETIC-VALUE":1,"Bearer PRIVATE-SYNTHETIC-VALUE":2}'])
@pytest.mark.parametrize('wrapper', ['{}', '```json\n{}\n```', '公开前置说明\n{}\n公开后置说明'])
def test_duplicates_rejected_at_every_depth_and_after_extraction_without_key_echo(raw,wrapper):
    from app.providers import DuplicateJSONFieldError
    with pytest.raises(DuplicateJSONFieldError) as caught:extract_json(wrapper.format(raw))
    assert str(caught.value) == '模型JSON包含重复字段，未合并或覆盖。'


@pytest.mark.parametrize('raw', ['{"a":1,"b":2}', '{"left":{"id":1},"right":{"id":2}}', '{"items":[{"id":1},{"id":2}]}'])
def test_different_objects_may_reuse_keys_and_existing_wrappers_still_work(raw):
    expected=json.loads(raw)
    for text in (raw,'```json\n'+raw+'\n```','公开前置说明\n'+raw+'\n公开后置说明'):
        assert extract_json(text)==expected


@pytest.mark.parametrize('retries',[0,3])
def test_ambiguous_model_json_stops_once_keeps_response_usage_and_no_parsed_candidate(retries):
    raw='{"schema_version":1,"nodes":[{"id":"must_not_drop"}],"nodes":[],"edges":[]}'
    result,op,calls,reason=run([(raw,USAGE)],settings={'max_retries':retries,'max_minutes':1,'max_cost_usd':1})
    assert result is None and reason=='invalid_plan_format' and len(calls)==1
    assert op['last_response_excerpt']==raw and not op.get('last_candidate') and not op.get('decision_report')
    assert op['attempts'][0]['status']=='invalid' and op['attempts'][0]['usage']==USAGE
    assert '重复字段' in '\n'.join(op['diagnostics']) and 'must_not_drop' not in '\n'.join(op['diagnostics'])


def test_planning_api_keeps_old_revision_plan_confirmations_and_settles_one_call(client,monkeypatch):
    planning_provider(client);t=approved(client);url='/api/tasks/'+t['id']
    response=client.post(url+'/plan',json={'revision':t['revision'],'plan':plan()});assert response.status_code==200
    before=response.json();raw='{"schema_version":1,"nodes":[],"nodes":[],"edges":[]}';calls=[]
    async def fake(*args,**kwargs):calls.append(args[2]);return raw,USAGE
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(url+'/plan/generate',json={'revision':before['revision']});assert response.status_code==422 and '重复字段' in response.text
    saved=client.get(url).json();op=saved['planning_runs'][-1]
    assert len(calls)==1 and op['stop_reason']=='invalid_plan_format' and op['last_response_excerpt']==raw
    for key in ('revision','requirements','configuration','workflow_plan','requirements_confirmed','configuration_confirmed','artifact','runs'):
        assert saved.get(key)==before.get(key),key
    assert len(main.budgets.get(t['id'])['entries'])==1


def test_interview_duplicate_patch_is_not_applied_and_original_cost_is_kept(client,monkeypatch):
    planning_provider(client);t=approved(client);url='/api/tasks/'+t['id'];before=copy.deepcopy(main.get_task(t['id']));calls=[]
    raw='{"message":"合成建议","requirements_patch":{"goal":"first","goal":"second"}}'
    async def fake(*args,**kwargs):calls.append(args[2]);return raw,USAGE
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post(url+'/messages',json={'content':'请整理当前需求','revision':before['revision']})
    assert response.status_code==200,response.text
    saved=client.get(url).json()
    assert len(calls)==1 and saved['revision']==before['revision'] and saved['requirements']==before['requirements']
    assert saved['requirements_confirmed']==before['requirements_confirmed']
    assert saved['configuration_confirmed']==before['configuration_confirmed']
    assert saved['interview_attempts'][-1]['response_excerpt']==raw and saved['interview_attempts'][-1]['applied'] is False
    assert len(main.budgets.get(t['id'])['entries'])==1
