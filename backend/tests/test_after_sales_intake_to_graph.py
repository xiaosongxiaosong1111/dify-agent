import copy
import json
from uuid import uuid4

import pytest
import yaml

from test_api import client, create_env, forbid_api_external_calls, planning_provider
from test_after_sales_starter import context, inputs
from test_delivery_bundle import bundle, unpack
from test_workflow_publication import confirm as confirm_publish, prepare as prepare_publish
from app import main
from app.after_sales_starter import prepare
from app.intake import BASE
from app.mock_order import PREFIX


OPENING = '我想做一个售后问答助手'
REQUIREMENTS = {
    'goal': '服务售后常见问题，也能帮顾客查订单。',
    'audience': '面向已购买商品的顾客。',
    'input': '文本咨询。查订单时需要订单号，没有就追问。',
    'output': '返回一条中文回复。',
    'rules': '区分资料咨询和查订单；查订单只查模拟记录。问答模型不接收历史轮次。会话状态只记本会话是否在等待补号，补号后消费等待标记，不跨会话。',
    'knowledge': '使用合成知识库 existing-faq，只按检索到的资料答复。模拟记录 DEMO-001 为已发货。',
    'exceptions': '不开场白，不设建议问题。无命中回复「知识库暂无相关信息，请联系人工客服。」；缺号回复「请提供订单号。」；意图不清回复「请明确咨询资料还是查订单。」',
    'tests': '命中按资料回答；无命中提示人工；缺号时追问，同一会话补 DEMO-001 后返回模拟发货记录。',
}

FAQ_ANSWER = '公开退货政策：签收七天内且未拆封可退货。'
ORDER_ANSWER = PREFIX + '合成样例：已发货。'


def acceptance_cases():
    def turn(query, answer, mode='equals'):
        return {'input': {'query': query}, 'expectation': {'mode': mode, 'target': 'answer', 'expected': answer}}
    def case(case_id, query, answer, mode='equals'):
        return {'id': case_id, 'name': case_id, **turn(query, answer, mode)}
    order = case('missing-order', '查订单', inputs()['missing_order_reply'])
    order['followups'] = [turn('DEMO-001', ORDER_ANSWER)]
    return [case('faq', '退货政策是什么？', FAQ_ANSWER), case('no-hit', '有没有维修资料？', '相关', 'contains'), order]


