"""Deterministic derivation of reviewed-planning380 from the pinned 377 sources.

Trust chain: a full Git commit id, five normalized-LF origin SHA256 values, an
ordered exact-count replacement table, forbidden-string gate checks, compile
checks and four final derived SHA256 constants.  Nothing here executes product
code, imports backend modules, reads data/work payloads, or talks to any network.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
ORIGIN_COMMIT = 'ec8d7b706fb12b98230eb1ec33e14933d5fcb2e9'
ORIGIN_DIR = 'tools/preserved-planning377'
ORIGIN_FILES = ('common.py', 'worker.py', 'tool.py', 'checks.py', 'README.md')
ORIGIN_SHA = {
    "common.py": "3bbf5466b61a16f225a4cd55f192183907a8099b5c74d11c0e403a99a96bfcd1",
    "worker.py": "cf0ba4b289d6005dcf15f5487696f285c4578da49a3b91e7904a29ac69ec1a91",
    "tool.py": "084cbd011b9cf84129f08c57ebf6aa3c7ee9aa1dffa790041f2e8b223baa64d2",
    "checks.py": "5840b94b4780d09e5939abb214ad4490a586cd6b2074ccc4d35428e86a9d4cc7",
    "README.md": "2bdf8c05e1cb9d3afac4cb7f5b1e23420b064ed65f91cfbc00a0b79145cbabaf",
}
DERIVED_FILES = ('common.py', 'worker.py', 'tool.py', 'checks.py')
TRACKER_DIR = 'tools/reviewed-planning380'
TRACKER_FILES = ('derive.py', 'run_checks.py', 'README.md')
WORK_ROOT = 'work/reviewed-planning380'

# Frozen after the first --print-sha run and committed with the tracker sources.
DERIVED_SHA = {
    'common.py': '395c31937b730f3877779e192dd0bc7808940d5ff3d00d21cd181ed8ddf72387',
    'worker.py': 'c4c80571b12b444021a394aaaaa480d3ca9201144100e7da4720a585eb1272f1',
    'tool.py': '251df52f4c6f8bdca5533673804c752d60eb6d460ffff2500b40338f16ae1fc4',
    'checks.py': '0fd7ce4a4feb815d90fb9c74c1e86bb2737caaef58e805bae04a358ea5e4ccf9',
}


def _require(value, message):
    if not value:
        raise RuntimeError(message)


def _sha_bytes(value):
    _require(isinstance(value, bytes), 'Digest input is not bytes')
    return hashlib.sha256(value).hexdigest()


def _norm(raw):
    _require(isinstance(raw, bytes), 'Source is not bytes')
    return raw.replace(b'\r\n', b'\n')


# Each operation is (label, old, new, expected_count).  old/new are UTF-8 text.
OPS = {
    'common.py': [
        ('batch and canonical',
         "PROJECT = Path(__file__).resolve().parents[2]\n"
         "BATCH = 'preserved-planning377'\n"
         "CANONICAL = Path(r'E:\\workSpace\\dify-agent\\work\\preserved-planning377')\n",
         "PROJECT = Path(__file__).resolve().parents[2]\n"
         "BATCH = 'reviewed-planning380'\n"
         "CANONICAL = Path(r'E:\\workSpace\\dify-agent\\work\\reviewed-planning380')\n",
         1),
        ('managed runtime identity',
         "RUNTIME_BUILD = '0.411.0-90c28f738d4306fbff75'\n"
         "RUNTIME_VERSION = '0.411.0'\n"
         "RUNTIME_FILE_COUNT = 298\n"
         "RUNTIME_PID_OBSERVED = 12020\n",
         "RUNTIME_BUILD = '0.412.0-4b3c27aad0a80a616364'\n"
         "RUNTIME_VERSION = '0.412.0'\n"
         "RUNTIME_FILE_COUNT = 298\n"
         "RUNTIME_PID_OBSERVED = 34736\n",
         1),
        ('budget ledger baseline',
         "SETTLED_TOTAL = '0.020125524'\nOLD_ENTRY_COUNT = 3\n",
         "SETTLED_TOTAL = '0.023166216'\nOLD_ENTRY_COUNT = 4\n",
         1),
        ('approval literal',
         "APPROVAL_PHRASE = '允许将375剩余一槽及0.100 USD预留明确改授本次单规划批'\n",
         "APPROVAL_PHRASE = '允许将375剩余一槽及0.100 USD预留明确改授380单规划批'\n",
         1),
        ('retired old ref',
         "OLD_REFS = {\n",
         "OLD_REFS = {\n    'call_653c3204d2c842648bbfaddba3d298b4/q0',\n",
         1),
        ('seal identity',
         "OLD_375_PLAN_SHA = "
         "'5b1edcd51cfb54415a3a555089368efe26a8b93ce518cfdf305a794e6af43f97'\n"
         "SEAL_INDEX_SHA = "
         "'e3daff9307529b626b003d081035a601d9cc81f9a2420d88f2ddd6593fb4cdb6'\n"
         "OLD_MAP_COUNT = 831\nSEAL_ENTRY_COUNT = 27\nTOTAL_SEALED_COUNT = 859\n",
         "OLD_PLAN_SHA = "
         "'8ef81075e59a60b9544e0c188e052c07c3bdd5ba3ae08ecbae2dc93564ec2c9f'\n"
         "SEAL_INDEX_SHA = "
         "'541fe1d45a1ef7b9fa1473a8abef8ff72140761a3c2df5145160b51c7e75e8da'\n"
         "OLD_MAP_COUNT = 859\nSEAL_ENTRY_COUNT = 14\nTOTAL_SEALED_COUNT = 874\n",
         1),
        ('prior package paths',
         "OLD_375_ATTEMPT = 'work/autonomous-dual375/attempt.json'\n",
         "OLD_375_ATTEMPT = 'work/autonomous-dual375/attempt.json'\n"
         "PRIOR_DIR = 'work/preserved-planning377'\n"
         "PRIOR_PROGRESS = 'work/preserved-planning377/live-output/progress.json'\n"
         "PRIOR_RESULT = 'work/preserved-planning377/live-output/result.json'\n"
         "PRIOR_ATTEMPT = 'work/preserved-planning377/attempt.json'\n"
         "PRIOR_APPROVAL = 'work/preserved-planning377/approval.json'\n"
         "OLD_375_APPROVAL = 'work/autonomous-dual375/approval.json'\n",
         1),
        ('seal key prefix',
         "        result[OLD_375_DIR + '/' + name] = value_sha\n",
         "        result[PRIOR_DIR + '/' + name] = value_sha\n",
         1),
        ('seal key message',
         "'375 seal must be a 27-entry relative map'",
         "'prior seal must be a 14-entry relative map'",
         1),
        ('merge old map message',
         "'Old 831 map changed'", "'Old 859 map changed'", 1),
        ('merge seal count message',
         "'375 seal entry count changed'", "'prior seal entry count changed'", 1),
        ('merge total message',
         "'Sealed total is not 859'", "'Sealed total is not 874'", 1),
        ('source pins and package',
         "SOURCE_PINS = {\n"
         "    'tools/autonomous-dual375': {'commit': '6fbd030', "
         "'files': ['derivation.py']},\n"
         "    'tools/autonomous-dual374': {'commit': '4ac8e32',\n"
         "                                 'files': ['reuse_policy.py', "
         "'storage_guard.py']},\n"
         "}\n"
         "PACKAGE_FILES = ('README.md', 'checks.py', 'common.py', 'tool.py', "
         "'worker.py')\n",
         "SOURCE_PINS = {\n"
         "    'tools/preserved-planning377': {\n"
         "        'commit': 'ec8d7b706fb12b98230eb1ec33e14933d5fcb2e9',\n"
         "        'files': ['common.py', 'worker.py', 'tool.py', 'checks.py', "
         "'README.md']},\n"
         "}\n"
         "SOURCE_FILE_SHA = {\n"
         "    'common.py': "
         "'3bbf5466b61a16f225a4cd55f192183907a8099b5c74d11c0e403a99a96bfcd1',\n"
         "    'worker.py': "
         "'cf0ba4b289d6005dcf15f5487696f285c4578da49a3b91e7904a29ac69ec1a91',\n"
         "    'tool.py': "
         "'084cbd011b9cf84129f08c57ebf6aa3c7ee9aa1dffa790041f2e8b223baa64d2',\n"
         "    'checks.py': "
         "'5840b94b4780d09e5939abb214ad4490a586cd6b2074ccc4d35428e86a9d4cc7',\n"
         "    'README.md': "
         "'2bdf8c05e1cb9d3afac4cb7f5b1e23420b064ed65f91cfbc00a0b79145cbabaf',\n"
         "}\n"
         "DERIVE_DIR = 'tools/reviewed-planning380'\n"
         "DERIVE_FILES = ('derive.py', 'run_checks.py', 'README.md')\n"
         "DERIVED_FILES = ('common.py', 'worker.py', 'tool.py', 'checks.py')\n"
         "PACKAGE_FILES = ('README.md', 'checks.py', 'common.py', 'tool.py', "
         "'worker.py',\n"
         "                 'derive.py', 'run_checks.py')\n",
         1),
        ('pinned source digest check',
         "            raw = normalize_source(git_blob(project, full, "
         "directory + '/' + name))\n"
         "            local = project / directory / name\n"
         "            require(local.is_file() and not local.is_symlink(), "
         "'Local pinned source missing')\n"
         "            require(normalize_source(local.read_bytes()) == raw,\n"
         "                    'Worktree differs from pinned source: ' + "
         "directory + '/' + name)\n"
         "            compile(raw, directory + '/' + name, 'exec')\n",
         "            raw = normalize_source(git_blob(project, full, "
         "directory + '/' + name))\n"
         "            require(SOURCE_FILE_SHA.get(name) == sha_bytes(raw),\n"
         "                    'Pinned source digest changed: ' + name)\n"
         "            local = project / directory / name\n"
         "            require(local.is_file() and not local.is_symlink(),\n"
         "                    'Local pinned source missing')\n"
         "            require(normalize_source(local.read_bytes()) == raw,\n"
         "                    'Worktree differs from pinned source: ' + "
         "directory + '/' + name)\n"
         "            if name.endswith('.py'):\n"
         "                compile(raw, directory + '/' + name, 'exec')\n",
         1),
        ('prior stop and source binding helpers',
         "    return {'state': 'stopped', 'model': 0, 'reads': 6, 'login': 1,\n"
         "            'physical_http': 7, 'late_receipt': False}\n",
         "    return {'state': 'stopped', 'model': 0, 'reads': 6, 'login': 1,\n"
         "            'physical_http': 7, 'late_receipt': False}\n"
         "\n"
         "\n"
         "def verify_377_stop(project=PROJECT):\n"
         "    \"\"\"377 stopped on needs_decision: one model HTTP, no complete graph.\"\"\"\n"
         "    attempt_path = Path(project) / PRIOR_ATTEMPT\n"
         "    result_path = Path(project) / PRIOR_RESULT\n"
         "    progress_path = Path(project) / PRIOR_PROGRESS\n"
         "    for path in (attempt_path, result_path, progress_path):\n"
         "        require(path.is_file() and not path.is_symlink(),\n"
         "                '377 stop file missing: ' + str(path))\n"
         "    attempt = load(attempt_path)\n"
         "    result = load(result_path)\n"
         "    progress = load(progress_path)\n"
         "    require(attempt.get('state') == 'stopped'\n"
         "            and result.get('state') == 'stopped'\n"
         "            and progress.get('state') == 'stopped', '377 is not stopped')\n"
         "    for value, label in ((attempt, 'attempt'), (result, 'result'),\n"
         "                         (progress, 'progress')):\n"
         "        require(type(value.get('model_http_started')) is int\n"
         "                and value.get('model_http_started') == 1,\n"
         "                '377 model_http_started changed: ' + label)\n"
         "        require(type(value.get('physical_http')) is int\n"
         "                and value.get('physical_http') == 1,\n"
         "                '377 physical_http changed: ' + label)\n"
         "    require(result.get('workflow_plan_saved') is False,\n"
         "            '377 saved a complete graph')\n"
         "    operation = result.get('planning_run')\n"
         "    require(isinstance(operation, dict)\n"
         "            and operation.get('stop_reason') == 'needs_decision',\n"
         "            '377 stop reason changed')\n"
         "    for folder in (Path(project) / PRIOR_DIR,\n"
         "                   Path(project) / PRIOR_DIR / 'live-output'):\n"
         "        receipts = [p for p in folder.glob('review-*.json')\n"
         "                    if not p.name.startswith('review-source-')]\n"
         "        require(not receipts, 'Unexpected late 377 review receipt: '\n"
         "                + (str(receipts[0]) if receipts else ''))\n"
         "    return {'state': 'stopped', 'stop_reason': 'needs_decision',\n"
         "            'model_http_started': 1, 'physical_http': 1,\n"
         "            'graph_saved': False, 'late_receipt': False}\n"
         "\n"
         "\n"
         "def retired_refs(project=PROJECT):\n"
         "    \"\"\"Every prior question_ref stays rejected; old approvals are sealed.\"\"\"\n"
         "    refs = set(OLD_REFS)\n"
         "    for rel in (OLD_375_APPROVAL, PRIOR_APPROVAL):\n"
         "        path = Path(project) / rel\n"
         "        require(path.is_file() and not path.is_symlink(),\n"
         "                'Prior approval missing: ' + rel)\n"
         "        value = load(path)\n"
         "        ref = value.get('question_ref')\n"
         "        require(isinstance(ref, str) and ref,\n"
         "                'Prior approval ref missing: ' + rel)\n"
         "        refs.add(ref)\n"
         "    return refs\n"
         "\n"
         "\n"
         "def verified_derive(project, commit, root):\n"
         "    \"\"\"Prove canonical tracker sources equal the committed 380 sources.\"\"\"\n"
         "    require(isinstance(commit, str)\n"
         "            and re.fullmatch(r'[0-9a-f]{40}', commit),\n"
         "            'Derive commit is not a full Git id')\n"
         "    root = Path(root)\n"
         "    result = {}\n"
         "    for name in DERIVE_FILES:\n"
         "        raw = normalize_source(git_blob(project, commit,\n"
         "                                       DERIVE_DIR + '/' + name))\n"
         "        path = root / name\n"
         "        require(path.is_file() and not path.is_symlink(),\n"
         "                'Derived tracker missing: ' + name)\n"
         "        require(normalize_source(path.read_bytes()) == raw,\n"
         "                'Canonical tracker differs from committed source: ' + name)\n"
         "        result[name] = sha_bytes(raw)\n"
         "    return result\n"
         "\n"
         "\n"
         "def derived_digests(root, names=DERIVED_FILES):\n"
         "    \"\"\"Raw SHA256 of the materialized derived package files.\"\"\"\n"
         "    result = {}\n"
         "    root = Path(root)\n"
         "    for name in names:\n"
         "        path = root / name\n"
         "        require(path.is_file() and not path.is_symlink(),\n"
         "                'Derived package file missing: ' + name)\n"
         "        result[name] = sha(path)\n"
         "    return result\n",
         1),
        ('seal loader identity',
         "def load_sealed_map(project=PROJECT, old_plan_sha=OLD_375_PLAN_SHA,\n",
         "def load_sealed_map(project=PROJECT, old_plan_sha=OLD_PLAN_SHA,\n",
         1),
        ('seal loader plan path',
         "    old_plan_path = project / OLD_375_DIR / 'plan.json'\n",
         "    old_plan_path = project / PRIOR_DIR / 'plan.json'\n",
         1),
        ('seal loader plan message',
         "'Old 375 plan missing'", "'Old 377 plan missing'", 1),
        ('seal loader plan change',
         "'Old 375 plan changed'", "'Old 377 plan changed'", 1),
        ('seal loader map message',
         "'Old 375 protected_files'", "'Old 377 protected_files'", 1),
        ('seal loader seal path',
         "    seal_path = project / OLD_375_DIR / 'seal-after-stop.json'\n",
         "    seal_path = project / PRIOR_DIR / 'seal-after-stop.json'\n",
         1),
        ('seal loader seal missing',
         "'375 seal missing'", "'377 seal missing'", 1),
        ('seal loader seal changed',
         "'375 seal index changed'", "'377 seal index changed'", 1),
        ('seal loader index key',
         "    index_entries = {OLD_375_DIR + '/seal-after-stop.json': "
         "seal_index_sha}\n",
         "    index_entries = {PRIOR_DIR + '/seal-after-stop.json': "
         "seal_index_sha}\n",
         1),
        ('seal loader prior stop',
         "    merged = merge_sealed(old_map, seal_entries, index_entries)\n"
         "    verify_375_stop(project)\n",
         "    merged = merge_sealed(old_map, seal_entries, index_entries)\n"
         "    verify_375_stop(project)\n"
         "    verify_377_stop(project)\n",
         1),
        ('verify sealed map default',
         "def verify_sealed_map(project, protected_files, "
         "old_plan_sha=OLD_375_PLAN_SHA,\n",
         "def verify_sealed_map(project, protected_files, "
         "old_plan_sha=OLD_PLAN_SHA,\n",
         1),
    ],
    'worker.py': [
        ('public prior shape',
         "        'messages': [{'role': 'assistant', 'source': 'system', "
         "'content': '公开替身历史 %d' % i}\n"
         "                     for i in range(6)],\n"
         "        'versions': [{'id': str(uuid4()), 'revision': i, "
         "'label': '公开替身历史'}\n"
         "                     for i in range(1, 6)],\n"
         "        'planning_runs': [{'id': str(uuid4()), 'revision': 6, "
         "'provider_id': PUBLIC_PROVIDER,\n"
         "                           'model': 'deepseek-flash', 'status': 'paused',\n"
         "                           'stop_reason': 'needs_decision',\n"
         "                           'decision_report': {'message': "
         "'公开替身旧 needs_decision'},\n"
         "                           'last_candidate': None, 'attempts': [], "
         "'created_at': _now()}],\n"
         "        'runs': [], 'confirmations': [], 'workflow_plan': None, "
         "'agent_plan': None,\n",
         "        'messages': [{'role': 'assistant', 'source': 'system', "
         "'content': '公开替身历史 %d' % i}\n"
         "                     for i in range(7)],\n"
         "        'versions': [{'id': str(uuid4()), 'revision': i, "
         "'label': '公开替身历史'}\n"
         "                     for i in range(1, 6)],\n"
         "        'planning_runs': [\n"
         "            {'id': str(uuid4()), 'revision': 6, "
         "'provider_id': PUBLIC_PROVIDER,\n"
         "             'model': 'deepseek-flash', 'status': 'paused',\n"
         "             'stop_reason': 'needs_decision',\n"
         "             'decision_report': {'message': '公开替身旧 needs_decision'},\n"
         "             'last_candidate': None, 'attempts': [], "
         "'created_at': _now()},\n"
         "            {'id': str(uuid4()), 'revision': 6, 'status': 'paused',\n"
         "             'stop_reason': 'needs_decision'}],\n"
         "        'runs': [], 'confirmations': [{'id': str(uuid4()), "
         "'revision': 6,\n"
         "                                        'source': "
         "'synthetic_prior_shape'}],\n"
         "        'workflow_plan': None, 'agent_plan': None,\n",
         1),
        ('public ledger shape',
         "    charged = ('0.0034545', '0.005911224', '0.0107598')\n",
         "    charged = ('0.0034545', '0.005911224', '0.0107598', "
         "'0.003040692')\n",
         1),
        ('public prior assertions',
         "            require(old_task.get('revision') == TARGET_REVISION\n"
         "                    and old_task.get('status') == 'paused'\n"
         "                    and old_task.get('workflow_plan') is None\n"
         "                    and 'interview_attempts' not in old_task,\n"
         "                    'Public prior shape changed')\n",
         "            require(old_task.get('revision') == TARGET_REVISION\n"
         "                    and old_task.get('status') == 'paused'\n"
         "                    and old_task.get('workflow_plan') is None\n"
         "                    and len(old_task.get('planning_runs') or []) == 2\n"
         "                    and len(old_task.get('confirmations') or []) == 1\n"
         "                    and 'interview_attempts' not in old_task,\n"
         "                    'Public prior shape changed')\n",
         1),
    ],
    'tool.py': [
        ('source imports',
         "from common import (APPROVAL_PHRASE, APPROVAL_SUFFIX, BATCH, CANONICAL,\n"
         "                    EXPECTED_COUNTS, ISOLATED, LIMITS, MAX_MODEL_HTTP,\n"
         "                    MODEL_BOOK_UPPER_USD, OLD_375_PLAN_SHA, OLD_ENTRY_COUNT,\n"
         "                    OLD_REFS, ORIGINAL_PROJECT, OUTPUT_TOKENS, PACKAGE_FILES,\n"
         "                    PER_CALL_USD, PER_MODEL_TOTAL_USD, PROJECT, PROVIDER_ID,\n"
         "                    PROVIDER_MODEL, PROVIDER_PROTOCOL, ReadOnly, RUNTIME_BUILD,\n"
         "                    RUNTIME_FILE_COUNT, RUNTIME_PID_OBSERVED, RUNTIME_VERSION,\n"
         "                    SEAL_INDEX_SHA, SETTLED_TOTAL, SOURCE_PINS, TARGET_REVISION,\n"
         "                    TARGET_TASK, TIMEOUT_SECONDS, TOTAL_SEALED_COUNT, UPPER,\n"
         "                    WALL_SECONDS, capture, digest, history_prefix, is_hex, load,\n"
         "                    load_sealed_map, money, require, sha, sha_bytes, uuid,\n"
         "                    verified_sources, verify_sealed_map, verify_375_stop)\n",
         "from common import (APPROVAL_PHRASE, APPROVAL_SUFFIX, BATCH, CANONICAL,\n"
         "                    DERIVED_FILES, DERIVE_FILES, EXPECTED_COUNTS, ISOLATED,\n"
         "                    LIMITS, MAX_MODEL_HTTP, MODEL_BOOK_UPPER_USD, OLD_PLAN_SHA,\n"
         "                    OLD_ENTRY_COUNT, OLD_REFS, ORIGINAL_PROJECT, OUTPUT_TOKENS,\n"
         "                    PACKAGE_FILES, PER_CALL_USD, PER_MODEL_TOTAL_USD, PROJECT,\n"
         "                    PROVIDER_ID, PROVIDER_MODEL, PROVIDER_PROTOCOL, ReadOnly,\n"
         "                    RUNTIME_BUILD, RUNTIME_FILE_COUNT, RUNTIME_PID_OBSERVED,\n"
         "                    RUNTIME_VERSION, SEAL_INDEX_SHA, SETTLED_TOTAL,\n"
         "                    SOURCE_FILE_SHA, SOURCE_PINS,\n"
         "                    TARGET_REVISION, TARGET_TASK, TIMEOUT_SECONDS,\n"
         "                    TOTAL_SEALED_COUNT, UPPER, WALL_SECONDS, capture,\n"
         "                    derived_digests, digest, history_prefix, is_hex, load,\n"
         "                    load_sealed_map, money, normalize_source, require,\n"
         "                    retired_refs, sha, sha_bytes, uuid, verified_derive,\n"
         "                    verified_sources, verify_sealed_map, verify_375_stop,\n"
         "                    verify_377_stop)\n",
         1),
        ('target shape counts',
         "    'counts': {'messages': 6, 'versions': 5, 'planning_runs': 1,\n"
         "               'intake_history': 1, 'runs': 0},\n",
         "    'counts': {'messages': 7, 'versions': 5, 'planning_runs': 2,\n"
         "               'intake_history': 1, 'runs': 0},\n",
         1),
        ('target shape confirmations',
         "    'interview_attempts_present': False, 'execution_limits_present': False,\n",
         "    'confirmations': 1,\n"
         "    'interview_attempts_present': False, 'execution_limits_present': False,\n",
         1),
        ('regrant remaining',
         "REGRANT = {'from_batch': 'autonomous-dual375', 'model_slot': 1, "
         "'estimate_usd': '0.100',\n"
         "           'remaining_kept': {'model': 2, 'estimate_usd': '0.200',\n",
         "REGRANT = {'from_batch': 'autonomous-dual375', 'model_slot': 1, "
         "'estimate_usd': '0.100',\n"
         "           'prior_regrant': {'batch': 'preserved-planning377', "
         "'model_slot': 1,\n"
         "                             'estimate_usd': '0.100'},\n"
         "           'remaining_kept': {'model': 1, 'estimate_usd': '0.100',\n",
         1),
        ('plan required keys',
         "    'old_375_plan_sha256', 'seal_index_sha256', 'old_375_stop', "
         "'source_pins',\n",
         "    'old_plan_sha256', 'seal_index_sha256', 'old_375_stop', "
         "'old_377_stop',\n"
         "    'derive_commit', 'derive_file_sha256', 'derived_file_sha256', "
         "'source_pins',\n",
         1),
        ('seal identity check',
         "    require(p['protected_count'] == TOTAL_SEALED_COUNT\n"
         "            and p['old_375_plan_sha256'] == OLD_375_PLAN_SHA\n"
         "            and p['seal_index_sha256'] == SEAL_INDEX_SHA, "
         "'Seal identity changed')\n",
         "    require(p['protected_count'] == TOTAL_SEALED_COUNT\n"
         "            and p['old_plan_sha256'] == OLD_PLAN_SHA\n"
         "            and p['seal_index_sha256'] == SEAL_INDEX_SHA, "
         "'Seal identity changed')\n",
         1),
        ('old plan digest key',
         "                ('target_task_sha256', 'target_budget_sha256', "
         "'intake_review_sha256',\n",
         "                ('target_task_sha256', 'target_budget_sha256', "
         "'old_plan_sha256',\n"
         "                 'intake_review_sha256',\n",
         1),
        ('derive and prior stop plan checks',
         "    require(isinstance(p['protected_files'], dict)\n"
         "            and len(p['protected_files']) == TOTAL_SEALED_COUNT\n"
         "            and digest(p['protected_files']) == "
         "p['protected_files_sha256'],\n"
         "            'Protected file map changed')\n",
         "    require(isinstance(p['protected_files'], dict)\n"
         "            and len(p['protected_files']) == TOTAL_SEALED_COUNT\n"
         "            and digest(p['protected_files']) == "
         "p['protected_files_sha256'],\n"
         "            'Protected file map changed')\n"
         "    require(isinstance(p['derive_commit'], str)\n"
         "            and re.fullmatch(r'[0-9a-f]{40}', p['derive_commit']) "
         "is not None,\n"
         "            'Derive commit invalid')\n"
         "    require(isinstance(p['derive_file_sha256'], dict)\n"
         "            and set(p['derive_file_sha256']) == set(DERIVE_FILES)\n"
         "            and all(is_hex(value) for value in "
         "p['derive_file_sha256'].values()),\n"
         "            'Derive source digests changed')\n"
         "    require(isinstance(p['derived_file_sha256'], dict)\n"
         "            and set(p['derived_file_sha256']) == set(DERIVED_FILES)\n"
         "            and all(is_hex(value) for value in "
         "p['derived_file_sha256'].values()),\n"
         "            'Derived package digests changed')\n"
         "    require(isinstance(p['old_375_stop'], dict) and p['old_375_stop'],\n"
         "            'Old 375 stop facts missing')\n"
         "    require(isinstance(p['old_377_stop'], dict) and p['old_377_stop'],\n"
         "            'Old 377 stop facts missing')\n",
         1),
        ('retired refs gate',
         "def validate_authorization(a, plan, plan_sha, manifest_sha):\n",
         "def validate_authorization(a, plan, plan_sha, manifest_sha, retired=None):\n",
         1),
        ('retired refs body',
         "    ref = a['question_ref']\n"
         "    require(isinstance(ref, str) and bool(re.fullmatch("
         "r'call_[A-Za-z0-9_-]{1,64}/q0', ref))\n"
         "            and ref not in OLD_REFS, 'New question_ref required')\n",
         "    ref = a['question_ref']\n"
         "    if retired is None:\n"
         "        retired = retired_refs(PROJECT)\n"
         "    require(isinstance(ref, str) and bool(re.fullmatch("
         "r'call_[A-Za-z0-9_-]{1,64}/q0', ref))\n"
         "            and ref not in retired, 'New question_ref required')\n",
         1),
        ('verify derive helper',
         "def verify_package(root, plan=None):\n",
         "def _load_verified_derive(root, expected_sha=None):\n"
         "    import importlib.util\n"
         "    path = Path(root) / 'derive.py'\n"
         "    require(path.is_file() and not path.is_symlink(),\n"
         "            'Verified derive.py missing')\n"
         "    raw = path.read_bytes()\n"
         "    if expected_sha is not None:\n"
         "        require(sha_bytes(normalize_source(raw)) == expected_sha,\n"
         "                'Verified derive.py changed before load')\n"
         "    spec = importlib.util.spec_from_file_location(\n"
         "        'reviewed_planning380_derive_' + sha_bytes(raw)[:16], path)\n"
         "    require(spec is not None and spec.loader is not None,\n"
         "            'Verified derive.py cannot load')\n"
         "    module = importlib.util.module_from_spec(spec)\n"
         "    spec.loader.exec_module(module)\n"
         "    require(Path(module.__file__).resolve() == path.resolve(),\n"
         "            'Verified derive module identity changed')\n"
         "    require(tuple(module.DERIVED_FILES) == tuple(DERIVED_FILES),\n"
         "            'Verified derive file set changed')\n"
         "    origin = SOURCE_PINS[module.ORIGIN_DIR]\n"
         "    require(origin['commit'] == module.ORIGIN_COMMIT\n"
         "            and tuple(origin['files']) == tuple(module.ORIGIN_FILES)\n"
         "            and SOURCE_FILE_SHA == module.ORIGIN_SHA,\n"
         "            'Verified derive origin pins changed')\n"
         "    return module\n"
         "\n"
         "\n"
         "def verify_derive(root, plan, project=PROJECT, "
         "origin_project=PROJECT):\n"
         "    \"\"\"Recompute derived bytes from committed tracker sources, every gate.\"\"\"\n"
         "    files = verified_derive(project, plan['derive_commit'], root)\n"
         "    require(files == plan['derive_file_sha256'], "
         "'Derive source digests changed')\n"
         "    module = _load_verified_derive(root, files['derive.py'])\n"
         "    require(module.frozen(), 'DERIVED_SHA is not frozen')\n"
         "    digests = module.check(origin_project, root)\n"
         "    require(set(digests) == set(DERIVED_FILES),\n"
         "            'Derived recompute file set changed')\n"
         "    require(digests == plan['derived_file_sha256'],\n"
         "            'Derived package bytes changed')\n"
         "    return files\n"
         "\n"
         "\n"
         "def verify_package(root, plan=None):\n",
         1),
        ('verify derive inside package gate',
         "                'Source pin file list changed')\n"
         "    return blobs\n",
         "                'Source pin file list changed')\n"
         "        verify_derive(root, plan)\n"
         "    return blobs\n",
         1),
        ('compile every package source',
         "    for name in ('common.py', 'tool.py', 'worker.py', 'checks.py'):\n"
         "        compile((root / name).read_bytes(), name, 'exec')\n",
         "    for name in PACKAGE_FILES:\n"
         "        if name.endswith('.py'):\n"
         "            compile((root / name).read_bytes(), name, 'exec')\n",
         1),
        ('startup planning runs',
         "    planning = task.get('planning_runs') or []\n"
         "    require(len(planning) == 1 and isinstance(planning[0], dict)\n"
         "            and digest(planning[0].get('decision_report')) == "
         "plan['decision_report_sha256'],\n"
         "            'Old decision report changed')\n",
         "    planning = task.get('planning_runs') or []\n"
         "    require(len(planning) == 2 and isinstance(planning[0], dict)\n"
         "            and isinstance(planning[1], dict)\n"
         "            and digest(planning[0].get('decision_report')) == "
         "plan['decision_report_sha256'],\n"
         "            'Old decision report changed')\n"
         "    require(all(run.get('status') == 'paused'\n"
         "                and run.get('stop_reason') == 'needs_decision'\n"
         "                and run.get('last_candidate') is None "
         "for run in planning),\n"
         "            'Old planning runs changed')\n"
         "    require(len(task.get('confirmations') or []) == 1,\n"
         "            'Old confirmation count changed')\n",
         1),
        ('startup old run block',
         "    old_run = planning[0]\n"
         "    require(old_run.get('status') == 'paused'\n"
         "            and old_run.get('stop_reason') == 'needs_decision'\n"
         "            and old_run.get('last_candidate') is None, "
         "'Old planning run changed')\n",
         "    require(len(task.get('confirmations') or []) == 1,\n"
         "            'Old confirmation count changed')\n",
         1),
        ('startup prior stop',
         "    require(verify_375_stop(PROJECT) == plan['old_375_stop'], "
         "'375 stop facts changed')\n",
         "    require(verify_375_stop(PROJECT) == plan['old_375_stop'], "
         "'375 stop facts changed')\n"
         "    require(verify_377_stop(PROJECT) == plan['old_377_stop'], "
         "'377 stop facts changed')\n",
         1),
        ('pending signature',
         "def pending(root):\n    root = canonical(root)\n",
         "def pending(root, derive_commit):\n"
         "    root = canonical(root)\n"
         "    require(derive_commit, 'Derive commit required')\n"
         "    files = verified_derive(PROJECT, derive_commit, root)\n"
         "    module = _load_verified_derive(root, files['derive.py'])\n"
         "    require(module.frozen(), 'DERIVED_SHA is not frozen')\n"
         "    derived = module.check(PROJECT, root)\n",
         1),
        ('pending old runs',
         "    old_run = (task.get('planning_runs') or [None])[0]\n"
         "    require(isinstance(old_run, dict) and "
         "old_run.get('status') == 'paused'\n"
         "            and old_run.get('stop_reason') == 'needs_decision'\n"
         "            and isinstance(old_run.get('decision_report'), dict)\n"
         "            and old_run.get('last_candidate') is None, "
         "'Old needs_decision changed')\n",
         "    planning = task.get('planning_runs') or []\n"
         "    old_run = planning[0] if planning else None\n"
         "    require(len(planning) == 2 and isinstance(old_run, dict)\n"
         "            and old_run.get('status') == 'paused'\n"
         "            and old_run.get('stop_reason') == 'needs_decision'\n"
         "            and isinstance(old_run.get('decision_report'), dict)\n"
         "            and old_run.get('last_candidate') is None, "
         "'Old needs_decision changed')\n"
         "    require(all(isinstance(run, dict)\n"
         "                and run.get('status') == 'paused'\n"
         "                and run.get('stop_reason') == 'needs_decision'\n"
         "                and run.get('last_candidate') is None "
         "for run in planning),\n"
         "            'Old planning runs changed')\n"
         "    require(len(task.get('confirmations') or []) == 1,\n"
         "            'Old confirmation count changed')\n",
         1),
        ('pending shape confirmations',
         "             'interview_attempts_present': "
         "history['interview_attempts']['present'],\n"
         "             'execution_limits_present': limits is not None}\n",
         "             'interview_attempts_present': "
         "history['interview_attempts']['present'],\n"
         "             'confirmations': len(task.get('confirmations') or []),\n"
         "             'execution_limits_present': limits is not None}\n",
         1),
        ('pending prior stop facts',
         "    stop_facts = verify_375_stop(PROJECT)\n",
         "    stop_facts = verify_375_stop(PROJECT)\n"
         "    prior_stop = verify_377_stop(PROJECT)\n",
         1),
        ('pending plan keys',
         "        'old_375_plan_sha256': OLD_375_PLAN_SHA, "
         "'seal_index_sha256': SEAL_INDEX_SHA,\n"
         "        'old_375_stop': stop_facts,\n",
         "        'old_plan_sha256': OLD_PLAN_SHA, "
         "'seal_index_sha256': SEAL_INDEX_SHA,\n"
         "        'old_375_stop': stop_facts, 'old_377_stop': prior_stop,\n"
         "        'derive_commit': derive_commit,\n"
         "        'derive_file_sha256': files,\n"
         "        'derived_file_sha256': derived,\n",
         1),
        ('pending verify before write',
         "    validate_plan(plan)\n"
         "    manifest = {'schema_version': 1, 'batch_id': BATCH,\n",
         "    validate_plan(plan)\n"
         "    verify_derive(root, plan)\n"
         "    manifest = {'schema_version': 1, 'batch_id': BATCH,\n",
         1),
        ('pending proposal path',
         "        'proposal_doc': 'tools/preserved-planning377/README.md',\n"
         "        'proposal_sha256': sha(PROJECT / 'tools' / "
         "'preserved-planning377' / 'README.md'),\n",
         "        'proposal_doc': 'tools/reviewed-planning380/README.md',\n"
         "        'proposal_sha256': sha(PROJECT / 'tools' / "
         "'reviewed-planning380' / 'README.md'),\n",
         1),
        ('pending readme compare',
         "    require(sha(PROJECT / 'tools' / 'preserved-planning377' / "
         "'README.md')\n"
         "            == sha(root / 'README.md'), "
         "'Canonical README differs from committed source')\n",
         "    require(normalize_source((PROJECT / 'tools' / "
         "'reviewed-planning380'\n"
         "                             / 'README.md').read_bytes())\n"
         "            == normalize_source((root / 'README.md').read_bytes()),\n"
         "            'Canonical README differs from committed source')\n",
         1),
        ('canonical clone reject',
         "    require(raw.is_dir(), 'Canonical root missing')\n",
         "    require(raw.is_dir(), 'Canonical root missing')\n"
         "    require(not (raw / '.git').exists(),\n"
         "            'Canonical root must not be a Git checkout')\n",
         1),
        ('derive commit argument',
         "    parser.add_argument('--authorization')\n"
         "    parser.add_argument('--output')\n",
         "    parser.add_argument('--authorization')\n"
         "    parser.add_argument('--output')\n"
         "    parser.add_argument('--derive-commit')\n",
         1),
        ('pending derive commit call',
         "    if args.action == 'pending':\n        pending(root)\n        return\n",
         "    if args.action == 'pending':\n"
         "        require(args.derive_commit, '--derive-commit is required')\n"
         "        pending(root, args.derive_commit)\n"
         "        return\n",
         1),
    ],
    'checks.py': [
        ('synthetic plan keys',
         "        'old_375_plan_sha256': common.OLD_375_PLAN_SHA,\n"
         "        'seal_index_sha256': common.SEAL_INDEX_SHA, "
         "'old_375_stop': {},\n",
         "        'old_plan_sha256': common.OLD_PLAN_SHA,\n"
         "        'seal_index_sha256': common.SEAL_INDEX_SHA, "
         "'old_375_stop': {'state': 'stopped'},\n"
         "        'old_377_stop': {'state': 'stopped'},\n"
         "        'derive_commit': 'a' * 40,\n"
         "        'derive_file_sha256': {name: 'b' * 64\n"
         "                               for name in common.DERIVE_FILES},\n"
         "        'derived_file_sha256': {name: 'c' * 64\n"
         "                                for name in common.DERIVED_FILES},\n",
         1),
        ('invalid json ledger count',
         "    assert result['ledger']['after_entries'] == 4\n",
         "    assert result['ledger']['after_entries'] == 5\n",
         1),
        ('success revision and ledger',
         "    assert result['revision_before'] == 6 and "
         "result['revision_after'] == 7\n"
         "    assert result['ledger']['before_entries'] == 3 and "
         "result['ledger']['after_entries'] == 4\n",
         "    assert result['revision_before'] == 6 and "
         "result['revision_after'] == 7\n"
         "    assert result['ledger']['before_entries'] == 4 and "
         "result['ledger']['after_entries'] == 5\n",
         1),
        ('success history counts',
         "    assert len(task['messages']) == 8 and len(task['versions']) == 6\n"
         "    assert len(task['planning_runs']) == 2\n",
         "    assert len(task['messages']) == 9 and len(task['versions']) == 6\n"
         "    assert len(task['planning_runs']) == 3\n",
         1),
        ('success ledger prefix',
         "    assert common.digest(stored_budget['entries'][:3]) == "
         "result['ledger']['before_sha256']\n",
         "    assert common.digest(stored_budget['entries'][:4]) == "
         "result['ledger']['before_sha256']\n",
         1),
        ('sealed map shape',
         "    old_map = {'work/old/%04d' % i: _sha('old%d' % i) "
         "for i in range(831)}\n"
         "    seal = {'work/autonomous-dual375/seal/%02d' % i: "
         "_sha('seal%d' % i)\n"
         "            for i in range(27)}\n"
         "    index = {'work/autonomous-dual375/index.json': "
         "common.SEAL_INDEX_SHA}\n"
         "    merged = common.merge_sealed(old_map, seal, index)\n"
         "    assert len(merged) == 859 == common.TOTAL_SEALED_COUNT\n"
         "    assert common.OLD_MAP_COUNT + common.SEAL_ENTRY_COUNT + 1 == 859\n"
         "    bad_cases = [\n"
         "        (dict(list(old_map.items())[:830]), seal, index),\n"
         "        (old_map, dict(list(seal.items())[:26]), index),\n"
         "        (old_map, seal, {**index, "
         "'work/autonomous-dual375/other.json':\n"
         "                         common.SEAL_INDEX_SHA}),\n"
         "    ]\n",
         "    old_map = {'work/old/%04d' % i: _sha('old%d' % i) "
         "for i in range(859)}\n"
         "    seal = {'work/preserved-planning377/seal/%02d' % i: "
         "_sha('seal%d' % i)\n"
         "            for i in range(14)}\n"
         "    index = {'work/preserved-planning377/index.json': "
         "common.SEAL_INDEX_SHA}\n"
         "    merged = common.merge_sealed(old_map, seal, index)\n"
         "    assert len(merged) == 874 == common.TOTAL_SEALED_COUNT\n"
         "    assert common.OLD_MAP_COUNT + common.SEAL_ENTRY_COUNT + 1 == 874\n"
         "    bad_cases = [\n"
         "        (dict(list(old_map.items())[:858]), seal, index),\n"
         "        (old_map, dict(list(seal.items())[:13]), index),\n"
         "        (old_map, seal, {**index, "
         "'work/preserved-planning377/other.json':\n"
         "                         common.SEAL_INDEX_SHA}),\n"
         "    ]\n",
         1),
        ('stop fixture',
         "def _stop_fixture(folder):\n"
         "    package = Path(folder) / 'work' / 'autonomous-dual375'\n"
         "    live = package / 'live-output'\n"
         "    live.mkdir(parents=True, exist_ok=True)\n"
         "    progress = {'state': 'stopped',\n"
         "                'dispatch_counts': {'model': 0, 'reads': 6, "
         "'login': 1,\n"
         "                                    'import': 0, 'publish': 0, "
         "'key': 0, 'run': 0},\n"
         "                'physical_http': 7}\n"
         "    _write(live / 'progress.json', json.dumps(progress))\n"
         "    _write(package / 'attempt.json', "
         "json.dumps({'state': 'stopped'}))\n"
         "    _write(live / 'review-source-faq_read.json', '{}')\n"
         "    return package, live\n",
         "def _stop_fixture(folder):\n"
         "    folder = Path(folder)\n"
         "    old_package = folder / 'work' / 'autonomous-dual375'\n"
         "    old_live = old_package / 'live-output'\n"
         "    old_live.mkdir(parents=True, exist_ok=True)\n"
         "    _write(old_live / 'progress.json', json.dumps(\n"
         "        {'state': 'stopped',\n"
         "         'dispatch_counts': {'model': 0, 'reads': 6, 'login': 1,\n"
         "                             'import': 0, 'publish': 0, "
         "'key': 0, 'run': 0},\n"
         "         'physical_http': 7}))\n"
         "    _write(old_package / 'attempt.json', "
         "json.dumps({'state': 'stopped'}))\n"
         "    package = folder / 'work' / 'preserved-planning377'\n"
         "    live = package / 'live-output'\n"
         "    live.mkdir(parents=True, exist_ok=True)\n"
         "    stopped = {'state': 'stopped', 'model_http_started': 1,\n"
         "               'physical_http': 1}\n"
         "    _write(package / 'attempt.json', json.dumps(stopped))\n"
         "    _write(live / 'progress.json', json.dumps(stopped))\n"
         "    _write(live / 'result.json', json.dumps(\n"
         "        dict(stopped, workflow_plan_saved=False,\n"
         "             planning_run={'stop_reason': 'needs_decision'})))\n"
         "    _write(live / 'review-source-original.json', '{}')\n"
         "    _write(package / 'approval.json', json.dumps(\n"
         "        {'question_ref': 'call_old377fixture/q0'}))\n"
         "    return old_package, old_live, package, live\n",
         1),
        ('sealed loader fixture unpack',
         "        package, live = _stop_fixture(folder)\n"
         "        old = {}\n",
         "        old_package, old_live, package, live = _stop_fixture(folder)\n"
         "        old = {}\n",
         1),
        ('sealed loader old map size',
         "        for i in range(831):\n",
         "        for i in range(859):\n",
         1),
        ('sealed loader names',
         "        names = ['README.md', 'approval.json', 'attempt.json', "
         "'profile.json',\n"
         "                 'worker.py', 'execute.py', 'prepare.py', "
         "'checks.py',\n"
         "                 'derivation.py', 'live-output/progress.json',\n"
         "                 'live-output/review-source-faq_read.json']\n"
         "        names += ['member-%02d.txt' % i for i in range(16)]\n",
         "        names = ['approval.json', 'attempt.json', "
         "'live-output/progress.json',\n"
         "                 'live-output/result.json',\n"
         "                 'live-output/review-source-original.json']\n"
         "        names += ['member-%02d.txt' % i for i in range(9)]\n",
         1),
        ('sealed loader totals',
         "        assert len(merged) == 859 == common.TOTAL_SEALED_COUNT\n"
         "        assert merged['work/autonomous-dual375/"
         "live-output/progress.json'] == \\\n"
         "            seal['live-output/progress.json']\n"
         "        assert merged['work/autonomous-dual375/"
         "seal-after-stop.json'] == seal_sha\n",
         "        assert len(merged) == 874 == common.TOTAL_SEALED_COUNT\n"
         "        assert merged['work/preserved-planning377/"
         "live-output/progress.json'] == \\\n"
         "            seal['live-output/progress.json']\n"
         "        assert merged['work/preserved-planning377/"
         "seal-after-stop.json'] == seal_sha\n",
         1),
        ('receipt fixtures',
         "def test_receipts():\n"
         "    folder = Path(tempfile.mkdtemp())\n"
         "    try:\n"
         "        package, live = _stop_fixture(folder)\n"
         "        common.verify_375_stop(folder)\n"
         "        _write(live / 'review-faq_read.json', '{}')\n"
         "        try:\n"
         "            common.verify_375_stop(folder)\n"
         "            raise AssertionError('live-output receipt was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "        (live / 'review-faq_read.json').unlink()\n"
         "        _write(package / 'review-faq_read.json', '{}')\n"
         "        try:\n"
         "            common.verify_375_stop(folder)\n"
         "            raise AssertionError('root receipt was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "    finally:\n"
         "        shutil.rmtree(folder, ignore_errors=True)\n"
         "    ok('only review-source-* is allowed; live-output and root "
         "receipts are rejected')\n",
         "def test_receipts():\n"
         "    folder = Path(tempfile.mkdtemp())\n"
         "    try:\n"
         "        old_package, old_live, package, live = _stop_fixture(folder)\n"
         "        common.verify_375_stop(folder)\n"
         "        common.verify_377_stop(folder)\n"
         "        _write(old_live / 'review-faq_read.json', '{}')\n"
         "        try:\n"
         "            common.verify_375_stop(folder)\n"
         "            raise AssertionError('375 live-output receipt was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "        (old_live / 'review-faq_read.json').unlink()\n"
         "        _write(old_package / 'review-faq_read.json', '{}')\n"
         "        try:\n"
         "            common.verify_375_stop(folder)\n"
         "            raise AssertionError('375 root receipt was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "        (old_package / 'review-faq_read.json').unlink()\n"
         "        _write(live / 'review-faq_read.json', '{}')\n"
         "        try:\n"
         "            common.verify_377_stop(folder)\n"
         "            raise AssertionError('377 live-output receipt was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "        (live / 'review-faq_read.json').unlink()\n"
         "        _write(package / 'review-faq_read.json', '{}')\n"
         "        try:\n"
         "            common.verify_377_stop(folder)\n"
         "            raise AssertionError('377 root receipt was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "    finally:\n"
         "        shutil.rmtree(folder, ignore_errors=True)\n"
         "    ok('only review-source-* is allowed; 375/377 receipts are "
         "rejected')\n",
         1),
        ('runtime bad version',
         "                           ('runtime_version', '0.410.0'),\n",
         "                           ('runtime_version', '0.411.0'),\n",
         1),
        ('runtime observed pid',
         "12020", "34736", 6),
        ('runtime old snapshot',
         "'0.410.0-old'", "'0.411.0-old'", 1),
        ('source pin set',
         "    assert set(blobs) == {'tools/autonomous-dual375/derivation.py',\n"
         "                          'tools/autonomous-dual374/reuse_policy.py',\n"
         "                          'tools/autonomous-dual374/storage_guard.py'}\n",
         "    assert set(blobs) == {'tools/preserved-planning377/' + name\n"
         "                          for name in common.SOURCE_PINS[\n"
         "                              'tools/preserved-planning377']['files']}\n"
         "    assert all(common.sha_bytes(raw) == common.SOURCE_FILE_SHA[\n"
         "        name.rsplit('/', 1)[1]] for name, raw in blobs.items())\n",
         1),
        ('source pin compile guard',
         "    for name, raw in blobs.items():\n"
         "        compile(raw, name, 'exec')\n",
         "    for name, raw in blobs.items():\n"
         "        if name.endswith('.py'):\n"
         "            compile(raw, name, 'exec')\n",
         1),
        ('source pin bad commit',
         "    bad['tools/autonomous-dual375']['commit'] = '0' * 40\n",
         "    bad['tools/preserved-planning377']['commit'] = '0' * 40\n",
         1),
        ('source pin bad file',
         "    bad['tools/autonomous-dual375']['files'] = ['no-such-377.py']\n",
         "    bad['tools/preserved-planning377']['files'] = ['no-such-377.py']\n",
         1),
        ('approval fixture ref',
         "            'question_ref': 'call_newvalid377/q0', 'plan_sha256': 'a' * 64,\n",
         "            'question_ref': 'call_newvalid380/q0', 'plan_sha256': 'a' * 64,\n",
         1),
        ('approval rejection gate',
         "def test_approval_rejections():\n"
         "    plan = {'limits': common.LIMITS, 'max_model_http': 1}\n"
         "    approval = _valid_approval()\n"
         "    tool.validate_authorization(approval, plan, 'a' * 64, 'b' * 64)\n"
         "    bad = []\n"
         "    value = copy.deepcopy(approval); value['question_ref'] = "
         "'call_f5b63df1752f441284ac9ee97f031930/q0'; bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['authorization_source'] = "
         "'agent_delegated'; bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['reply'] = '同意'; "
         "bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['plan_sha256'] = 'c' * 64; "
         "bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['limits'] = "
         "dict(common.LIMITS, model=2); bad.append(value)\n"
         "    for value in bad:\n"
         "        try:\n"
         "            tool.validate_authorization(value, plan, 'a' * 64, 'b' * 64)\n"
         "            raise AssertionError('bad approval was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "\n"
         "    folder = Path(tempfile.mkdtemp())\n"
         "    try:\n"
         "        tool.assert_unconsumed(folder)\n",
         "def test_approval_rejections():\n"
         "    plan = {'limits': common.LIMITS, 'max_model_http': 1}\n"
         "    approval = _valid_approval()\n"
         "    retired = {'call_f5b63df1752f441284ac9ee97f031930/q0',\n"
         "               'call_653c3204d2c842648bbfaddba3d298b4/q0',\n"
         "               'call_old377fixture/q0'}\n"
         "    tool.validate_authorization(approval, plan, 'a' * 64, 'b' * 64, "
         "retired)\n"
         "    bad = []\n"
         "    value = copy.deepcopy(approval); value['question_ref'] = "
         "'call_f5b63df1752f441284ac9ee97f031930/q0'; bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['question_ref'] = "
         "'call_653c3204d2c842648bbfaddba3d298b4/q0'; bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['question_ref'] = "
         "'call_old377fixture/q0'; bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['authorization_source'] = "
         "'agent_delegated'; bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['reply'] = '同意'; "
         "bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['plan_sha256'] = 'c' * 64; "
         "bad.append(value)\n"
         "    value = copy.deepcopy(approval); value['limits'] = "
         "dict(common.LIMITS, model=2); bad.append(value)\n"
         "    for value in bad:\n"
         "        try:\n"
         "            tool.validate_authorization(value, plan, 'a' * 64, "
         "'b' * 64, retired)\n"
         "            raise AssertionError('bad approval was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "\n"
         "    folder = Path(tempfile.mkdtemp())\n"
         "    try:\n"
         "        _write(folder / 'work/autonomous-dual375/approval.json',\n"
         "               '{\"question_ref\": \"call_old375fixture/q0\"}')\n"
         "        _write(folder / 'work/preserved-planning377/approval.json',\n"
         "               '{\"question_ref\": \"call_old377fixture/q0\"}')\n"
         "        refs = common.retired_refs(folder)\n"
         "        assert 'call_old375fixture/q0' in refs\n"
         "        assert 'call_old377fixture/q0' in refs\n"
         "        (folder / 'work/preserved-planning377/approval.json').unlink()\n"
         "        try:\n"
         "            common.retired_refs(folder)\n"
         "            raise AssertionError('missing prior approval was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "        tool.assert_unconsumed(folder)\n",
         1),
        ('derive binding test',
         "def main():\n"
         "    root = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                 prefix='preserved-planning377-check-'))\n",
         "def test_derive_binding():\n"
         "    folder = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                  prefix='reviewed-planning380-git-'))\n"
         "    try:\n"
         "        package = folder / 'tools' / 'reviewed-planning380'\n"
         "        package.mkdir(parents=True)\n"
         "        for name in common.DERIVE_FILES:\n"
         "            shutil.copy2(HERE / name, package / name)\n"
         "        env = dict(os.environ, GIT_AUTHOR_NAME='fixture',\n"
         "                   GIT_AUTHOR_EMAIL='f@example.invalid',\n"
         "                   GIT_COMMITTER_NAME='fixture',\n"
         "                   GIT_COMMITTER_EMAIL='f@example.invalid')\n"
         "        subprocess.run(['git', 'init', '-q', str(folder)], check=True,\n"
         "                       capture_output=True)\n"
         "        subprocess.run(['git', '-C', str(folder), 'add', '.'],\n"
         "                       check=True, capture_output=True)\n"
         "        subprocess.run(['git', '-C', str(folder), 'commit', '-q', '-m',\n"
         "                        'fixture'], check=True, capture_output=True,\n"
         "                       env=env)\n"
         "        commit = subprocess.run(['git', '-C', str(folder),\n"
         "                                 'rev-parse', 'HEAD'], check=True,\n"
         "                                capture_output=True,\n"
         "                                text=True).stdout.strip()\n"
         "        root = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                     prefix='reviewed-planning380-pkg-'))\n"
         "        try:\n"
         "            for name in common.DERIVE_FILES:\n"
         "                shutil.copy2(HERE / name, root / name)\n"
         "            files = common.verified_derive(folder, commit, root)\n"
         "            assert set(files) == set(common.DERIVE_FILES)\n"
         "            wrong = dict(files)\n"
         "            wrong['derive.py'] = '0' * 64\n"
         "            assert wrong != files\n"
         "            (root / 'run_checks.py').write_text('tampered', 'utf-8')\n"
         "            try:\n"
         "                common.verified_derive(folder, commit, root)\n"
         "                raise AssertionError('tampered tracker was accepted')\n"
         "            except RuntimeError:\n"
         "                pass\n"
         "            (root / 'run_checks.py').unlink()\n"
         "            try:\n"
         "                common.verified_derive(folder, commit, root)\n"
         "                raise AssertionError('missing tracker was accepted')\n"
         "            except RuntimeError:\n"
         "                pass\n"
         "            try:\n"
         "                common.verified_derive(folder, 'f' * 40, root)\n"
         "                raise AssertionError('unknown commit was accepted')\n"
         "            except RuntimeError:\n"
         "                pass\n"
         "            shutil.copy2(HERE / 'run_checks.py', root / 'run_checks.py')\n"
         "            _write(package / 'derive.py', 'uncommitted change\\n')\n"
         "            shutil.copy2(package / 'derive.py', root / 'derive.py')\n"
         "            try:\n"
         "                common.verified_derive(folder, commit, root)\n"
         "                raise AssertionError('uncommitted change was accepted')\n"
         "            except RuntimeError:\n"
         "                pass\n"
         "        finally:\n"
         "            shutil.rmtree(root, ignore_errors=True)\n"
         "    finally:\n"
         "        shutil.rmtree(folder, ignore_errors=True)\n"
         "    ok('tracker sources bind to the commit; tamper/missing/old/wrong '\n"
         "       'are rejected')\n"
         "\n"
         "\n"
         "def main():\n"
         "    root = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                 prefix='reviewed-planning380-check-'))\n",
         1),
        ('sealed label 874',
         "    ok('859 sealed map and real plan gate accept 859 and reject "
         "tampering')\n",
         "    ok('874 sealed map and real plan gate accept 874 and reject "
         "tampering')\n",
         1),
        ('real recompute gate tests',
         "def main():\n"
         "    root = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                 prefix='reviewed-planning380-check-'))\n",
         "def _gate_repo(derive_text):\n"
         "    base = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                prefix='reviewed-planning380-git-'))\n"
         "    package = base / 'tools' / 'reviewed-planning380'\n"
         "    package.mkdir(parents=True)\n"
         "    (package / 'derive.py').write_text(derive_text, 'utf-8')\n"
         "    for name in ('run_checks.py', 'README.md'):\n"
         "        shutil.copy2(HERE / name, package / name)\n"
         "    env = dict(os.environ, GIT_AUTHOR_NAME='fixture',\n"
         "               GIT_AUTHOR_EMAIL='f@example.invalid',\n"
         "               GIT_COMMITTER_NAME='fixture',\n"
         "               GIT_COMMITTER_EMAIL='f@example.invalid')\n"
         "    subprocess.run(['git', 'init', '-q', str(base)], check=True,\n"
         "                   capture_output=True)\n"
         "    subprocess.run(['git', '-C', str(base), '-c', "
         "'core.autocrlf=false', 'add', '.'], check=True,\n"
         "                   capture_output=True)\n"
         "    subprocess.run(['git', '-C', str(base), '-c', "
         "'core.autocrlf=false', 'commit', '-q', '-m', 'fixture'],\n"
         "                   check=True, capture_output=True, env=env)\n"
         "    commit = subprocess.run(['git', '-C', str(base), 'rev-parse',\n"
         "                             'HEAD'], check=True, "
         "capture_output=True,\n"
         "                            text=True).stdout.strip()\n"
         "    return base, commit\n"
         "\n"
         "\n"
         "def _gate_pkg(derive_text, outputs):\n"
         "    root = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                 prefix='reviewed-planning380-gate-'))\n"
         "    (root / 'derive.py').write_text(derive_text, 'utf-8')\n"
         "    for name in ('run_checks.py', 'README.md'):\n"
         "        shutil.copy2(HERE / name, root / name)\n"
         "    for name, raw in outputs.items():\n"
         "        (root / name).write_bytes(raw)\n"
         "    return root\n"
         "\n"
         "\n"
         "def _frozen_text(outputs):\n"
         "    digests = {name: hashlib.sha256(raw).hexdigest()\n"
         "               for name, raw in outputs.items()}\n"
         "    text = (HERE / 'derive.py').read_text('utf-8')\n"
         "    for name, digest in digests.items():\n"
         "        marker = \"    %r: '\" % name\n"
         "        start = text.index(marker)\n"
         "        end = text.index(\"',\", start)\n"
         "        text = text[:start] + marker + digest + text[end:]\n"
         "    return text, digests\n"
         "\n"
         "\n"
         "def test_source_worktree():\n"
         "    folder = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                   prefix='reviewed-planning380-pins-'))\n"
         "    try:\n"
         "        package = folder / 'tools' / 'preserved-planning377'\n"
         "        package.mkdir(parents=True)\n"
         "        names = common.SOURCE_PINS\n"
         "        names = names['tools/preserved-planning377']['files']\n"
         "        for name in names:\n"
         "            shutil.copy2(PROJECT / 'tools' / "
         "'preserved-planning377' / name, package / name)\n"
         "        env = dict(os.environ, GIT_AUTHOR_NAME='fixture',\n"
         "                   GIT_AUTHOR_EMAIL='f@example.invalid',\n"
         "                   GIT_COMMITTER_NAME='fixture',\n"
         "                   GIT_COMMITTER_EMAIL='f@example.invalid')\n"
         "        subprocess.run(['git', 'init', '-q', str(folder)], "
         "check=True, capture_output=True)\n"
         "        subprocess.run(['git', '-C', str(folder), '-c', "
         "'core.autocrlf=false', 'add', '.'], check=True,\n"
         "                       capture_output=True)\n"
         "        subprocess.run(['git', '-C', str(folder), '-c', "
         "'core.autocrlf=false', 'commit', '-q', '-m', 'fixture'],\n"
         "                       check=True, capture_output=True, env=env)\n"
         "        commit = subprocess.run(['git', '-C', str(folder),\n"
         "                                 'rev-parse', 'HEAD'], check=True,\n"
         "                                capture_output=True,\n"
         "                                text=True).stdout.strip()\n"
         "        pins = {'tools/preserved-planning377': {\n"
         "            'commit': commit, 'files': list(names)}}\n"
         "        common.verified_sources(folder, pins)\n"
         "        target = package / 'common.py'\n"
         "        target.write_bytes(target.read_bytes() + b'\\n# drift\\n')\n"
         "        try:\n"
         "            common.verified_sources(folder, pins)\n"
         "            raise AssertionError('worktree drift was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "        target.unlink()\n"
         "        try:\n"
         "            common.verified_sources(folder, pins)\n"
         "            raise AssertionError('missing worktree pin was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "        shutil.copy2(PROJECT / 'tools' / 'preserved-planning377'\n"
         "                     / 'common.py', target)\n"
         "        real = package / 'real_common.py'\n"
         "        shutil.copy2(target, real)\n"
         "        target.unlink()\n"
         "        try:\n"
         "            os.symlink(real, target)\n"
         "        except (OSError, NotImplementedError):\n"
         "            print('SKIP symlink pinned-source check')\n"
         "        else:\n"
         "            try:\n"
         "                common.verified_sources(folder, pins)\n"
         "                raise AssertionError('symlink pin was accepted')\n"
         "            except RuntimeError:\n"
         "                pass\n"
         "    finally:\n"
         "        shutil.rmtree(folder, ignore_errors=True)\n"
         "    ok('pinned worktree drift/missing/symlink are rejected')\n"
         "\n"
         "\n"
         "def test_derive_gate():\n"
         "    import derive\n"
         "    outputs = derive.compute(PROJECT)\n"
         "    frozen, digests = _frozen_text(outputs)\n"
         "    base, commit = _gate_repo(frozen)\n"
         "    pkg = _gate_pkg(frozen, outputs)\n"
         "    try:\n"
         "        files = common.verified_derive(base, commit, pkg)\n"
         "        plan = {'derive_commit': commit,\n"
         "                'derive_file_sha256': files,\n"
         "                'derived_file_sha256': digests}\n"
         "        tool.verify_derive(pkg, plan, base, PROJECT)\n"
         "        forged_root = _gate_pkg(frozen, outputs)\n"
         "        try:\n"
         "            (forged_root / 'worker.py').write_bytes(\n"
         "                outputs['worker.py'] + b'\\n# forged\\n')\n"
         "            forged = {'derive_commit': commit,\n"
         "                      'derive_file_sha256': files,\n"
         "                      'derived_file_sha256':\n"
         "                          common.derived_digests(forged_root)}\n"
         "            try:\n"
         "                tool.verify_derive(forged_root, forged, base, PROJECT)\n"
         "                raise AssertionError(\n"
         "                    'forged derived bytes were accepted')\n"
         "            except RuntimeError:\n"
         "                pass\n"
         "        finally:\n"
         "            shutil.rmtree(forged_root, ignore_errors=True)\n"
         "    finally:\n"
         "        shutil.rmtree(pkg, ignore_errors=True)\n"
         "        shutil.rmtree(base, ignore_errors=True)\n"
         "    zero = frozen\n"
         "    for name in derive.DERIVED_FILES:\n"
         "        marker = \"    %r: '\" % name\n"
         "        zero = zero.replace(marker + digests[name],\n"
         "                            marker + '0' * 64)\n"
         "    base, commit = _gate_repo(zero)\n"
         "    pkg = _gate_pkg(zero, outputs)\n"
         "    try:\n"
         "        files = common.verified_derive(base, commit, pkg)\n"
         "        plan = {'derive_commit': commit,\n"
         "                'derive_file_sha256': files,\n"
         "                'derived_file_sha256': digests}\n"
         "        try:\n"
         "            tool.verify_derive(pkg, plan, base, PROJECT)\n"
         "            raise AssertionError('tampered DERIVED_SHA was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "    finally:\n"
         "        shutil.rmtree(pkg, ignore_errors=True)\n"
         "        shutil.rmtree(base, ignore_errors=True)\n"
         "    unfrozen = frozen\n"
         "    for name in derive.DERIVED_FILES:\n"
         "        marker = \"    %r: '\" % name\n"
         "        unfrozen = unfrozen.replace(marker + digests[name], marker)\n"
         "    base, commit = _gate_repo(unfrozen)\n"
         "    pkg = _gate_pkg(unfrozen, outputs)\n"
         "    try:\n"
         "        files = common.verified_derive(base, commit, pkg)\n"
         "        plan = {'derive_commit': commit,\n"
         "                'derive_file_sha256': files,\n"
         "                'derived_file_sha256': digests}\n"
         "        try:\n"
         "            tool.verify_derive(pkg, plan, base, PROJECT)\n"
         "            raise AssertionError('unfrozen DERIVED_SHA was accepted')\n"
         "        except RuntimeError:\n"
         "            pass\n"
         "    finally:\n"
         "        shutil.rmtree(pkg, ignore_errors=True)\n"
         "        shutil.rmtree(base, ignore_errors=True)\n"
         "    ok('real recompute accepts frozen bytes and rejects forgery/constants')\n"
         "\n"
         "\n"
         "def main():\n"
         "    root = Path(tempfile.mkdtemp(dir=PROJECT / 'work',\n"
         "                                 prefix='reviewed-planning380-check-'))\n",
         1),
        ('main test list',
         "        test_approval_rejections()\n"
         "        test_manifest_tamper()\n",
         "        test_approval_rejections()\n"
         "        test_manifest_tamper()\n"
         "        test_source_worktree()\n"
         "        test_derive_gate()\n"
         "        test_derive_binding()\n",
         1),
    ],
}

FORBIDDEN = {
    'common.py': [
        "BATCH = 'preserved-planning377'",
        "work\\preserved-planning377')",
        'OLD_375_PLAN_SHA',
        "'Old 375 plan",
        "'Old 831 map changed'",
        "OLD_ENTRY_COUNT = 3",
        "TOTAL_SEALED_COUNT = 859",
        "RUNTIME_PID_OBSERVED = 12020",
    ],
    'worker.py': [
        'for i in range(6)',
        "'confirmations': []",
        '0.020125524',
    ],
    'tool.py': [
        "'messages': 6, 'versions': 5, 'planning_runs': 1",
        "OLD_375_PLAN_SHA",
        'ref not in OLD_REFS',
        'len(planning) == 1 and',
        'def pending(root):',
    ],
    'checks.py': [
        'range(831)',
        'range(27)',
        '== 859',
        "'0.410.0'",
        '12020',
        'derivation.py',
    ],
}

GATES = {
    'common.py': [
        'TOTAL_SEALED_COUNT = 874',
        'SOURCE_FILE_SHA',
        'def verify_377_stop',
        'def retired_refs',
        'def verified_derive',
        'def derived_digests',
        'refs = set(OLD_REFS)',
        'PRIOR_DIR = ',
    ],
    'worker.py': ['range(7)', '0.003040692', "len(old_task.get('planning_runs') or []) == 2"],
    'tool.py': [
        "retired = retired_refs(PROJECT)",
        "ref not in retired",
        'def verify_derive',
        'def _load_verified_derive',
        'module.check(origin_project, root)',
        'module.frozen()',
        'verify_derive(root, plan)',
        'verify_377_stop',
        "require(len(planning) == 2",
        "'derived_file_sha256': derived,",
        "args.derive_commit",
    ],
    'checks.py': [
        'range(859)',
        'range(14)',
        '874',
        '874 sealed map',
        'test_derive_binding',
        'test_source_worktree',
        'test_derive_gate',
        '34736',
        "'0.411.0-old'",
        'verify_377_stop',
    ],
}

# === ENGINE BELOW ===


def _git_blob(project, commit, path):
    _require(isinstance(commit, str) and len(commit) == 40
             and all(ch in '0123456789abcdef' for ch in commit),
             'Origin commit is not a full Git id')
    _require(isinstance(path, str) and path and '\\' not in path,
             'Origin path changed')
    done = subprocess.run(['git', '-C', str(project), 'cat-file', 'blob',
                           commit + ':' + path], capture_output=True)
    _require(done.returncode == 0, 'Missing trusted Git source: ' + path)
    return done.stdout


def load_origin(project=PROJECT):
    project = Path(project)
    result = {}
    for name in ORIGIN_FILES:
        raw = _norm(_git_blob(project, ORIGIN_COMMIT, ORIGIN_DIR + '/' + name))
        _require(_sha_bytes(raw) == ORIGIN_SHA[name],
                 'Origin digest changed: ' + name)
        result[name] = raw
    return result


def _apply(name, text):
    for index, item in enumerate(OPS[name]):
        label, old, new, expected = item
        count = text.count(old)
        _require(count == expected,
                 name + ' op ' + str(index) + ' ' + label + ' count ' + str(count))
        text = text.replace(old, new)
    for value in FORBIDDEN[name]:
        _require(value not in text, name + ' retains forbidden text: ' + value)
    for value in GATES[name]:
        _require(value in text, name + ' is missing gate text: ' + value)
    return text


def compute(project=PROJECT):
    origin = load_origin(project)
    result = {}
    for name in DERIVED_FILES:
        text = _apply(name, origin[name].decode('utf-8'))
        raw = text.encode('utf-8')
        compile(raw, name, 'exec')
        result[name] = raw
    return result


def frozen():
    values = [DERIVED_SHA[name] for name in DERIVED_FILES]
    return all(isinstance(value, str) and len(value) == 64
               and all(ch in '0123456789abcdef' for ch in value)
               for value in values)


def _enforce(digests, allow_bootstrap):
    if frozen():
        for name in DERIVED_FILES:
            _require(digests[name] == DERIVED_SHA[name],
                     'Derived digest changed: ' + name)
        return
    _require(allow_bootstrap,
             'DERIVED_SHA is not frozen; run derive.py --print-sha and commit '
             'the four constants before any real freeze')
    print('WARNING bootstrap: DERIVED_SHA is not frozen; public checks only',
          file=sys.stderr)


def _first_diff(left, right):
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right))


def _root_path(project, root):
    project = Path(project).resolve()
    work = project / 'work'
    raw = Path(root)
    _require(raw.is_absolute(), 'Root must be absolute')
    lexical = Path(os.path.abspath(str(raw)))
    _require(lexical.parent == work, 'Root must be a direct child of work')
    probe = lexical
    while True:
        _require(not probe.is_symlink(),
                 'Root path may not use symlinks: ' + str(probe))
        if probe == work:
            break
        _require(work in probe.parents, 'Root escaped work')
        probe = probe.parent
    resolved = lexical.resolve()
    _require(resolved.parent == work.resolve(),
             'Resolved root must be a direct child of work')
    _require(not resolved.is_symlink(), 'Root must not be a symlink')
    return resolved


def materialize(project, root, templates=(), allow_bootstrap=False):
    root = _root_path(project, root)
    _require(not (root / '.git').exists(), 'Root must not be a Git checkout')
    allowed = set(DERIVED_FILES) | set(templates)
    if root.exists():
        _require(root.is_dir(), 'Root is not a directory')
        for path in root.iterdir():
            _require(path.name in allowed, 'Unexpected file in root: ' + path.name)
    else:
        root.mkdir()
    outputs = compute(project)
    digests = {name: _sha_bytes(raw) for name, raw in outputs.items()}
    _enforce(digests, allow_bootstrap)
    for name, raw in outputs.items():
        path = root / name
        if path.exists():
            _require(path.is_file() and not path.is_symlink(),
                     'Derived path is not a file: ' + name)
            _require(path.read_bytes() == raw,
                     'Derived file differs from derivation: ' + name)
        else:
            path.write_bytes(raw)
    return digests


def check(project, root):
    root = _root_path(project, root)
    _require(root.is_dir(), 'Root missing')
    outputs = compute(project)
    digests = {}
    for name, raw in outputs.items():
        path = root / name
        _require(path.is_file() and not path.is_symlink(),
                 'Derived file missing: ' + name)
        actual = path.read_bytes()
        _require(actual == raw,
                 'Derived bytes differ: ' + name + ' at '
                 + str(_first_diff(actual, raw)))
        digests[name] = _sha_bytes(raw)
    _enforce(digests, False)
    return digests


def print_sha(project=PROJECT):
    project = Path(project).resolve()
    folder = Path(tempfile.mkdtemp(dir=project / 'work',
                                  prefix='reviewed-planning380-sha-'))
    try:
        digests = materialize(project, folder, allow_bootstrap=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    print('DERIVED_SHA = {')
    for name in DERIVED_FILES:
        print('    %r: %r,' % (name, digests[name]))
    print('}')
    return digests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--print-sha', action='store_true')
    parser.add_argument('--materialize', action='store_true')
    parser.add_argument('--root')
    parser.add_argument('--allow-bootstrap', action='store_true')
    args = parser.parse_args()
    if args.print_sha:
        print_sha(PROJECT)
        return
    _require(args.root, '--root is required')
    if args.check:
        value = check(PROJECT, args.root)
    else:
        _require(args.materialize, 'Use --check, --materialize or --print-sha')
        value = materialize(PROJECT, args.root, templates=TRACKER_FILES,
                            allow_bootstrap=args.allow_bootstrap)
    print(json.dumps({'root': str(Path(args.root).resolve()),
                      'frozen': frozen(), 'files': value},
                     ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
