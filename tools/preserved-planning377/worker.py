"""One normal POST /plan/generate; save the complete model candidate and exit.

Public modes use a synthetic prior shape and a fake transport.  Live mode is
only reachable through tool.py's canonical, approval and once-only gates.
"""
import copy
import hashlib
import json
import os
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from common import (BATCH, CASES, CONFIGURATION, INPUTS, PER_CALL_USD,
                    PROJECT, PUBLIC_ENV, PUBLIC_KEY, PUBLIC_PROVIDER, PUBLIC_TASK,
                    REQUIREMENTS, ReadOnly, SETTINGS, TARGET_REVISION, capture,
                    digest, money, require, sha_bytes)

STAGES = ('original',)
PUBLIC_ENV_OBJECT = {'id': PUBLIC_ENV, 'name': '公开替身连接',
                     'base_url': 'https://public-dify.invalid', 'version': '1.17.1',
                     'console_workspace_id': '00000000-0000-4000-8000-000000000380'}
PUBLIC_PROVIDER_OBJECT = {'id': PUBLIC_PROVIDER, 'name': '公开替身主模型', 'role': 'main',
                          'provider': 'deepseek', 'protocol': 'openai-compatible',
                          'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash',
                          'pricing': {'input_per_million_usd': .3,
                                      'cached_input_per_million_usd': .006,
                                      'output_per_million_usd': 1.2}}
KNOWN_USAGE = {'prompt_tokens': 200, 'completion_tokens': 300, 'total_tokens': 500}


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def forbidden_sync(*args, **kwargs):
    raise RuntimeError('Synchronous/other HTTP is forbidden')


class Boundary:
    def __init__(self, provider, key, record, save, stop_path, live):
        self.provider = provider
        self.key = key
        self.record = record
        self.save = save
        self.stop_path = Path(stop_path)
        self.live = live
        self.phase = None
        self.started = time.monotonic()
        self.halted = False
        self.calls = {stage: 0 for stage in STAGES}
        self.quotes = {}
        self.in_call = False
        self.armed = False
        self.message_sha = None

    def begin(self):
        require(not self.halted and self.phase is None and not self.in_call,
                'Model stage unavailable or already used')
        self.phase = 'original'

    def prepare(self, provider, key, messages, kwargs):
        from app.planning import reserve_cost
        require(not self.halted and time.monotonic() - self.started < 600,
                'Worker wall limit reached')
        require(not self.stop_path.exists(), 'Explicit stop before model dispatch')
        require(self.phase == 'original' and self.calls['original'] == 0
                and not self.in_call, 'No second model call')
        require(all(provider.get(field) == self.provider.get(field)
                    for field in ('id', 'provider', 'protocol', 'base_url', 'model', 'pricing'))
                and key == self.key, 'Wrong provider or credential')
        require(kwargs.get('max_tokens') == 6000
                and type(kwargs.get('timeout')) in (int, float)
                and 0 < kwargs.get('timeout', 0) <= 120
                and kwargs.get('json_mode') is True
                and kwargs.get('stream', False) is False
                and kwargs.get('allow_images', False) is False,
                'Model call settings changed')
        require(isinstance(messages, list) and messages
                and all(isinstance(m, dict) and m.get('role') in {'system', 'user', 'assistant'}
                        and isinstance(m.get('content'), str) for m in messages),
                'Only frozen text messages')
        quote = reserve_cost(messages, provider['pricing'], 6000)
        require(Decimal(0) <= quote <= Decimal(PER_CALL_USD), 'Per-call quote exceeded')
        self.quotes['original'] = quote
        self.message_sha = digest(messages)
        self.record.setdefault('quotes', {})['original'] = str(quote)
        self.in_call = True
        self.armed = True
        self.save()

    def admit(self, request):
        require(self.armed and self.in_call and not self.halted, 'Transport not admitted')
        endpoint = self.provider['base_url'].rstrip('/') + '/chat/completions'
        require(request.method == 'POST' and str(request.url) == endpoint,
                'Only the prepared model endpoint is allowed')
        require(request.headers.get('authorization') == 'Bearer ' + self.key,
                'Wrong model credential')
        try:
            body = json.loads(request.content)
        except Exception:
            raise RuntimeError('Model body is not JSON') from None
        require(isinstance(body, dict) and body.get('model') == self.provider['model']
                and body.get('max_tokens') == 6000
                and body.get('stream') is False
                and body.get('thinking') == {'type': 'disabled'}
                and body.get('response_format') == {'type': 'json_object'},
                'Unexpected model body')
        require(digest(body.get('messages')) == self.message_sha,
                'Quoted messages changed before dispatch')
        self.armed = False
        self.calls['original'] += 1
        self.record['model_http_started'] = sum(self.calls.values())
        self.record['stage_counts'] = dict(self.calls)
        self.save()

    def physical(self):
        self.record['physical_http'] = self.record.get('physical_http', 0) + 1
        self.save()

    def finish(self):
        self.in_call = False
        self.armed = False

    def stop(self):
        self.halted = True
        self.armed = False
        self.save()


