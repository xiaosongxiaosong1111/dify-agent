"""Isolated single-sentence batch 385: no import-time action; prepare reads production read-only; approve binds an external direct-user reply; run is the only key-decrypting single model request. Production Task/artifact/ZIP/credentials and old work/data stay unchanged."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
BATCH = 'isolated-modification385'
TASK = '1154f0c0-5e01-4492-b5c7-97bfbbbc2a61'
SOURCE_REVISION = 8
SOURCE_TASK_SHA = 'df157950695c641990aa4ef3fa2fff130b05c43f150633a1809f08103b17a5c7'
SOURCE_BUDGET_SHA = 'b2472f1c98a48418bded9a9a73c776a14cc0b56bf0a6f04c21d87b2fea94bad0'
SOURCE_PLAN_SHA = 'dd71f629c0d6a1e82d8e88aa424341fbe751369fbe0cedf19a9f1b5f44198c69'
ORIGINAL = '知识库暂无相关信息，请联系人工客服。'
MODIFIED = '知识库暂无相关信息，请联系人工客服并提供商品型号。'
NODE_PATHS = (('no_hit_text', 'template', 'whole'), ('faq_llm', 'system_prompt', 'contains'))
NODE_COUNT = 23
PIN_377 = 'ec8d7b706fb12b98230eb1ec33e14933d5fcb2e9'
OLD_REFS = {'call_f5b63df1752f441284ac9ee97f031930/q0',
            'call_653c3204d2c842648bbfaddba3d298b4/q0',
            'call_a7ee288e3a8b474b8b8d3dbc99c2f729/q0'}
APPROVAL_PHRASE = '允许将375剩余一槽及0.100 USD预留明确改授385隔离改版批'
LIMITS = {'model_calls': 1, 'output_tokens': 6000, 'timeout_seconds': 120,
          'per_call_usd': '0.100', 'model_http': 1, 'physical_http': 1,
          'production_writes': 0, 'dify': 0, 'login': 0, 'resources': 0, 'runs': 0}
SEAL_377_PLAN = 'work/preserved-planning377/plan.json'
SEAL_377_STOP = 'work/preserved-planning377/seal-after-stop.json'
SEAL_380 = 'work/reviewed-planning380/seal-after-review.json'
SEAL_SHAS = {SEAL_377_PLAN: '8ef81075e59a60b9544e0c188e052c07c3bdd5ba3ae08ecbae2dc93564ec2c9f',
             SEAL_377_STOP: '541fe1d45a1ef7b9fa1473a8abef8ff72140761a3c2df5145160b51c7e75e8da',
             SEAL_380: 'a0166d894fefdb95ae4c841e1033e929975452776dcf3d84cd6317d97875bd2c'}
SEAL_COUNTS = (859, 874, 892)
ROOT_PLAN = 'work/autonomous-dual375/plan.json'
SOURCE_FILES = ('tool.py', 'checks.py', 'README.md')
PACKAGE_FILES = ('tool.py', 'checks.py', 'README.md', 'source-pins.json', 'plan.json', 'protected-892.json')
RUNTIME_BUILD = '0.412.0-4b3c27aad0a80a616364'
RUNTIME_VERSION = '0.412.0'
RUNTIME_SOURCE_COUNT = 298
RUNTIME_CONTENT_SHA = '4b3c27aad0a80a61636444f6705c5446092e02996842c3603cc7c4eb4165be6b'
RUNTIME_HOST = '127.0.0.1'
RUNTIME_PORT = '8765'
SECRET_FIELDS = ('api_key', 'console_token', 'csrf_token', 'service_api_key', 'dataset_api_key')
TREE_IGNORE = {'flowcraft.sqlite3-shm', 'flowcraft.sqlite3-wal', 'server.pid',
               'server.out.log', 'server.err.log'}
SPEC = {'node_count': NODE_COUNT,
        'paths': tuple((node, key, mode, ORIGINAL, MODIFIED) for node, key, mode in NODE_PATHS)}
DEFAULT_EXPECTED = {'task_sha256': SOURCE_TASK_SHA, 'budget_sha256': SOURCE_BUDGET_SHA,
                    'plan_sha256': SOURCE_PLAN_SHA, 'node_count': NODE_COUNT,
                    'seal_counts': SEAL_COUNTS, 'roots_count': 12}

def require(value, message):
    if not value: raise RuntimeError(message)
def now(): return datetime.now(timezone.utc).isoformat()
def sha_bytes(value): return hashlib.sha256(value).hexdigest()
def sha_file(path): return sha_bytes(Path(path).read_bytes())

def digest(value):
    return sha_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                separators=(',', ':'), allow_nan=False).encode('utf-8'))

def read_json(path, label='JSON'):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), label + ' missing or linked: ' + str(path))
    raw = path.read_bytes()
    try:
        def unique(pairs):
            out = {}
            for key, value in pairs:
                require(key not in out, label + ' has duplicate keys'); out[key] = value
            return out
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RuntimeError(label + ' is not strict UTF-8 JSON') from exc
    return value, raw

def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), 'utf-8')
    os.replace(tmp, path)
def exclusive_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)

def normalize_lf(raw):
    return raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
def _no_links(project, rel):
    require(isinstance(rel, str) and rel and not Path(rel).is_absolute(), 'relative path required')
    require('\x00' not in rel and '..' not in Path(rel).parts, 'path escapes project: ' + rel)
    current = Path(project)
    require(not current.is_symlink(), 'project path is a symlink')
    for part in Path(rel).parts:
        current = current / part
        require(not current.is_symlink(), 'symlink in path refused: ' + str(current))
    return current
def safe_path(project, rel):
    _no_links(project, rel)
    path = Path(project) / rel
    require(path.resolve().is_relative_to(Path(project).resolve()), 'path escapes project: ' + rel)
    return path

def tree_digest(path):
    path = Path(path)
    require(not path.is_symlink(), 'root symlink refused: ' + str(path))
    if path.is_file():
        return {'kind': 'file', 'sha256': sha_file(path), 'bytes': path.stat().st_size}
    require(path.is_dir(), 'root neither file nor directory: ' + str(path))
    rows = []
    for item in sorted(path.rglob('*')):
        require(not item.is_symlink(), 'tree symlink refused: ' + str(item))
        if item.name in TREE_IGNORE:
            continue
        if item.is_file():
            rows.append([item.relative_to(path).as_posix(), sha_file(item), item.stat().st_size])
    return {'kind': 'directory', 'count': len(rows), 'sha256': digest(rows)}

def git(project, *args):
    result = subprocess.run(['git', '-C', str(project), *args], capture_output=True, check=False)
    return result.returncode, result.stdout, result.stderr

def git_blob(project, commit, rel):
    code, out, _ = git(project, 'cat-file', 'blob', commit + ':' + rel)
    require(code == 0, 'Git blob missing: ' + commit + ':' + rel)
    return out

def verify_source(project, source_commit):
    project = Path(project)
    require(isinstance(source_commit, str) and re.fullmatch(r'[0-9a-f]{40}', source_commit or ''),
            'full 40-hex source commit required')
    code, out, _ = git(project, 'rev-parse', '--verify', source_commit + '^{commit}')
    require(code == 0 and out.decode().strip() == source_commit, 'source commit is not the exact commit')
    files = {}
    for name in SOURCE_FILES:
        path = safe_path(project, 'tools/' + BATCH + '/' + name)
        raw = normalize_lf(path.read_bytes())
        blob = normalize_lf(git_blob(project, source_commit, 'tools/' + BATCH + '/' + name))
        require(raw == blob, 'worktree differs from Git blob (LF): ' + name)
        files['tools/' + BATCH + '/' + name] = sha_bytes(raw)
    return {'commit': source_commit, 'files': files, 'line_endings': 'LF'}

def verify_source_binding(project, root, plan):
    project = Path(project); root = Path(root)
    sources = verify_source(project, plan.get('source_commit'))
    require(plan.get('source_files') == sources['files'], 'plan source_files are not the committed three sources')
    for name in SOURCE_FILES:
        rel = 'tools/' + BATCH + '/' + name
        canonical = safe_path(root, name)
        require(canonical.is_file(), 'canonical source missing: ' + name)
        work = normalize_lf(safe_path(project, rel).read_bytes())
        blob = normalize_lf(git_blob(project, plan['source_commit'], rel))
        require(normalize_lf(canonical.read_bytes()) == work == blob, 'canonical source not bound to committed blob: ' + name)
        require(sha_bytes(work) == sources['files'][rel], 'source LF digest changed: ' + name)
    return sources

def load_pinned(project, commit=PIN_377):
    project = Path(project)
    code, out, _ = git(project, 'rev-parse', '--verify', commit + '^{commit}')
    require(code == 0 and out.decode().strip() == commit, 'pinned 377 commit missing')
    folder = project / 'tools/preserved-planning377'
    files = {}
    for name in ('common.py', 'worker.py'):
        path = safe_path(project, 'tools/preserved-planning377/' + name)
        raw = normalize_lf(path.read_bytes())
        blob = normalize_lf(git_blob(project, commit, 'tools/preserved-planning377/' + name))
        require(raw == blob, 'pinned 377 worktree differs (LF): ' + name)
        files[name] = sha_bytes(raw)
    for name in ('common', 'worker'):
        loaded = sys.modules.get(name)
        if loaded and Path(loaded.__file__).resolve() != folder / (name + '.py'):
            raise RuntimeError('module name collision: ' + name)
    sys.path.insert(0, str(folder))
    try:
        common = importlib.import_module('common')
        worker = importlib.import_module('worker')
    finally:
        if sys.path and sys.path[0] == str(folder):
            sys.path.pop(0)
    require(Path(common.__file__).resolve() == folder / 'common.py', 'wrong common module')
    require(Path(worker.__file__).resolve() == folder / 'worker.py', 'wrong worker module')
    require(all(hasattr(common, k) for k in ('ReadOnly', 'capture', 'history_prefix')), '377 common API missing')
    require(hasattr(worker, 'Boundary'), '377 Boundary missing')
    return {'commit': commit, 'files': files, 'common': common, 'worker': worker}
def load_runtime(project, expected_count=RUNTIME_SOURCE_COUNT, expected_build=RUNTIME_BUILD,
                 expected_version=RUNTIME_VERSION, expected_content=RUNTIME_CONTENT_SHA):
    project = Path(project)
    root = safe_path(project, '.runtime/snapshots/' + expected_build)
    require(root.is_dir(), 'runtime snapshot missing')
    manifest_path = next((p for p in (root / 'runtime-manifest.json', root / 'backend/runtime-manifest.json') if p.is_file()), None)
    require(manifest_path is not None, 'runtime manifest missing')
    manifest, raw = read_json(manifest_path, 'runtime manifest')
    build = manifest.get('build_id') or manifest.get('build') or manifest.get('snapshot')
    require(build == expected_build, 'runtime build mismatch')
    version = manifest.get('version') or manifest.get('app_version')
    require(version == expected_version, 'runtime version mismatch')
    files = manifest.get('files')
    require(isinstance(files, dict) and len(files) == expected_count, 'runtime source count mismatch')
    content = manifest.get('content_sha256') or manifest.get('snapshot_sha256') or manifest.get('sha256')
    require(content == expected_content, 'runtime content SHA changed')
    for rel, value in files.items():
        require(isinstance(rel, str) and isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value), 'runtime file entry invalid')
        snapshot_file = safe_path(root, rel); project_file = safe_path(project, rel)
        require(snapshot_file.is_file() and project_file.is_file(), 'runtime source file missing: ' + rel)
        require(sha_file(snapshot_file) == value and sha_file(project_file) == value,
                'runtime snapshot/project source differs: ' + rel)
    backend = root / 'backend'
    require(backend.is_dir() and not backend.is_symlink(), 'runtime backend missing')
    return {'build': build, 'version': version, 'file_count': len(files),
            'content_sha256': content, 'manifest_sha256': sha_bytes(raw),
            'backend': str(backend), 'root': str(root)}
def _norm_path(value):
    return os.path.normcase(str(Path(value).resolve())).replace('\\', '/')
def runtime_process_matches(exe, argv, backend, venv, host=RUNTIME_HOST, port=RUNTIME_PORT):
    require(isinstance(argv, list) and argv, 'process command line missing')
    require(_norm_path(exe) == _norm_path(venv), 'runtime exe is not the original venv')
    require('uvicorn' in argv and 'app.main:app' in argv, 'runtime is not the expected uvicorn app')
    value = None
    for index, token in enumerate(argv):
        if token == '--app-dir' and index + 1 < len(argv): value = argv[index + 1]
        elif token.startswith('--app-dir='): value = token.split('=', 1)[1]
    require(value is not None and _norm_path(value) == _norm_path(backend), 'runtime app-dir is not the fixed snapshot')
    def flag(name):
        for index, token in enumerate(argv):
            if token == name and index + 1 < len(argv): return argv[index + 1]
            if token.startswith(name + '='): return token.split('=', 1)[1]
        return None
    require(flag('--host') == host and flag('--port') == port, 'runtime host/port mismatch')
    return True
def _split_command_line(text):
    import shlex
    return [value.strip('"') for value in shlex.split(text, posix=False)]
def _process_facts(pid):
    try:
        import psutil
        process = psutil.Process(pid)
        return process.exe(), list(process.cmdline())
    except Exception:
        pass
    script = ('Get-CimInstance Win32_Process -Filter "ProcessId=' + str(pid) +
              '" | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress')
    try:
        result = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, check=False, timeout=20)
    except subprocess.TimeoutExpired:
        raise RuntimeError('CIM process query timed out') from None
    require(result.returncode == 0 and result.stdout.strip(), 'CIM process query failed')
    value = json.loads(result.stdout.decode('utf-8'))
    require(isinstance(value, dict) and value.get('ExecutablePath') and value.get('CommandLine'), 'CIM process facts missing')
    return value['ExecutablePath'], _split_command_line(value['CommandLine'])
def verify_runtime_process(project, backend, venv=None):
    venv = Path(venv) if venv else Path(project) / '.venv/Scripts/python.exe'
    pid = int(safe_path(project, 'data/server.pid').read_text('utf-8').strip())
    exe, argv = _process_facts(pid)
    runtime_process_matches(exe, argv, backend, venv)
    return {'pid': pid, 'exe': exe, 'argv_sha256': sha_bytes(json.dumps(argv, ensure_ascii=False).encode('utf-8'))}

def _merge(target, source):
    for rel, value in source.items():
        if rel in target and target[rel] != value:
            raise RuntimeError('sealed map conflict: ' + rel)
        target[rel] = value

def _seal_map(project, rel, prefix, expected_sha=None):
    path = safe_path(project, rel)
    value, raw = read_json(path, rel)
    require(isinstance(value, dict), rel + ' must be a mapping')
    if expected_sha is not None:
        require(sha_bytes(raw) == expected_sha, rel + ' SHA changed')
    out = {}
    for key, value_sha in value.items():
        require(isinstance(key, str) and key and isinstance(value_sha, str) and
                re.fullmatch(r'[0-9a-f]{64}', value_sha), rel + ' has invalid member')
        require(not Path(key).is_absolute() and '..' not in Path(key).parts and key != rel,
                rel + ' member path invalid')
        out[prefix + key] = value_sha
    out[prefix + path.name] = sha_bytes(raw)
    return out

def verify_sealed(project, counts=SEAL_COUNTS, expected_shas=SEAL_SHAS):
    project = Path(project)
    expected_shas = expected_shas or {}
    plan, raw = read_json(safe_path(project, SEAL_377_PLAN), SEAL_377_PLAN)
    if expected_shas.get(SEAL_377_PLAN):
        require(sha_bytes(raw) == expected_shas[SEAL_377_PLAN], SEAL_377_PLAN + ' SHA changed')
    protected = plan.get('protected_files')
    require(isinstance(protected, dict) and len(protected) == counts[0],
            'protected map count is not ' + str(counts[0]))
    merged = {}
    for rel, value in protected.items():
        require(isinstance(rel, str) and isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value),
                'protected member invalid')
        _merge(merged, {rel: value})
    _merge(merged, _seal_map(project, SEAL_377_STOP, 'work/preserved-planning377/',
                             expected_shas.get(SEAL_377_STOP)))
    require(len(merged) == counts[1], 'protected+377 stop count is not ' + str(counts[1]))
    _merge(merged, _seal_map(project, SEAL_380, 'work/reviewed-planning380/',
                             expected_shas.get(SEAL_380)))
    require(len(merged) == counts[2], 'final sealed count is not ' + str(counts[2]))
    for rel, value in merged.items():
        path = safe_path(project, rel)
        require(path.is_file(), 'sealed file missing: ' + rel)
        require(sha_file(path) == value, 'sealed SHA changed: ' + rel)
    return merged

def _root_fingerprint(project, rel, common):
    path = safe_path(project, rel)
    require(path.exists(), 'isolated root missing: ' + rel)
    if path.is_dir() and (path / 'flowcraft.sqlite3').is_file():
        return {'kind': 'sqlite', 'capture': common.capture(common.ReadOnly(path))}
    return {'kind': 'tree', 'digest': tree_digest(path)}
def load_roots(project, common, expected_isolated=11, expected_count=12):
    project = Path(project)
    plan, _ = read_json(safe_path(project, ROOT_PLAN), ROOT_PLAN)
    paths = plan.get('isolated_paths')
    if isinstance(paths, dict):
        require(all(isinstance(k, str) and isinstance(v, str) and v for k, v in paths.items()), 'isolated_paths map invalid')
        paths = list(paths.values())
    require(isinstance(paths, list) and len(paths) == expected_isolated and len(set(paths)) == len(paths),
            'isolated_paths is not ' + str(expected_isolated) + ' unique paths')
    roots = {rel: _root_fingerprint(project, rel, common) for rel in paths}
    require('data' not in roots, 'isolated_paths already contains data root')
    roots['data'] = _root_fingerprint(project, 'data', common)
    require(len(roots) == expected_count, 'root count is not ' + str(expected_count))
    return roots
def verify_roots(project, expected, common, expected_count=12):
    require(isinstance(expected, dict), 'expected roots missing')
    current = load_roots(project, common, expected_isolated=expected_count - 1, expected_count=expected_count)
    require(current == expected, '12 protected roots changed')
    return current

def artifact_info(project, data_dir, task):
    artifact = task.get('artifact'); require(isinstance(artifact, dict), 'source artifact missing')
    require(artifact.get('revision') == task.get('revision'), 'artifact revision differs')
    filename = artifact.get('filename'); require(isinstance(filename, str) and filename and Path(filename).name == filename, 'artifact name invalid')
    folder = safe_path(project, 'data/' + task['id']); path = folder / filename
    require(path.resolve().parent == folder.resolve() and not path.is_symlink(), 'artifact path invalid')
    require(path.is_file() and sha_file(path) == artifact.get('sha256'), 'artifact file/SHA invalid')
    return {'filename': filename, 'sha256': artifact.get('sha256'), 'revision': artifact.get('revision')}

def diff_paths(left, right, path=()):
    out = []
    if type(left) is not type(right):
        return [(path, left, right)]
    if isinstance(left, dict):
        if set(left) != set(right):
            return [(path, left, right)]
        for key in sorted(left):
            out.extend(diff_paths(left[key], right[key], path + (key,)))
    elif isinstance(left, list):
        if len(left) != len(right):
            return [(path, left, right)]
        for index, (a, b) in enumerate(zip(left, right)):
            out.extend(diff_paths(a, b, path + (index,)))
    elif left != right:
        out.append((path, left, right))
    return out

def check_candidate(baseline, candidate, spec=SPEC):
    require(isinstance(baseline, dict) and isinstance(candidate, dict), 'plans must be objects')
    require([n.get('id') for n in candidate.get('nodes', [])] ==
            [n.get('id') for n in baseline.get('nodes', [])], 'node identities changed')
    require(len(candidate.get('nodes', [])) == spec['node_count'], 'candidate node count differs')
    expected = []
    for node_id, key, mode, old, new in spec['paths']:
        matches = [i for i, node in enumerate(baseline['nodes']) if node.get('id') == node_id]
        require(len(matches) == 1, 'baseline node missing: ' + node_id)
        index = matches[0]
        before = baseline['nodes'][index].get('config', {}).get(key)
        require(isinstance(before, str), 'baseline sentence field missing at ' + node_id + '.' + key)
        require((before == old) if mode == 'whole' else (before.count(old) == 1),
                'baseline sentence ' + ('mis-matched' if mode == 'whole' else 'not exactly once') + ' at ' + node_id + '.' + key)
        after = new if mode == 'whole' else before.replace(old, new, 1)
        require(candidate['nodes'][index].get('config', {}).get(key) == after,
                'candidate sentence wrong at ' + node_id + '.' + key)
        expected.append((('nodes', index, 'config', key), before, after))
    actual = diff_paths(baseline, candidate)
    require(len(actual) == len(expected), 'candidate has extra or missing changes')
    for path, old, new in actual:
        require(any(path == p and old == o and new == n for p, o, n in expected),
                'candidate change outside allowed two fields: ' + repr(path))
    return {'node_count': spec['node_count'],
            'paths': [{'path': list(p), 'old': o, 'new': n} for p, o, n in actual]}

def _strip_secrets(value):
    if isinstance(value, dict):
        return {k: _strip_secrets(v) for k, v in value.items() if k not in SECRET_FIELDS}
    if isinstance(value, list):
        return [_strip_secrets(v) for v in value]
    return copy.deepcopy(value)

def _replace_once_strings(value, old, new):
    if isinstance(value, str):
        count = value.count(old); require(count <= 1, 'multiple target-sentence occurrences in one value')
        return value.replace(old, new, 1), count
    if isinstance(value, dict):
        out = {}; total = 0
        for key, item in value.items():
            out[key], count = _replace_once_strings(item, old, new); total += count
        return out, total
    if isinstance(value, list):
        out = []; total = 0
        for item in value:
            changed, count = _replace_once_strings(item, old, new); out.append(changed); total += count
        return out, total
    return copy.deepcopy(value), 0
def _sync_sample(task):
    rows = task.get('test_cases') or []
    matches = [i for i, row in enumerate(rows) if isinstance(row, dict) and
               json.dumps(row.get('expectation', row.get('expected')), ensure_ascii=False).count(ORIGINAL)]
    require(len(matches) == 1, 'faq-no-answer expectation is not unique')
    row = rows[matches[0]]; key = 'expectation' if 'expectation' in row else 'expected'
    before = copy.deepcopy(row.get(key)); after, count = _replace_once_strings(before, ORIGINAL, MODIFIED)
    require(count == 1, 'faq-no-answer expectation must contain the sentence exactly once')
    row[key] = after
    return {'index': matches[0], 'key': key, 'before': before, 'after': after}
def canonical_root(project, must_exist=False):
    work = Path(project) / 'work'; require(work.is_dir() and not work.is_symlink(), 'project work directory missing or linked')
    root = work / BATCH
    if must_exist:
        require(root.is_dir() and not root.is_symlink() and root.resolve().parent == work.resolve(), 'canonical work directory missing or linked')
    else:
        require(not root.exists(), 'canonical work directory already exists')
        require(root.resolve().parent == work.resolve(), 'canonical work directory escapes work')
    return root

def prepare(project, source_commit, expected=None, data_dir=None, now_value=None):
    project = Path(project)
    expected = expected or DEFAULT_EXPECTED
    data_dir = Path(data_dir) if data_dir else project / 'data'
    sources = verify_source(project, source_commit)
    pinned = load_pinned(project)
    runtime = load_runtime(project)
    process = verify_runtime_process(project, runtime['backend'])
    if runtime['backend'] not in sys.path:
        sys.path.insert(0, runtime['backend'])
    from app.storage import Store
    reader = pinned['common'].ReadOnly(data_dir)
    task = reader.get('task', TASK)
    budget = reader.get('task_budget', TASK)
    provider = reader.get('provider', (task or {}).get('configuration', {}).get('assistant_provider_id') or '')
    environment = reader.get('environment', (task or {}).get('environment_id') or '')
    require(isinstance(task, dict) and isinstance(budget, dict), 'source Task/budget missing')
    require(isinstance(provider, dict) and isinstance(environment, dict),
            'source provider/environment metadata missing')
    require(task.get('id') == TASK and task.get('revision') == SOURCE_REVISION, 'source Task identity changed')
    require(task.get('status') == 'draft_ready' and task.get('plan_source') == 'manual', 'source Task state changed')
    require(digest(task) == expected['task_sha256'], 'source Task SHA changed')
    require(digest(budget) == expected['budget_sha256'], 'source budget SHA changed')
    plan = task.get('workflow_plan')
    require(isinstance(plan, dict), 'source workflow_plan missing')
    require(len(plan.get('nodes', [])) == expected['node_count'], 'source plan node count changed')
    require(digest(plan) == expected['plan_sha256'], 'source plan SHA changed')
    for node_id, key, mode in NODE_PATHS:
        matches = [n for n in plan['nodes'] if n.get('id') == node_id]
        require(len(matches) == 1 and isinstance(matches[0].get('config', {}).get(key), str), 'source sentence field missing at ' + node_id + '.' + key)
        value = matches[0]['config'][key]
        require((value == ORIGINAL) if mode == 'whole' else (value.count(ORIGINAL) == 1),
                'source sentence ' + ('must equal' if mode == 'whole' else 'must occur exactly once at') + ' ' + node_id + '.' + key)
    artifact = artifact_info(project, data_dir, task)
    captured = pinned['common'].capture(pinned['common'].ReadOnly(data_dir))
    sealed = verify_sealed(project, expected['seal_counts'])
    roots = load_roots(project, pinned['common'], expected_count=expected['roots_count'])
    root = canonical_root(project)
    root.mkdir()
    iso = root / 'isolated-data'
    iso.mkdir()
    store = Store(iso)
    task_copy = _strip_secrets(task)
    for key in ('actions', 'active_interview_id', 'active_image_operation_id'):
        task_copy.pop(key, None)
    output = task_copy.get('requirements', {}).get('output')
    require(isinstance(output, str) and output.count(ORIGINAL) == 1,
            'source requirements.output must contain the target sentence exactly once')
    task_copy['requirements']['output'] = output.replace(ORIGINAL, MODIFIED, 1)
    sample_change = _sync_sample(task_copy)
    intake_record = copy.deepcopy(task_copy.get('intake_review'))
    if intake_record:
        require(isinstance(task_copy.get('intake_history', []), list), 'source intake_history is not a list')
        task_copy.setdefault('intake_history', []).append(intake_record)
    task_copy.update(status='requirements', requirements_confirmed=False,
                     configuration_confirmed=False, intake_required=True, intake_review=None,
                     plan_stale=True, artifact=None, dify_app_id=None)
    clone_changes = {'output': {'before': output, 'after': task_copy['requirements']['output']},
                     'sample': sample_change,
                     'intake_record_preserved_to_history': bool(intake_record)}
    store.put('task', TASK, task_copy)
    store.put('task_budget', TASK, _strip_secrets(budget))
    store.put('provider', provider['id'], _strip_secrets(provider))
    store.put('environment', environment['id'], _strip_secrets(environment))
    atomic_json(root / 'protected-892.json', sealed)
    source_pins = {'source': sources, 'pinned_377': {'commit': pinned['commit'], 'files': pinned['files']},
                   'template': {'original': ORIGINAL, 'modified': MODIFIED,
                                'paths': [list(p) for p in NODE_PATHS]},
                   'runtime': {'build': runtime['build'], 'version': runtime['version'],
                               'file_count': runtime['file_count'],
                               'content_sha256': runtime['content_sha256'],
                               'manifest_sha256': runtime['manifest_sha256'],
                               'process': process}}
    atomic_json(root / 'source-pins.json', source_pins)
    for name in SOURCE_FILES:
        (root / name).write_bytes(safe_path(project, 'tools/' + BATCH + '/' + name).read_bytes())
    value = {'schema_version': 1, 'batch_id': BATCH, 'scope': BATCH,
             'created_at': now_value or now(), 'approval_state': 'pending',
             'source_commit': source_commit, 'source_files': sources['files'],
             'pinned_377': {'commit': pinned['commit'], 'files': pinned['files']},
             'template_pin': {'original': ORIGINAL, 'modified': MODIFIED,
                              'paths': [list(p) for p in NODE_PATHS]},
             'target': {'task_id': TASK, 'source_revision': SOURCE_REVISION,
                        'task_sha256': expected['task_sha256'], 'budget_sha256': expected['budget_sha256'],
                        'plan_sha256': expected['plan_sha256'], 'node_count': expected['node_count'],
                        'provider_id': provider.get('id'), 'environment_id': environment.get('id'),
                        'artifact': artifact},
             'production': {'capture_sha256': digest(captured),
                            'capture_counts': {k: len(v) for k, v in captured.items() if isinstance(v, dict)},
                            'sealed_count': len(sealed), 'sealed_sha256': digest(sealed),
                            'sealed_counts': list(expected['seal_counts']),
                            'roots': roots, 'roots_count': len(roots)},
             'isolated': {'data': 'work/' + BATCH + '/isolated-data',
                          'task_sha256': digest(store.get('task', TASK)),
                          'budget_sha256': digest(store.get('task_budget', TASK)),
                          'clone_changes': clone_changes},
             'runtime': {'build': runtime['build'], 'version': runtime['version'],
                         'file_count': runtime['file_count'],
                         'content_sha256': runtime['content_sha256'],
                         'manifest_sha256': runtime['manifest_sha256'],
                         'backend': runtime['backend'], 'pid': process['pid'],
                         'exe': process['exe'], 'argv_sha256': process['argv_sha256']},
             'backend_path': runtime['backend'],
             'limits': LIMITS, 'approval_phrase': APPROVAL_PHRASE,
             'old_refs': sorted(OLD_REFS), 'expected_candidate': SPEC}
    atomic_json(root / 'plan.json', value)
    files = {name: sha_file(root / name) for name in PACKAGE_FILES}
    manifest = {'schema_version': 1, 'batch_id': BATCH, 'source_commit': source_commit,
                'plan_sha256': sha_file(root / 'plan.json'), 'files': files, 'created_at': now_value or now()}
    atomic_json(root / 'manifest.json', manifest)
    return value

def assert_unconsumed(root):
    require(not any((Path(root) / name).exists() for name in ('attempt.json', 'worker-started.json', 'live-output')),
            'consumption marker already exists')
def external_file(project, path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'external authorization file required')
    require(os.path.normcase(str(path.parent.resolve())) == os.path.normcase(str(path.parent)),
            'authorization parent symlink refused')
    require(not path.resolve().is_relative_to(Path(project).resolve()),
            'authorization file must be outside the project')
    return path
def validate_authorization(auth, plan, plan_sha, manifest_sha):
    require(isinstance(auth, dict), 'authorization must be an object')
    require(auth.get('authorization_source') == 'direct_user_reply', 'direct user reply required')
    require(auth.get('scope') == BATCH, 'scope mismatch')
    ref = auth.get('question_ref')
    require(isinstance(ref, str) and re.fullmatch(r'call_[0-9a-f]{32}/q0', ref), 'new call_ID/q0 required')
    require(ref not in OLD_REFS and all(old not in json.dumps(auth) for old in OLD_REFS), 'old 375/377/380 authorization reference refused')
    require(auth.get('literal') == APPROVAL_PHRASE, 'approval literal mismatch')
    require(auth.get('plan_sha256') == plan_sha and auth.get('manifest_sha256') == manifest_sha, 'plan/manifest binding mismatch')
    require(auth.get('limits') == LIMITS, 'authorization limits mismatch')
    require(auth.get('single_use') is True and auth.get('retry') is False, 'single-use/no-retry required')
    return True

def approve(project, authorization_path):
    project = Path(project)
    root = canonical_root(project, must_exist=True)
    plan, _ = read_json(root / 'plan.json', 'plan')
    manifest, _ = read_json(root / 'manifest.json', 'manifest')
    verify_package(root)
    verify_source_binding(project, root, plan)
    load_pinned(project)
    load_runtime(project)
    require(manifest.get('plan_sha256') == sha_file(root / 'plan.json'), 'manifest/plan mismatch')
    auth, _ = read_json(external_file(project, authorization_path), 'authorization')
    validate_authorization(auth, plan, sha_file(root / 'plan.json'), sha_file(root / 'manifest.json'))
    require(not (root / 'approval.json').exists(), 'approval already exists')
    assert_unconsumed(root)
    approval = {'schema_version': 1, 'batch_id': BATCH, 'authorization_source': 'direct_user_reply',
                'scope': BATCH, 'question_ref': auth['question_ref'], 'literal': APPROVAL_PHRASE,
                'plan_sha256': sha_file(root / 'plan.json'),
                'manifest_sha256': sha_file(root / 'manifest.json'), 'limits': LIMITS,
                'single_use': True, 'retry': False, 'created_at': now()}
    exclusive_json(root / 'approval.json', approval)
    return approval

def verify_package(root):
    root = Path(root); manifest, _ = read_json(root / 'manifest.json', 'manifest')
    files = manifest.get('files')
    require(isinstance(files, dict) and set(files) == set(PACKAGE_FILES), 'manifest file set changed')
    for name, value in files.items():
        path = root / name
        require(path.is_file() and not path.is_symlink() and sha_file(path) == value, 'package file changed: ' + name)
    require(manifest.get('plan_sha256') == files.get('plan.json'), 'plan digest mismatch')
    return manifest
def verify_approval(root, plan, manifest_sha):
    root = Path(root); approval, _ = read_json(root / 'approval.json', 'approval')
    require(approval.get('batch_id') == BATCH and approval.get('authorization_source') == 'direct_user_reply', 'approval identity changed')
    require(approval.get('scope') == BATCH and approval.get('literal') == APPROVAL_PHRASE, 'approval scope/literal changed')
    require(isinstance(approval.get('question_ref'), str) and re.fullmatch(r'call_[0-9a-f]{32}/q0', approval['question_ref']), 'approval ref invalid')
    require(approval.get('question_ref') not in OLD_REFS, 'old approval reference')
    require(approval.get('limits') == LIMITS and approval.get('single_use') is True and approval.get('retry') is False, 'approval limits/single-use changed')
    require(approval.get('plan_sha256') == sha_file(root / 'plan.json') and approval.get('manifest_sha256') == manifest_sha, 'approval binding changed')
    return approval

class GuardedStore:
    """Run-phase adapter: only the isolated task/task_budget writes and one in-memory key."""
    def __init__(self, base, key, provider_id, task_id):
        self.base, self.key, self.provider_id, self.task_id, self.lock = base, key, provider_id, task_id, base.lock
        initial = base.get('task_budget', task_id)
        require(isinstance(initial, dict) and isinstance(initial.get('entries'), list), 'isolated budget metadata missing')
        self.budget_meta = {k: copy.deepcopy(v) for k, v in initial.items() if k != 'entries'}
        self.budget_prefix = copy.deepcopy(initial['entries'])
    def get(self, kind, item_id): return self.base.get(kind, item_id)
    def list(self, kind): return self.base.list(kind)
    def task_summaries(self): return self.base.task_summaries()
    def _check_budget(self, value):
        require(isinstance(value, dict) and isinstance(value.get('entries'), list), 'budget structure invalid')
        require({k: v for k, v in value.items() if k != 'entries'} == self.budget_meta, 'old budget metadata changed')
        entries = value['entries']
        require(entries[:len(self.budget_prefix)] == self.budget_prefix, 'old budget entries prefix changed')
        require(len(entries) <= len(self.budget_prefix) + 1, 'budget may append at most one entry')
    def put(self, kind, item_id, value):
        require(kind in {'task', 'task_budget'} and item_id == self.task_id, 'run may write only the isolated task/task_budget')
        if kind == 'task_budget': self._check_budget(value)
        return self.base.put(kind, item_id, value)
    def put_many(self, records):
        require(all(kind in {'task', 'task_budget'} and item_id == self.task_id for kind, item_id, _ in records), 'run may write only the isolated task/task_budget')
        for kind, _, value in records:
            if kind == 'task_budget': self._check_budget(value)
        return self.base.put_many(records)
    def has_secret(self, item_id, key): return item_id == self.provider_id and key == 'api_key'
    def secret(self, item_id, key):
        require(item_id == self.provider_id and key == 'api_key', 'other secret access refused')
        return self.key
    def connect(self): raise RuntimeError('raw store connection refused during run')
    def set_secret(self, *args, **kwargs): raise RuntimeError('secret writes refused during run')
    def put_with_secrets(self, *args, **kwargs): raise RuntimeError('secret writes refused during run')
    def put_many_with_secrets(self, *args, **kwargs): raise RuntimeError('secret writes refused during run')
    def delete(self, *args, **kwargs): raise RuntimeError('deletes refused during run')
def known_usage(value):
    return isinstance(value, dict) and (type(value.get('completion_tokens')) is int or type(value.get('output_tokens')) is int)

def install_boundary(h, boundary, output_dir):
    import httpx
    from app.providers import usage_summary, ProviderError
    original_call = h.call_model
    original_async = httpx.AsyncHTTPTransport.handle_async_request
    original_sync = httpx.HTTPTransport.handle_request
    async def model(selected, key, messages, **kwargs):
        require(key == boundary.key, 'wrong provider credential')
        if boundary.phase is None: boundary.begin()
        boundary.prepare(selected, key, messages, kwargs)
        try:
            text, usage = await original_call(selected, key, messages, **{**kwargs, 'require_final_text': True})
        finally:
            boundary.finish()
        require(isinstance(text, str) and text and len(text) <= 100000, 'bounded response required')
        require(key not in text, 'model response contains credential')
        (Path(output_dir) / 'model-response-modified.txt').write_text(text, 'utf-8')
        summary = usage_summary(usage)
        if not known_usage(summary):
            raise ProviderError('模型用量未知，按本批规则停止；原文与占用已保存，不重试。', usage=usage)
        boundary.record['usage'] = summary
        boundary.save()
        return text, usage
    async def intercept(own, request):
        boundary.admit(request)
        boundary.physical()
        return await original_async(own, request)
    def forbidden(*args, **kwargs):
        raise RuntimeError('synchronous or other HTTP refused')
    h.call_model = model
    httpx.AsyncHTTPTransport.handle_async_request = intercept
    httpx.HTTPTransport.handle_request = forbidden
    def restore():
        h.call_model = original_call
        httpx.AsyncHTTPTransport.handle_async_request = original_async
        httpx.HTTPTransport.handle_request = original_sync
    return restore

def _topic_note(topic, task, cfg, types, nodes, req):
    if topic == 'memory': return f"conversation_memory={cfg.get('conversation_memory', False)}；memory_turns={cfg.get('memory_turns')}；本批保持。"
    if topic == 'dialogue': return f"opening_statement={cfg.get('opening_statement', '')!r}；suggested_questions={cfg.get('suggested_questions', [])}；本批保持。"
    if topic == 'retrieval': return f"dataset_ids={cfg.get('dataset_ids', [])}；top_k={cfg.get('retrieval_top_k')}；知识检索节点={'knowledge-retrieval' in types}；本批保持。"
    if topic == 'external': return f"mock_dependencies={cfg.get('mock_dependencies', [])}；bindings={cfg.get('mock_dependency_bindings', [])}；http节点={'http-request' in types}；本批保持，不新增接口。"
    if topic == 'batch': return f"迭代节点={'iteration' in types}；本批保持现有逐项处理，不新增批量。"
    if topic == 'human': return f"人工审核节点={'human-input' in types}；本批保持。"
    if topic == 'trigger': return f"定时入口={'trigger-schedule' in types}；本批保持。"
    if topic == 'loop_policy': return f"循环节点={'loop' in types}；本批保持。"
    if topic == 'document_processing': return f"文档提取节点={'document-extractor' in types}；文件输入={any(n.get('type') == 'start' and n.get('config', {}).get('variables') for n in nodes)}；本批保持。"
    if topic == 'conversation_state': return f"conversation_variables={[{'name': n.get('name'), 'var_type': n.get('var_type'), 'initial_value': n.get('initial_value')} for n in (task.get('workflow_plan') or {}).get('conversation_variables', []) if isinstance(n, dict)]}；本批保持。"
    if topic == 'json_input_scope': return f"start变量类型={[v.get('type') for v in next((n.get('config', {}).get('variables', []) for n in nodes if n.get('type') == 'start'), []) if isinstance(v, dict)]}；本批保持。"
    if topic == 'agent_tools': return f"app_type={task.get('app_type')}；本批不新增工具。"
    if topic == 'batch_outcomes': return f"迭代节点={'iteration' in types}；本批保持现有结果合同。"
    if str(topic).startswith('schedule_'): return f"定时入口={'trigger-schedule' in types}；本批保持现有定时配置。"
    return f"当前requirements.rules={req.get('rules', '')[:2000]}；本批保持现有流程与资源配置，仅改无答案文案。"
def _answers(task, standard, intake=None):
    require(isinstance(standard, list) and standard, 'intake standard missing')
    req = task.get('requirements', {}); cfg = task.get('configuration') or {}
    plan = task.get('workflow_plan') or {}; nodes = [n for n in plan.get('nodes', []) if isinstance(n, dict)]
    types = {n.get('type') for n in nodes}
    review = ((intake or {}).get('record') or {}).get('review') or {}
    details = {r.get('topic'): r.get('detail') for r in review.get('checks', []) if isinstance(r, dict) and r.get('detail')}
    answers = {}
    for row in standard:
        topic = row['id']
        answers[topic] = req[topic] if topic in req else details.get(topic) or _topic_note(topic, task, cfg, types, nodes, req)
    require(all(isinstance(value, str) and value.strip() for value in answers.values()), 'intake answers incomplete')
    return answers

def planning_call(h, task_id, boundary, output_dir, spec=SPEC):
    from fastapi.testclient import TestClient
    client = TestClient(h.app)
    try:
        task = h.get_task(task_id)
        if task.get('intake_required') or not task.get('requirements_confirmed'):
            intake = client.get('/api/tasks/' + task_id + '/intake').json()
            response = client.post('/api/tasks/' + task_id + '/intake/manual', json={
                'revision': task['revision'], 'context_token': intake['context_token'],
                'answers': _answers(task, intake.get('standard'), intake),
                'acknowledge_review': True, 'actor': 'agent_delegated',
                'actor_note': '依据当前requirements/config及原review各主题来源准备，受根委托执行隔离改版核对；这是代理复核，不是模型新访谈或人类签收。'})
            require(response.status_code == 200, 'manual intake rejected with HTTP ' + str(response.status_code))
            task = response.json()
            require(task.get('intake_review', {}).get('source') == 'agent_declared',
                    'manual intake provenance changed')
            response = client.post('/api/tasks/' + task_id + '/confirm',
                                    json={'kind': 'requirements', 'revision': task['revision']})
            require(response.status_code == 200, 'requirements confirmation rejected with HTTP ' + str(response.status_code))
            task = response.json()
        baseline = copy.deepcopy(task.get('workflow_plan'))
        before = copy.deepcopy(h.budgets.get(task_id))
        response = client.post('/api/tasks/' + task_id + '/plan/generate',
                               json={'revision': task['revision']})
        current = h.get_task(task_id)
        operate = (current.get('planning_runs') or [None])[-1]
        require(isinstance(operate, dict), 'planning run missing')
        require(response.status_code == 422 and operate.get('stop_reason') == 'replanning_review',
                'candidate did not stop at replanning_review (HTTP ' + str(response.status_code) + ')')
        candidate = operate.get('last_candidate')
        report = check_candidate(baseline, candidate, spec)
        require(current.get('status') == 'paused', 'task was not paused after retained candidate')
        require(digest(current.get('workflow_plan')) == digest(baseline), 'formal plan was replaced')
        require(len(operate.get('attempts') or []) == 1, 'model call count is not one')
        usage = (operate['attempts'][0] or {}).get('usage')
        require(known_usage(usage), 'planning usage is unknown')
        ledger = h.budgets.get(task_id)
        require(len(ledger.get('entries') or []) == len(before.get('entries') or []) + 1,
                'budget entry count changed by more than one')
        entry = ledger['entries'][-1]
        require(entry.get('status') == 'settled' and entry.get('call_status') == 'returned',
                'budget was not settled')
        require(known_usage(entry.get('usage')), 'budget usage is unknown')
        require(boundary.calls.get('original') == 1 and boundary.record.get('physical_http') == 1,
                'model/physical call count is not one')
        return {'task_id': task_id, 'revision_before': task['revision'],
                'stop_reason': 'replanning_review', 'candidate_sha256': digest(candidate),
                'candidate': report, 'usage': usage, 'budget_entry': entry,
                'model_http_started': 1, 'physical_http': 1, 'automatic_retry': False,
                'intake_source': (h.get_task(task_id).get('intake_review') or {}).get('source'),
                'formal_plan_unchanged': True}
    finally:
        client.close()

def protection_report(project, pinned, plan, data_dir, iso, budget_prefix):
    try:
        capture = pinned['common'].capture(pinned['common'].ReadOnly(data_dir))
        roots = load_roots(project, pinned['common'], expected_count=plan['production']['roots_count'])
        sealed = verify_sealed(project, tuple(plan['production']['sealed_counts']), expected_shas=None)
        from app.storage import Store
        ledger = Store(iso).get('task_budget', TASK)
        prefix_ok = isinstance(ledger, dict) and isinstance(ledger.get('entries'), list) and ledger['entries'][:len(budget_prefix)] == budget_prefix
        return {'production_capture_sha256': digest(capture), 'production_capture_unchanged': digest(capture) == plan['production']['capture_sha256'],
                'roots_unchanged': roots == plan['production']['roots'], 'sealed_sha256': digest(sealed),
                'sealed_unchanged': digest(sealed) == plan['production']['sealed_sha256'], 'isolated_budget_prefix_unchanged': prefix_ok}
    except BaseException as exc:
        return {'error': type(exc).__name__, 'message': 'protection recheck failed'}
def failure_class(exc):
    name = type(exc).__name__
    return {'ProviderError': 'provider_error', 'HTTPException': 'api_rejected',
            'PlanningStopped': 'planning_stopped', 'RuntimeError': 'boundary_stopped'}.get(name, 'unclassified_failure')
def safe_failure(exc, key=None):
    kind = failure_class(exc)
    reason = {'provider_error': '模型请求或用量的供应商错误；完整响应、已知或 unknown 用量已保存在专用文件/账本。',
              'api_rejected': '正常产品 API 在准入或静态条件阶段拒绝。',
              'planning_stopped': '规划按停止规则结束，未重试。',
              'boundary_stopped': '隔离边界、候选校验或预算前缀检查停止。',
              'unclassified_failure': '未分类本机失败；未打印供应商正文或 Key。'}[kind]
    if key and key in reason:
        reason = reason.replace(key, '[redacted]')
    return {'failure_type': kind, 'failure_reason': reason}

def run(project):
    project = Path(project)
    root = canonical_root(project, must_exist=True)
    verify_package(root)
    plan, _ = read_json(root / 'plan.json', 'plan')
    require(plan.get('batch_id') == BATCH and plan.get('approval_state') == 'pending', 'plan identity changed')
    verify_source_binding(project, root, plan)
    pinned = load_pinned(project)
    runtime = load_runtime(project)
    process = verify_runtime_process(project, runtime['backend'])
    require(plan.get('runtime', {}).get('build') == runtime['build'] and
            plan.get('runtime', {}).get('version') == runtime['version'] and
            plan.get('runtime', {}).get('file_count') == runtime['file_count'] and
            plan.get('runtime', {}).get('content_sha256') == runtime['content_sha256'] and
            plan.get('runtime', {}).get('manifest_sha256') == runtime['manifest_sha256'] and
            plan.get('runtime', {}).get('pid') == process['pid'] and
            plan.get('runtime', {}).get('exe') == process['exe'] and
            plan.get('runtime', {}).get('argv_sha256') == process['argv_sha256'], 'runtime identity changed')
    verify_approval(root, plan, sha_file(root / 'manifest.json'))
    assert_unconsumed(root)
    data_dir = project / 'data'
    reader = pinned['common'].ReadOnly(data_dir)
    task = reader.get('task', TASK); budget = reader.get('task_budget', TASK)
    provider = reader.get('provider', plan['target'].get('provider_id') or '')
    require(isinstance(task, dict) and isinstance(budget, dict) and isinstance(provider, dict), 'production metadata missing')
    require(digest(task) == plan['target']['task_sha256'], 'production Task changed')
    require(digest(budget) == plan['target']['budget_sha256'], 'production budget changed')
    require(digest(task.get('workflow_plan')) == plan['target']['plan_sha256'], 'production plan changed')
    artifact = artifact_info(project, data_dir, task)
    require(artifact['sha256'] == plan['target']['artifact']['sha256'], 'artifact changed')
    before = pinned['common'].capture(pinned['common'].ReadOnly(data_dir))
    require(digest(before) == plan['production']['capture_sha256'], 'production capture changed')
    sealed = verify_sealed(project, tuple(plan['production']['sealed_counts']), expected_shas=None)
    require(digest(sealed) == plan['production']['sealed_sha256'], 'sealed 892 changed')
    roots = load_roots(project, pinned['common'], expected_count=plan['production']['roots_count'])
    require(roots == plan['production']['roots'], '12 roots changed')
    iso = safe_path(project, plan['isolated']['data'])
    if runtime['backend'] not in sys.path:
        sys.path.insert(0, runtime['backend'])
    os.environ['FLOWCRAFT_DATA_DIR'] = str(iso)
    from cryptography.fernet import Fernet
    from app.storage import Store
    isolated = Store(iso)
    isolated_task = isolated.get('task', TASK); isolated_budget = isolated.get('task_budget', TASK)
    require(isinstance(isolated_task, dict) and isinstance(isolated_budget, dict), 'isolated data missing')
    require(digest(isolated_task) == plan['isolated']['task_sha256'], 'isolated Task changed')
    require(digest(isolated_budget) == plan['isolated']['budget_sha256'], 'isolated budget changed')
    budget_prefix = copy.deepcopy(isolated_budget.get('entries') or [])
    output = root / 'live-output'; require(not output.exists(), 'live-output already exists'); output.mkdir()
    attempt = {'schema_version': 1, 'batch_id': BATCH, 'state': 'admitted', 'approval_sha256': sha_file(root / 'approval.json'), 'plan_sha256': sha_file(root / 'plan.json'), 'manifest_sha256': sha_file(root / 'manifest.json'), 'created_at': now(), 'automatic_retry': False}
    exclusive_json(root / 'attempt.json', attempt)
    exclusive_json(root / 'worker-started.json', {'pid': os.getpid(), 'plan_sha256': sha_file(root / 'plan.json'), 'single_worker': True})
    record = {'batch': BATCH, 'mode': 'live', 'external_role': 'modified', 'internal_stage_label': 'original',
              'model_http_started': 0, 'physical_http': 0, 'automatic_retry': False,
              'json_repair_http': 0, 'second_model_call': False, 'responses': {}, 'usage': None}
    atomic_json(output / 'progress.json', record)
    try:
        reader.cipher = Fernet((data_dir / '.credential-key').read_bytes())
        key = Store.secret(reader, provider['id'], 'api_key')
        require(bool(key), 'provider key missing')
        from app import main as h
        require(Path(h.DATA_ROOT).resolve() == iso.resolve(), 'product data root is not isolated')
        require(h.store.get('task', TASK) is not None, 'product isolated Task missing')
        guarded = GuardedStore(isolated, key, provider['id'], TASK)
        h.store = guarded; h.DATA_ROOT = iso
        h.get_settings = lambda response=None: {'max_retries': 0, 'max_minutes': 2, 'max_cost_usd': 0.100}
        boundary = pinned['worker'].Boundary(provider, key, record,
                                             lambda: atomic_json(output / 'progress.json', record),
                                             output / 'stop.json', True)
        restore = install_boundary(h, boundary, output)
        try:
            result = planning_call(h, TASK, boundary, output)
        finally:
            restore()
        after = pinned['common'].capture(pinned['common'].ReadOnly(data_dir))
        require(digest(after) == digest(before), 'production capture changed during run')
        sealed_after = verify_sealed(project, tuple(plan['production']['sealed_counts']), expected_shas=None)
        require(digest(sealed_after) == plan['production']['sealed_sha256'], 'sealed 892 changed during run')
        roots_after = load_roots(project, pinned['common'], expected_count=plan['production']['roots_count'])
        require(roots_after == plan['production']['roots'], '12 roots changed during run')
        ledger = Store(iso).get('task_budget', TASK)
        require(isinstance(ledger, dict) and ledger.get('entries', [])[:len(budget_prefix)] == budget_prefix,
                'isolated budget prefix changed during run')
        result.update({'production_preserved': True, 'sealed_892_count': plan['production']['sealed_count'],
                       'roots_count': plan['production']['roots_count'], 'official_task_unchanged': True,
                       'external_role': 'modified', 'internal_stage_label': 'original'})
        atomic_json(output / 'result.json', result)
        attempt.update(state='passed', result_sha256=digest(result), completed_at=now())
        atomic_json(root / 'attempt.json', attempt)
        return result
    except BaseException as exc:
        failure = safe_failure(exc, locals().get('key'))
        protection = protection_report(project, pinned, plan, data_dir, iso, budget_prefix)
        attempt.update(state='stopped', failure_type=failure['failure_type'],
                       failure_reason=failure['failure_reason'],
                       protection=protection, completed_at=now())
        atomic_json(root / 'attempt.json', attempt)
        atomic_json(output / 'failure.json', {'state': 'stopped', 'failure_type': failure['failure_type'],
                                              'failure_reason': failure['failure_reason'],
                                              'protection': protection})
        raise

def main(argv=None):
    parser = argparse.ArgumentParser(description='isolated-modification385: no default side effect')
    parser.add_argument('--project', default=r'E:\workSpace\dify-agent')
    sub = parser.add_subparsers(dest='command')
    prepare_parser = sub.add_parser('prepare', help='read production once and create isolated package')
    prepare_parser.add_argument('--source-commit', required=True)
    approve_parser = sub.add_parser('approve', help='bind an external direct-user reply')
    approve_parser.add_argument('--authorization', required=True)
    sub.add_parser('run', help='single approved attempt; consumes the batch')
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        if args.command == 'prepare':
            prepare(args.project, args.source_commit)
        elif args.command == 'approve':
            approve(args.project, args.authorization)
        elif args.command == 'run':
            run(args.project)
    except Exception as exc:
        print('stopped:', failure_class(exc))
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
