"""Bounded current saved examples for planning, never runtime evidence or facts."""
import copy
import hashlib
import json

from fastapi import HTTPException
from .evaluation import validate_test_cases
from .plan_drafts import inspect_text

MAX_CASES = 30
MAX_BYTES = 24_000
CASE_FIELDS = ('id', 'name', 'input', 'expectation', 'required', 'followups')
EXPECTATION_FIELDS = ('mode', 'target', 'expected', 'description')


def current(task):
    cases = task.get('test_cases', [])
    if not isinstance(cases, list) or len(cases) > MAX_CASES:
        raise HTTPException(422, '当前验收样例须为最多30项的列表；请先核对保存范围，未裁剪或派发规划。')
    try:
        valid = validate_test_cases(cases, task['app_type'])['valid']
    except (ValueError, TypeError, RecursionError, OverflowError):
        valid = False
    if not valid:
        raise HTTPException(422, '当前保存的验收样例结构无效，请先修正；未回显内容、裁剪或派发规划。')
    items = []
    ignored = 0
    for case in cases:
        item = {key: copy.deepcopy(case[key]) for key in CASE_FIELDS if key in case}
        ignored += len(set(case) - set(CASE_FIELDS))
        turns = [item, *item.get('followups', [])]
        for turn in turns:
            expected = turn['expectation']
            ignored += len(set(expected) - set(EXPECTATION_FIELDS))
            turn['expectation'] = {key: expected[key] for key in EXPECTATION_FIELDS if key in expected}
        items.append(item)
    try:
        text = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        encoded = text.encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise HTTPException(422, '当前验收样例无法安全编码，请先核对结构和文字；未派发规划。') from None
    if len(encoded) > MAX_BYTES:
        raise HTTPException(422, '当前验收样例的规划内容超过24000字节，请明确缩小当前保存范围；未截断、漏读或派发规划。')
    try:
        inspect_text(text)
    except HTTPException:
        raise HTTPException(422, '当前验收样例含疑似凭据、非法文字或超出安全结构范围，请先处理；未回显内容或派发规划。') from None
    return {
        'source': 'current_saved_test_cases', 'revision': task['revision'],
        'case_count': len(items), 'turn_count': sum(1 + len(item.get('followups', [])) for item in items),
        'content_sha256': hashlib.sha256(encoded).hexdigest(), 'json_bytes': len(encoded),
        'projection': 'saved case fields and expectation rules; no additional metadata',
        'ignored_metadata_fields': ignored, 'truncated': False,
        'execution_verified': False, 'resource_permission_granted': False, 'items': items,
    }


def provenance(context):
    return {key: copy.deepcopy(value) for key, value in context.items() if key != 'items'}