def _public_task():
    intake = {'source': 'model', 'origin_revision': 6, 'created_at': _now(),
              'review': {'checks': [{'topic': 'goal', 'status': 'complete',
                                     'detail': '公开替身形状，不代表真实访谈。'}],
                         'questions': []}}
    task = {
        'id': PUBLIC_TASK, 'name': '公开替身已存访谈后的单次原规划', 'app_type': 'advanced-chat',
        'created_at': _now(), 'updated_at': _now(), 'environment_id': PUBLIC_ENV,
        'revision': 6, 'status': 'paused', 'synthetic_prior_shape': True,
        'requirements': copy.deepcopy(REQUIREMENTS), 'configuration': None,
        'materials': [], 'test_cases': copy.deepcopy(CASES),
        'requirements_confirmed': True, 'configuration_confirmed': False,
        'intake_required': True, 'plan_review_required': True,
        'intake_review': intake,
        'intake_history': [{'source': 'model', 'origin_revision': 3, 'created_at': _now(),
                            'review': {'checks': [], 'questions': []}}],
        'messages': [{'role': 'assistant', 'source': 'system', 'content': '公开替身历史 %d' % i}
                     for i in range(6)],
        'versions': [{'id': str(uuid4()), 'revision': i, 'label': '公开替身历史'}
                     for i in range(1, 6)],
        'planning_runs': [{'id': str(uuid4()), 'revision': 6, 'provider_id': PUBLIC_PROVIDER,
                           'model': 'deepseek-flash', 'status': 'paused',
                           'stop_reason': 'needs_decision',
                           'decision_report': {'message': '公开替身旧 needs_decision'},
                           'last_candidate': None, 'attempts': [], 'created_at': _now()}],
        'runs': [], 'confirmations': [], 'workflow_plan': None, 'agent_plan': None,
        'plan_source': None, 'plan_stale': False, 'artifact': None, 'dify_app_id': None,
    }
    task['configuration'] = copy.deepcopy(CONFIGURATION)
    task['configuration']['assistant_provider_id'] = PUBLIC_PROVIDER
    return task


def _public_budget():
    charged = ('0.0034545', '0.005911224', '0.0107598')
    entries = []
    for index, amount in enumerate(charged):
        entries.append({'id': str(uuid4()), 'operation_id': str(uuid4()), 'revision': 6,
                        'kind': 'interview' if index < 2 else 'plan',
                        'provider_id': PUBLIC_PROVIDER, 'model': 'deepseek-flash',
                        'pricing': copy.deepcopy(PUBLIC_PROVIDER_OBJECT['pricing']),
                        'reserved_usd': amount, 'charged_usd': amount,
                        'status': 'settled', 'call_status': 'returned',
                        'cost_basis': 'reported_usage', 'modality': 'text',
                        'usage': copy.deepcopy(KNOWN_USAGE), 'started_at': _now(),
                        'finished_at': _now(), 'policy_revision': 1})
    return {'id': PUBLIC_TASK, 'policy_revision': 1, 'limit_usd': '0.600',
            'created_at': _now(), 'excluded_history_present': True,
            'scope': 'since_ledger_start', 'entries': entries, 'policy_history': []}


