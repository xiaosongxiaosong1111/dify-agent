import copy
import pytest

from test_delivery_bundle import client, built, bundle, unpack, forbid_api_external_calls
from app import main


def test_bundle_includes_saved_version_changes_and_revision_bound_confirmations(client, monkeypatch):
    task = built(client)
    before = copy.deepcopy(main.get_task(task['id']))
    assert before['versions'] and before['confirmations']
    def forbidden(*args, **kwargs):
        raise AssertionError('History export must not write data or decrypt credentials')
    monkeypatch.setattr(main.store, 'put', forbidden)
    monkeypatch.setattr(main.store, 'secret', forbidden)
    files, manifest = unpack(bundle(client, task))
    report = files[f"report-r{task['revision']}.md"].decode()
    assert '## 版本、修改与确认记录' in report
    assert '保存快照与后续变更' in report and '确认日志' in report
    assert all(row['created_at'] in report for row in before['confirmations'])
    assert main.get_task(task['id']) == before
    assert manifest['platform_checked'] is False and manifest['business_verified'] is False


def test_history_index_compares_only_recorded_fields_and_does_not_export_old_values():
    from app.delivery_history import snapshot, render
    task = {'revision': 3, 'requirements_confirmed': True, 'configuration_confirmed': True,
            'requirements': {'goal': 'current'}, 'configuration': {},
            'versions': [{'id': 'invalid-private-id', 'revision': 1, 'created_at': 'bad-time',
                          'label': 'Bearer PRIVATE-HISTORY-CREDENTIAL', 'requirements': {'goal': 'OLD-PRIVATE-TEXT'}},
                         {'revision': 2, 'requirements': {'goal': 'newer'}}],
            'confirmations': [{'revision': 1, 'kind': 'requirements', 'created_at': '2026-10-30T01:02:03Z'},
                              {'revision': 3, 'kind': 'requirements', 'carried_from_revision': 2}]}
    before = copy.deepcopy(task)
    data = snapshot(task); text = '\n'.join(render(task))
    assert data['version_rows'][0]['changed_sections'] == ['需求']
    assert '配置' in data['version_rows'][0]['unrecorded_sections']
    assert data['version_rows'][0]['id'] is None and data['version_rows'][0]['created_at'] is None
    assert data['confirmation_rows'][0]['matches_current_revision'] is False
    assert data['confirmation_rows'][1]['carried_from_revision'] == 2
    assert '从r2沿用' in text and '配置：所列日志没有当前修订' in text
    assert 'PRIVATE' not in text and 'current' not in text and 'newer' not in text
    assert task == before


@pytest.mark.parametrize('versions,confirmations', [([], []), (None, {}), ([None, {'revision': True}], [None, {'revision': 2, 'kind': 'unrecognized'}])])
def test_absent_or_unreadable_history_is_explicit_not_fabricated(versions, confirmations):
    from app.delivery_history import render
    task = {'revision': 2, 'requirements_confirmed': True, 'configuration_confirmed': True,
            'versions': versions, 'confirmations': confirmations}
    text = '\n'.join(render(task))
    assert '不以当前内容补造旧版本' in text and '没有当前修订的确认记录' in text


def test_limits_keep_counts_and_do_not_make_omitted_records_current():
    from app.delivery_history import snapshot
    task = {'revision': 1000,
            'versions': [{'revision': n} for n in range(1, 151)],
            'confirmations': [{'kind': 'requirements', 'revision': n} for n in range(1, 601)]}
    data = snapshot(task)
    assert data['version_total'] == 150 and data['version_omitted'] == 50
    assert data['confirmation_total'] == 600 and data['confirmation_omitted'] == 100
    assert len(data['version_rows']) == 100 and len(data['confirmation_rows']) == 500
    assert not any(row['matches_current_revision'] for row in data['confirmation_rows'])


@pytest.mark.parametrize('row', [{'kind':'requirements','revision':True},
                               {'kind':[],'revision':3},
                               {'kind':{},'revision':3},
                               {'kind':'requirements','revision':4},
                               {'kind':'requirements','revision':3,'carried_from_revision':3},
                               {'kind':'requirements','revision':3,'carried_from_revision':False}])
def test_invalid_or_future_confirmation_never_claims_explicit_current_confirmation(row):
    from app.delivery_history import snapshot
    data = snapshot({'revision': 3, 'confirmations': [row]})
    assert data['confirmation_rows'] == [] and data['unreadable_confirmations'] == 1
