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
    try:
        raw=json.dumps([task['id'],task['revision'],task.get('app_type'),task.get('environment_id'),
            task.get('dify_app_id'),selected],sort_keys=True,ensure_ascii=True,allow_nan=True,separators=(',',':')).encode()
        export_token=hashlib.sha256(raw).hexdigest() if len(raw)<=8_000_000 else None
    except (ValueError,TypeError,RecursionError,OverflowError):export_token=None
    return {'schema_version': 1, 'task_id': task['id'], 'revision': task['revision'],
        'before_run_id': before_id, 'after_run_id': after_id, 'snapshot_token': token,'export_token':export_token,
        'records': metadata, 'conditions_same': conditions, 'sections': sections, 'warnings': warnings,
        'verification': 'saved_single_turn_records_only', 'task_changed': False, 'network_requested': False,
        'automatic_execution': False, 'business_verified': False}


def render_report(value):
    def fence(text):
        import re
        marker='`'*max(3,1+max((len(m.group()) for m in re.finditer(r'`+',text)),default=0))
        return marker+'\n'+text+'\n'+marker
    labels={'input':'实际输入','expectation':'运行时预期','output':'保存的实际输出'}
    states={'same':'保存值相同','changed':'保存值不同','missing':'字段未完整保存','unavailable':'未作比较'}
    lines=['# Sierra 两次保存试跑对照','',f"当前任务修订：r{value['revision']}",
        '仅导出本机保存记录；不重新评分、重跑或把差异归因为质量提升，旧通过不继承当前版本。',
        '文件不是平台实时证明或签名；输入/输出可能含业务文字，分享前请审阅。','',
        '## 来源记录与条件','',fence(json.dumps({'records':value['records'],'conditions_same':value['conditions_same']},ensure_ascii=False,indent=2)),
        '', '## 对照观察标识','',fence(json.dumps({'snapshot_token':value['snapshot_token'],'export_token':value['export_token']},indent=2))]
    for section in value['sections']:
        lines+=['',f"## {labels[section['field']]} · {states[section['comparison']]}",'',
            '左侧保存值',fence(section['before']['text']),'右侧保存值',fence(section['after']['text'])]
    lines+=['','## 限制与待核对','']+['- '+s for s in value['warnings']]
    return '\n'.join(lines)+'\n'


def register(h):
    router = APIRouter()
    @router.get('/api/tasks/{item_id}/run-comparison')
    def read(item_id: str, response: Response, revision: int = Query(ge=1), before_run_id: str = Query(min_length=1, max_length=128),
            after_run_id: str = Query(min_length=1, max_length=128)):
        with h.store.lock:
            task = h.get_task(item_id); h.require_revision(task, revision)
            response.headers['Cache-Control'] = 'no-store'
            return compare(task, before_run_id, after_run_id)
    @router.get('/api/tasks/{item_id}/run-comparison/report')
    def report(item_id:str,revision:int=Query(ge=1),before_run_id:str=Query(min_length=1,max_length=128),
            after_run_id:str=Query(min_length=1,max_length=128),snapshot_token:str=Query(pattern=r'^[a-f0-9]{64}$'),
            export_token:str=Query(pattern=r'^[a-f0-9]{64}$')):
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision)
            value=compare(task,before_run_id,after_run_id)
            if value['snapshot_token']!=snapshot_token or value['export_token']!=export_token:
                raise HTTPException(409,'所见对照或保存来源已变化，请重新读取核对后再导出；未返回混合说明。')
            content=render_report(value)
            if len(content.encode('utf-8'))>200000:
                raise HTTPException(422,'对照说明超过200KB导出范围，请分别查看原记录；未截断或返回部分说明。')
            latest=compare(h.get_task(item_id),before_run_id,after_run_id)
            if latest['snapshot_token']!=snapshot_token or latest['export_token']!=export_token:
                raise HTTPException(409,'导出期间保存来源变化，未返回说明；请重新核对。')
        return Response(content,media_type='text/markdown',headers={'Cache-Control':'no-store',
            'Content-Disposition':f'attachment; filename="run-comparison-r{revision}.md"',
            'X-Sierra-Revision':str(revision),'X-Sierra-Comparison-Token':snapshot_token,
            'X-Sierra-Export-Token':export_token})
    h.app.include_router(router)
