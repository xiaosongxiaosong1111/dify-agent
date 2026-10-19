import copy
import json
import pytest
from test_api import client, create
from test_file_structured_run import shape
from test_file_model_run import MODEL
from app import main
from app.file_structured_template import template
from app.plan_field_text import normalize, MAX_FIELD_BYTES

HUGE = 900719925474099312345678901


def draft():
    schema = shape()
    schema['properties']['amount']['maximum'] = HUGE
    plan = template(json.dumps(schema), ['.txt'])
    plan['nodes'][2]['config']['model'] = copy.deepcopy(MODEL)
    return plan


@pytest.mark.parametrize('transport', ['plan', 'plan_text'])
def test_manual_save_parses_only_explicit_llm_json_field_without_rounding(client, transport):
    task = create(client)
    plan = draft()
    expected = copy.deepcopy(plan)
    plan['nodes'][2]['config']['structured_output'] = json.dumps(expected['nodes'][2]['config']['structured_output'])
    before = copy.deepcopy(plan)
    value = plan if transport == 'plan' else json.dumps(plan)
    response = client.post(f"/api/tasks/{task['id']}/plan", json={'revision': task['revision'], transport: value})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert plan == before and saved['workflow_plan'] == expected
    assert json.loads(saved['plan_text']) == expected and str(HUGE) in saved['plan_text']
    assert main.store.get('task', task['id'])['workflow_plan'] == expected


@pytest.mark.parametrize('raw', [
    '{"schema":{},"schema":{}}', '{"schema":{"type":"object","type":"array"}}',
    '{unfinished-private-raw', '[]', 'null', '{"schema":NaN}', '{"schema":1e999}',
    '{"schema":"\ud800"}', ' ' * (MAX_FIELD_BYTES + 1), '',
], ids=['outer-duplicate','nested-duplicate','unfinished','array','null','nonfinite','overflow','surrogate','size','empty'])
def test_invalid_field_never_partially_saves_or_changes_confirmations(client, raw):
    task = create(client)
    before = copy.deepcopy(main.get_task(task['id']))
    plan = draft()
    plan['nodes'][2]['config']['structured_output'] = raw
    response = client.post(f"/api/tasks/{task['id']}/plan", json={'revision': task['revision'], 'plan_text': json.dumps(plan)})
    assert response.status_code == 422 and 'private-raw' not in response.text
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('container', ['iteration','loop'])
def test_single_layer_container_only_known_llm_field_is_normalized(container):
    node = draft()['nodes'][2]
    expected = copy.deepcopy(node)
    node['config']['structured_output'] = json.dumps(node['config']['structured_output'])
    other = {'id':'custom','type':'code','config':{'structured_output':'{private-untouched','code':'unchanged'}}
    plan = {'nodes':[{'id':'outer','type':container,'config':{'nodes':[node, other], 'private':'unchanged'}}], 'edges':[]}
    before = copy.deepcopy(plan)
    result = normalize(plan)
    assert result['nodes'][0]['config']['nodes'] == [expected, other]
    assert plan == before and result['edges'] == before['edges']


def test_object_values_and_unknown_structures_are_not_reinterpreted():
    plan = draft()
    plan['nodes'].append({'id':'unknown','type':'custom','config':{'nodes':[{'type':'llm','config':{'structured_output':'{bad'}}]}})
    assert normalize(plan) == plan


def test_json_field_parsing_does_not_enable_output_or_relax_schema_rules(client):
    task = create(client)
    before = copy.deepcopy(main.get_task(task['id']))
    for change in ['missing_switch', 'unknown_keyword', 'wrong_wrapper']:
        plan = draft(); cfg = plan['nodes'][2]['config']
        if change == 'missing_switch': cfg.pop('structured_output_enabled')
        if change == 'unknown_keyword': cfg['structured_output']['schema']['private_unknown'] = True
        if change == 'wrong_wrapper': cfg['structured_output']['other'] = 1
        cfg['structured_output'] = json.dumps(cfg['structured_output'])
        response = client.post(f"/api/tasks/{task['id']}/plan", json={'revision':task['revision'],'plan':plan})
        assert response.status_code == 422 and main.get_task(task['id']) == before


def test_normalized_reply_encoding_is_preflighted_before_any_mutation(client, monkeypatch):
    from app import plan_text_codec
    task = create(client); before = copy.deepcopy(main.get_task(task['id'])); plan = draft()
    plan['nodes'][2]['config']['structured_output'] = json.dumps(plan['nodes'][2]['config']['structured_output'])
    def refuse(value):
        assert isinstance(value['nodes'][2]['config']['structured_output'], dict)
        raise ValueError('private-encoding-sentinel')
    monkeypatch.setattr(plan_text_codec, 'render', refuse)
    response = client.post(f"/api/tasks/{task['id']}/plan", json={'revision':task['revision'],'plan':plan})
    assert response.status_code == 422 and 'private-encoding-sentinel' not in response.text
    assert main.get_task(task['id']) == before