def _seed_public(data):
    from app import main as h
    from app.storage import Store
    from app.intake import digest as intake_digest
    store = Store(data)
    store.put('provider', PUBLIC_PROVIDER, copy.deepcopy(PUBLIC_PROVIDER_OBJECT))
    store.put('environment', PUBLIC_ENV, copy.deepcopy(PUBLIC_ENV_OBJECT))
    task = _public_task()
    task['intake_review'].pop('context_digest', None)
    task['intake_review']['context_digest'] = intake_digest(task)
    store.put('task', PUBLIC_TASK, task)
    store.put('task_budget', PUBLIC_TASK, _public_budget())
    return store.get('task', PUBLIC_TASK), store.get('task_budget', PUBLIC_TASK)


def _check_task_value(owner, old_task, value, candidates):
    require(isinstance(value, dict), 'Task must be a mapping')
    require(value.get('id') == owner and value.get('app_type') == 'advanced-chat',
            'Wrong Task identity/type')
    require(value.get('name') == old_task.get('name')
            and value.get('created_at') == old_task.get('created_at')
            and value.get('environment_id') == old_task.get('environment_id'),
            'Task identity changed')
    require(value.get('requirements') == old_task.get('requirements'), 'Requirements changed')
    require(value.get('configuration') == old_task.get('configuration'), 'Configuration changed')
    require(value.get('materials') == old_task.get('materials'), 'Materials changed')
    require(value.get('test_cases') == old_task.get('test_cases'), 'Saved cases changed')
    require(value.get('requirements_confirmed') is True
            and value.get('configuration_confirmed') is False, 'Confirmation state changed')
    require(value.get('intake_required') == old_task.get('intake_required')
            and value.get('plan_review_required') == old_task.get('plan_review_required'),
            'Intake/review gates changed')
    require(value.get('artifact') is None and value.get('dify_app_id') is None,
            'Artifact/App changed')
    require(value.get('agent_plan') is None, 'Agent plan changed')
    require(value.get('plan_source') in {None, 'model'}, 'Plan source changed')
    require(value.get('plan_stale') in {False, None}, 'Plan stale changed')
    revision = value.get('revision')
    require(type(revision) is int and revision in {old_task['revision'], old_task['revision'] + 1},
            'Revision jumped')
    require(value.get('status') in {'paused', 'planning', 'configuration'},
            'Unexpected Task status')
    plan = value.get('workflow_plan')
    require(plan is None or (isinstance(plan, dict) and digest(plan) in candidates),
            'Task graph is not the complete model candidate')
    limits = (('messages', 2), ('versions', 1), ('planning_runs', 1),
              ('confirmations', 1), ('intake_history', 0), ('runs', 0))
    for key, extra in limits:
        old = old_task.get(key, [])
        current = value.get(key, [])
        require(isinstance(old, list) and isinstance(current, list),
                'History type changed: ' + key)
        require(current[:len(old)] == old, 'Original Task history overwritten: ' + key)
        require(len(current) - len(old) <= extra, 'Too many new ' + key)
    if 'interview_attempts' in old_task:
        require(isinstance(value.get('interview_attempts'), list)
                and value['interview_attempts'][:len(old_task['interview_attempts'])]
                == old_task['interview_attempts'], 'interview_attempts overwritten')
    else:
        require('interview_attempts' not in value, 'interview_attempts invented')
    allowed_new = {'updated_at', 'state_sequence', 'agent_plan', 'plan_source',
                   'plan_stale', 'workflow_plan', 'confirmations', 'dify_app_id',
                   'artifact'}
    require(set(value) - set(old_task) <= allowed_new, 'Unexpected new Task fields')
    require(set(old_task) - set(value) == set(), 'Task fields removed')
    allowed_top = {'revision', 'status', 'updated_at', 'state_sequence', 'plan_source',
                   'plan_stale', 'workflow_plan', 'agent_plan', 'messages', 'versions',
                   'planning_runs', 'confirmations'}
    for key in set(old_task) - allowed_top:
        require(value.get(key) == old_task.get(key), 'Task field changed: ' + key)
    sequence = value.get('state_sequence', old_task.get('state_sequence', 0))
    require(type(sequence) is int and sequence >= old_task.get('state_sequence', 0),
            'Task state sequence moved backwards')
    new_runs = value.get('planning_runs', [])[len(old_task.get('planning_runs', [])):]
    for run in new_runs:
        require(isinstance(run, dict), 'Malformed new planning run')
        candidate = run.get('last_candidate')
        if candidate is not None:
            require(isinstance(candidate, dict) and digest(candidate) in candidates,
                    'Planning run candidate is not the model response')


