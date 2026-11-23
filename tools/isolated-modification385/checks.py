"""Public synthetic checks for isolated-modification385.

Temporary directories, synthetic Git/Task/budget/provider, fake transport.
No real work/data, credential, runtime process or external endpoint is used.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tool  # noqa: E402


def rejected(fn, label):
    try:
        fn()
    except RuntimeError:
        return
    raise AssertionError(label + ' was accepted or raised an unexpected type')


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value, 'utf-8')


def git_commit(project):
    subprocess.run(['git', 'init'], cwd=project, capture_output=True, check=True)
    subprocess.run(['git', 'add', '.'], cwd=project, capture_output=True, check=True)
    subprocess.run(['git', '-c', 'user.email=public@example.invalid', '-c', 'user.name=public',
                    'commit', '-m', 'synthetic'], cwd=project, capture_output=True, check=True)
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=project, capture_output=True, check=True).stdout.decode().strip()


def test_source_and_pin():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        for name in tool.SOURCE_FILES:
            write(project / 'tools' / tool.BATCH / name, 'synthetic-\r\n' + name + '\r\n')
        commit = git_commit(project)
        sources = tool.verify_source(project, commit)
        root = project / 'work' / tool.BATCH
        for name in tool.SOURCE_FILES:
            write(root / name, (project / 'tools' / tool.BATCH / name).read_text('utf-8'))
        for name in ('source-pins.json', 'protected-892.json'):
            write(root / name, name)
        plan = {'source_commit': commit, 'source_files': sources['files']}
        tool.atomic_json(root / 'plan.json', plan)
        files = {name: tool.sha_file(root / name) for name in tool.PACKAGE_FILES}
        tool.atomic_json(root / 'manifest.json', {'batch_id': tool.BATCH, 'plan_sha256': files['plan.json'], 'files': files})
        tool.verify_package(root)
        tool.verify_source_binding(project, root, plan)
        write(root / 'tool.py', 'tampered canonical')
        files = {name: tool.sha_file(root / name) for name in tool.PACKAGE_FILES}
        tool.atomic_json(root / 'manifest.json', {'batch_id': tool.BATCH, 'plan_sha256': files['plan.json'], 'files': files})
        tool.verify_package(root)
        rejected(lambda: tool.verify_source_binding(project, root, plan), 'canonical source tamper')
        rejected(lambda: tool.verify_source_binding(project, root, {**plan, 'source_files': {}}), 'source_files mismatch')
        write(project / 'tools' / tool.BATCH / 'tool.py', 'changed')
        rejected(lambda: tool.verify_source(project, commit), 'source drift')
        outside = project.parent / 'outside'
        outside.mkdir(exist_ok=True)
        try:
            (project / 'linked').symlink_to(outside, target_is_directory=True)
            rejected(lambda: tool.safe_path(project, 'linked/file'), 'parent symlink')
        finally:
            if (project / 'linked').exists():
                (project / 'linked').unlink()
    pinned = tool.load_pinned(ROOT)
    assert hasattr(pinned['worker'], 'Boundary') and hasattr(pinned['common'], 'ReadOnly')


def test_sealed_and_roots():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        write(project / 'a.txt', 'a')
        write(project / 'work/preserved-planning377/b.txt', 'b')
        write(project / 'work/reviewed-planning380/c.txt', 'c')
        write(project / 'work/preserved-planning377/plan.json',
              json.dumps({'protected_files': {'a.txt': tool.sha_file(project / 'a.txt')}}))
        write(project / 'work/preserved-planning377/seal-after-stop.json',
              json.dumps({'b.txt': tool.sha_file(project / 'work/preserved-planning377/b.txt')}))
        write(project / 'work/reviewed-planning380/seal-after-review.json',
              json.dumps({'c.txt': tool.sha_file(project / 'work/reviewed-planning380/c.txt')}))
        tool.verify_sealed(project, (1, 3, 5), None)
        write(project / 'work/preserved-planning377/b.txt', 'tampered')
        rejected(lambda: tool.verify_sealed(project, (1, 3, 5), None), 'sealed tamper')
        from app.storage import Store
        sqlite = Store(project / 'two')
        sqlite.put('task', 't', {'id': 't', 'x': 1})
        write(project / 'work/autonomous-dual375/plan.json',
              json.dumps({'isolated_paths': {'one': 'one.txt', 'two': 'two'}}))
        write(project / 'one.txt', 'one')
        write(project / 'data/live.txt', 'live')
        pinned = tool.load_pinned(ROOT)
        roots = tool.load_roots(project, pinned['common'], expected_isolated=2, expected_count=3)
        tool.verify_roots(project, roots, pinned['common'], expected_count=3)
        sqlite.put('task', 't', {'id': 't', 'x': 2})
        rejected(lambda: tool.verify_roots(project, roots, pinned['common'], expected_count=3),
                 'SQLite root change')


def synthetic_package(project):
    root = project / 'work' / tool.BATCH
    for name in ('tool.py', 'checks.py', 'README.md', 'source-pins.json', 'protected-892.json'):
        write(root / name, name)
    plan = {'schema_version': 1, 'batch_id': tool.BATCH, 'approval_state': 'pending'}
    tool.atomic_json(root / 'plan.json', plan)
    files = {name: tool.sha_file(root / name) for name in tool.PACKAGE_FILES}
    manifest = {'schema_version': 1, 'batch_id': tool.BATCH, 'plan_sha256': files['plan.json'], 'files': files}
    tool.atomic_json(root / 'manifest.json', manifest)
    return root, plan, manifest


def test_authorization_and_interlock():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        root, plan, manifest = synthetic_package(project)
        tool.verify_package(root)
        plan_sha = tool.sha_file(root / 'plan.json'); manifest_sha = tool.sha_file(root / 'manifest.json')
        ref = 'call_' + 'a' * 32 + '/q0'
        auth = {'authorization_source': 'direct_user_reply', 'scope': tool.BATCH, 'question_ref': ref,
                'literal': tool.APPROVAL_PHRASE, 'plan_sha256': plan_sha, 'manifest_sha256': manifest_sha,
                'limits': tool.LIMITS, 'single_use': True, 'retry': False}
        tool.validate_authorization(auth, plan, plan_sha, manifest_sha)
        rejected(lambda: tool.validate_authorization({**auth, 'question_ref': sorted(tool.OLD_REFS)[0]}, plan, plan_sha, manifest_sha), 'old ref')
        rejected(lambda: tool.validate_authorization({**auth, 'scope': 'other'}, plan, plan_sha, manifest_sha), 'wrong scope')
        rejected(lambda: tool.validate_authorization({**auth, 'limits': {'model_calls': 2}}, plan, plan_sha, manifest_sha), 'wrong limits')
        approval = {**auth, 'batch_id': tool.BATCH, 'created_at': tool.now()}
        tool.atomic_json(root / 'approval.json', approval)
        tool.verify_approval(root, plan, manifest_sha)
        rejected(lambda: tool.verify_approval(root, plan, manifest_sha + 'x'), 'approval binding')
        tool.assert_unconsumed(root)
        tool.atomic_json(root / 'attempt.json', {'state': 'admitted'})
        rejected(lambda: tool.assert_unconsumed(root), 'consumed marker')
        rejected(lambda: tool.external_file(project, root / 'approval.json'), 'authorization inside project')


def test_candidate_diff_and_runtime():
    spec = {'node_count': 2, 'paths': (
        ('no_hit_text', 'template', 'whole', 'old', 'new'),
        ('faq_llm', 'system_prompt', 'contains', 'old', 'new'))}
    baseline = {'nodes': [{'id': 'no_hit_text', 'config': {'template': 'old'}},
                          {'id': 'faq_llm', 'config': {'system_prompt': '前文。old。后文。'}}]}
    candidate = copy.deepcopy(baseline)
    candidate['nodes'][0]['config']['template'] = 'new'
    candidate['nodes'][1]['config']['system_prompt'] = '前文。new。后文。'
    assert len(tool.check_candidate(baseline, candidate, spec)['paths']) == 2
    extra = copy.deepcopy(candidate); extra['nodes'][0]['config']['other'] = 1
    rejected(lambda: tool.check_candidate(baseline, extra, spec), 'extra field')
    typed = copy.deepcopy(candidate); typed['nodes'][1]['config']['system_prompt'] = True
    rejected(lambda: tool.check_candidate(baseline, typed, spec), 'type change')
    twice = copy.deepcopy(baseline); twice['nodes'][1]['config']['system_prompt'] = 'old。old。'
    rejected(lambda: tool.check_candidate(twice, candidate, spec), 'baseline twice')
    backend = Path('C:/fake/snapshot/backend'); venv = Path('C:/fake/.venv/Scripts/python.exe')
    argv = ['python', '-m', 'uvicorn', 'app.main:app', '--app-dir', str(backend),
            '--host', '127.0.0.1', '--port', '8765']
    tool.runtime_process_matches(str(venv), argv, backend, venv)
    rejected(lambda: tool.runtime_process_matches(str(venv), argv[:-1] + ['8766'], backend, venv), 'wrong port')
    rejected(lambda: tool.runtime_process_matches('C:/other/python.exe', argv, backend, venv), 'wrong venv')
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp); snap = project / '.runtime/snapshots/b'
        write(project / 'backend/a.py', 'a'); write(project / 'backend/b.py', 'b')
        write(snap / 'backend/a.py', 'a'); write(snap / 'backend/b.py', 'b')
        files = {'backend/a.py': tool.sha_file(snap / 'backend/a.py'), 'backend/b.py': tool.sha_file(snap / 'backend/b.py')}
        write(snap / 'runtime-manifest.json', json.dumps({'build_id': 'b', 'version': 'v',
              'files': files, 'content_sha256': 'c' * 64}))
        tool.load_runtime(project, expected_count=2, expected_build='b', expected_version='v', expected_content='c' * 64)
        write(snap / 'backend/a.py', 'tampered')
        rejected(lambda: tool.load_runtime(project, expected_count=2, expected_build='b', expected_version='v',
                                           expected_content='c' * 64), 'runtime snapshot file')
        write(snap / 'backend/a.py', 'a'); write(project / 'backend/a.py', 'tampered')
        rejected(lambda: tool.load_runtime(project, expected_count=2, expected_build='b', expected_version='v',
                                           expected_content='c' * 64), 'runtime project file')


def test_guarded_store():
    from app.storage import Store
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        production = Store(project / 'production')
        production.put('task', 't', {'id': 't', 'x': 1})
        production.put('task_budget', 't', {'id': 't', 'entries': []})
        pinned = tool.load_pinned(ROOT)
        before = pinned['common'].capture(pinned['common'].ReadOnly(production.root))
        isolated = Store(project / 'isolated')
        isolated.put('task_budget', 't', {'id': 't', 'entries': []})
        guarded = tool.GuardedStore(isolated, 'FAKE-KEY', 'p', 't')
        guarded.put('task', 't', {'id': 't', 'x': 2}); guarded.put('task_budget', 't', {'id': 't', 'entries': []})
        rejected(lambda: guarded.put('task_budget', 't', {'id': 't', 'entries': [{}, {}]}), 'budget two entries')
        rejected(lambda: guarded.put('task_budget', 't', {'id': 't', 'entries': [], 'limit_usd': '999'}), 'budget metadata')
        rejected(lambda: guarded.put('provider', 'p', {}), 'provider write')
        rejected(lambda: guarded.put('task', 'other', {}), 'other Task write')
        rejected(lambda: guarded.put_with_secrets('task', 't', {}, {}), 'secret write')
        assert guarded.secret('p', 'api_key') == 'FAKE-KEY' and guarded.has_secret('p', 'api_key')
        assert isolated.has_secret('p', 'api_key') is False
        assert before == pinned['common'].capture(pinned['common'].ReadOnly(production.root))


def base_plan():
    prompt = '仅依据资料回答。' + tool.ORIGINAL + '不要补造。'
    return {'schema_version': 1, 'nodes': [
        {'id': 'start', 'type': 'start', 'config': {'variables': []}},
        {'id': 'no_hit_text', 'type': 'template-transform', 'config': {'template': tool.ORIGINAL, 'variables': []}},
        {'id': 'faq_llm', 'type': 'llm', 'config': {'system_prompt': prompt, 'user_prompt': '{{#sys.query#}}'}},
        {'id': 'answer', 'type': 'answer', 'config': {'answer': '{{#faq_llm.text#}}'}}],
        'edges': [{'source': 'start', 'target': 'no_hit_text'},
                  {'source': 'no_hit_text', 'target': 'faq_llm'},
                  {'source': 'faq_llm', 'target': 'answer'}]}


def candidate(plan, extra=False):
    value = copy.deepcopy(plan)
    value['nodes'][1]['config']['template'] = tool.MODIFIED
    value['nodes'][2]['config']['system_prompt'] = plan['nodes'][2]['config']['system_prompt'].replace(tool.ORIGINAL, tool.MODIFIED, 1)
    if extra: value['nodes'][3]['config']['answer'] = 'changed'
    return value


def seed(h, store, task_id, plan):
    provider_id = 'synthetic-provider'
    task = {'id': task_id, 'name': 'synthetic', 'app_type': 'advanced-chat', 'revision': 8,
            'status': 'requirements', 'requirements': {key: '明确说明' for key in h.REQ_KEYS},
            'configuration': copy.deepcopy(h.CONFIG_DEFAULT), 'materials': [], 'messages': [],
            'versions': [], 'planning_runs': [], 'runs': [], 'test_cases': [],
            'requirements_confirmed': False, 'configuration_confirmed': False,
            'intake_required': True, 'intake_review': None, 'plan_stale': True,
            'workflow_plan': copy.deepcopy(plan)}
    task['requirements']['output'] = '无答案固定文案：' + tool.MODIFIED
    task['configuration'].update(assistant_provider_id=provider_id, dify_model_provider='deepseek',
                                 dify_model='deepseek-flash',
                                 resource_plan='只创建新的应用，不覆盖已有应用或知识库。')
    budget = {'id': task_id, 'policy_revision': 1, 'limit_usd': '0.600', 'entries': [],
              'policy_history': [], 'excluded_history_present': False,
              'scope': 'since_ledger_start', 'created_at': h.now()}
    provider = {'id': provider_id, 'provider': 'deepseek', 'preset_id': 'deepseek-flash',
                'protocol': 'openai-compatible', 'base_url': 'https://api.deepseek.com',
                'model': 'deepseek-flash', 'role': 'main',
                'pricing': {'input_per_million_usd': 0.3, 'output_per_million_usd': 1.2,
                            'cached_input_per_million_usd': 0.006}}
    store.put('task', task_id, task); store.put('task_budget', task_id, budget)
    store.put('provider', provider_id, provider); store.set_secret(provider_id, 'api_key', 'FAKE385')
    return provider


def scenario(h, store, pinned, plan, spec, tmp, label, reply, usage, retries=0, ok=False,
             expected=(RuntimeError,), reasons=()):
    import httpx
    task_id = 'synthetic-' + label
    provider = seed(h, store, task_id, plan)
    initial_budget = copy.deepcopy(store.get('task_budget', task_id))
    h.store = tool.GuardedStore(store, 'FAKE385', provider['id'], task_id)
    h.get_settings = lambda response=None, r=retries: {'max_retries': r, 'max_minutes': 2, 'max_cost_usd': 0.100}
    record = {'model_http_started': 0, 'physical_http': 0, 'automatic_retry': False}
    boundary = pinned['worker'].Boundary(provider, 'FAKE385', record, lambda: None, Path(tmp) / ('stop-' + label), True)
    original_async = httpx.AsyncHTTPTransport.handle_async_request
    async def fake(own, request):
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': reply},
            'finish_reason': 'stop'}], 'usage': usage}, request=request)
    httpx.AsyncHTTPTransport.handle_async_request = fake
    restore = tool.install_boundary(h, boundary, Path(tmp))
    try:
        if ok:
            result = tool.planning_call(h, task_id, boundary, Path(tmp), spec)
        else:
            try:
                tool.planning_call(h, task_id, boundary, Path(tmp), spec)
            except Exception as exc:
                assert isinstance(exc, expected), label + ' raised unexpected ' + type(exc).__name__
                if reasons:
                    assert any(reason in str(exc) for reason in reasons), label + ' reason: ' + str(exc)
            else:
                raise AssertionError(label + ' was accepted')
            result = None
    finally:
        restore(); httpx.AsyncHTTPTransport.handle_async_request = original_async
    assert boundary.calls.get('original') == 1
    assert record.get('physical_http') == 1
    current_budget = store.get('task_budget', task_id)
    assert {k: v for k, v in current_budget.items() if k != 'entries'} == {
        k: v for k, v in initial_budget.items() if k != 'entries'}
    assert current_budget['entries'][:len(initial_budget['entries'])] == initial_budget['entries']
    assert len(current_budget['entries']) <= len(initial_budget['entries']) + 1
    if ok:
        assert result['intake_source'] == 'agent_declared' and result['formal_plan_unchanged']
        assert result['physical_http'] == 1 and len(result['candidate']['paths']) == 2
    return task_id, boundary


def test_normal_api():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['FLOWCRAFT_DATA_DIR'] = str(Path(tmp) / 'data')
        from app import main as h
        from app.providers import ProviderError
        pinned = tool.load_pinned(ROOT); plan = base_plan(); store = h.store
        spec = {'node_count': 4, 'paths': (
            ('no_hit_text', 'template', 'whole', tool.ORIGINAL, tool.MODIFIED),
            ('faq_llm', 'system_prompt', 'contains', tool.ORIGINAL, tool.MODIFIED))}
        task_id, boundary = scenario(h, store, pinned, plan, spec, tmp, 'success',
                                     json.dumps(candidate(plan)), {'prompt_tokens': 10, 'completion_tokens': 20}, ok=True)
        assert h.get_task(task_id)['workflow_plan'] == plan
        rejected(lambda: boundary.prepare({'id': 'synthetic-provider'}, 'FAKE385', [{'role': 'user', 'content': 'x'}],
                                          {'max_tokens': 6000, 'timeout': 120, 'json_mode': True}), 'second call')
        scenario(h, store, pinned, plan, spec, tmp, 'unknown-usage', json.dumps(candidate(plan)), {},
                 expected=(ProviderError, RuntimeError),
                 reasons=('模型用量未知', 'did not stop at replanning_review', 'planning run missing'))
        budget = store.get('task_budget', 'synthetic-unknown-usage')
        assert budget['entries'][-1]['status'] == 'unknown'
        scenario(h, store, pinned, plan, spec, tmp, 'bad-json', '{"bad":', {'prompt_tokens': 10, 'completion_tokens': 20},
                 reasons=('did not stop at replanning_review', 'planning run missing'))
        scenario(h, store, pinned, plan, spec, tmp, 'extra-field', json.dumps(candidate(plan, extra=True)),
                 {'prompt_tokens': 10, 'completion_tokens': 20},
                 reasons=('candidate', 'did not stop at replanning_review'))
        scenario(h, store, pinned, plan, spec, tmp, 'second-request', '{"bad":',
                 {'prompt_tokens': 10, 'completion_tokens': 20}, retries=1,
                 reasons=('No second model call', 'budget may append at most one entry',
                          'did not stop at replanning_review', 'planning run missing'))


def test_cli_rejection():
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / 'missing-project'
        result = subprocess.run([sys.executable, tool.__file__, '--project', str(missing), 'run'],
                                capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert 'stopped:' in output
        assert 'Traceback' not in output
        assert not missing.exists()


def main():
    tests = (test_source_and_pin, test_sealed_and_roots, test_authorization_and_interlock,
             test_candidate_diff_and_runtime, test_guarded_store, test_normal_api, test_cli_rejection)
    for test in tests:
        test(); print('ok', test.__name__)
    print('isolated-modification385 synthetic checks passed')


if __name__ == '__main__':
    main()
