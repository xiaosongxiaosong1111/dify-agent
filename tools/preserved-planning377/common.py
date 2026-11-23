"""Shared read-only helpers and frozen constants for preserved-planning377.

Nothing here writes to data/work on import.  Real production access only happens
inside tool.py after its canonical/approval gates have passed.
"""
import contextlib
import hashlib
import json
import re
import sqlite3
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
BATCH = 'preserved-planning377'
CANONICAL = Path(r'E:\workSpace\dify-agent\work\preserved-planning377')
ORIGINAL_PROJECT = Path(r'E:\workSpace\dify-agent')

TARGET_TASK = '1154f0c0-5e01-4492-b5c7-97bfbbbc2a61'
TARGET_REVISION = 6
ENVIRONMENT_ID = '202bfb35-2f92-47c1-bc1b-eac32082181d'
PROVIDER_ID = '9513f594-c256-46b7-882a-35d9871bf9d0'
PROVIDER_MODEL = 'deepseek-flash'
PROVIDER_PROTOCOL = 'openai-compatible'
RUNTIME_BUILD = '0.411.0-90c28f738d4306fbff75'
RUNTIME_VERSION = '0.411.0'
RUNTIME_FILE_COUNT = 298
RUNTIME_PID_OBSERVED = 12020

BUDGET_LIMIT = '0.600'
BUDGET_POLICY_REVISION = 1
SETTLED_TOTAL = '0.020125524'
OLD_ENTRY_COUNT = 3
PER_CALL_USD = '0.100'
PER_MODEL_TOTAL_USD = '0.100'
MODEL_BOOK_UPPER_USD = '3.355473652'
WALL_SECONDS = 600
MAX_MODEL_HTTP = 1
OUTPUT_TOKENS = 6000
TIMEOUT_SECONDS = 120

LIMITS = {'new_tasks': 0, 'model': 1, 'reads': 0, 'login': 0,
          'import': 0, 'publish': 0, 'key': 0, 'run': 0}
UPPER = {'model': 57, 'reads': 1730, 'login': 50, 'import': 30,
         'publish': 30, 'key': 30, 'run': 148}
EXPECTED_COUNTS = {'task': 27, 'environment': 10, 'provider': 2}

APPROVAL_PHRASE = '允许将375剩余一槽及0.100 USD预留明确改授本次单规划批'
APPROVAL_SUFFIX = '/q0'
OLD_REFS = {
    'call_f5b63df1752f441284ac9ee97f031930/q0',
    'call_f946936e3fa747669cd271019cf87e75/q0',
    'call_b4c700f1b4d24950a303b16fbe157440/q0',
    'call_ae6b67f5efb74c0c92f2dff733484166/q0',
    'call_19a54287e07f4214acf3a0235a269efc/q0',
    'call_2198e5ab4b42451d988d3bda9e350cb3/q0',
}

OLD_375_PLAN_SHA = '5b1edcd51cfb54415a3a555089368efe26a8b93ce518cfdf305a794e6af43f97'
SEAL_INDEX_SHA = 'e3daff9307529b626b003d081035a601d9cc81f9a2420d88f2ddd6593fb4cdb6'
OLD_MAP_COUNT = 831
SEAL_ENTRY_COUNT = 27
TOTAL_SEALED_COUNT = 859

OLD_375_DIR = 'work/autonomous-dual375'
OLD_375_PROGRESS = 'work/autonomous-dual375/live-output/progress.json'
OLD_375_ATTEMPT = 'work/autonomous-dual375/attempt.json'

ISOLATED = {
    '391': 'work/chatflow-model391/live-output/data',
    '394': 'work/clarified-chatflow394/live-output/data',
    '399': 'work/bounded-chatflow399/live-output/data',
    '401': 'work/reviewed-chatflow401/live-output/data',
    '405': 'work/offline-candidate405/data',
    '408': 'work/reviewed-planning408/live-output/data',
    '409': 'work/offline-candidate409/data',
    '414': 'work/autonomous-chatflow414/live-output/data',
    '416': 'work/autonomous-chatflow416/live-output/data',
    '418': 'work/recovered-chatflow418/live-output/data',
    '420': 'work/reviewed-spec-planning420/live-output/data',
}