def _check_budget_value(owner, old_budget, value, provider_id):
    require(isinstance(value, dict) and value.get('id') == owner, 'Wrong Task budget')
    require(set(value) == set(old_budget), 'Budget fields changed')
    for key in set(old_budget) - {'entries'}:
        require(value.get(key) == old_budget[key], 'Budget policy changed: ' + key)
    old_entries = old_budget.get('entries', [])
    entries = value.get('entries', [])
    require(isinstance(entries, list) and entries[:len(old_entries)] == old_entries,
            'Original settled ledger changed')
    extra = entries[len(old_entries):]
    require(len(extra) <= 1, 'More than one new ledger entry')
    for entry in extra:
        require(isinstance(entry, dict) and entry.get('provider_id') == provider_id,
                'New ledger provider changed')
        require(entry.get('kind') == 'plan' and entry.get('revision') == TARGET_REVISION,
                'New ledger operation changed')
        require(entry.get('status') in {'reserved', 'settled', 'unknown'},
                'Unexpected new ledger status')
        require(money(entry.get('reserved_usd')) <= Decimal(PER_CALL_USD),
                'Per-call estimate exceeded')


def _guarded(base, data, owner, old_task, old_budget, candidates, provider_id, key_value):
    data = Path(data).resolve()

    class Guarded(base):
        def __init__(self, root):
            require(Path(root).resolve() == data, 'Wrong data root')
            super().__init__(root)

        def _put_object(self, conn, states, kind, item_id, value):
            require(Path(self.root).resolve() == data, 'Wrong data root')
            if kind == 'task' and item_id == owner:
                _check_task_value(owner, old_task, value, candidates)
            elif kind == 'task_budget' and item_id == owner:
                _check_budget_value(owner, old_budget, value, provider_id)
            else:
                raise RuntimeError('Unapproved object write: ' + kind + ':' + item_id)
            return super()._put_object(conn, states, kind, item_id, value)

        def secret(self, item, key):
            require(item == provider_id and key == 'api_key',
                    'Other credential read forbidden')
            return key_value

        def has_secret(self, item, key):
            return item == provider_id and key == 'api_key' and bool(key_value)

        def set_secret(self, *args, **kwargs):
            raise RuntimeError('Credential writes forbidden')

        def put_with_secrets(self, *args, **kwargs):
            raise RuntimeError('Credential writes forbidden')

        def put_many_with_secrets(self, *args, **kwargs):
            raise RuntimeError('Credential writes forbidden')

        def put_many_with_secret_sets(self, *args, **kwargs):
            raise RuntimeError('Credential writes forbidden')

        def delete(self, *args, **kwargs):
            raise RuntimeError('Delete forbidden')

    return Guarded


