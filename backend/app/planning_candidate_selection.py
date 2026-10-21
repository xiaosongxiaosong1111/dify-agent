"""Compose an unconfirmed draft from explicitly selected candidate differences."""
import copy
import hashlib
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, Field
from .acceptance import same_json
from .dsl_roundtrip import digest
from .plan_text_codec import render
from .plan_drafts import inspect_text, DraftRoute
from .retained_plan import candidate

LIMIT = 400
NOTE = '只把明确勾选的字段变化放入草稿，其余保持当前已存方案；不自动判断目标范围，不保存正式方案或沿用审批，不代表静态、平台或业务通过。列表整组选择须核对组内全部变化。'


def changes(before, after):
    rows = []
    def add(path, old, new, has_old=True, has_new=True):
        if len(rows) >= LIMIT: raise HTTPException(422, '候选变化超过400项，未返回部分选择；请缩小范围或核对完整候选。')
        def preview(value, exists):
            if not exists: return {'text': '（不存在）', 'truncated': False}
            text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            return {'text': text[:1200], 'truncated': len(text) > 1200}
        row = {'path': path, 'operation': 'replace' if has_old and has_new else ('add' if has_new else 'remove'), 'before': preview(old, has_old), 'after': preview(new, has_new),
               'whole_list': isinstance(old, list) or isinstance(new, list), '_after': new, '_has_after': has_new}
        row['id'] = digest({'path': path, 'old': old, 'new': new, 'has_old': has_old, 'has_new': has_new})
        rows.append(row)
    def walk(left, right, path):
        if same_json(left, right): return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                if key not in left: add(path + [key], None, right[key], False, True)
                elif key not in right: add(path + [key], left[key], None, True, False)
                else: walk(left[key], right[key], path + [key])
        elif (isinstance(left, list) and isinstance(right, list) and path and path[-1] == 'nodes'
                and left and len(left) == len(right) and all(isinstance(n, dict) and isinstance(n.get('id'), str) for n in left + right)
                and len({n['id'] for n in left}) == len(left) and [n['id'] for n in left] == [n['id'] for n in right]):
            for index, (a, b) in enumerate(zip(left, right)): walk(a, b, path + [index])
        else: add(path, left, right)
    walk(before, after, [])
    return rows


def visible(row): return {k: v for k, v in row.items() if not k.startswith('_')}


class Compose(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=1)
    review_token: StrictStr = Field(pattern='^[a-f0-9]{64}$')
    selected_ids: list[StrictStr] = Field(min_length=1, max_length=LIMIT)


def register(h):
    router = APIRouter(route_class=DraftRoute)
    def source(item_id, run_id, revision):
        task = h.get_task(item_id); h.require_revision(task, revision); h.require_idle(task)
        value = candidate(task, run_id)
        if not value['is_current_revision']:
            raise HTTPException(409, '旧修订候选只能查看，不能合成当前草稿。')
        key = 'agent_plan' if task['app_type'] == 'agent' else 'workflow_plan'
        baseline = task.get(key)
        if not isinstance(baseline, dict) or not baseline:
            raise HTTPException(409, '当前没有完整已存方案，不能选择性合成；请核对完整候选。')
        # Rendering and credential/structure checks run before recursive comparison.
        try:
            text = render(baseline); inspect_text(text)
            plan = json.loads(value['plan_text']); inspect_text(value['plan_text'])
        except (ValueError, TypeError, RecursionError, OverflowError, UnicodeError):
            raise HTTPException(422, '候选或基线结构不完整，不能选择性合成；原方案保持。') from None
        binding = {'task_id': item_id, 'revision': revision, 'app_type': task['app_type'], 'run_id': run_id,
                   'candidate_sha256': value['source_sha256'], 'baseline_sha256': hashlib.sha256(text.encode()).hexdigest(),
                   'requirements': task.get('requirements'), 'configuration': task.get('configuration'), 'pause_generation': task.get('pause_generation', 0)}
        rows = changes(baseline, plan)
        return task, baseline, rows, digest(binding), value['source_sha256']

    def metadata(task, run_id, token, candidate_sha):
        return {'task_id': task['id'], 'planning_run_id': run_id, 'revision': task['revision'], 'app_type': task['app_type'], 'review_token': token, 'candidate_sha256': candidate_sha,
                'formal_plan_changed': False, 'network_requested': False, 'business_verified': False, 'platform_checked': False, 'note': NOTE}

    @router.get('/api/tasks/{item_id}/planning/{run_id}/candidate-selection')
    def read(item_id: str, run_id: str, revision: int):
        with h.store.lock:
            task, _, rows, token, candidate_sha = source(item_id, run_id, revision)
            return metadata(task, run_id, token, candidate_sha) | {'verification': 'explicit_candidate_difference_review', 'changes': [visible(r) for r in rows], 'truncated': False}

    @router.post('/api/tasks/{item_id}/planning/{run_id}/candidate-selection/compose')
    def compose(item_id: str, run_id: str, payload: Compose):
        with h.store.lock:
            task, baseline, rows, token, candidate_sha = source(item_id, run_id, payload.revision)
            selected = payload.selected_ids
            if token != payload.review_token:
                raise HTTPException(409, '候选、原方案或当前输入已变化，原字段选择失效；请重新读取。')
            if len(set(selected)) != len(selected) or any(i not in {r['id'] for r in rows} for i in selected):
                raise HTTPException(422, '选择包含重复项或未知字段，未合成草稿。')
            result = copy.deepcopy(baseline)
            for row in rows:
                if row['id'] not in selected: continue
                path = row['path']; parent = result
                for part in path[:-1]: parent = parent[part]
                if not path: result = copy.deepcopy(row['_after'])
                elif row['_has_after']: parent[path[-1]] = copy.deepcopy(row['_after'])
                else: del parent[path[-1]]
            text = render(result); size, state = inspect_text(text)
            if state != 'json_object': raise HTTPException(422, '所选变化未形成完整对象，未返回草稿。')
            return metadata(task, run_id, token, candidate_sha) | {'verification': 'selected_candidate_unconfirmed_draft', 'plan_text': text, 'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
                    'byte_count': size, 'selected_ids': selected, 'selected_count': len(selected), 'unselected_count': len(rows) - len(selected), 'static_validated': False}
    h.app.include_router(router)
