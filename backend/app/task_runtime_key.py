"""Task-scoped local runtime-key registration. Never sends a Dify request."""
import copy
import hashlib
import json
import re
import uuid

from fastapi import APIRouter, HTTPException, Request

from .dsl_roundtrip import digest

NOTE = '仅登记本机加密运行Key与App对应关系；未请求Dify、未创建Key或验证其有效性。真实可用性须由该App的试跑另行核对。'


def register(h):
    router = APIRouter()

    def snapshot(item_id, revision):
        task = h.get_task(item_id); h.require_revision(task, revision)
        if task.get('app_type') not in {'workflow', 'advanced-chat', 'agent'}:
            raise HTTPException(422, '此应用类型尚不支持运行Key登记。')
        env = h.environment(task); app = task.get('dify_app_id')
        if (not app or not any(r.get('kind') == 'import' and r.get('status') == 'success'
                and r.get('revision') == revision and r.get('environment_id') == env['id']
                and (r.get('result') or {}).get('app_id') == app for r in task.get('runs', []))):
            raise HTTPException(409, '请先完成当前修订的新建导入，不能为未知App登记运行Key。')
        raw = h.artifact_path(task).read_bytes()
        key = h.store.secret(env['id'], 'service_api_key')
        binding = {'task_id': item_id, 'revision': revision, 'app_id': app,
                   'artifact_sha256': hashlib.sha256(raw).hexdigest(), 'pause_generation': task.get('pause_generation', 0),
                   'environment': {k: env.get(k) for k in ('id', 'base_url', 'version', 'connection_revision', 'console_workspace_id', 'service_app_id')},
                   'active_key_fingerprint': hashlib.sha256((key or '').encode()).hexdigest(),
                   'shared_tasks': sorted((t['id'], t.get('dify_app_id') or '') for t in h.store.list('task') if t.get('environment_id') == env['id'])}
        return task, env, binding, bool(key)

    def status(item_id, revision):
        task, env, binding, has_key = snapshot(item_id, revision)
        shared = len(binding['shared_tasks'])
        return {'task_id': item_id, 'revision': revision, 'app_id': task['dify_app_id'],
                'environment_id': env['id'], 'environment_url': env['base_url'], 'environment_version': env['version'],
                'active_app_id': env.get('service_app_id') or '', 'has_runtime_key': has_key,
                'matches_current_app': has_key and env.get('service_app_id') == task['dify_app_id'],
                'shared_environment_tasks': shared, 'review_token': digest(binding), 'network_requested': False,
                'key_created': False, 'business_verified': False, 'note': NOTE}

    @router.get('/api/tasks/{item_id}/runtime-key')
    def read(item_id: str, revision: int):
        with h.store.lock: return status(item_id, revision)

    @router.post('/api/tasks/{item_id}/runtime-key')
    async def save(item_id: str, request: Request):
        # Do not let framework validation errors echo a password-like body value.
        try:
            if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json': raise ValueError()
            raw = await request.body()
            if len(raw) > 16384: raise ValueError()
            def unique(pairs):
                value = {}
                for k, v in pairs:
                    if k in value: raise ValueError()
                    value[k] = v
                return value
            data = json.loads(raw, object_pairs_hook=unique)
            if not isinstance(data, dict) or set(data) != {'revision', 'review_token', 'confirm_bind', 'service_api_key'}: raise ValueError()
            key = data['service_api_key']
            if (type(data['revision']) is not int or type(data['confirm_bind']) is not bool or data['confirm_bind'] is not True
                    or not isinstance(data['review_token'], str) or not re.fullmatch('[0-9a-f]{64}', data['review_token'])
                    or not isinstance(key, str) or not 8 <= len(key) <= 4096 or any(not 33 <= ord(c) <= 126 for c in key)):
                raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            raise HTTPException(422, '请填写有效的Dify应用运行Key并明确确认绑定；请求格式不完整，未保存，密钥不会回显。') from None
        try:
            with h.store.lock:
                task, env, binding, _ = snapshot(item_id, data['revision']); h.require_idle(task)
                if h.environment_busy(env['id']): raise HTTPException(409, '该环境有任务或资源操作在执行，暂不能替换运行Key。')
                if task.get('status') == 'paused': raise HTTPException(409, '任务已暂停，请先明确恢复后登记。')
                if digest(binding) != data['review_token']:
                    raise HTTPException(409, '任务、成果或环境绑定已变化，请重新读取当前App状态后确认；未保存Key。')
                unchanged = env.get('service_app_id') == task['dify_app_id'] and h.store.secret(env['id'], 'service_api_key') == key
                if not unchanged:
                    current = copy.deepcopy(env); current['service_app_id'] = task['dify_app_id']
                    current['connection_revision'] = str(uuid.uuid4())
                    if not isinstance(current.get('capabilities'), dict): current['capabilities'] = {}
                    current['capabilities']['runtime'] = 'registered_unverified'
                    h.store.put_with_secrets('environment', env['id'], current, {'service_api_key': key})
                return status(item_id, data['revision']) | {'saved': True, 'unchanged': unchanged}
        finally:
            key = ''; data['service_api_key'] = ''; raw = b''

    h.app.include_router(router)
