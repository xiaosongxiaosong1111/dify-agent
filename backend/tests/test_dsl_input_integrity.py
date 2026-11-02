"""Unreadable or uninspectable DSL must not become a saved source reference."""
import copy
import pytest
import yaml
from fastapi.testclient import TestClient
from test_api import client
from test_dsl_roundtrip import prepared, forbid_external_calls
from app import main
from app.dsl_roundtrip import load_document


BAD_VARIABLES = [None, True, 7, 'PRIVATE-VARIABLE', {},
    {'hidden': {'value_type': 'secret', 'value': 'PRIVATE-VALUE'}}, ['PRIVATE-ROW'], [None]]


def submit(client, task, root, route):
    return client.post(f"/api/tasks/{task['id']}/{route}", json={
        'revision': task['revision'], 'filename': '公开当前.yaml',
        'content': yaml.safe_dump(root, allow_unicode=True)})


@pytest.mark.parametrize('route', ['dsl-reference', 'reference-dsl/preview'])
@pytest.mark.parametrize('variables', BAD_VARIABLES)
def test_uninspectable_environment_variables_rejected_without_persistence(client, variables, route):
    task, root = prepared(client)
    root['workflow']['environment_variables'] = variables
    before = copy.deepcopy(main.get_task(task['id']))
    with main.store.connect() as db:
        records = db.execute('SELECT kind,id,value FROM objects ORDER BY kind,id').fetchall()
    with TestClient(main.app, raise_server_exceptions=False) as safe:
        response = submit(safe, task, root, route)
    assert response.status_code == 422, response.text
    assert 'PRIVATE' not in response.text
    assert main.get_task(task['id']) == before
    with main.store.connect() as db:
        assert db.execute('SELECT kind,id,value FROM objects ORDER BY kind,id').fetchall() == records


@pytest.mark.parametrize('route', ['dsl-reference', 'reference-dsl/preview'])
@pytest.mark.parametrize('value', [None, False, 0, [], {}])
def test_secret_variable_must_be_explicitly_empty_string_even_without_http_auth(client, route, value):
    task, root = prepared(client)
    root['workflow']['environment_variables'] = [{'name': 'public_secret', 'value_type': 'secret', 'value': value}]
    before = copy.deepcopy(main.get_task(task['id']))
    response = submit(client, task, root, route)
    assert response.status_code == 422, response.text
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('route', ['dsl-reference', 'reference-dsl/preview'])
@pytest.mark.parametrize('location', ['key', 'value'])
def test_yaml_escaped_invalid_unicode_rejected_before_a_reference_is_saved(client, route, location):
    task, root = prepared(client)
    if location == 'key':
        root['PRIVATE\ud800'] = 'public'
    else:
        root['app']['name'] = 'PRIVATE\ud800'
    text = yaml.safe_dump(root, allow_unicode=False)
    assert '\\uD800' in text or '\\ud800' in text
    before = copy.deepcopy(main.get_task(task['id']))
    with TestClient(main.app, raise_server_exceptions=False) as safe:
        response = safe.post(f"/api/tasks/{task['id']}/{route}", json={
            'revision': task['revision'], 'filename': '公开当前.yaml', 'content': text})
    assert response.status_code == 422, response.text
    assert '编码' in response.text and 'PRIVATE' not in response.text
    assert main.get_task(task['id']) == before


def test_raw_invalid_unicode_has_fixed_chinese_error_without_decoder_echo():
    with pytest.raises(ValueError) as exc:
        load_document('PRIVATE\ud800')
    assert '编码' in str(exc.value) and 'PRIVATE' not in str(exc.value)


@pytest.mark.parametrize('route', ['dsl-reference', 'reference-dsl/preview'])
def test_valid_environment_variables_and_unknown_metadata_are_preserved(client, route):
    task, root = prepared(client)
    variables = [{'name': f'public_{i}', 'value_type': 'string', 'value': f'保留文字{i}',
                  'legacy_note': {'keep': True}} for i in range(101)]
    variables.append({'name': 'public_secret', 'value_type': 'secret', 'value': ''})
    root['workflow']['environment_variables'] = variables
    root['app']['description'] = '原样保留 😀 与汉字'
    assert load_document(yaml.safe_dump(root, allow_unicode=True)) == root
    response = submit(client, task, root, route)
    assert response.status_code == 200, response.text
    if route == 'dsl-reference':
        reference_id = main.get_task(task['id'])['dsl_reference']['id']
        saved = main.store.get('dsl_reference', reference_id)
        assert saved['current'] == root
    else:
        assert main.get_task(task['id']) == task