SOURCE_PINS = {
    'tools/autonomous-dual375': {'commit': '6fbd030', 'files': ['derivation.py']},
    'tools/autonomous-dual374': {'commit': '4ac8e32',
                                 'files': ['reuse_policy.py', 'storage_guard.py']},
}
PACKAGE_FILES = ('README.md', 'checks.py', 'common.py', 'tool.py', 'worker.py')

SETTINGS = {'max_retries': 0, 'max_minutes': 2, 'max_cost_usd': .100}

PUBLIC_TASK = '00000000-0000-4000-8000-000000000377'
PUBLIC_ENV = '00000000-0000-4000-8000-000000000378'
PUBLIC_PROVIDER = '00000000-0000-4000-8000-000000000379'
PUBLIC_KEY = 'PUBLIC_SYNTHETIC_ONLY'

REQUIREMENTS = {
    'goal': '为内部演示用户提供售后资料问答及合成订单查询Chatflow，仅使用公开合成资料和订单，不接入客户数据。',
    'audience': '内部开发和演示用户；不接入真实客户或真实订单系统。',
    'input': '每次一个必填query文字；新样例新会话，缺少订单号时追问，下一轮只补明确订单号。',
    'output': '输出answer文字；订单回复明确标为模拟。缺号逐字回复：订单查询目前为模拟，请提供订单号。 范围外逐字回复：目前只支持售后资料问答和模拟订单查询，请说明您的诉求。 资料无答案逐字回复：知识库暂无相关信息，请联系人工客服，并提供订单号。',
    'rules': '先分类资料问答、订单查询或范围外。资料支路先检索；空结果直接固定无答案回复，有片段才调用回答模型且只依据片段；片段不足仍用同一无答案文字，不编造政策。订单支路只提取明确订单号，提取失败不查询而追问；成功才查询唯一合成表。记忆明确启用最近5轮；同一缺号追问后补DEMO-001须仍走订单支路，不猜其它单号；不同样例不复用会话。提取成功后另行验证业务单号为非空文字，空白用原固定追问且不查询；类型错误停止，不把required或成功标识当业务有效保证。两个每会话boolean登记/消费标记初始false，不同表示等待；每轮先消费，仅等待且原格式编号绕过分类进入原提取/非空守卫，缺号再登记，新话题仍分类。不保存单号或敏感信息，不跨会话共享。两个每会话状态order_wait_requested和order_wait_consumed均为boolean，初值false、未更新保留；不相等表示等待，不跨会话。补号格式为1至64位、首位字母数字、其余字母数字下划线或连字符，仅等待时绕过分类仍走原提取及非空检查；每状态唯一根writer，不放松。',
    'knowledge': '复用公开合成FAQ d12cf081-5c52-41e3-b869-e94e6f8d37b1，TopK3、无阈值、不重排。订单接口缺少，明确采用订单查询模拟，唯一合成表DEMO-001=合成样例：已发货。分类/提取/回答模型deepseek-flash，thinking=false、温度0.2、最大输出512。',
    'exceptions': '技术调用失败停止，不冒充无命中或提取失败；未知不重跑。无答案可来自空检索或有片段但不足，分别记录轨迹，不把后者称作空检索。转人工只是文字，不创建人工服务或外部接口。',
    'tests': '六个公开样例：资料命中、资料无相关答案、范围外、订单存在、订单不存在、缺号后同会话补号；最后样例两轮，其余单轮。本批仅规划静态核对，不执行这些样例，未导入或运行Dify。',
}

CONFIGURATION = {
    'dify_model_provider': 'langgenius/deepseek/deepseek',
    'dify_model': 'deepseek-flash',
    'temperature': 0.2,
    'max_tokens': 512,
    'model_parameters': {'thinking': False},
    'opening_statement': '内部公开演示：订单为合成模拟，非真实订单。',
    'suggested_questions': [],
    'conversation_memory': True,
    'memory_turns': 5,
    'dataset_ids': ['d12cf081-5c52-41e3-b869-e94e6f8d37b1'],
    'retrieval_top_k': 3,
    'mock_dependencies': ['订单查询模拟'],
    'mock_dependency_bindings': [{
        'node_id': 'order_lookup',
        'dependency': '订单查询模拟',
        'replacement_todo': '公开替身只验证协议；不连接真实订单。',
    }],
    'resource_plan': '本机公开替身；0真实模型/Dify/登录/资源/运行。',
}

