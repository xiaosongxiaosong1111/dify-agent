import copy

import httpx
import pytest

from test_api import client
from app import main
from app.intake import ReviewContractError, base_gaps, topics, validate_review

REQ = {'goal': '将单条文本转成大写，范围仅文本转换。', 'audience': '内部同事使用。', 'input': '单条必填文本 query；空白时提示重新输入。', 'output': '返回 result 字符串，不保存到外部。', 'rules': '去除首尾空白再转大写，不改内部空白。', 'knowledge': '无额外资料或服务，纯文本处理。', 'exceptions': '输入空白返回明确提示；调用失败提示重试，不伪造成功。', 'tests': '输入 abc 输出 ABC；输入空白显示输入错误。'}
SPECIAL_DEFAULT = '本项明确不适用：本次只做文本转换，不包含相关流程。'
POSITIVE_RULES = ['不了解的问题转人工处理。', '不知道答案时请联系人工客服。', '不确定订单号时先追问用户。', '尚未确定的型号交人工核对。', '返回“待定”文字。']


@pytest.fixture(autouse=True)
def forbid_unknown_answers_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('明确占位回归不得访问真实 HTTP 或调用真实模型')

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main.DifyClient, 'request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)


def create(client, rules=None):
    task = client.post('/api/tasks', json={'name': '明确占位任务', 'app_type': 'workflow'}).json()
    assert task['intake_required']
    if rules is not None:
        task = client.patch(f"/api/tasks/{task['id']}", json={'requirements': {**REQ, 'rules': rules}}).json()
    return task


def state(client, task):
    return client.get(f"/api/tasks/{task['id']}/intake").json()


def supplied_answers(client, task):
    current = state(client, task)
    return {row['id']: task['requirements'].get(row['id'], SPECIAL_DEFAULT) for row in current['standard']}


def manual(client, task, answers):
    current = state(client, task)
    return client.post(f"/api/tasks/{task['id']}/intake/manual", json={'revision': task['revision'], 'context_token': current['context_token'], 'answers': answers, 'acknowledge_review': True})


@pytest.mark.parametrize('placeholder', ['不知道', ' 不确定。', '待定？ '])
def test_explicit_unknown_rule_is_gap_and_manual_is_rejected_without_side_effects(client, placeholder):
    task = create(client, placeholder)
    current = state(client, task)
    assert current['state'] == 'needs_input'
    assert 'rules' in {gap['topic'] for gap in current['gaps']}
    assert any(question['topic'] == 'rules' for question in current['questions'])
    assert not current['can_confirm']
    before = client.get(f"/api/tasks/{task['id']}").json()
    ledger = copy.deepcopy(main.budgets.get(task['id']))
    rejected = manual(client, before, supplied_answers(client, before))
    assert rejected.status_code == 422 and '仍有未明确内容' in rejected.text
    assert client.get(f"/api/tasks/{task['id']}").json() == before
    assert before['revision'] == task['revision']
    assert main.budgets.get(task['id']) == ledger
    assert client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': before['revision'], 'kind': 'requirements'}).status_code == 422
    after = client.get(f"/api/tasks/{task['id']}").json()
    assert after['revision'] == task['revision'] and not after['requirements_confirmed']
    assert not after.get('workflow_plan') and not after.get('agent_plan') and not after.get('artifact') and not after['runs'] and not after.get('dify_app_id')
    assert client.get(f"/api/tasks/{task['id']}/artifact").status_code == 404


def task_with_rule(rule):
    return {'app_type': 'workflow', 'revision': 1, 'requirements': {**REQ, 'rules': rule}, 'messages': [], 'materials': []}


def review_for(task, unresolved=None):
    rows = []
    for row in topics(task):
        if row['id'] == unresolved:
            rows.append({'topic': row['id'], 'status': 'needs_input', 'detail': '规则仍是明确占位，需用户给出可执行规则。', 'evidence': []})
        else:
            rows.append({'topic': row['id'], 'status': 'complete', 'detail': '已按当前需求明确。', 'evidence': [{'kind': 'requirement', 'id': row['id'], 'quote': task['requirements'][row['id']]}]})
    return rows


def rule_question():
    return {'topic': 'rules', 'question': '请给出可执行的分类规则，不能只写不知道。', 'recommendation': '请补充规则和例子。', 'reason': '避免把未知占位当作已确认。', 'experience': '补充后再规划。', 'cost': '未发生真实模型费用。', 'manual_work': '需用户回答。'}


def test_complete_model_review_cannot_accept_explicit_unknown_rule():
    task = task_with_rule('不知道')
    with pytest.raises(ReviewContractError, match='不能标记为已明确'):
        validate_review(task, {'schema_version': 1, 'checks': review_for(task), 'questions': []})


def test_needs_input_review_for_explicit_unknown_rule_remains_valid():
    task = task_with_rule('不知道')
    value = {'schema_version': 1, 'checks': review_for(task, 'rules'), 'questions': [rule_question()]}
    assert validate_review(task, value) == value
    gaps = {row['topic'] for row in value['checks'] if row['status'] == 'needs_input'}
    assert gaps == {question['topic'] for question in value['questions']} == {'rules'}


@pytest.mark.parametrize('rule', POSITIVE_RULES)
def test_business_rule_containing_unknown_word_still_saves_and_confirms(client, rule):
    task = create(client, rule)
    current = state(client, task)
    assert current['gaps'] == []
    assert {row['id'] for row in current['standard']} == set(REQ)
    saved = manual(client, task, supplied_answers(client, task))
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    assert saved['revision'] == task['revision'] + 1
    assert state(client, saved)['can_confirm']
    confirmed = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': saved['revision'], 'kind': 'requirements'})
    assert confirmed.status_code == 200, confirmed.text
    confirmed = confirmed.json()
    assert confirmed['requirements_confirmed'] and confirmed['revision'] == saved['revision']
    assert confirmed['confirmations'][-1]['revision'] == saved['revision']
    assert not confirmed['configuration_confirmed']
    assert not confirmed.get('workflow_plan') and not confirmed.get('agent_plan') and not confirmed.get('artifact') and not confirmed['runs'] and not confirmed.get('dify_app_id')


@pytest.mark.parametrize('value', ['不知道', '不清楚', '不确定', '未确定', '待定', '尚未确定', '尚未明确', '未想好', '未提供', ' 不知道？ ', '不清楚。', '未确定．', '待定！', '尚未明确?'])
def test_short_explicit_placeholders_are_recognized(value):
    from app.intake import unknown_placeholder

    assert unknown_placeholder(value)


@pytest.mark.parametrize('value', POSITIVE_RULES + ['无', '没有', '不适用', '待确认：请补充规则', '建议：先按关键词分类', '草案：分类', '', '   '])
def test_business_text_plain_negatives_and_prefixes_are_not_exact_placeholders(value):
    from app.intake import unknown_placeholder

    assert not unknown_placeholder(value)


@pytest.mark.parametrize('rule', ['', '待确认：请用户确认分类', '建议：先按关键词分类', '假设：按退款优先'])
def test_blank_and_legacy_unknown_prefixes_remain_gaps(rule):
    assert 'rules' in {gap['topic'] for gap in base_gaps(task_with_rule(rule))}


def test_plain_negative_answer_is_not_forced_unknown():
    assert base_gaps(task_with_rule('不适用')) == []
