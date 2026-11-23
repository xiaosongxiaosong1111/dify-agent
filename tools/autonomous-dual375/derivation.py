"""Small shared helper: trusted Git source pins, exact byte derivation and history shapes.

Only source text is normalized (CRLF -> LF).  Data, old seals, runtime files and
profile values are never rewritten here.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

BATCH = 'autonomous-dual375'
SOURCE_DIR_337 = 'tools/autonomous-dual337'
SOURCE_DIR_374 = 'tools/autonomous-dual374'
SOURCE_COMMIT_337 = 'f0e7beefb331db0b9c07f24cf19786b85d05b13c'
SOURCE_COMMIT_374 = '4ac8e3282093fe0ba6a5298fcac9cc279e3e03bf'
SOURCE_NORMALIZATION = 'crlf_to_lf'

PINNED_337 = (
    'common.py', 'boundary.py', 'candidate.py', 'reviews.py', 'pagination.py',
    'runtime_reference.py', 'fixture.json',
)
PINNED_374 = (
    'reuse_policy.py', 'storage_guard.py', 'synthetic.py', 'synthetic_seed.py',
    'rehearse.py', 'journey.py',
)
LOCAL_DIR = 'tools/autonomous-dual375'
LOCAL_FILES = ('derivation.py', 'worker.py', 'execute.py', 'profile.json', 'README.md')
FREEZE_SOURCE = 'prepare.py'
PACKAGE_FILES = tuple(sorted(set(PINNED_337) | set(PINNED_374) | set(LOCAL_FILES)))
FROZEN_SOURCE_FILES = tuple(sorted(set(PACKAGE_FILES) | {'freeze.py', 'approved_scope.md'}))
NAMES = tuple(sorted(set(FROZEN_SOURCE_FILES) | {'plan.json'}))
INTERVIEW_FACTS = {
    'first_interview': {
        'revision': 3,
        'source_sha256': 'b03bee47e7abb510d1b8bb8b695fa914e48d9b3c0979609ffcbdf87a389a2ca7'},
    'complete_interview': {
        'revision': 6,
        'source_sha256': '075790d95559ed63dc060d64a3515ac0eaa2b31117c6bad84c344ad5b61619e7'},
}

LIMITS = {'new_tasks': 0, 'model': 3, 'reads': 122, 'login': 1,
          'import': 2, 'publish': 2, 'key': 2, 'run': 14}
UPPER = {'model': 57, 'reads': 1730, 'login': 50, 'import': 30,
         'publish': 30, 'key': 30, 'run': 148}

SEALS = {
    'autonomous-dual366': {
        'path': 'work/autonomous-dual366/seal-after-stop.json',
        'sha256': 'bb6ab4daf437039b71b844748d881752030db17ef9f07cf5602b24cfc6856803',
        'entries': 26},
    'console-http-probe369': {
        'path': 'work/console-http-probe369/seal.json',
        'sha256': '9bd03c377eeb064b667c0ab23086b76fc315c939ca2ebb49ed29d045f3f6a972',
        'entries': 2},
    'console-port-forward370': {
        'path': 'work/console-port-forward370/seal.json',
        'sha256': '2cbfb287f9cc38b9e65e6fb28c2f14127350ad5b66465c2b864f10b96c3fff85',
        'entries': 6},
    'autonomous-dual371': {
        'path': 'work/autonomous-dual371/seal-after-stop.json',
        'sha256': 'd5d248d5a6ac06afffbb67cc664787332db8c9663b7c44e0d075a589c6e93092',
        'entries': 35},
}

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

MODEL_STAGES_OLD = (b"MODEL_STAGES=('first_interview','complete_interview','additional_interview',"
                    b"'original_plan','modified_interview','modified_plan')")
MODEL_STAGES_NEW = b"MODEL_STAGES=('original_plan','modified_interview','modified_plan')"
RUNTIME_VERSION_OLD = b"runtime.get('version')=='0.410.0'"
RUNTIME_VERSION_NEW = b"runtime.get('version')=='0.411.0'"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def digest(value):
    return sha_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                separators=(',', ':'), allow_nan=False).encode())


def _hex(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{64}', value))


def _githex(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{40}', value))


def normalize_source(raw):
    require(isinstance(raw, bytes), 'Source is not bytes')
    return raw.replace(b'\r\n', b'\n')


def replace_once(raw, old, new, label):
    require(isinstance(raw, bytes), label + ' is not bytes')
    require(isinstance(old, bytes) and isinstance(new, bytes), label + ' replacement is not bytes')
    count = raw.count(old)
    require(count == 1, label + ' replacement count ' + str(count))
    return raw.replace(old, new)


def _text(value):
    return value.encode('utf-8')


def derive_common(raw):
    value = replace_once(raw, b"BATCH_ID='autonomous-dual337'",
                         b"BATCH_ID='autonomous-dual375'", 'BATCH_ID')
    value = replace_once(
        value,
        b"LIMITS={'new_tasks':1,'model':6,'reads':128,'login':1,'import':2,'publish':2,'key':2,'run':14}",
        b"LIMITS={'new_tasks':0,'model':3,'reads':122,'login':1,'import':2,'publish':2,'key':2,'run':14}",
        'LIMITS')
    value = replace_once(value, MODEL_STAGES_OLD, MODEL_STAGES_NEW, 'MODEL_STAGES')
    value = replace_once(value, b"MODEL_TOTAL_USD='0.600'", b"MODEL_TOTAL_USD='0.300'",
                         'MODEL_TOTAL_USD')
    require(b"MODEL_CAP_USD='0.100'" in value, 'Per-call cap changed')
    require(b'autonomous-dual337' not in value, 'Derived common still names 337')
    require(b"'first_interview'" not in value and b"'complete_interview'" not in value,
            'Derived common still exposes old interview stages')
    return value


def derive_journey(raw):
    value = replace_once(
        raw,
        b"'source': 'synthetic_transport', 'dataset_id': dataset,",
        b"'source': 'console_api' if mode=='live' else 'synthetic_transport', 'dataset_id': dataset,",
        'FAQ source label')
    value = replace_once(
        value,
        b"'verification': 'synthetic_public_segments_not_real_platform'})",
        b"'verification': 'actual_public_segments_for_root_review' if mode=='live' "
        b"else 'synthetic_public_segments_not_real_platform'})",
        'FAQ verification label')
    value = replace_once(
        value,
        _text("actor_note='公开替身正常API准入；根代理按本批委托核对，非人类签收，也不代表真实模型访谈。')"),
        _text("actor_note=('根代理按本批委托核对当前历史与模型原文后正常手工采纳；非人类签收，也不代表业务验收。' "
              "if mode=='live' else '公开替身正常API准入；根代理按本批委托核对，非人类签收，也不代表真实模型访谈。'))"),
        'delegated intake note')
    value = replace_once(
        value,
        b"historical_seed='synthetic_prior_shape',",
        b"historical_seed=('actual_preserved_371_interviews' if mode=='live' "
        b"else 'synthetic_prior_shape'),",
        'historical seed label')
    value = replace_once(value, b"synthetic_protocol=True)",
                         b"synthetic_protocol=(mode!='live'))", 'synthetic protocol label')
    value = replace_once(
        value,
        b"'new_tasks': 0, 'physical_http': 0,",
        b"'new_tasks': 0, 'physical_http': (0 if mode!='live' else record.get('physical_http')),",
        'public physical count')
    value = replace_once(
        value,
        b"'reused_interviews': 'synthetic_prior_shape',",
        b"'reused_interviews': ('actual_preserved_371_interviews' if mode=='live' "
        b"else 'synthetic_prior_shape'),",
        'reused interview label')
    value = replace_once(
        value,
        b"'verification': 'synthetic_protocol_only',",
        b"'verification': ('live_normal_product_api_root_reviewed' if mode=='live' "
        b"else 'synthetic_protocol_only'),",
        'verification label')
    require(b"'source': 'synthetic_transport', 'dataset_id'" not in value,
            'FAQ source label not derived')
    require(b"'reused_interviews': 'synthetic_prior_shape'" not in value,
            'Reused interview label not derived')
    return value


def derive_runtime_reference(raw):
    """Change exactly the managed runtime version literal; every other byte stays pinned."""
    value = replace_once(raw, RUNTIME_VERSION_OLD, RUNTIME_VERSION_NEW,
                         'managed runtime version')
    require(b"'0.410.0'" not in value, 'Derived runtime still names 0.410.0')
    require(b"'0.411.0'" in value, 'Derived runtime version missing')
    return value


def derive(name, raw):
    if name == 'common.py':
        return derive_common(raw)
    if name == 'journey.py':
        return derive_journey(raw)
    if name == 'runtime_reference.py':
        return derive_runtime_reference(raw)
    return raw


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
        result['interview_attempts'] = {'present': True, 'count': len(value),
                                        'sha256': digest(value)}
    else:
        result['interview_attempts'] = {'present': False, 'count': 0,
                                        'sha256': digest([])}
    return result


def git_blob(project, commit, path):
    require(_githex(commit), 'Source commit is not a full Git id')
    require(isinstance(path, str) and path and '\\' not in path, 'Source path changed')
    result = subprocess.run(['git', '-C', str(project), 'cat-file', 'blob',
                             commit + ':' + path], capture_output=True)
    require(result.returncode == 0, 'Trusted Git source missing: ' + path)
    return result.stdout


def _inside(project, path, label):
    """Prove a real file whose whole resolved path stays inside the project."""
    project = Path(project).resolve()
    path = Path(path)
    require(path.is_file(), label + ' missing')
    require(not path.is_symlink(), label + ' is a symlink')
    resolved = path.resolve()
    require(resolved != project and resolved.is_relative_to(project),
            label + ' escaped project')
    return path


def local_bytes(project):
    """Read the local 375 implementation after proving every path stays inside."""
    project = Path(project).resolve()
    result = {}
    for name in LOCAL_FILES + (FREEZE_SOURCE,):
        path = project / LOCAL_DIR / name
        _inside(project, path, 'Local file')
        result[name] = path.read_bytes()
    return result


def verified_local(project, commit):
    """Prove local 375 sources equal the committed implementation before freezing."""
    project = Path(project).resolve()
    require(_githex(commit), 'Local source commit is not a full Git id')
    result = local_bytes(project)
    for name, raw in result.items():
        blob = normalize_source(git_blob(project, commit, LOCAL_DIR + '/' + name))
        require(normalize_source(raw) == blob,
                'Local file differs from committed implementation: ' + name)
    return result


def verified_sources(project, source_pins):
    """Read exact reviewed Git blobs and prove the worktree still matches before use."""
    project = Path(project).resolve()
    require(isinstance(source_pins, dict) and set(source_pins) ==
            {SOURCE_DIR_337, SOURCE_DIR_374}, 'Source pin set changed')
    result = {}
    for directory, expected_commit, expected_files in (
            (SOURCE_DIR_337, SOURCE_COMMIT_337, PINNED_337),
            (SOURCE_DIR_374, SOURCE_COMMIT_374, PINNED_374)):
        spec = source_pins[directory]
        require(isinstance(spec, dict) and set(spec) == {'commit', 'files'},
                'Source pin fields changed')
        require(spec['commit'] == expected_commit, 'Source commit changed: ' + directory)
        require(isinstance(spec['files'], list) and set(spec['files']) == set(expected_files)
                and len(spec['files']) == len(expected_files), 'Source file pin changed')
        require(not Path(directory).is_absolute(), 'Source directory changed')
        for name in expected_files:
            raw = normalize_source(git_blob(project, spec['commit'], directory + '/' + name))
            work = project / directory / name
            _inside(project, work, 'Working source')
            require(normalize_source(work.read_bytes()) == raw,
                    'Working source differs from trusted commit: ' + name)
            require(name not in result, 'Duplicate pinned source name: ' + name)
            result[name] = raw
    require(set(result) == set(PINNED_337) | set(PINNED_374), 'Verified source set changed')
    return result
