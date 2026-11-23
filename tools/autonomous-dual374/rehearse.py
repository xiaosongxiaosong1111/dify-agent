"""Run only three public rehearsals; physical HTTP must stay zero."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from common import PROJECT, require

MODES = ('success', 'invalid_model_json', 'second_turn_business_failure')


def _child(mode, output):
    from worker import run
    value = run(mode, output)
    require(value['physical_http'] == 0, 'Physical HTTP during public rehearsal')
    counts = value.get('dispatch_counts') or {}
    if mode == 'success':
        require(value['state'] == 'passed', 'Public success did not pass')
        require(counts.get('model') == 3 and counts.get('import') == 2
                and counts.get('publish') == 2 and counts.get('key') == 2
                and counts.get('run') == 14 and counts.get('login') == 1
                and counts.get('reads', 0) <= 122, 'Success counts changed')
        require(value.get('new_task_created') is False, 'A new Task was created')
        require(not value.get('protection_failure'), 'Protection failure')
        require((value.get('protection') or {}).get('execution_policy_12_45') is True,
                'Successful batch did not prove 12/45/None policy')
    elif mode == 'invalid_model_json':
        require(value['state'] == 'stopped', 'Invalid JSON did not stop')
        require(counts.get('model') == 1 and counts.get('import') == 0
                and counts.get('publish') == 0 and counts.get('key') == 0
                and counts.get('run') == 0, 'Invalid JSON dispatched later stages')
    elif mode == 'second_turn_business_failure':
        require(value['state'] == 'stopped', 'Business failure did not stop')
        require(counts.get('model') == 1 and counts.get('import') == 1
                and counts.get('publish') == 1 and counts.get('key') == 1
                and counts.get('run') == 7, 'Business failure counts changed')
        failure = value.get('failure_capture') or {}
        require(failure.get('management_reads') == 4 and failure.get('state') == 'captured',
                'Unique failure diagnostic not capped/captured')
        require(counts.get('model') == 1 and counts.get('import') == 1,
                'Post-failure modification was dispatched')
    print(json.dumps({'mode': mode, 'state': value['state'], 'counts': counts,
                      'physical_http': 0}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--mode', choices=MODES)
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    require(output.is_relative_to(PROJECT / 'work') and not output.exists(),
            'New public work directory required')
    if args.child:
        require(args.mode is not None, 'Child mode required')
        _child(args.mode, output)
        return
    output.mkdir()
    rows = []
    for mode in MODES if args.all else (args.mode or 'success',):
        child = output / mode
        result = subprocess.run([sys.executable, __file__, '--child', '--mode', mode,
                                 '--output', str(child)], capture_output=True, text=True,
                                timeout=1800)
        (output / (mode + '.log')).write_text(result.stdout + result.stderr, 'utf-8')
        require(result.returncode == 0, 'Rehearsal failed: ' + mode + '; see ' + str(output / (mode + '.log')))
        value = json.loads((child / 'progress.json').read_text('utf-8'))
        rows.append({'mode': mode, 'state': value['state'],
                     'counts': value.get('dispatch_counts'), 'physical_http': value['physical_http']})
    (output / 'summary.json').write_text(
        json.dumps({'state': 'passed', 'modes': rows, 'physical_http': 0}, indent=2), 'utf-8')
    print(json.dumps({'state': 'passed', 'modes': len(rows), 'physical_http': 0}))


if __name__ == '__main__':
    main()
