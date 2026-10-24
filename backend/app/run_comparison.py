"""Explicit comparison of two saved single-turn results, never a quality verdict."""
import hashlib
import json

from fastapi import APIRouter, HTTPException, Query, Response

from .acceptance import same_json
from .dsl import _contains_secret_key
from .evaluation import _json_value_error
from .plan_drafts import _SECRET, _ASSIGNMENT
from .run_diagnostics import safe_text

LIMIT = 16000
NOTE = ('这里只对照已保存单轮记录，不重新评价、修改汇总或派发请求。旧通过不继承到当前修订；'
        '即使输入和记录条件相同，也未证明发布图、模型及实际服务条件一致，不是受控质量比较。')


def view(present, value):
    if not present:
        return {'state': 'missing', 'text': '未保存此字段，不按空值或空对象处理。'}
    if _json_value_error(value):
        return {'state': 'unavailable', 'text': '保存值不符合有界JSON，未显示或比较。'}
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    if len(text.encode()) > LIMIT:
        return {'state': 'unavailable', 'text': '保存值超过16000字节对照上限，请分别查看原记录；不按截断前缀判断相同。'}
    if _contains_secret_key(value) or _SECRET.search(text) or _ASSIGNMENT.search(text):
        return {'state': 'unavailable', 'text': '保存值疑似含凭据，未显示或比较，不读取密钥解密。'}
    sanitized = safe_text(text, limit=LIMIT)
    if sanitized != text:
        return {'state': 'unavailable', 'text': '保存值包含需脱敏内容，未显示或比较。'}
    return {'state': 'saved', 'text': text}


def fields(run):
    case = run.get('test_case')
    result = run.get('result')
    if run['app_type'] == 'workflow':
        data = result.get('data') if isinstance(result, dict) else None
        output_present = isinstance(data, dict) and 'outputs' in data
        output = data.get('outputs') if isinstance(data, dict) else None
    else:
        output_present = isinstance(result, dict) and 'answer' in result
        output = {'answer': result['answer']} if output_present else None
    return {'input': ('input' in run, run.get('input')),
        'expectation': (isinstance(case, dict) and 'expectation' in case, case.get('expectation') if isinstance(case, dict) else None),
        'output': (output_present, output)}


def compare(task, before_id, after_id):
    if before_id == after_id:
        raise HTTPException(422, '请选择两条不同的本任务试跑记录，不自动挑选。')
    selected = []
    for run_id in (before_id, after_id):
        rows = [r for r in task.get('runs', []) if isinstance(r, dict) and r.get('id') == run_id]
        if len(rows) != 1 or rows[0].get('kind') != 'run':
            raise HTTPException(404, '所选记录不属于本任务的唯一普通试跑，未读取其它任务。')
        run = rows[0]; case = run.get('test_case') or {}; result = run.get('result') or {}
        if (run.get('app_type') not in {'workflow', 'advanced-chat', 'agent'}
                or 'conversation_context' in run or run.get('file_case') is not None
                or (isinstance(case, dict) and case.get('followups'))
                or (isinstance(result, dict) and result.get('conversation_case') is True)):
            raise HTTPException(422, '本次只对照有明确类型的普通单轮记录；多轮、复用会话、文件及缺类型旧记录请分别查看，不丢弃上下文后比较。')
        selected.append(run)
    before, after = selected
    if before['app_type'] != after['app_type']:
        raise HTTPException(422, '两条记录应用类型不同，不能当同类型修改前后比较。')
    sections = []
    for key, (present, value) in fields(before).items():
        other_present, other = fields(after)[key]
        left, right = view(present, value), view(other_present, other)
        state = 'unavailable' if 'unavailable' in {left['state'], right['state']} else (
            'missing' if not present or not other_present else ('same' if same_json(value, other) else 'changed'))
        sections.append({'field': key, 'comparison': state, 'before': left, 'after': right})
    conditions = {key: (same_json(before[key], after[key]) if key in before and key in after
        and before[key] is not None and after[key] is not None
        and not _json_value_error(before[key]) and not _json_value_error(after[key]) else None)
        for key in ('revision', 'environment_id', 'app_id', 'environment_binding')}
    cases = [r.get('test_case') for r in selected]
    conditions['case_id'] = (cases[0].get('id') == cases[1].get('id') if all(isinstance(c, dict) and c.get('id') for c in cases) else None)
    warnings = [NOTE]
    if any(value is not True for value in conditions.values()):
        warnings.append('两条记录的修订、环境、App、连接快照或样例归属不同／缺失；差异可能来自这些条件，不能归因某次修改。')
    if any(r.get('status') != 'success' for r in selected):
        warnings.append('所选记录包含未成功／未知／在途状态；显示内容可能不完整，不能据返回片段宣称运行完成，不能直接重试。')
    if any(s['comparison'] in {'missing', 'unavailable'} for s in sections):
        warnings.append('部分字段缺失、超限或需脱敏，未作相同／不同判断；不把不可比较当没有变化。')
    metadata = []
    for run in selected:
        metadata.append({key: safe_text(run.get(key), limit=200) if isinstance(run.get(key), str) else (
            run.get(key) if key == 'revision' and type(run.get(key)) is int else None)
            for key in ('id', 'revision', 'app_type', 'environment_id', 'app_id', 'status', 'created_at')})
    token = hashlib.sha256(json.dumps([task['id'], task['revision'], metadata, conditions, sections], sort_keys=True,
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return {'schema_version': 1, 'task_id': task['id'], 'revision': task['revision'],
        'before_run_id': before_id, 'after_run_id': after_id, 'snapshot_token': token,
        'records': metadata, 'conditions_same': conditions, 'sections': sections, 'warnings': warnings,
        'verification': 'saved_single_turn_records_only', 'task_changed': False, 'network_requested': False,
        'automatic_execution': False, 'business_verified': False}


def register(h):
    router = APIRouter()
    @router.get('/api/tasks/{item_id}/run-comparison')
    def read(item_id: str, response: Response, revision: int = Query(ge=1), before_run_id: str = Query(min_length=1, max_length=128),
            after_run_id: str = Query(min_length=1, max_length=128)):
        with h.store.lock:
            task = h.get_task(item_id); h.require_revision(task, revision)
            response.headers['Cache-Control'] = 'no-store'
            return compare(task, before_run_id, after_run_id)
    h.app.include_router(router)
