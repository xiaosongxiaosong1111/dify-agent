import json

import yaml

from test_api import client, forbid_api_external_calls, planning_provider
from test_after_sales_starter import context, inputs
from app import main
from app.after_sales_starter import prepare
from app.intake import BASE


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


def test_empty_chatflow_clarifies_colloquial_order_lookup_and_builds_graph(client, monkeypatch):
    planning_provider(client)
    task = client.post('/api/tasks', json={'name': '隔离售后问答', 'app_type': 'advanced-chat'}).json()
    url = f"/api/tasks/{task['id']}"
    assert task['intake_required'] and not any(task['requirements'].values())
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
    assert calls == ['interview', 'interview', 'plan']
