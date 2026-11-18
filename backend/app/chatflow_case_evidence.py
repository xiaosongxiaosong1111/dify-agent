"""Extract bounded saved Chatflow replies for the current delivery report."""

import json

from fastapi import HTTPException

from .acceptance import matches_case, matches_current_app
from .conversation_cases import matched_turns
from .delivery_bundle import check_text
from .run_diagnostics import safe_text

ANSWER_LIMIT = 4_000
TOTAL_ANSWER_LIMIT = 96_000
CASE_LIMIT = 100
NOTE = (
    '仅列取自当前样例汇总对应试跑的已保存答复，最多 100 个样例、每轮 4 KB、全文答复合计 96 KB。'
    '限额或疑似含凭据的答复标为省略，缺少可信来源的轮次不补写。原始响应元数据和中断轮的未确认正文不导出。'
)


def _answer_for_report(answer, limit):
    if not isinstance(answer, str) or not answer.strip():
        return {'state': 'unavailable'}, 0
    if len(answer) > limit:
        return {'state': 'over_limit'}, 0
    try:
        encoded = json.dumps(answer, ensure_ascii=False).encode('utf-8')
        if len(encoded) > limit:
            return {'state': 'over_limit'}, 0
        check_text(encoded, limit)
    except (HTTPException, UnicodeError):
        return {'state': 'withheld'}, 0
    if safe_text(answer, limit=ANSWER_LIMIT) != answer:
        return {'state': 'withheld'}, 0
    return {'state': 'saved', 'answer': answer}, len(encoded)


def replies(task, summary):
    cases = {case['id']: case for case in task['test_cases']}
    runs = {
        run['id']: run for run in task['runs'] if run.get('kind') == 'run'
        and run.get('revision') == task['revision'] and run.get('environment_id') == task.get('environment_id')
        and matches_current_app(task, run)
    }
    remaining = TOTAL_ANSWER_LIMIT
    evidence = []
    for row in summary['cases'][:len(cases)]:
        case = cases[row['id']]
        run = runs.get(row['run_id'])
        if not run or not matches_case(case, run):
            continue
        result = run.get('result')
        if case.get('followups'):
            completed = result['turns'] if matched_turns(case, result) else []
        else:
            completed = [{'index': 1, 'result': result}] if run['status'] == 'success' else []
        turns = []
        for step in completed:
            returned = step['result']
            answer = returned.get('answer') if isinstance(returned, dict) else None
            item, used = _answer_for_report(answer, min(ANSWER_LIMIT, remaining))
            turns.append({'index': step['index'], **item})
            remaining -= used
        evidence.append({'case_id': row['id'], 'run_id': run['id'],
                         'status': row['status'], 'turns': turns})
        if len(evidence) == CASE_LIMIT:
            break
    return evidence
