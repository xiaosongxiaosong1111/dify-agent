"""Disposable public synthetic prior shape; never called for live or production data."""
import copy
from uuid import uuid4

from common import require


MESSAGES_MARK = '【公开合成旧访谈形状，不是本次调用或真实生产访谈】'


def _requirements_text(requirements):
    return '\n'.join(key + '：' + value for key, value in requirements.items())


def build_task(now, tid, fixture, provider_id, environment_id):
    requirements = copy.deepcopy(fixture['requirements'])
    configuration = copy.deepcopy(fixture['configuration'])
    configuration['assistant_provider_id'] = provider_id
    cases = copy.deepcopy(fixture['cases'])
    messages = [
        {'role': 'assistant', 'source': 'system', 'content': '你已选择 Chatflow。',
         'created_at': now(), 'context_revision': 1, 'result_revision': 1},
        {'role': 'user', 'content': MESSAGES_MARK + ' 我想做一个售后问答助手。',
         'created_at': now(), 'context_revision': 1, 'synthetic_prior_shape': True},
        {'role': 'assistant', 'source': 'synthetic_prior_shape',
         'content': MESSAGES_MARK + ' 首访只暂拟目标，其余字段尚需明确。',
         'created_at': now(), 'context_revision': 1, 'result_revision': 1,
         'synthetic_prior_shape': True},
        {'role': 'user', 'content': MESSAGES_MARK + ' 完整合成需求：\n' + _requirements_text(requirements),
         'created_at': now(), 'context_revision': 2, 'synthetic_prior_shape': True},
        {'role': 'assistant', 'source': 'synthetic_prior_shape',
         'content': MESSAGES_MARK + ' 八项公开需求、配置和六例已整理，待复核。',
         'created_at': now(), 'context_revision': 2, 'result_revision': 2,
         'synthetic_prior_shape': True},
        {'role': 'assistant', 'source': 'system',
         'content': '公开合成旧访谈前缀；需求已确认、配置未确认；不证明真实模型质量。',
         'created_at': now(), 'context_revision': 2, 'result_revision': 2,
         'synthetic_prior_shape': True},
    ]
    task = {
        'id': tid, 'name': fixture['task_name'], 'app_type': 'advanced-chat', 'revision': 6,
        'status': 'paused', 'intake_required': True, 'plan_review_required': True,
        'requirements_confirmed': True, 'configuration_confirmed': False,
        'environment_id': environment_id, 'requirements': requirements,
        'configuration': configuration, 'messages': messages, 'materials': [],
        'versions': [], 'runs': [], 'artifact': None, 'dify_app_id': None,
        'created_at': now(), 'updated_at': now(), 'test_cases': cases,
        'workflow_plan': None, 'agent_plan': None, 'plan_source': None, 'plan_stale': False,
        'intake_history': [], 'intake_review': None,
        'synthetic_prior_shape': True,
    }
    from app.intake import topics as intake_topics, digest as intake_digest
    mapping = {'memory': 'rules', 'dialogue': 'exceptions', 'retrieval': 'knowledge',
               'external': 'knowledge', 'conversation_state': 'rules'}
    checks = []
    for topic in intake_topics(task):
        source = mapping.get(topic['id'], topic['id'])
        source = source if source in requirements else 'rules'
        checks.append({'topic': topic['id'], 'status': 'complete',
                       'detail': '公开合成旧访谈已覆盖该主题；不代表真实模型质量。',
                       'evidence': [{'kind': 'requirement', 'id': source,
                                     'quote': requirements[source]}]})
    review = {'schema_version': 1, 'checks': checks, 'questions': []}
    task['intake_review'] = {'review': review, 'source': 'model', 'origin_revision': 6,
                             'created_at': now(), 'synthetic_prior_shape': True}
    task['intake_review']['context_digest'] = intake_digest(task)
    task['intake_history'] = [{'review': copy.deepcopy(review), 'source': 'model', 'origin_revision': 5,
                               'created_at': now(), 'synthetic_prior_shape': True}]
    task['versions'] = [{'id': str(uuid4()), 'revision': revision,
                         'label': '公开合成旧版本' + str(revision),
                         'requirements': copy.deepcopy(requirements),
                         'configuration': copy.deepcopy(configuration),
                         'environment_id': environment_id,
                         'materials': [], 'artifact': None, 'workflow_plan': None,
                         'agent_plan': None, 'plan_source': None, 'plan_stale': False,
                         'test_cases': copy.deepcopy(cases), 'dsl_reference': None,
                         'dsl_overlay': None, 'coverage_review': None, 'conflict_review': None,
                         'intake_review': None, 'intake_history': [], 'intake_required': True,
                         'created_at': now(), 'synthetic_prior_shape': True}
                        for revision in range(1, 6)]
    task['planning_runs'] = [{
        'id': str(uuid4()), 'revision': 6, 'provider_id': provider_id,
        'model': fixture.get('provider_model', 'deepseek-flash'), 'status': 'paused',
        'stop_reason': 'needs_decision', 'previous_status': 'paused',
        'message': '公开合成旧原规划 needs_decision；候选未应用。',
        'created_at': now(), 'completed_at': now(), 'attempts': [{
            'status': 'settled', 'cost_basis': 'reported_usage',
            'estimated_cost_usd': '0.0107598', 'reserved_cost_usd': '0.0530871',
            'usage': {'prompt_tokens': 200, 'completion_tokens': 100, 'total_tokens': 300},
        }], 'estimated_cost_usd': '0.0107598',
        'decision_report': {'needs_decision': [{'question': '公开合成旧规划问题'}]},
        'synthetic_prior_shape': True,
    }]
    return task


