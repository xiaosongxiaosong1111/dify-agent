"""Local history comparison and a revision-bound restore decision.

Only field names, counts and fixed labels leave this comparison. Snapshots remain
the authority; the preview neither evaluates their validity nor touches Dify.
"""
import copy
import hashlib
import hmac
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

RESTORED_KEYS = ('requirements', 'configuration', 'environment_id', 'materials',
                 'workflow_plan', 'agent_plan', 'plan_source', 'plan_stale',
                 'test_cases', 'dsl_reference', 'dsl_overlay', 'coverage_review',
                 'conflict_review', 'intake_review', 'intake_required')
REQ = {'goal': '目标', 'audience': '服务对象', 'input': '输入', 'output': '输出',
       'rules': '业务规则', 'knowledge': '知识与依赖', 'exceptions': '异常处理', 'tests': '验收要求'}
CFG = {'assistant_provider_id': '助手模型服务', 'dify_model_provider': 'Dify模型供应商',
       'dify_model': 'Dify模型', 'temperature': '温度', 'max_tokens': '输出Token上限',
       'model_parameters': '模型参数', 'opening_statement': '开场白',
       'suggested_questions': '建议问题', 'conversation_memory': '对话记忆',
       'memory_turns': '记忆轮数', 'dataset_ids': '知识库选择',
       'retrieval_top_k': '检索数量', 'mock_dependencies': '模拟依赖', 'resource_plan': '资源方案'}
IMPACTS = [
    '恢复前的当前内容会先保存为历史快照；随后创建新修订，不改写原历史。',
    '需求和配置确认、当前DSL成果与Dify应用绑定会失效，需重新核对、确认和构建。',
    '不恢复历史运行通过状态、模型服务或环境凭据，不创建、修改、删除或还原Dify资源。',
    '历史材料和DSL引用可能已缺文件或依赖；恢复不证明文件存在、静态有效或业务通过。',
    '样例和引用按快照替换；当前运行、对话、费用账本及确认历史继续保留。',
]


def canonical(value):
    try:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                          separators=(',', ':')).encode('utf-8')
        if len(data) > 8_000_000:
            raise ValueError()
        return data
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise HTTPException(422, '历史内容超出本次比较范围或结构无效；未返回部分比较，也未恢复。') from None


def equal(a, b):
    # Keep bool, integer, float and absent values distinct under JSON semantics.
    return canonical(a) == canonical(b)


def projection(item):
    return {k: {'present': k in item, 'value': item.get(k)} for k in RESTORED_KEYS}


def select(task, version_id):
    rows = [v for v in task.get('versions', []) if isinstance(v, dict) and v.get('id') == version_id]
    if len(rows) != 1:
        raise HTTPException(404, '历史快照不存在或不能唯一定位；未恢复。')
    version = rows[0]
    if any(k not in version for k in ('requirements', 'configuration', 'environment_id')):
        raise HTTPException(422, '历史快照缺少恢复所需字段；未返回可确认预览，也未恢复。')
    if any(not isinstance(version[k], dict) for k in ('requirements', 'configuration')) or not (version['environment_id'] is None or isinstance(version['environment_id'], str)):
        raise HTTPException(422, '历史需求、配置或环境结构无效；未恢复。')
    if any(version.get(k) is not None and not isinstance(version[k], dict) for k in ('workflow_plan', 'agent_plan', 'coverage_review', 'conflict_review', 'intake_review')):
        raise HTTPException(422, '历史流程或检查结构无效；未恢复。')
    # Missing legacy materials keep the current list; explicit null cannot be
    # restored because the normal intake flow requires a material list.
    if ('materials' in version and not isinstance(version['materials'], list)) or (version.get('test_cases') is not None and not isinstance(version['test_cases'], list)):
        raise HTTPException(422, '历史材料或样例结构无效；未恢复。')
    return version


def token(task, version):
    decision = {'schema_version': 1, 'task_id': task['id'], 'app_type': task['app_type'],
                'revision': task['revision'], 'current': projection(task),
                'current_state': {k: task.get(k) for k in
                                  ('requirements_confirmed', 'configuration_confirmed', 'artifact', 'dify_app_id')},
                'version_id': version['id'], 'historical': projection(version)}
    return hashlib.sha256(canonical(decision)).hexdigest()


