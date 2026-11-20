import copy

import httpx
import pytest

from test_api import client, create
from app import main

REQ = {'goal': '将单条文本转成大写，范围仅文本转换。', 'audience': '内部同事使用。', 'input': '单条必填文本 query；空白时提示重新输入。', 'output': '返回 result 字符串，不保存到外部。', 'rules': '去除首尾空白再转大写，不改内部空白。', 'knowledge': '无额外资料或服务，纯文本处理。', 'exceptions': '输入空白返回明确提示；调用失败提示重试，不伪造成功。', 'tests': '输入 abc 输出 ABC；输入空白显示输入错误。'}


@pytest.fixture(autouse=True)
def forbid_confirmation_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('旧任务确认回归不得访问真实 HTTP 或调用真实模型')

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main.DifyClient, 'request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def legacy(client, mode):
    task = create(client)
    if mode == 'missing':
        stored = main.get_task(task['id'])
        stored.pop('intake_required', None)
        main.save_task(stored)
        task = main.get_task(task['id'])
        assert 'intake_required' not in task
    else:
        task = main.get_task(task['id'])
        assert task['intake_required'] is False
    assert not main.budgets.get(task['id'])['entries']
    return task


def fill(client, task, rules):
    response = client.patch(f"/api/tasks/{task['id']}", json={'requirements': {**REQ, 'rules': rules}})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('mode', ['missing', 'false'])
@pytest.mark.parametrize('placeholder', [' 不知道。', '待定？'])
def test_legacy_confirmation_rejects_explicit_unknown_and_stays_unchanged(client, mode, placeholder):
    task = legacy(client, mode)
    task = fill(client, task, placeholder)
    current = client.get(f"/api/tasks/{task['id']}/intake").json()
    assert current['can_confirm'] is False and 'rules' in {gap['topic'] for gap in current['gaps']}
    before = client.get(f"/api/tasks/{task['id']}").json()
    ledger = copy.deepcopy(main.budgets.get(task['id']))
    rejected = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': before['revision'], 'kind': 'requirements'})
    assert rejected.status_code == 422, rejected.text
    assert '缺失字段：rules' in rejected.text
    assert '不知道' not in rejected.text and '待定' not in rejected.text
    assert client.get(f"/api/tasks/{task['id']}").json() == before
    assert before['revision'] == task['revision'] and not before['requirements_confirmed']
    assert main.budgets.get(task['id']) == ledger and not ledger['entries']
    assert not before.get('workflow_plan') and not before.get('agent_plan') and not before.get('artifact') and not before['runs'] and not before.get('dify_app_id')
    assert client.get(f"/api/tasks/{task['id']}/artifact").status_code == 404
    patched = client.patch(f"/api/tasks/{task['id']}", json={'requirements': {'rules': '不了解的问题转人工处理。'}})
    assert patched.status_code == 200, patched.text
    saved = patched.json()
    assert saved['revision'] == before['revision'] + 1
    confirmed = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': saved['revision'], 'kind': 'requirements'})
    assert confirmed.status_code == 200, confirmed.text
    confirmed = confirmed.json()
    assert confirmed['requirements_confirmed'] and not confirmed['configuration_confirmed']
    assert confirmed.get('intake_required') in (None, False)
    assert not confirmed.get('intake_review') and not confirmed.get('interview_attempts')
    assert confirmed['confirmations'][-1]['revision'] == saved['revision']


@pytest.mark.parametrize('rule', ['不知道答案时请联系人工客服。', '不确定订单号时先追问。'])
def test_legacy_confirmation_accepts_business_sentence_with_unknown_word(client, rule):
    task = legacy(client, 'false')
    task = fill(client, task, rule)
    current = client.get(f"/api/tasks/{task['id']}/intake").json()
    assert current['can_confirm'] is True and current['gaps'] == []
    confirmed = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': task['revision'], 'kind': 'requirements'})
    assert confirmed.status_code == 200, confirmed.text
    confirmed = confirmed.json()
    assert confirmed['requirements_confirmed'] and not confirmed['configuration_confirmed']
    assert confirmed['intake_required'] is False
    assert not confirmed.get('intake_review') and not confirmed.get('interview_attempts')
    assert confirmed['confirmations'][-1]['revision'] == task['revision']