INPUTS = {
    'source_text': '',
    'dependency': '订单查询模拟',
    'records_text': '{"DEMO-001":"合成样例：已发货。"}',
    'no_hit_reply': '知识库暂无相关信息，请联系人工客服，并提供订单号。',
    'missing_order_reply': '订单查询目前为模拟，请提供订单号。',
    'clarify_reply': '目前只支持售后资料问答和模拟订单查询，请说明您的诉求。',
}

CASES = [
    {'id': 'faq-hit', 'name': '资料政策命中',
     'input': {'query': 'ZXRET715在签收后七天内且未拆封，能否退货？请给出政策编号。'},
     'expectation': {'mode': 'contains', 'target': 'answer', 'expected': ['ZXRET715', '七天', '未拆封']},
     'required': True},
    {'id': 'faq-no-answer', 'name': '资料无相关答案',
     'input': {'query': '请查询售后资料中的政策编号 ZXUNLISTED90371。'},
     'expectation': {'mode': 'equals', 'target': 'answer', 'expected': '知识库暂无相关信息，请联系人工客服，并提供订单号。'},
     'required': True},
    {'id': 'clarify', 'name': '范围外请求澄清',
     'input': {'query': '请帮我预订去火星的机票。'},
     'expectation': {'mode': 'equals', 'target': 'answer', 'expected': '目前只支持售后资料问答和模拟订单查询，请说明您的诉求。'},
     'required': True},
    {'id': 'order-found', 'name': '模拟订单存在',
     'input': {'query': '查询订单 DEMO-001'},
     'expectation': {'mode': 'equals', 'target': 'answer', 'expected': '模拟订单查询（非真实订单）：合成样例：已发货。'},
     'required': True},
    {'id': 'order-not-found', 'name': '模拟订单不存在',
     'input': {'query': '查询订单 UNLISTED-DEMO'},
     'expectation': {'mode': 'equals', 'target': 'answer', 'expected': '模拟订单查询（非真实订单）：未找到该模拟订单，请核对订单号。'},
     'required': True},
    {'id': 'missing-then-order', 'name': '先缺号再补号的同会话',
     'input': {'query': '我想查询订单状态，但尚未提供订单号。'},
     'expectation': {'mode': 'equals', 'target': 'answer', 'expected': '订单查询目前为模拟，请提供订单号。'},
     'required': True,
     'followups': [{'input': {'query': 'DEMO-001'},
                    'expectation': {'mode': 'equals', 'target': 'answer',
                                    'expected': '模拟订单查询（非真实订单）：合成样例：已发货。'}}]},
]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def uuid(value):
    from uuid import UUID
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def is_hex(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{64}', value))


def money(value, label='amount'):
    require(isinstance(value, str) and value, label + ' must be decimal text')
    try:
        amount = Decimal(value)
    except InvalidOperation:
        require(False, label + ' is not decimal')
    require(amount.is_finite() and amount >= 0, label + ' must be finite and non-negative')
    return amount


def load(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result
    raw = Path(path).read_bytes()
    require(len(raw) <= 20_000_000, 'JSON too large')
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'Non-finite JSON'))


def normalize_source(raw):
    require(isinstance(raw, bytes), 'Source is not bytes')
    return raw.replace(b'\r\n', b'\n')


class ReadOnly:
    """Open the SQLite database read-only.  Never decrypts or writes."""

    def __init__(self, root):
        self.root = Path(root)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect((self.root / 'flowcraft.sqlite3').as_uri() + '?mode=ro', uri=True)
        try:
            yield db
        finally:
            db.close()

    def get(self, kind, item):
        with self.connect() as db:
            row = db.execute('SELECT value FROM objects WHERE kind=? AND id=?', (kind, item)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind):
        with self.connect() as db:
            return [json.loads(row[0]) for row in
                    db.execute('SELECT value FROM objects WHERE kind=?', (kind,))]


EXCLUDED_FILES = {'flowcraft.sqlite3', 'flowcraft.sqlite3-shm', 'flowcraft.sqlite3-wal',
                  'server.pid', 'server.out.log', 'server.err.log'}


def capture(store):
    with store.connect() as db:
        objects = {kind + ':' + item: digest(json.loads(value)) for kind, item, value in
                   db.execute('SELECT kind,id,value FROM objects')}
        secrets = {item: sha_bytes(bytes(value)) for item, value in
                   db.execute('SELECT id,value FROM secrets')}
    files = {}
    root = Path(store.root)
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if path.parent == root and path.name in EXCLUDED_FILES:
            continue
        require(path.resolve().is_relative_to(root.resolve()), 'Asset link outside data root')
        files[str(path.relative_to(root)).replace('\\', '/')] = sha(path)
    return {'objects': objects, 'secrets': secrets, 'files': files}


