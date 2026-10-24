"""Explicit, read-only manual format preview of one retained boolean literal."""
import copy
import hashlib
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from .condition_settings import BOOLEAN_RHS_ERROR
from .dsl_roundtrip import digest
from .plan_drafts import DraftRoute, inspect_text
from .retained_plan import candidate
from .workflow_plan import validate_plan


NOTE = '仅预览一处明确的JSON布尔格式修正，其余完整图保持；这是人工修正副本，不代表原模型成功。放入草稿后仍须明确保存和重新确认；不证明平台运行或业务正确。'


class Compose(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=1)
    review_token: StrictStr = Field(pattern='^[a-f0-9]{64}$')


def preview(task, run_id):
    retained = candidate(task, run_id)
    if not retained['is_current_revision']:
        raise HTTPException(409, '旧修订候选只能查看，不能生成当前格式修正草稿。')
    if task['app_type'] not in ('workflow', 'advanced-chat'):
        raise HTTPException(422, '此格式预览仅支持Workflow和Chatflow流程候选。')
    original = json.loads(retained['plan_text'])
    matches = []
    for ni, node in enumerate(original.get('nodes', []) if isinstance(original.get('nodes'), list) else []):
        if not isinstance(node, dict) or node.get('type') != 'if-else' or not isinstance(node.get('config'), dict):
            continue
        cases = node['config'].get('cases')
        for ci, case in enumerate(cases if isinstance(cases, list) else []):
            conditions = case.get('conditions') if isinstance(case, dict) else None
            for ri, row in enumerate(conditions if isinstance(conditions, list) else []):
                if (isinstance(row, dict) and row.get('varType') == 'boolean'
                        and type(row.get('value')) is str and row['value'] in ('true', 'false')
                        and isinstance(row.get('comparison_operator'), str) and row['comparison_operator'] in ('is', 'is not')):
                    matches.append((ni, ci, ri, node.get('id'), row['value']))
    if len(matches) != 1:
        raise HTTPException(422, '只支持恰好一处明确的布尔字符串true或false格式错误；未猜测其他修正。')
    ni, ci, ri, node_id, old = matches[0]
    corrected = copy.deepcopy(original)
    corrected['nodes'][ni]['config']['cases'][ci]['conditions'][ri]['value'] = old == 'true'
    try:
        before = validate_plan(task, original)
        after = validate_plan(task, corrected)
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        raise HTTPException(422, '完整图校验未完成，未提供格式修正草稿；原候选保持。') from None
    expected = f'条件 {node_id}：cases[{ci}].conditions[{ri}] {BOOLEAN_RHS_ERROR}'
    if before['valid'] or before['errors'] != [expected] or not after['valid']:
        raise HTTPException(422, '候选还有其他图错误或变量类型不明确，不能仅作一处格式修正。')
    text = json.dumps(corrected, ensure_ascii=False, indent=2, allow_nan=False)
    size, state = inspect_text(text)
    if state != 'json_object':
        raise HTTPException(422, '修正副本不是完整对象，未提供草稿。')
    token = digest({'task_id': task['id'], 'revision': task['revision'], 'app_type': task['app_type'],
                    'run_id': run_id, 'candidate_sha256': retained['source_sha256'],
                    'requirements': task.get('requirements'), 'configuration': task.get('configuration'),
                    'workflow_plan': task.get('workflow_plan'), 'pause_generation': task.get('pause_generation', 0)})
    return {'task_id': task['id'], 'planning_run_id': run_id, 'revision': task['revision'], 'app_type': task['app_type'],
            'candidate_sha256': retained['source_sha256'], 'review_token': token,
            'change': {'path': ['nodes', ni, 'config', 'cases', ci, 'conditions', ri, 'value'],
                       'before': old, 'before_type': 'string', 'after': old == 'true', 'after_type': 'boolean'},
            'plan_text': text, 'byte_count': size, 'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'verification': 'manual_boolean_format_preview', 'static_validated': True,
            'warnings': after['warnings'], 'formal_plan_changed': False, 'network_requested': False,
            'platform_checked': False, 'business_verified': False, 'note': NOTE}


def register(h):
    router = APIRouter(route_class=DraftRoute)

    def source(item_id, run_id, revision):
        task = h.get_task(item_id)
        h.require_revision(task, revision)
        h.require_idle(task)
        return preview(task, run_id)

    @router.get('/api/tasks/{item_id}/planning/{run_id}/boolean-format-preview')
    def read(item_id: str, run_id: str, revision: int):
        with h.store.lock:
            return source(item_id, run_id, revision)

    @router.post('/api/tasks/{item_id}/planning/{run_id}/boolean-format-preview/compose')
    def compose(item_id: str, run_id: str, payload: Compose):
        with h.store.lock:
            value = source(item_id, run_id, payload.revision)
            if value['review_token'] != payload.review_token:
                raise HTTPException(409, '候选、原方案或当前输入已变化，格式预览失效；请重新读取。')
            return value

    h.app.include_router(router)
