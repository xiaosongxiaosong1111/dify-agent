"""Build an isolated 374 source package from pinned 337 modules plus this narrow overlay.

Only the `sources` action exists.  It never reads the DB, a secret, a receipt or
the network.  It does not create approval, attempt or live markers.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
WORK = (PROJECT / 'work').resolve()
SOURCE_337 = PROJECT / 'tools' / 'autonomous-dual337'
BATCH = 'autonomous-dual374'

# Unchanged, already reviewed 337 modules that the isolated package still needs.
COPIED_337 = (
    'boundary.py', 'candidate.py', 'reviews.py', 'pagination.py', 'runtime_reference.py',
    'fixture.json', 'boundary_checks.py', 'reviews_checks.py', 'pagination_checks.py',
)
# Narrow local overlay; these are the only files changed by this batch.
LOCAL = (
    'worker.py', 'journey.py', 'storage_guard.py', 'synthetic.py', 'reuse_policy.py',
    'reuse_checks.py', 'rehearse.py', 'synthetic_seed.py', 'README.md', 'prepare.py',
)
DERIVED = ('common.py',)
EXPECTED = set(COPIED_337) | set(LOCAL) | set(DERIVED)

MODEL_STAGES_OLD = (b"MODEL_STAGES=('first_interview','complete_interview','additional_interview',"
                    b"'original_plan','modified_interview','modified_plan')")
MODEL_STAGES_NEW = b"MODEL_STAGES=('original_plan','modified_interview','modified_plan')"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _replace_once(raw, old, new, label):
    require(isinstance(raw, bytes), label + ' is not bytes')
    count = raw.count(old)
    require(count == 1, label + ' replacement count ' + str(count))
    return raw.replace(old, new)


def derive_common(raw):
    value = _replace_once(raw, b"BATCH_ID='autonomous-dual337'",
                          b"BATCH_ID='autonomous-dual374'", 'BATCH_ID')
    value = _replace_once(
        value,
        b"LIMITS={'new_tasks':1,'model':6,'reads':128,'login':1,'import':2,'publish':2,'key':2,'run':14}",
        b"LIMITS={'new_tasks':0,'model':3,'reads':122,'login':1,'import':2,'publish':2,'key':2,'run':14}",
        'LIMITS')
    value = _replace_once(value, MODEL_STAGES_OLD, MODEL_STAGES_NEW, 'MODEL_STAGES')
    value = _replace_once(value, b"MODEL_TOTAL_USD='0.600'", b"MODEL_TOTAL_USD='0.300'",
                          'MODEL_TOTAL_USD')
    require(b"MODEL_CAP_USD='0.100'" in value, 'Per-call cap changed')
    require(b'autonomous-dual337' not in value, 'Derived common still names 337')
    require(b"'first_interview'" not in value and b"'complete_interview'" not in value,
            'Derived common still exposes old interview stages')
    return value


def _read_source(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Source file missing or symlink: ' + str(path))
    return path.read_bytes()


def build(output):
    out = Path(output).resolve()
    require(out.parent == WORK, 'Output must be a direct child of work')
    require(not out.exists() and not out.is_symlink(), 'Output must be new and not a symlink')
    require(out.name == BATCH or out.name.startswith(BATCH + '-'), 'Output name must identify 374')
    require(SOURCE_337.is_dir() and not SOURCE_337.is_symlink(), 'Pinned 337 source missing')
    out.mkdir()
    written = {}
    for name in COPIED_337:
        raw = _read_source(SOURCE_337 / name)
        (out / name).write_bytes(raw)
        written[name] = sha(out / name)
    common_raw = _read_source(SOURCE_337 / 'common.py')
    (out / 'common.py').write_bytes(derive_common(common_raw))
    written['common.py'] = sha(out / 'common.py')
    for name in LOCAL:
        raw = _read_source(HERE / name)
        (out / name).write_bytes(raw)
        written[name] = sha(out / name)
    require(set(path.name for path in out.iterdir() if path.is_file()) == EXPECTED,
            'Written file set changed')
    return {'state': 'sources_ready', 'batch': BATCH, 'output': str(out),
            'files': len(EXPECTED), 'physical_http': 0, 'secret_reads': 0,
            'packaged': written}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sources = sub.add_parser('sources')
    sources.add_argument('--output', required=True)
    args = parser.parse_args()
    require(args.command == 'sources', 'Only sources is allowed')
    print(json.dumps(build(args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