@pytest.fixture
def original_chatflow(client, monkeypatch, request):
    planning_provider(client)
    env_id = create_env(client)['id'] if getattr(request, 'param', False) else None
    task = client.post('/api/tasks', json={'name': '隔离售后问答', 'app_type': 'advanced-chat', 'environment_id': env_id}).json()
    url = f"/api/tasks/{task['id']}"
    assert task['intake_required'] and not any(task['requirements'].values())
    if env_id:
        response = client.post(f'{url}/test-cases', json={'revision': task['revision'], 'cases': acceptance_cases()})
        assert response.status_code == 200, response.text
        task = response.json()
    requirements = REQUIREMENTS
    answer = '\n'.join(requirements.values())
    cfg = context()['configuration']
    cases = inputs() | {'clarify_reply': '请明确咨询资料还是查订单。'}
    expected = set(BASE) | {'memory', 'dialogue', 'retrieval', 'external', 'conversation_state'}
    calls = []

    async def model(provider, key, messages, **kwargs):
        prompt = messages[1]['content']
        if prompt.startswith('当前任务资料：'):
            data = json.loads(prompt.removeprefix('当前任务资料：'))
            if len(calls) == 0:
                assert OPENING in messages[-1]['content'] and not any(data['requirements'].values())
                rows = [{'topic': key, 'status': 'needs_input', 'detail': '尚需明确', 'evidence': []}
                        for key in (*BASE, 'memory', 'dialogue')]
                question = {'topic': 'goal', 'question': '售后助手要处理哪些问题，还需要查订单吗？',
                            'recommendation': '先说明资料与订单范围。', 'reason': '明确需覆盖的分支。',
                            'experience': '先确认范围再出图。', 'cost': '资源费用后续核对。', 'manual_work': '请补充规则。'}
                result = {'message': question['question'], 'requirements_patch': {},
                          'intake_review': {'schema_version': 1, 'checks': rows, 'questions': [question]}}
            else:
                assert answer in messages[-1]['content']
                source = next(x for x in data['intake_sources'] if x['kind'] == 'message' and x['text'] == answer)
                special = {'memory': 'rules', 'dialogue': 'exceptions', 'retrieval': 'knowledge',
                           'external': 'rules', 'conversation_state': 'rules'}
                rows = [{'topic': key, 'status': 'complete', 'detail': '用户已补充规则。',
                         'evidence': [{'kind': 'message', 'id': source['id'],
                                       'quote': requirements[special.get(key, key)]}]} for key in sorted(expected)]
                result = {'message': '售后范围和模拟条件已记录，请核对确认。', 'requirements_patch': requirements,
                          'intake_review': {'schema_version': 1, 'checks': rows, 'questions': []}}
            calls.append('interview')
        else:
            data = json.loads(prompt)
            assert calls == ['interview', 'interview']
            assert data['requirements'] == requirements and data['intake_assessment']['can_confirm']
            assert data['existing_plan_context'] is None
            # Deterministic fixture for the planner response. The API still validates and saves it.
            result = json.loads(prepare(main.get_task(task['id']), cases)[0])
            calls.append('plan')
        return json.dumps(result, ensure_ascii=False), {'prompt_tokens': 100, 'completion_tokens': 30}

    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f'{url}/messages', json={'revision': task['revision'], 'content': OPENING})
    assert response.status_code == 200, response.text
    task = response.json()
    intake = client.get(f'{url}/intake').json()
    assert intake['questions'][0]['topic'] == 'goal' and not intake['can_confirm']
    assert not task['workflow_plan'] and not task['artifact']
    assert client.post(f'{url}/plan/generate', json={'revision': task['revision']}).status_code == 422
    assert calls == ['interview']

    response = client.post(f'{url}/messages', json={'revision': task['revision'], 'content': answer})
    assert response.status_code == 200, response.text
    task = response.json()
    intake = client.get(f'{url}/intake').json()
    assert intake['can_confirm'], task['messages'][-1]['content']
    assert {row['id'] for row in intake['standard']} == expected
    assert task['requirements'] == requirements and not task['workflow_plan']

    response = client.patch(url, json={'configuration': cfg, 'expected_revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()
    for endpoint, body in [('confirm', {'kind': 'requirements'}), ('plan/generate', {}),
                           ('confirm', {'kind': 'configuration'}), ('build', {})]:
        response = client.post(f'{url}/{endpoint}', json={'revision': task['revision'], **body})
        assert response.status_code == 200, response.text
        task = response.json()

    assert calls == ['interview', 'interview', 'plan']
    return task


def test_empty_chatflow_clarifies_colloquial_order_lookup_and_builds_graph(client, original_chatflow):
    task = original_chatflow
    url = f"/api/tasks/{task['id']}"
    document = yaml.safe_load(client.get(f'{url}/dsl').json()['content'])
    graph = document['workflow']['graph']
    assert document['app']['mode'] == 'advanced-chat'
    nodes = {node['id']: node['data'] for node in graph['nodes']}
    edges = {(edge['source'], edge['sourceHandle'], edge['target']) for edge in graph['edges']}
    assert {('intent', 'faq', 'retrieve'), ('intent', 'order', 'extract_order'),
            ('check_hit', 'false', 'no_hit'), ('request_order_wait', 'source', 'missing_order'),
            ('check_order_value', 'has_order', 'order_lookup')} <= edges
    assert '【模拟订单查询，非真实订单】' in nodes['order_lookup']['code']
    assert len(graph['nodes']) == 23 and len(graph['edges']) == 24
    assert task['artifact']['validation']['valid'] and task['artifact']['revision'] == task['revision']
    assert not task['dify_app_id'] and not task['runs']


def checked_delivery(client, task, reply):
    revision = task['revision']
    response = bundle(client, task)
    files, manifest = unpack(response)
    assert response.headers['x-sierra-revision'] == str(revision)
    assert f"r{revision}-delivery.zip" in response.headers['content-disposition']
    assert (manifest['task_id'], manifest['revision'], manifest['app_type']) == (task['id'], revision, 'advanced-chat')
    assert manifest['app_id'] == task['dify_app_id'] and manifest['environment_id'] == task['environment_id']
    assert manifest['artifact_verification'] == 'static_only'
    assert manifest['mock_dependencies'] == task['configuration']['mock_dependencies']
    assert all(manifest[field] is False for field in ('platform_checked', 'business_verified', 'network_requested', 'task_changed'))
    name = f'dify-advanced-chat-r{revision}.yaml'
    assert manifest['files'][name]['sha256'] == task['artifact']['sha256']
    report = files[f'report-r{revision}.md'].decode()
    assert f"类型：advanced-chat；版本：r{revision}" in report
    assert f"- exceptions：{task['requirements']['exceptions']}" in report
    if task['dify_app_id']:
        assert f"当前应用标识：{task['dify_app_id']}" in report
        assert '成功运行返回 3 次，已声明必选样例 3 / 3 通过' in report
        current_cases = report.split('## 当前修订的样例汇总', 1)[1].split('```json\n', 1)[1].split('\n```', 1)[0]
        assert json.loads(current_cases) == client.get(f"/api/tasks/{task['id']}/acceptance").json()
    graph = yaml.safe_load(files[name])['workflow']['graph']
    nodes = {node['id']: node['data'] for node in graph['nodes']}
    assert nodes['no_hit']['template'] == reply
    assert any(reply in part['text'] for part in nodes['grounded_answer']['prompt_template'])
    return files[name], manifest


def run_with_substitute_platform(client, monkeypatch, task, no_hit_reply):
    url = f"/api/tasks/{task['id']}"
    revision = {'revision': task['revision']}
    app_id = str(uuid4())
    publish_path = f'/console/api/apps/{app_id}/workflows/publish'
    root = yaml.safe_load(main.artifact_path(task).read_bytes())
    draft = root['workflow'] | {'hash': 'fixture-draft'}
    published = None
    turns = []
    replies = [FAQ_ANSWER, no_hit_reply, inputs()['missing_order_reply'], ORDER_ANSWER]
    queries = [case['input']['query'] for case in task['test_cases']] + ['DEMO-001']

    async def request(self, method, path, *, credential, **kwargs):
        nonlocal published
        assert self.env['id'] == task['environment_id']
        if path == '/console/api/apps/imports':
            assert (method, credential) == ('POST', 'console_token')
            assert yaml.safe_load(kwargs['json']['yaml_content']) == root
            return {'status': 'completed', 'app_id': app_id}
        if path == '/v1/chat-messages':
            assert (method, credential) == ('POST', 'service_api_key')
            assert published and self.env['service_app_id'] == app_id
            index = len(turns)
            body = kwargs['json']
            cid = f"{app_id}-order" if index >= 2 else f"{app_id}-{index}"
            assert body['query'] == queries[index] and body['inputs'] == {}
            assert body.get('conversation_id') == (cid if index == 3 else None)
            turns.append(body['query'])
            return {'answer': replies[index], 'conversation_id': cid}
        assert credential == 'console_token'
        if path == publish_path:
            if method == 'POST':
                assert published is None
                published = draft | {'id': str(uuid4())}
                return {'result': 'success'}
            assert method == 'GET'
            return published
        assert method == 'GET'
        if path == f'/console/api/apps/{app_id}/workflows/draft':
            return draft
        assert path == f'/console/api/apps/{app_id}'
        return {'id': app_id, 'mode': 'advanced-chat'}

    monkeypatch.setattr(main.DifyClient, 'request', request)
    imported = client.post(f'{url}/import', json=revision)
    assert imported.status_code == 200, imported.text
    current = imported.json()
    assert current['dify_app_id'] == app_id
    proposal = prepare_publish(client, current)
    assert proposal.status_code == 200, proposal.text
    result = confirm_publish(client, current, proposal.json())
    assert result.status_code == 200 and result.json()['state'] == 'succeeded', result.text
    assert client.patch(f"/api/environments/{task['environment_id']}", json={
        'service_app_id': app_id, 'service_api_key': 'isolated-runtime-key',
    }).status_code == 200
    accepted = client.get(f'{url}/acceptance').json()
    assert accepted['required']['not_run'] == 3 and all(row['run_id'] is None for row in accepted['cases'])

    run_ids = []
    for case, reply in zip(task['test_cases'], replies[:3], strict=True):
        run_response = client.post(f'{url}/run', json={**revision, 'case_id': case['id']})
        assert run_response.status_code == 200, run_response.text
        current = run_response.json()
        run = current['runs'][-1]
        assert (run['app_id'], run['revision'], run['environment_id']) == (app_id, task['revision'], task['environment_id'])
        assert run['evaluation']['status'] == 'passed'
        result = run['result']['turns'][0]['result'] if case.get('followups') else run['result']
        assert result['answer'] == reply
        run_ids.append(run['id'])

    accepted = client.get(f'{url}/acceptance').json()
    assert accepted['required']['passed'] == 3 and [row['run_id'] for row in accepted['cases']] == run_ids
    assert turns == queries
    return current


@pytest.mark.parametrize('original_chatflow', [False, True], indirect=True, ids=['static', 'with-runtime'])
def test_natural_language_edit_preserves_original_and_binds_both_delivery_bundles(client, monkeypatch, original_chatflow):
    original = original_chatflow
    url = f"/api/tasks/{original['id']}"
    old_reply = inputs()['no_hit_reply']
    new_reply = '暂未找到与问题相关的资料，请提交售后工单。'
    request = f'请把无命中和资料不足的固定回复都改成「{new_reply}」。其余规则和分支保持。'
    if original['environment_id']:
        original = run_with_substitute_platform(client, monkeypatch, original, old_reply)
    original_dsl, original_manifest = checked_delivery(client, original, old_reply)
    old_plan = original['workflow_plan']
    new_plan = copy.deepcopy(old_plan)
    nodes = {node['id']: node for node in new_plan['nodes']}
    nodes['no_hit']['config']['template'] = new_reply
    config = nodes['grounded_answer']['config']
    assert old_reply in config['system_prompt']
    config['system_prompt'] = config['system_prompt'].replace(old_reply, new_reply)
    exceptions = original['requirements']['exceptions'].replace(old_reply, new_reply)
    calls = []

    async def model(provider, key, messages, **kwargs):
        prompt = messages[1]['content']
        if prompt.startswith('当前任务资料：'):
            context = json.loads(prompt.removeprefix('当前任务资料：'))
            source = next(row for row in context['intake_sources'] if row['kind'] == 'message' and row['text'] == request)
            review = copy.deepcopy(context['previous_intake'])
            for row in review['checks']:
                if row['topic'] in {'exceptions', 'dialogue'}:
                    row['evidence'] = [{'kind': 'message', 'id': source['id'], 'quote': new_reply}]
            result = {'message': '已记录新回复，其余规则保持，请复核。', 'requirements_patch': {'exceptions': exceptions},
                      'intake_review': review}
            calls.append('interview')
        else:
            context = json.loads(prompt)
            baseline = context['existing_plan_context']
            assert baseline['plan'] == old_plan and baseline['baseline_revision'] == original['revision']
            assert baseline['changed_requirements_fields'] == ['exceptions']
            assert context['requirements'] == {**original['requirements'], 'exceptions': exceptions}
            result = new_plan
            calls.append('plan')
        return json.dumps(result, ensure_ascii=False), {'prompt_tokens': 100, 'completion_tokens': 30}

    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f'{url}/messages', json={'revision': original['revision'], 'content': request})
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft['revision'] == original['revision'] + 1 and draft['workflow_plan'] == old_plan
    assert draft['requirements']['exceptions'] == exceptions
    assert draft['plan_stale'] and not draft['artifact']
    assert not draft['requirements_confirmed'] and not draft['configuration_confirmed']
    assert bundle(client, original).status_code == 409 and bundle(client, draft).status_code == 422

    revision = {'revision': draft['revision']}
    response = client.post(f'{url}/confirm', json={**revision, 'kind': 'requirements'})
    assert response.status_code == 200, response.text
    assert client.post(f'{url}/confirm', json={**revision, 'kind': 'configuration'}).status_code == 422
    assert client.post(f'{url}/plan/generate', json=revision).status_code == 422
    pending = client.get(url).json()
    run = pending['planning_runs'][-1]
    assert run['stop_reason'] == 'replanning_review' and pending['workflow_plan'] == old_plan
    retained = client.get(f"{url}/planning/{run['id']}/candidate").json()
    assert json.loads(retained['plan_text']) == new_plan and not retained['formal_plan_changed']

    response = client.post(f'{url}/plan', json={**revision, 'plan_text': retained['plan_text']})
    assert response.status_code == 200, response.text
    revised = response.json()
    assert revised['workflow_plan'] == new_plan and not revised['plan_stale']
    assert revised['revision'] == draft['revision'] + 1 and revised['requirements_confirmed']
    assert not revised['configuration_confirmed'] and bundle(client, revised).status_code == 422
    revision = {'revision': revised['revision']}
    assert client.post(f'{url}/build', json=revision).status_code == 422
    response = client.post(f'{url}/confirm', json={**revision, 'kind': 'configuration'})
    assert response.status_code == 200, response.text
    response = client.post(f'{url}/build', json=revision)
    assert response.status_code == 200, response.text
    revised = response.json()

    assert not revised['dify_app_id'] and revised['runs'] == original['runs']
    if revised['environment_id']:
        revised = run_with_substitute_platform(client, monkeypatch, revised, new_reply)
        assert revised['dify_app_id'] != original['dify_app_id']
        assert revised['runs'][:len(original['runs'])] == original['runs']
    revised_dsl, revised_manifest = checked_delivery(client, revised, new_reply)
    assert revised_dsl != original_dsl and revised_manifest['revision'] > original_manifest['revision']
    assert main.artifact_path(original).read_bytes() == original_dsl
    assert any(saved['revision'] == original['revision'] and saved['workflow_plan'] == old_plan
               and saved['requirements'] == original['requirements']
               and saved['artifact'] == original['artifact'] for saved in revised['versions'])
    confirmations = {(row['kind'], row['revision'], row.get('carried_from_revision')) for row in revised['confirmations']}
    assert {('configuration', original['revision'], None), ('requirements', draft['revision'], None),
            ('requirements', revised['revision'], draft['revision']),
            ('configuration', revised['revision'], None)} <= confirmations
    assert bundle(client, original).status_code == 409
    assert calls == ['interview', 'plan']
