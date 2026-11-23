"""Public checks for reviewed-planning380.

Default behaviour refuses to run while DERIVED_SHA is empty: it prints the
current computed mapping and exits nonzero, so the root can paste the mapping
once.  Only a frozen derive.py is allowed to materialize and execute the derived
public checks.  `--print-sha` is an explicit read-only diagnostic that prints
the same mapping and exits zero.
"""
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import derive


def _decode(raw):
    if not raw:
        return ''
    for encoding in ('utf-8', 'gbk', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def _emit(stream, raw):
    if not raw:
        return
    buffer = getattr(stream, 'buffer', None)
    if buffer is not None:
        buffer.write(raw)
        buffer.flush()
    else:
        stream.write(_decode(raw))


def _mapping():
    outputs = derive.compute(derive.PROJECT)
    return {name: hashlib.sha256(outputs[name]).hexdigest()
            for name in derive.DERIVED_FILES}


def _print_mapping(mapping):
    print('DERIVED_SHA = {')
    for name in derive.DERIVED_FILES:
        print('    %r: %r,' % (name, mapping[name]))
    print('}')


def _cleanup(path):
    path = Path(path).resolve()
    work = (PROJECT / 'work').resolve()
    if path.parent == work and path.name.startswith(
            'reviewed-planning380-check-'):
        shutil.rmtree(path, ignore_errors=True)
        return True
    print('REFUSED cleanup outside verified temp root: ' + str(path),
          file=sys.stderr)
    return False


def main():
    derive._require(PROJECT == derive.PROJECT,
                    'Tracker and check project roots differ')
    print_sha = '--print-sha' in sys.argv[1:]
    mapping = _mapping()
    if print_sha:
        _print_mapping(mapping)
        return
    if not derive.frozen():
        _print_mapping(mapping)
        print('REFUSED: DERIVED_SHA is not frozen; paste this mapping into '
              'derive.py, commit it, and rerun run_checks.py', file=sys.stderr)
        raise SystemExit(2)
    for name in derive.DERIVED_FILES:
        derive._require(mapping[name] == derive.DERIVED_SHA[name],
                        'DERIVED_SHA mismatch: ' + name)
    staging = Path(tempfile.mkdtemp(dir=PROJECT / 'work',
                                   prefix='reviewed-planning380-check-'))
    try:
        for name in derive.TRACKER_FILES:
            shutil.copy2(HERE / name, staging / name)
        digests = derive.materialize(PROJECT, staging,
                                     templates=derive.TRACKER_FILES)
        for name in derive.DERIVED_FILES:
            path = staging / name
            derive._require(path.is_file() and not path.is_symlink(),
                            'Materialized file missing: ' + name)
        derive._require((staging / 'README.md').read_bytes()
                        == (HERE / 'README.md').read_bytes(),
                        'Package README is not the tracker README')
        expected = set(derive.DERIVED_FILES) | set(derive.TRACKER_FILES)
        actual = {path.name for path in staging.iterdir()}
        derive._require(actual == expected, 'Public package file set changed')
        done = subprocess.run([sys.executable, '-I', str(staging / 'checks.py')],
                              cwd=str(PROJECT), capture_output=True,
                              timeout=1800)
        _emit(sys.stdout, done.stdout)
        if done.returncode != 0:
            _emit(sys.stderr, done.stderr)
            raise SystemExit(done.returncode)
        if done.stderr and done.stderr.strip():
            _emit(sys.stderr, done.stderr)
        print('DONE reviewed-planning380 public checks: derived digests frozen')
        for name in derive.DERIVED_FILES:
            print('%s %s' % (digests[name], name))
    finally:
        _cleanup(staging)


if __name__ == '__main__':
    main()
