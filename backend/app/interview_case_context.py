"""Current saved examples are design evidence, never retrieved facts or runs."""
import json
from fastapi import HTTPException
from .planning_case_context import current as planning_current,provenance


def current(task):
    try:
        return planning_current(task)
    except HTTPException:
        raise HTTPException(422,'当前保存的验收样例须结构有效、最多30项且投影不超过24000字节，并去除疑似凭据或非法文字；请先核对，未记录对话、读取Key或派发访谈。') from None


def sources(task):
    if not task.get('test_cases'):
        return {}
    try:
        value=current(task)
    except HTTPException:
        # Legacy malformed examples must not break read-only intake views. The
        # paid review entry rejects them before creating any operation.
        return {}
    def text(case):
        parts=[json.dumps(case,ensure_ascii=False,sort_keys=True,separators=(',',':'))]
        def fields(v):
            if isinstance(v,str):parts.append(v)
            elif isinstance(v,dict):
                for item in v.values():fields(item)
            elif isinstance(v,list):
                for item in v:fields(item)
        fields(case)
        return '\n\n'.join(parts)
    return {('test_case',c['id']):text(c) for c in value['items']}


def review_binding(task):
    rows=((task.get('intake_review') or {}).get('review') or {}).get('checks',[])
    if not any(r.get('kind')=='test_case' for c in rows for r in c.get('evidence',[])):
        return None
    try:
        value=current(task)
        return {k:value[k] for k in ('source','content_sha256','case_count','turn_count')}
    except HTTPException:
        return {'current_saved_test_cases_invalid':True}