def dictionary_changes(current, target, labels):
    if not isinstance(current, dict) or not isinstance(target, dict):
        return ['整份内容或结构'] if not equal(current, target) else []
    fields = [label for k, label in labels.items()
              if (k in current) != (k in target) or not equal(current.get(k), target.get(k))]
    other = (set(current) | set(target)) - set(labels)
    if any((k in current) != (k in target) or not equal(current.get(k), target.get(k)) for k in other):
        fields.append('其他保存字段')
    return fields


def node_changes(a, b):
    from .version_node_changes import compare
    return compare(a, b, equal)


def restored_content(task, version):
    """Match the existing restore defaults without reviving old confirmation."""
    result = {k: copy.deepcopy(version.get(k)) for k in RESTORED_KEYS}
    if 'materials' not in version:
        result['materials'] = copy.deepcopy(task.get('materials'))
    result['plan_stale'] = bool(version.get('plan_stale', False))
    result['test_cases'] = copy.deepcopy(version.get('test_cases') or [])
    result['intake_required'] = bool(task.get('intake_required') or version.get('intake_required'))
    if result['conflict_review']:
        result['conflict_review']['confirmation'] = {}
    return result


def preview(task, version):
    # Validate the complete decision before exposing a usable preview.
    review_token = token(task, version)
    target = restored_content(task, version)
    sections = []
    names = [('requirements', '需求'), ('configuration', '配置'), ('environment_id', '目标环境'),
             ('workflow_plan', '工作流'), ('agent_plan', 'Agent方案'), ('test_cases', '验收样例'),
             ('materials', '参考材料'), ('dsl_reference', '实际DSL引用'), ('dsl_overlay', '手改保留信息'),
             ('plan_source', '流程来源'), ('plan_stale', '流程待复核状态'),
             ('coverage_review', '需求覆盖检查'), ('conflict_review', '分歧检查'),
             ('intake_review', '需求准入检查'), ('intake_required', '需求复核要求')]
    for key, label in names:
        changed = (key in task) != (key in target) or not equal(task.get(key), target.get(key))
        row = {'key': key, 'label': label, 'changed': changed}
        if key in {'requirements', 'configuration'}:
            row['fields'] = dictionary_changes(task.get(key), target.get(key), REQ if key == 'requirements' else CFG)
        elif key in {'workflow_plan', 'agent_plan'} and changed:
            row['nodes'] = node_changes(task.get(key), target.get(key))
        elif key in {'materials', 'test_cases'}:
            row['current_count'] = len(task[key]) if isinstance(task.get(key), list) else None
            row['historical_count'] = len(target[key]) if isinstance(target.get(key), list) else None
        sections.append(row)
    return {'schema_version': 1, 'task_id': task['id'], 'revision': task['revision'],
            'app_type': task['app_type'], 'version_id': version['id'],
            'historical_revision': version.get('revision') if type(version.get('revision')) is int else None,
            'review_token': review_token, 'sections': sections,
            'changed_sections': sum(s['changed'] for s in sections), 'impacts': list(IMPACTS),
            'verification': 'local_history_restore_preview_only', 'task_changed': False,
            'network_requested': False, 'business_verified': False,
            'note': '只比较已保存内容的字段和结构，不展示正文、模型／知识库标识、代码或凭据；不是内容质量、保留无损或运行结论。'}


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=1)
    version_id: UUID
    review_token: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    acknowledge_restore: StrictBool


class RestoreRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def guarded(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={'detail': '恢复请求无效：先比较当前修订与历史快照，再明确确认恢复；未恢复，不回显输入。'})
        return guarded


def verify(task, payload):
    version = select(task, str(payload.version_id))
    if not payload.acknowledge_restore:
        raise HTTPException(422, '请先核对替换内容及失效影响，再明确确认恢复；未恢复。')
    if not hmac.compare_digest(token(task, version), payload.review_token):
        raise HTTPException(409, '当前内容或历史快照已变化，请重新比较；未恢复。')
    return version


def register(host):
    router = APIRouter(route_class=RestoreRoute)
    @router.get('/api/tasks/{item_id}/versions/{version_id}/restore-preview')
    def read(item_id: str, version_id: UUID, revision: int = Query(ge=1)):
        with host.store.lock:
            task = host.get_task(item_id)
            host.require_revision(task, revision)
            return preview(task, select(task, str(version_id)))
    # The restore handler is registered here so both validation errors are fixed.
    router.add_api_route('/api/tasks/{item_id}/restore', host.restore, methods=['POST'])
    host.app.include_router(router)
