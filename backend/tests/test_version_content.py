import copy
import hashlib
import json
from uuid import uuid4

import httpx
import pytest
from test_api import client, approved, code_only_plan
from app import main
from app.version_restore import token


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail('History reading must not call models or HTTP')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def seeded(client):
    task = approved(client)
    task['workflow_plan'] = code_only_plan()
    task['requirements']['rules'] = '旧政策与原提示🙂' * 1300
    task['configuration']['max_tokens'] = 9007199254740993
    task['test_cases'] = []
    main.snapshot(task, '待核对旧版')
    version = copy.deepcopy(task['versions'][-1])
    task['versions'] = [version]
    task['requirements']['rules'] = '当前新版政策保持'
    main.store.put('task', task['id'], task)
    return task, version


def read(client, task, version, **params):
    source_token = params.pop('snapshot_token', None)
    if source_token is None: source_token = token(task, version)
    return client.get(f"/api/tasks/{task['id']}/versions/{version['id']}/content", params={
        'revision': task['revision'], 'section': 'requirements',
        'snapshot_token': source_token, **params})


def test_pages_reconstruct_exact_saved_json_without_writes_secrets_or_external(client, monkeypatch):
    task, version = seeded(client)
    before = copy.deepcopy(main.get_task(task['id']))
    ledger = copy.deepcopy(main.store.get('task_budget', task['id']))
    def forbidden(*a, **kw):
        pytest.fail('History reading must not write/decrypt')
    monkeypatch.setattr(main.store, 'put', forbidden)
    monkeypatch.setattr(main.store, 'secret', forbidden)
    chunks = []; offset = 0; source_hash = None
    while offset is not None:
        response = read(client, task, version, offset=offset)
        assert response.status_code == 200, response.text
        v = response.json()
        assert v['offset'] == offset and v['page_sha256'] == hashlib.sha256(v['text'].encode()).hexdigest()
        assert v['snapshot_token'] == token(task, version)
        assert len(v['text']) <= 4000
        if source_hash is None: source_hash = v['content_sha256']
        assert v['content_sha256'] == source_hash
        assert v['source_kind'] == 'historical_saved_value_json'
        assert all(v[k] is False for k in ['task_changed', 'network_requested', 'platform_checked', 'business_verified'])
        chunks.append(v['text']); offset = v['next_offset']
    text = ''.join(chunks)
    assert text == json.dumps(version['requirements'], ensure_ascii=False, indent=2, allow_nan=False)
    assert json.loads(text) == version['requirements']
    assert hashlib.sha256(text.encode()).hexdigest() == source_hash
    assert main.get_task(task['id']) == before and main.store.get('task_budget', task['id']) == ledger


@pytest.mark.parametrize('section', ['configuration', 'workflow_plan', 'agent_plan', 'test_cases'])
def test_selected_values_only_preserve_null_and_exact_large_numbers(client, section):
    task, version = seeded(client)
    v = read(client, task, version, section=section).json()
    assert json.loads(v['text']) == version[section]
    if section == 'configuration': assert '9007199254740993' in v['text']
    assert '当前新版政策' not in v['text'] and 'messages' not in v


@pytest.mark.parametrize('change', ['revision', 'current', 'confirm', 'historical', 'other_task'])
def test_stale_or_cross_task_token_rejected_without_partial_body(client, change):
    task, version = seeded(client); source_token = token(task, version)
    if change == 'revision': task['revision'] += 1
    elif change == 'current': task['configuration']['temperature'] = .8
    elif change == 'confirm': task['configuration_confirmed'] = not task['configuration_confirmed']
    elif change == 'historical': task['versions'][0]['requirements']['rules'] = 'SENSITIVE-CHANGED-HISTORY'
    else:
        other = approved(client); other['versions'] = [version]; task = other
    main.store.put('task', task['id'], task)
    response = read(client, task, version, snapshot_token=source_token)
    assert response.status_code == 409
    assert 'SENSITIVE' not in response.text and 'text' not in response.json()


@pytest.mark.parametrize('params', [
    {'section': 'materials'}, {'section': 'secrets'}, {'limit': 4001}, {'limit': 0},
    {'offset': -1}, {'offset': 2_000_000}, {'snapshot_token': 'PRIVATE-BAD'},
    {'revision': 'PRIVATE-BAD'}, {'version_id': 'PRIVATE-BAD'},
])
def test_bad_range_or_source_parameters_are_bounded_and_do_not_echo(client, params):
    task, version = seeded(client)
    if 'version_id' in params:
        version['id'] = params.pop('version_id')
    response = read(client, task, version, **params)
    assert response.status_code in (404, 422)
    assert 'PRIVATE' not in response.text and '旧政策' not in response.text


@pytest.mark.parametrize('value', [
    {'password': 'PRIVATE-SECRET'}, {'rules': 'Bearer SECRET_TOKEN_VALUE_123456'},
    {'rules': 'app-' + 'x' * 24}, {'rules': '\\u0070assword="PRIVATE-SECRET"'},
    {'rules': '字' * 700000}, {'rules': '\ud800'}, {'rules': float('inf')},
])
def test_whole_selected_section_checked_before_returning_any_page(client, monkeypatch, value):
    task, version = seeded(client)
    source_token = token(task, version)
    # In-memory fixture may contain invalid historical JSON; the endpoint must fail closed.
    version['requirements'] = value; task['versions'] = [version]
    if any(isinstance(x, float) for x in value.values()) or value.get('rules') == '\ud800':
        monkeypatch.setattr(main, 'get_task', lambda _: copy.deepcopy(task))
        response = read(client, task, version, snapshot_token=source_token, limit=1)
        assert response.status_code == 422 and 'text' not in response.json()
        return
    main.store.put('task', task['id'], task)
    response = read(client, task, version, limit=1)
    assert response.status_code == 422 and 'PRIVATE' not in response.text
    assert 'text' not in response.json()


def test_missing_historical_field_is_not_filled_from_current_and_busy_read_is_allowed(client):
    task, version = seeded(client)
    version.pop('agent_plan'); task['versions'] = [version]; task['status'] = 'running'
    main.store.put('task', task['id'], task)
    assert read(client, task, version, section='agent_plan').status_code == 404
    assert read(client, task, version, section='test_cases').status_code == 200


def test_duplicate_history_identity_is_not_selected_arbitrarily(client):
    task, version = seeded(client); task['versions'].append(copy.deepcopy(version))
    main.store.put('task', task['id'], task)
    assert read(client, task, version).status_code == 404


@pytest.mark.parametrize('revision', [0, -1, True, 'legacy', None])
def test_legacy_unknown_revision_is_not_fabricated_as_a_number(client, revision):
    task, version = seeded(client); version['revision'] = revision; task['versions'] = [version]
    main.store.put('task', task['id'], task)
    response = read(client, task, version)
    assert response.status_code == 200 and response.json()['historical_revision'] is None