def history_prefix(task):
    require(isinstance(task, dict), 'Task must be a mapping')
    result = {}
    for key in ('messages', 'versions', 'planning_runs', 'intake_history', 'runs'):
        value = task.get(key)
        require(isinstance(value, list), 'Task history field missing or not list: ' + key)
        result[key] = {'count': len(value), 'sha256': digest(value)}
    if 'interview_attempts' in task:
        value = task['interview_attempts']
        require(isinstance(value, list), 'interview_attempts must be a list when present')
        result['interview_attempts'] = {'present': True, 'count': len(value), 'sha256': digest(value)}
    else:
        result['interview_attempts'] = {'present': False, 'count': 0, 'sha256': digest([])}
    return result


def _direct_map(value, count, label):
    require(isinstance(value, dict) and len(value) == count, label + ' count changed')
    require(all(is_hex(v) for v in value.values()), label + ' SHA invalid')
    return value


def _relative_seal_map(value):
    """The real seal is a direct 27-entry map relative to the 375 package."""
    require(isinstance(value, dict) and len(value) == SEAL_ENTRY_COUNT,
            '375 seal must be a 27-entry relative map')
    result = {}
    for name, value_sha in value.items():
        require(isinstance(name, str) and name and not name.startswith('/')
                and '\\' not in name and ':' not in name
                and all(part and part not in {'.', '..'} for part in name.split('/'))
                and not name.startswith('work/'),
                '375 seal key must be package-relative: ' + str(name))
        require(is_hex(value_sha), '375 seal SHA invalid: ' + name)
        result[OLD_375_DIR + '/' + name] = value_sha
    return result


def _check_sealed_path(path):
    require(isinstance(path, str) and path and not path.startswith('/')
            and '..' not in path.split('/') and path.startswith('work/'),
            'Sealed path outside work: ' + str(path))


def merge_sealed(old_map, seal_entries, index_entries):
    require(isinstance(old_map, dict) and len(old_map) == OLD_MAP_COUNT, 'Old 831 map changed')
    require(isinstance(seal_entries, dict) and len(seal_entries) == SEAL_ENTRY_COUNT,
            '375 seal entry count changed')
    require(isinstance(index_entries, dict) and len(index_entries) == 1,
            'Sealed index count changed')
    merged = {}
    for part in (old_map, seal_entries, index_entries):
        for path, value in part.items():
            _check_sealed_path(path)
            require(is_hex(value), 'Sealed SHA invalid: ' + path)
            if path in merged:
                require(merged[path] == value, 'Conflicting sealed path: ' + path)
            else:
                merged[path] = value
    require(len(merged) == TOTAL_SEALED_COUNT, 'Sealed total is not 859')
    return merged


def verify_375_stop(project=PROJECT):
    """The consumed 375 batch must be stopped with model0/read6/login1 and no late receipt."""
    progress_path = Path(project) / OLD_375_PROGRESS
    attempt_path = Path(project) / OLD_375_ATTEMPT
    require(progress_path.is_file() and not progress_path.is_symlink(), '375 progress missing')
    require(attempt_path.is_file() and not attempt_path.is_symlink(), '375 attempt missing')
    progress = load(progress_path)
    attempt = load(attempt_path)
    expected = {'model': 0, 'reads': 6, 'login': 1, 'import': 0,
                'publish': 0, 'key': 0, 'run': 0}
    require(progress.get('state') == 'stopped', '375 is not stopped')
    require(attempt.get('state') == 'stopped', '375 attempt is not stopped')
    counts = progress.get('dispatch_counts')
    require(isinstance(counts, dict) and set(expected) <= set(counts)
            and all(type(counts[key]) is int and counts[key] == value
                    for key, value in expected.items()), '375 counts changed')
    require(type(progress.get('physical_http')) is int
            and progress['physical_http'] == 7, '375 physical count changed')
    if isinstance(attempt.get('counts'), dict):
        require(all(type(attempt['counts'].get(key)) is int
                    and attempt['counts'].get(key) == value
                    for key, value in expected.items()), '375 attempt counts changed')
    for folder in (Path(project) / OLD_375_DIR,
                   Path(project) / OLD_375_DIR / 'live-output'):
        receipts = [p for p in folder.glob('review-*.json')
                    if not p.name.startswith('review-source-')]
        require(not receipts, 'Unexpected late 375 review receipt: '
                + (str(receipts[0]) if receipts else ''))
    return {'state': 'stopped', 'model': 0, 'reads': 6, 'login': 1,
            'physical_http': 7, 'late_receipt': False}


