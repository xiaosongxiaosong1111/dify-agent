"""One bounded local-only reuse batch: no live entry, no new Task, three model stages."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import threading
from decimal import Decimal
from pathlib import Path

from common import LIMITS, MODEL_STAGES, PROJECT, capture, digest, known_apps, require
from reuse_policy import validate_start


MODEL_PHASES = MODEL_STAGES


def run(mode, output):
    """The 374 live entry is intentionally closed before any DB/secret read."""
    if mode == 'live':
        raise RuntimeError('autonomous-dual374 has no live entry; no DB, secret or external read')
    output = Path(output).resolve()
    require(output.is_relative_to(PROJECT / 'work') and not output.exists() and not sys.flags.optimize,
            'New nonoptimized work output required')
    output.mkdir()
    fixture = json.loads((Path(__file__).resolve().parent / 'fixture.json').read_text('utf-8'))
    record = {
        'state': 'running', 'mode': mode, 'physical_http': 0, 'automatic_retry': False,
        'approved_model_slots': 3, 'effective_model_http': 3, 'json_repair_http': 0,
        'responses': {}, 'reviews': {}, 'business_acceptance_complete': False,
        'human_signoff': False, 'synthetic_prior_shape': True, 'new_task_created': False,
    }
    lock = threading.RLock()

    def save():
        with lock:
            tmp = output / 'progress-writing.tmp'
            tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), 'utf-8')
            os.replace(tmp, output / 'progress.json')

    save()
    with tempfile.TemporaryDirectory(dir=output, prefix='bootstrap-') as bootstrap:
        os.environ['FLOWCRAFT_DATA_DIR'] = bootstrap
        sys.path.insert(0, str(PROJECT / 'backend'))
        from app import main as h
        from app.storage import Store
        from app.plan_drafts import inspect_text
        from app.planning import reserve_cost
        from app.providers import ProviderError
        from fastapi.testclient import TestClient
        import httpx
        with TestClient(h.app) as api:
            env = api.post('/api/environments', json={
                'name': '公开替身专用环境', 'base_url': 'https://public-dify.invalid', 'version': '1.17.1',
                'console_token': 'PUBLIC_OLD_CONSOLE', 'csrf_token': 'PUBLIC_OLD_CSRF',
                'service_api_key': 'app-PUBLIC_OLD_RUNTIME_KEY',
                'service_app_id': '11111111-1111-4111-8111-111111111111'}).json()
            source = h.store
            env = source.get('environment', env['id'])
            env.update(console_workspace_id=fixture['workspace_id'],
                       console_login_binding={'base_url': env['base_url'], 'version': '1.17.1',
                                              'workspace_id': fixture['workspace_id']})
            source.put_with_secrets('environment', env['id'], env, {
                'console_login_email': 'public@example.invalid',
                'console_login_password': 'PUBLIC_SYNTHETIC_ONLY'})
            provider = api.post('/api/providers', json={
                'name': '公开模型替身', 'provider': 'deepseek', 'protocol': 'openai-compatible',
                'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash',
                'api_key': 'PUBLIC_MODEL_KEY', 'role': 'main',
                'pricing': {'input_per_million_usd': .3, 'output_per_million_usd': 1.2}}).json()
            provider = source.get('provider', provider['id'])
            from synthetic_seed import seed
            target = seed(api, h, fixture, env, provider)
        fixture['environment_id'] = env['id']
        fixture['provider_id'] = provider['id']
        fixture['configuration']['assistant_provider_id'] = provider['id']
        initial_task = source.get('task', target)
        initial_budget = source.get('task_budget', target)
        initial_limits = source.get('execution_limits', target)
        require(initial_task and initial_budget and initial_task.get('synthetic_prior_shape') is True
                and initial_budget.get('entries'), 'Synthetic prior shape missing')
        validate_start(initial_task, initial_budget, initial_limits, fixture, env['id'], provider['id'],
                       expected={'task_id': target, 'task_digest': digest(initial_task),
                                 'budget_digest': digest(initial_budget)})
        before = capture(source)
        contract = {}
        from boundary import Boundary
        from storage_guard import guarded, verify
        from candidate import register
        from reviews import Reviews
        from synthetic import Synthetic
        key = source.secret(provider['id'], 'api_key')
        b = Boundary(env, provider, key, fixture, contract, record, known_apps(source))
        b.owner = target
        b.owner_configured = True
        b.default_config = copy.deepcopy(initial_task['configuration'])
        b.expected_config = copy.deepcopy(initial_task['configuration'])
        b.candidates = set()
        b.save = save
        b.initial_entry_count = len(initial_budget['entries'])
        reuse = {'task': initial_task, 'budget': initial_budget, 'limits': initial_limits,
                 'provider_id': provider['id'], 'target': target, 'fixture': fixture}
        Protected = guarded(Store, env, provider, fixture, contract, b, before, reuse)
        h.DATA_ROOT = source.root
        h.store = Protected(source.root)
        h.sierra_fixture = fixture
        h.sierra_review_secrets = [key] + [source.secret(env['id'], name) for name in
                                           ('console_token', 'csrf_token', 'console_login_password',
                                            'service_api_key')]
        h.sierra_review_secrets = [value for value in h.sierra_review_secrets if value]
        reviews = Reviews(output, h, record, False, save)
        b.wait_review = reviews.wait
        b.register_plan = lambda host, task, version, receipt: register(
            host, task, version, receipt, b, fixture, contract)
        original_model = h.call_model
        original_budget = h.budgets.call
        settings = copy.deepcopy(h.get_settings())
        h.get_settings = lambda: {**settings, 'max_retries': 0, 'max_minutes': 4,
                                  'max_cost_usd': .600}
        old_async = httpx.AsyncHTTPTransport.handle_async_request
        old_sync = httpx.HTTPTransport.handle_request
        synthetic = Synthetic(b, mode, h)
        h.sierra_synthetic_trace_expectations = synthetic.expectations
        settled = sum((Decimal(e['charged_usd']) for e in initial_budget['entries']), Decimal(0))
        record.update(task_id=target, historical_seed='synthetic_prior_shape',
                      reused_interviews={'source': 'synthetic_prior_shape', 'new_interview_calls': 0},
                      new_model_stages=list(MODEL_STAGES), new_task_created=False,
                      initial_ledger={'entries': len(initial_budget['entries']),
                                      'settled_usd': str(settled)},
                      reuse_binding={'task_digest': digest(initial_task),
                                     'budget_digest': digest(initial_budget)})
        save()

        def current():
            require(not (output / 'stop.json').exists(), 'Explicit stop')
            h.budgets.ready(b.owner)

        def require_policy():
            limits = h.store.get('execution_limits', b.owner)
            require(isinstance(limits, dict) and limits.get('max_started_runs') == 12
                    and limits.get('max_total_minutes') == 45
                    and limits.get('max_reported_cost_usd') is None,
                    'Execution policy must be 12/45/None before model admission')

        async def budget(item, revision, kind, selected, key_value, messages, **kwargs):
            current()
            require_policy()
            require(b.phase in MODEL_PHASES, 'Old or unknown model stage forbidden')
            task = h.get_task(b.owner)
            require(item == b.owner and revision == task['revision'] and selected == provider
                    and key_value == key, 'Wrong current model scope')
            require(kind == ('interview' if b.phase.endswith('interview') else 'plan')
                    and kwargs.get('max_tokens') == 6000 and 0 < kwargs.get('timeout', 0) <= 120
                    and not kwargs.get('stream'), 'Wrong model operation/settings')
            if b.phase == 'original_plan':
                require(fixture['changed_no_hit_reply'] not in json.dumps(messages, ensure_ascii=False),
                        'Future revision leaked into original model context')
            if kind == 'plan':
                payload = json.loads(messages[1]['content'])
                cases = payload.get('acceptance_cases') or {}
                require(cases.get('case_count') == 6 and cases.get('turn_count') == 7,
                        'Current six cases missing')
                if b.phase == 'original_plan':
                    require(payload.get('existing_plan_context') is None and not task.get('workflow_plan'),
                            'Original must begin without an old graph')
                else:
                    require(digest(payload['existing_plan_context']['plan'])
                            == digest(contract['original']['plan']), 'Wrong modified baseline')
            quote = reserve_cost(messages, provider['pricing'], 6000)
            require(Decimal(0) <= quote <= Decimal('.100'), 'Per-call quote exceeded')
            used = sum((Decimal(item['quote']) for item in record.get('new_model_quotes', [])), Decimal(0))
            require(used + quote <= Decimal('.300'), 'Batch model estimate exceeded')
            record.setdefault('new_model_quotes', []).append(
                {'stage': b.phase, 'quote': str(quote)})
            save()
            return await original_budget(item, revision, kind, selected, key_value, messages, **kwargs)

        h.budgets.call = budget

        async def model(selected, key_value, messages, **kwargs):
            current()
            require_policy()
            b.prepare_model(selected, key_value, messages, kwargs)
            try:
                text, usage = await original_model(selected, key_value, messages,
                                                   **{**kwargs, 'require_final_text': True})
                require(isinstance(text, str) and len(text) <= 100000, 'Incomplete/oversize model text')
                inspect_text(text)
                require(not any(s in text for s in h.sierra_review_secrets),
                        'Model response contains protected text')
                name = 'model-response-' + b.phase + '.txt'
                (output / name).write_text(text, 'utf-8')
                record['responses'][b.phase] = {
                    'file': name, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                    'characters': len(text)}
                value = json.loads(text, parse_constant=lambda _: require(False, 'Non-finite model JSON'))
                if isinstance(value, dict) and isinstance(value.get('nodes'), list):
                    b.candidates.add(digest(value))
                save()
                return text, usage
            except ProviderError:
                raise
            except Exception:
                raise ProviderError('本批模型候选无法安全核对，已停止，不修复重试。',
                                    usage=locals().get('usage', {})) from None
            finally:
                b.finish_model()

        h.call_model = model

        async def intercept(own, request):
            current()
            return await b.dispatch(synthetic, request)

        def forbidden(*args, **kwargs):
            raise RuntimeError('Synchronous physical HTTP forbidden')

        httpx.AsyncHTTPTransport.handle_async_request = intercept
        httpx.HTTPTransport.handle_request = forbidden
        try:
            from journey import run as journey
            with TestClient(h.app) as api:
                journey(api, h, b, fixture, contract, output, mode)
            require(record.get('state') == 'passed', 'Journey did not complete')
        except BaseException as exc:
            b.halted = True
            record.update(state='stopped', failure_type=type(exc).__name__, phase=b.phase)
            if not sys.flags.optimize:
                import traceback
                record.update(local_public_error=str(exc), local_public_traceback=traceback.format_exc())
        finally:
            protection_failure = None
            try:
                record['protection'] = verify(h.store, env, b, before, reuse)
            except Exception as exc:
                record.update(state='stopped', protection_failure=True)
                protection_failure = exc
            finally:
                try:
                    save()
                finally:
                    httpx.AsyncHTTPTransport.handle_async_request = old_async
                    httpx.HTTPTransport.handle_request = old_sync
            if protection_failure is not None:
                raise protection_failure
    return record
