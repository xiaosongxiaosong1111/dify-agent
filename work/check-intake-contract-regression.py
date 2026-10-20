"""逐项放宽访谈契约校验，确认隔离回归失败；仅修改子进程内存。"""
from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = {
    'extra_topic': [
        ('len(rows)!=len(expected)', 'len(rows)<len(expected)'),
        ('key not in expected or ', ''),
    ],
    'invalid_material_id': [
        ("available.get((ref['kind'],ref['id']))",
         "next((text for (kind, _), text in available.items() "
         "if kind == ref['kind'] and ref['quote'] in text), None)"),
    ],
    'complete_with_question': [
        ('or (not gaps and questions)', ''),
        ("q['topic'] not in gaps", "q['topic'] not in expected"),
    ],
}


def run_mutant(case):
    # Importing the fixtures creates only temporary test storage; call_model is mocked.
    import inspect
    sys.path.insert(0, str(ROOT / 'backend'))
    from app import intake, main
    import pytest

    source = inspect.getsource(intake.validate_review)
    for original, replacement in MUTATIONS[case]:
        if source.count(original) != 1:
            raise RuntimeError(f'无法唯一定位契约校验：{original}')
        source = source.replace(original, replacement)
    namespace = dict(vars(intake))
    exec(compile(source, f'<intake-mutant:{case}>', 'exec'), namespace)
    intake.validate_review = main.validate_intake = namespace['validate_review']
    return pytest.main([
        'backend/tests/test_intake.py', '-q', '--tb=short',
        '-k', f'test_interview_contract_failures_are_isolated and {case}',
    ])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    if len(sys.argv) == 2:
        raise SystemExit(run_mutant(sys.argv[1]))
    failures = []
    for case in MUTATIONS:
        print(f'\n临时放宽校验：{case}', flush=True)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), case], cwd=ROOT,
            text=True, encoding='utf-8', errors='replace', capture_output=True,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )
        print(result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        # Exit code alone is insufficient: setup/import errors must not count as proof.
        if (result.returncode != 1 or '1 failed' not in result.stdout
                or "assert saved['requirements'] == REQ" not in result.stdout
                or 'AssertionError' not in result.stdout):
            failures.append(case)
    if failures:
        raise SystemExit(f'未获得预期断言失败：{failures}')
    print('\n3 项临时还原均触发新增用例断言失败；生产文件未修改。')