def load_sealed_map(project=PROJECT, old_plan_sha=OLD_375_PLAN_SHA,
                    seal_index_sha=SEAL_INDEX_SHA):
    project = Path(project)
    old_plan_path = project / OLD_375_DIR / 'plan.json'
    require(old_plan_path.is_file() and not old_plan_path.is_symlink(), 'Old 375 plan missing')
    require(sha(old_plan_path) == old_plan_sha, 'Old 375 plan changed')
    old_map = _direct_map(load(old_plan_path).get('protected_files'),
                          OLD_MAP_COUNT, 'Old 375 protected_files')

    seal_path = project / OLD_375_DIR / 'seal-after-stop.json'
    require(seal_path.is_file() and not seal_path.is_symlink(), '375 seal missing')
    require(sha(seal_path) == seal_index_sha, '375 seal index changed')
    seal_entries = _relative_seal_map(load(seal_path))
    index_entries = {OLD_375_DIR + '/seal-after-stop.json': seal_index_sha}
    merged = merge_sealed(old_map, seal_entries, index_entries)
    verify_375_stop(project)
    return merged


def verify_sealed_map(project, protected_files, old_plan_sha=OLD_375_PLAN_SHA,
                      seal_index_sha=SEAL_INDEX_SHA):
    project = Path(project)
    actual = load_sealed_map(project, old_plan_sha, seal_index_sha)
    require(isinstance(protected_files, dict) and actual == protected_files,
            'Sealed map differs from frozen plan')
    root = project.resolve()
    for name, value in actual.items():
        _check_sealed_path(name)
        path = project / name
        require(path.is_file() and not path.is_symlink(), 'Sealed member missing: ' + name)
        require(path.resolve().is_relative_to(root),
                'Sealed member escapes project: ' + name)
        require(sha(path) == value, 'Sealed member changed: ' + name)
    return True


def resolve_commit(project, short):
    require(isinstance(short, str) and re.fullmatch(r'[0-9a-f]{7,40}', short),
            'Source commit is not a Git id')
    result = subprocess.run(['git', '-C', str(project), 'rev-parse', short + '^{commit}'],
                            capture_output=True)
    require(result.returncode == 0, 'Trusted source commit missing: ' + short)
    full = result.stdout.decode().strip()
    require(re.fullmatch(r'[0-9a-f]{40}', full), 'Resolved commit invalid')
    return full


def git_blob(project, commit, path):
    require(isinstance(commit, str) and re.fullmatch(r'[0-9a-f]{40}', commit),
            'Source commit is not a full Git id')
    require(isinstance(path, str) and path and '\\' not in path, 'Source path changed')
    result = subprocess.run(['git', '-C', str(project), 'cat-file', 'blob',
                             commit + ':' + path], capture_output=True)
    require(result.returncode == 0, 'Trusted Git source missing: ' + path)
    return result.stdout


def verified_sources(project=PROJECT, pins=SOURCE_PINS):
    """Read exact reviewed Git blobs and prove the current worktree matches."""
    project = Path(project)
    result = {}
    commits = {}
    for directory, spec in pins.items():
        require(isinstance(spec, dict) and set(spec) == {'commit', 'files'},
                'Source pin fields changed')
        full = resolve_commit(project, spec['commit'])
        commits[directory] = full
        for name in spec['files']:
            require(isinstance(name, str) and '/' not in name and '\\' not in name,
                    'Source file pin changed')
            raw = normalize_source(git_blob(project, full, directory + '/' + name))
            local = project / directory / name
            require(local.is_file() and not local.is_symlink(), 'Local pinned source missing')
            require(normalize_source(local.read_bytes()) == raw,
                    'Worktree differs from pinned source: ' + directory + '/' + name)
            compile(raw, directory + '/' + name, 'exec')
            result[directory + '/' + name] = raw
    return result, commits