def build_budget(now, tid, provider):
    def entry(index, kind, reserved, charged):
        return {
            'id': str(uuid4()), 'operation_id': str(uuid4()), 'revision': index,
            'kind': kind, 'provider_id': provider['id'], 'model': provider['model'],
            'pricing': copy.deepcopy(provider['pricing']), 'reserved_usd': reserved,
            'charged_usd': charged, 'status': 'settled', 'call_status': 'returned',
            'cost_basis': 'reported_usage', 'modality': 'text',
            'image_reserve_is_estimate': False,
            'usage': {'prompt_tokens': 100, 'completion_tokens': 100, 'total_tokens': 200},
            'started_at': now(), 'finished_at': now(), 'elapsed_seconds': 1.0,
            'policy_revision': 1, 'synthetic_prior_shape': True,
        }
    return {
        'id': tid, 'policy_revision': 1, 'limit_usd': '0.600', 'created_at': now(),
        'excluded_history_present': False, 'scope': 'since_ledger_start',
        'entries': [
            entry(1, 'interview', '0.017574', '0.0034545'),
            entry(2, 'interview', '0.0232176', '0.005911224'),
            entry(3, 'plan', '0.0530871', '0.0107598'),
        ],
        'policy_history': [{'before': None, 'after': '0.600',
                            'note': '公开合成旧上限；不是真实账单。',
                            'created_at': now(), 'source': 'user'}],
    }


def seed(api, h, fixture, environment, provider):
    """Create 26 protected Tasks plus one clearly synthetic prior-shape Task via normal API."""
    for index in range(26):
        require(api.post('/api/tasks', json={'name': '公开保护Task' + str(index),
                                             'app_type': 'workflow',
                                             'environment_id': environment['id']}).status_code == 201,
                'Protected Task seed failed')
    created = api.post('/api/tasks', json={'name': fixture['task_name'],
                                           'app_type': 'advanced-chat',
                                           'environment_id': environment['id']})
    require(created.status_code == 201, 'Synthetic prior Task creation failed')
    tid = created.json()['id']
    task = build_task(h.now, tid, fixture, provider['id'], environment['id'])
    h.store.put('task', tid, task)
    h.store.put('task_budget', tid, build_budget(h.now, tid, provider))
    return tid