def _verify_after(data, owner, old_task, old_budget, before, candidates, provider_id,
                  record):
    after = capture(ReadOnly(data))
    target_keys = {'task:' + owner, 'task_budget:' + owner}
    for key, value in before['objects'].items():
        if key in target_keys:
            continue
        require(after['objects'].get(key) == value, 'Other object changed: ' + key)
    require(set(after['objects']) - set(before['objects']) <= set(),
            'New object created')
    require(after['secrets'] == before['secrets'], 'Credentials changed')
    require(all(after['files'].get(key) == value for key, value in before['files'].items()),
            'Files changed')
    require(set(after['files']) - set(before['files']) <= set(), 'New file created')
    reader = ReadOnly(data)
    task = reader.get('task', owner)
    budget = reader.get('task_budget', owner)
    require(task and budget, 'Target Task/budget missing')
    _check_task_value(owner, old_task, task, candidates)
    require(type(task.get('state_sequence')) is int
            and task['state_sequence'] > old_task.get('state_sequence', 0),
            'Task state sequence did not advance')
    _check_budget_value(owner, old_budget, budget, provider_id)
    limits = reader.get('execution_limits', owner)
    require(limits is None, 'execution_limits must stay absent')
    extra = budget['entries'][len(old_budget['entries']):]
    if record.get('model_http_started'):
        require(len(extra) == 1, 'Model call and ledger entry count differ')
    else:
        require(len(extra) <= 1, 'Ledger entry without a model call')
    passed = record.get('state') == 'passed'
    if passed:
        require(len(extra) == 1, 'Successful run has no ledger entry')
        require(task.get('revision') == old_task['revision'] + 1, 'Revision did not advance')
        require(task.get('status') == 'configuration', 'Saved status is not configuration')
        require(task.get('plan_source') == 'model', 'Plan source is not model')
        require(isinstance(task.get('workflow_plan'), dict)
                and digest(task['workflow_plan']) in candidates,
                'Saved graph is not the model candidate')
        require(len(task.get('messages', [])) == len(old_task.get('messages', [])) + 2,
                'Plan system message and model reply were not both saved')
        require(len(task.get('versions', [])) == len(old_task.get('versions', [])) + 1,
                'Version snapshot was not saved')
        require(len(task.get('planning_runs', []))
                == len(old_task.get('planning_runs', [])) + 1, 'Planning run was not saved')
    if extra:
        entry = extra[0]
        if passed:
            require(entry.get('status') == 'settled' and entry.get('charged_usd') is not None
                    and entry.get('cost_basis') == 'reported_usage',
                    'Successful call is not settled with reported usage')
        if record.get('unknown_usage'):
            require(entry.get('status') == 'unknown' and entry.get('charged_usd') is None,
                    'Unknown usage was not preserved as unknown')
    return {'original_objects_kept': True, 'original_task_and_ledger_prefix_kept': True,
            'old_credentials_and_files_kept': True, 'new_tasks': 0,
            'execution_limits_none_kept': True, 'new_ledger_entries': len(extra)}


def _write_json(path, value):
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
    os.replace(tmp, path)


def run(mode, output, plan=None):
    live = mode == 'live'
    root = Path(__file__).resolve().parent
    output = Path(output).resolve()
    require(output.is_relative_to(PROJECT / 'work') and not output.exists(),
            'New work output required')
    require(not sys.flags.optimize, 'Unoptimized worker only')
    output.mkdir()
    stop_path = output / 'stop.json'
    record = {'batch': BATCH, 'mode': mode, 'state': 'running', 'live': live,
              'model_http_started': 0, 'physical_http': 0, 'automatic_retry': False,
              'json_repair_http': 0, 'second_model_call': False,
              'responses': {}, 'quotes': {}, 'unknown_usage': False,
              'synthetic_prior_shape': not live,
              'historical_seed': ('actual_preserved_r6_interviews' if live
                                  else 'synthetic_prior_shape')}

    def save():
        _write_json(output / 'progress.json', record)

    save()
    if live:
        from tool import authorize_worker
        baseline = authorize_worker(root, plan)
    with tempfile.TemporaryDirectory(dir=output, prefix='bootstrap-') as bootstrap:
        os.environ['FLOWCRAFT_DATA_DIR'] = bootstrap
        sys.path.insert(0, str(plan['backend_path'] if live else PROJECT / 'backend'))
        from app import main as h
        from app.storage import Store
        from app.plan_drafts import inspect_text
        from app.providers import ProviderError, usage_summary
        from app.planning import reserve_cost
        from fastapi.testclient import TestClient
        import httpx

        data = Path(PROJECT / 'data') if live else output / 'data'
        if live:
            owner = baseline['task']['id']
            old_task = baseline['task']
            old_budget = baseline['budget']
            provider = baseline['provider']
            environment = baseline['environment']
            reader = ReadOnly(data)
            from cryptography.fernet import Fernet
            reader.cipher = Fernet((data / '.credential-key').read_bytes())
            key_value = Store.secret(reader, provider['id'], 'api_key')
            require(bool(key_value), 'Provider API key missing')
            before = capture(ReadOnly(data))
            require(before == plan['protected_data'], 'Production baseline changed')
        else:
            old_task, old_budget = _seed_public(data)
            owner = PUBLIC_TASK
            store = Store(data)
            provider = store.get('provider', PUBLIC_PROVIDER)
            environment = store.get('environment', PUBLIC_ENV)
            key_value = PUBLIC_KEY
            before = capture(ReadOnly(data))
            require(old_task.get('synthetic_prior_shape') is True,
                    'Public prior shape must be marked synthetic')
            require(old_task.get('revision') == TARGET_REVISION
                    and old_task.get('status') == 'paused'
                    and old_task.get('workflow_plan') is None
                    and 'interview_attempts' not in old_task,
                    'Public prior shape changed')

        candidates = set()
        Guarded = _guarded(Store, data, owner, old_task, old_budget, candidates,
                           provider['id'], key_value)
        h.DATA_ROOT = data
        h.store = Guarded(data)
        h.get_settings = lambda response=None: dict(SETTINGS)
        boundary = Boundary(provider, key_value, record, save, stop_path, live)
        original_call = h.call_model
        original_budget = h.budgets.call
        original_async = httpx.AsyncHTTPTransport.handle_async_request
        original_sync = httpx.HTTPTransport.handle_request

        if not live:
            from app.after_sales_starter import prepare as starter_prepare
            plan_text, validation = starter_prepare(h.get_task(owner),
                                                    copy.deepcopy(INPUTS))
            require(validation.get('valid') is True, 'Public synthetic graph invalid')
            candidate = h.extract_json(plan_text)
            require(isinstance(candidate, dict) and isinstance(candidate.get('nodes'), list),
                    'Public synthetic candidate missing')
        else:
            plan_text = None

        def pre_dispatch():
            if not live:
                return
            from tool import pre_dispatch as check
            check(root, plan, stop_path)

        async def budget(item, revision, kind, selected, key_value_arg, messages, **kwargs):
            require(not stop_path.exists(), 'Explicit stop before budget admission')
            pre_dispatch()
            current = h.get_task(owner)
            require(item == owner and revision == current['revision'] == TARGET_REVISION,
                    'Wrong Task/revision')
            require(selected == provider and key_value_arg == key_value,
                    'Wrong provider/credential')
            require(kind == 'plan', 'Only the normal plan operation is allowed')
            require(kwargs.get('max_tokens') == 6000
                    and type(kwargs.get('timeout')) in (int, float)
                    and 0 < kwargs.get('timeout', 0) <= 120
                    and not kwargs.get('stream'), 'Wrong model settings')
            if boundary.phase is None:
                boundary.begin()
            require(boundary.phase == 'original', 'Wrong model phase')
            quote = reserve_cost(messages, provider['pricing'], 6000)
            require(Decimal(0) <= quote <= Decimal(PER_CALL_USD), 'Per-call quote exceeded')
            record['quotes']['original'] = str(quote)
            save()
            return await original_budget(item, revision, kind, selected, key_value_arg,
                                         messages, **kwargs)

        async def model(selected, key, messages, **kwargs):
            require(not stop_path.exists(), 'Explicit stop before model dispatch')
            pre_dispatch()
            boundary.prepare(selected, key, messages, kwargs)
            try:
                text, usage = await original_call(selected, key, messages,
                                                  **{**kwargs, 'require_final_text': True})
                require(isinstance(text, str) and text and len(text) <= 100000,
                        'Bounded complete response required')
                inspect_text(text)
                require(key not in text, 'Model response contains the credential')
                name = 'model-response-' + boundary.phase + '.txt'
                with (output / name).open('x', encoding='utf-8', newline='') as handle:
                    handle.write(text)
                record['responses'][boundary.phase] = {
                    'file': name, 'sha256': sha_bytes(text.encode()), 'characters': len(text)}
                try:
                    value = h.extract_json(text)
                except Exception:
                    value = None
                if isinstance(value, dict) and isinstance(value.get('nodes'), list):
                    candidates.add(digest(value))
                    record['candidate_sha256'] = digest(value)
                summary = usage_summary(usage)
                known = (isinstance(summary.get('completion_tokens'), int)
                         or isinstance(summary.get('output_tokens'), int))
                record['usage'] = summary
                if not known:
                    record['unknown_usage'] = True
                    save()
                    raise ProviderError('模型用量未知，按本批规则停止；原文与占用已保存，'
                                        '不按0结算、不重试。', usage=usage)
                save()
                return text, usage
            finally:
                boundary.finish()

        async def intercept(own, request):
            require(not stop_path.exists(), 'Explicit stop at transport admission')
            pre_dispatch()
            boundary.admit(request)
            if live:
                boundary.physical()
                return await original_async(own, request)
            if mode == 'invalid_json':
                content = '{"schema_version":1,"nodes": [}'
                usage = dict(KNOWN_USAGE)
            elif mode == 'needs_decision':
                content = json.dumps({'error': '公开替身：需要明确条件。',
                                      'needs_decision': [{'question': '请明确这个条件。'}]},
                                     ensure_ascii=False)
                usage = dict(KNOWN_USAGE)
            elif mode == 'unknown_usage':
                content = plan_text
                usage = {}
            else:
                content = plan_text
                usage = dict(KNOWN_USAGE)
            return httpx.Response(200, json={'choices': [{
                'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': content}}],
                'usage': usage}, request=request)

        h.budgets.call = budget
        h.call_model = model
        httpx.AsyncHTTPTransport.handle_async_request = intercept
        httpx.HTTPTransport.handle_request = forbidden_sync
        protection = None
        try:
            api = TestClient(h.app)
            try:
                record['revision_before'] = old_task['revision']
                response = api.post('/api/tasks/' + owner + '/plan/generate',
                                    json={'revision': old_task['revision']})
                record['http_status'] = response.status_code
                task = h.get_task(owner)
                operation = (task.get('planning_runs') or [None])[-1]
                record['planning_run'] = {
                    'id': operation.get('id'), 'status': operation.get('status'),
                    'stop_reason': operation.get('stop_reason'),
                    'message': operation.get('message'),
                    'estimated_cost_usd': operation.get('estimated_cost_usd'),
                    'attempt_count': len(operation.get('attempts') or []),
                    'decision_report': operation.get('decision_report'),
                } if isinstance(operation, dict) else None
                if (response.status_code == 200 and isinstance(operation, dict)
                        and operation.get('status') == 'succeeded'
                        and task.get('plan_source') == 'model'
                        and isinstance(task.get('workflow_plan'), dict)):
                    record['state'] = 'passed'
                else:
                    record['state'] = 'stopped'
                    record['failure_type'] = 'planning_stopped'
                    record['stop_reason'] = (operation.get('stop_reason')
                                             if isinstance(operation, dict)
                                             else 'missing_operation')
                    record['failure_reason'] = (
                        (operation.get('message') if isinstance(operation, dict) else None)
                        or record.get('stop_reason') or 'planning_stopped')[:500]
                record['revision_after'] = task.get('revision')
            finally:
                api.close()
            protection = _verify_after(data, owner, old_task, old_budget, before,
                                       candidates, provider['id'], record)
            record['protection'] = protection
        except BaseException as exc:
            try:
                boundary.stop()
            except Exception:
                pass
            record.update(state='stopped', failure_type=type(exc).__name__)
            record['failure_reason'] = (str(exc).strip().replace('\n', ' ')[:500]
                                        or type(exc).__name__)
            try:
                protection = _verify_after(data, owner, old_task, old_budget, before,
                                           candidates, provider['id'], record)
                record['protection'] = protection
            except BaseException as verify_exc:
                record['protection_error'] = type(verify_exc).__name__
                record['protection_message'] = str(verify_exc)
                record.setdefault('failure_reason', type(verify_exc).__name__)
            if not live:
                record['public_failure'] = str(exc)
        finally:
            h.budgets.call = original_budget
            h.call_model = original_call
            httpx.AsyncHTTPTransport.handle_async_request = original_async
            httpx.HTTPTransport.handle_request = original_sync

    reader = ReadOnly(data)
    task = reader.get('task', owner)
    budget = reader.get('task_budget', owner)
    extra = (budget.get('entries', [])[len(old_budget.get('entries', [])):]
             if isinstance(budget, dict) else [])
    result = {
        'batch': BATCH, 'mode': mode, 'state': record.get('state'),
        'target_task_id': owner,
        'revision_before': old_task.get('revision'),
        'revision_after': (task or {}).get('revision'),
        'plan_source': (task or {}).get('plan_source'),
        'candidate_sha256': (digest(task['workflow_plan'])
                             if isinstance(task, dict)
                             and isinstance(task.get('workflow_plan'), dict) else None),
        'workflow_plan_saved': isinstance(task, dict)
                               and isinstance(task.get('workflow_plan'), dict),
        'model_http_started': record.get('model_http_started', 0),
        'physical_http': record.get('physical_http', 0),
        'stage_counts': record.get('stage_counts'),
        'automatic_retry': False, 'json_repair_http': 0,
        'model_response': record.get('responses', {}).get('original'),
        'usage': record.get('usage'),
        'estimated_cost_usd': (record.get('planning_run') or {}).get('estimated_cost_usd'),
        'planning_run': record.get('planning_run'),
        'ledger': {'before_entries': len(old_budget.get('entries', [])),
                   'after_entries': len(extra) + len(old_budget.get('entries', [])),
                   'new_entry': extra[0] if extra else None,
                   'before_sha256': digest(old_budget.get('entries', [])),
                   'after_sha256': (digest(budget.get('entries', []))
                                    if isinstance(budget, dict) else None)},
        'execution_limits': None,
        'execution_limits_absent': True,
        'synthetic_prior_shape': not live,
        'historical_seed': record.get('historical_seed'),
        'root_review': ('pending_offline_review' if live
                        else 'public_synthetic_not_reviewed'),
        'semantic_reviewed': False, 'human_signoff': False,
        'business_verified': False, 'dify_verified': False,
        'verification': 'normal_product_api_saved_model_candidate_not_business_acceptance',
        'protection': record.get('protection'),
        'failure_type': record.get('failure_type'),
        'failure_reason': record.get('failure_reason'),
        'stop_reason': record.get('stop_reason'),
        'public_failure': record.get('public_failure'),
        'created_at': _now(),
    }
    _write_json(output / 'result.json', result)
    source = {
        'stage': 'original', 'task_id': owner,
        'revision_before': old_task.get('revision'),
        'revision_after': (task or {}).get('revision'),
        'saved_task_sha256': digest(task) if isinstance(task, dict) else None,
        'candidate': (task or {}).get('workflow_plan'),
        'candidate_sha256': result['candidate_sha256'],
        'model_response': result['model_response'],
        'usage': result['usage'],
        'estimated_cost_usd': result['estimated_cost_usd'],
        'planning_run': result['planning_run'],
        'ledger_new_entry': result['ledger']['new_entry'],
        'execution_limits_absent': True,
        'synthetic_prior_shape': not live,
        'verification': ('root_offline_review_required_not_business_acceptance'
                         if live else 'public_synthetic_protocol_not_business_acceptance'),
        'protection': result['protection'],
    }
    _write_json(output / 'review-source-original.json', source)
    save()
    return result


if __name__ == '__main__':
    require(len(sys.argv) == 3 and sys.argv[1] != 'live',
            'Public rehearsal only; live uses tool.py')
    result = run(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps({key: result.get(key) for key in
                      ('state', 'model_http_started', 'physical_http',
                       'candidate_sha256', 'public_failure')}, ensure_ascii=False))
