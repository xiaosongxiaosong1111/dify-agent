"""Explicit one-shot runtime-key creation for a current newly imported App."""
import copy
import hashlib
import re
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr
from .dsl_roundtrip import digest
from .dify import DifyError
from . import console_failures

KIND = 'app_runtime_key_creation'
ACTIVE = {'checking', 'creating'}
NOTE = '确认后核对原空间、App及现有Key；只在目标没有Key时创建1个并加密保存。将替换此连接运行绑定，原Key加密留档；不发布、不试跑。结果未知时禁止重发。'


def busy(store, environment_id, skip=None):
    owner = getattr(store, 'connection_store', store)
    listing = getattr(owner, 'list', None)
    return bool(environment_id) and callable(listing) and any(r.get('environment_id') == environment_id and r.get('state') in ACTIVE and r.get('id') != skip for r in listing(KIND))


class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt


class Confirm(Plan):
    proposal_id: StrictStr
    review_token: StrictStr
    confirm_create_and_bind: StrictBool


def public(row):
    names = ('id', 'task_id', 'revision', 'app_id', 'environment_id', 'environment_url', 'environment_version', 'workspace_id', 'shared_environment_tasks', 'previous_app_id', 'state', 'created_at', 'expires_at', 'review_token', 'write_attempted', 'key_id', 'message', 'diagnostic_code')
    return {k: copy.deepcopy(row[k]) for k in names if k in row} | {'new_keys': 1, 'planned_console_reads': 4, 'authentication_may_add_requests': True, 'publish_posts': 0, 'model_calls': 0, 'runs': 0, 'automatic_retry': False, 'business_verified': False, 'note': NOTE}


def register(h):
    router = APIRouter()

    def source(item_id, revision, skip=None):
        task = h.get_task(item_id); h.require_revision(task, revision); h.require_intake(task)
        if task.get('status') == 'paused' or not task.get('requirements_confirmed') or not task.get('configuration_confirmed') or task.get('plan_stale'):
            raise HTTPException(409, '请先恢复任务并确认当前修订需求及配置。')
        if task.get('app_type') not in {'workflow', 'advanced-chat'}:
            raise HTTPException(422, '此创建入口仅适配Workflow和Chatflow；原生Agent请在Dify核对，用户选择类型保持。')
        env = h.environment(task); app = task.get('dify_app_id')
        try:
            if str(uuid.UUID(app)) != app: raise ValueError()
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(409, '请先完成当前修订的新建导入。') from None
        if not any(r.get('kind') == 'import' and r.get('status') == 'success' and r.get('revision') == revision and r.get('environment_id') == env['id'] and (r.get('result') or {}).get('app_id') == app for r in task.get('runs', [])):
            raise HTTPException(409, '缺少当前修订的成功新建导入依据，不能创建Key。')
        if not env.get('console_workspace_id'):
            raise HTTPException(409, '请先连接并核对原Dify工作空间身份。')
        if env.get('console_login_blocked'):
            raise HTTPException(409, '自动登录已暂停，请先核对诊断并明确重新连接。')
        owner = env['id'] + ':app-runtime:' + app
        if h.store.get('app_runtime_credential', owner) or (env.get('service_app_id') == app and h.store.has_secret(env['id'], 'service_api_key')):
            raise HTTPException(409, '当前App已有本机运行Key记录，不创建第二个；请核对原绑定。')
        target = {'base_url': env['base_url'], 'version': env['version'], 'workspace_id': env['console_workspace_id'], 'app_id': app}
        for row in h.store.list(KIND):
            if row['id'] != skip and row.get('write_attempted') and row.get('target') == target:
                raise HTTPException(409, '此App已有Key创建派发记录，禁止重发；请在Dify核对原结果。')
        key = h.store.secret(env['id'], 'service_api_key')
        binding = {'task_id': item_id, 'revision': revision, 'app_id': app, 'app_type': task['app_type'], 'artifact_sha256': hashlib.sha256(h.artifact_path(task).read_bytes()).hexdigest(),
                   'pause_generation': task.get('pause_generation', 0), 'environment': h.env_snapshot(env), 'active_key_fingerprint': hashlib.sha256(key.encode()).hexdigest(),
                   'shared_tasks': sorted((t['id'], t.get('dify_app_id') or '') for t in h.store.list('task') if t.get('environment_id') == env['id'])}
        return task, env, target, binding

    def check(row):
        task, env, target, binding = source(row['task_id'], row['revision'], skip=row['id'])
        if digest(binding) != digest(row['binding']) or target != row['target']:
            raise HTTPException(409, '任务、成果或连接已变化；原Key创建确认失效，请核对原结果。')
        return task, env

    def idle(env_id):
        if h.environment_busy(env_id): raise HTTPException(409, '此连接有在途操作，请等待原结果，不并发创建Key。')
        for t in h.store.list('task'):
            if t.get('environment_id') == env_id: h.require_idle(t)

    @router.get('/api/tasks/{item_id}/runtime-key-creations')
    def history(item_id: str):
        h.get_task(item_id)
        return {'records': [public(r) for r in h.store.list(KIND) if r.get('task_id') == item_id][:10]}

    @router.post('/api/tasks/{item_id}/runtime-key-creation/plan')
    def prepare(item_id: str, payload: Plan):
        with h.store.lock:
            task, env, target, binding = source(item_id, payload.revision); idle(env['id'])
            row = {'id': str(uuid.uuid4()), 'task_id': item_id, 'revision': payload.revision, 'app_id': target['app_id'], 'environment_id': env['id'], 'environment_url': env['base_url'], 'environment_version': env['version'],
                   'workspace_id': target['workspace_id'], 'shared_environment_tasks': len(binding['shared_tasks']), 'previous_app_id': env.get('service_app_id') or '', 'binding': binding, 'target': target,
                   'state': 'prepared', 'created_at': h.now(), 'expires_at': time.time() + 900, 'write_attempted': False, 'message': '本机方案已准备，尚未请求Dify；请核对共享连接影响并明确确认。'}
            row['review_token'] = digest(row); h.store.put(KIND, row['id'], row)
            return public(row)

    @router.post('/api/tasks/{item_id}/runtime-key-creation/confirm')
    async def confirm(item_id: str, payload: Confirm):
        with h.store.lock:
            row = h.store.get(KIND, payload.proposal_id)
            if (not row or row.get('task_id') != item_id or row.get('revision') != payload.revision or row.get('review_token') != payload.review_token
                    or row.get('state') != 'prepared' or row.get('expires_at', 0) < time.time() or payload.confirm_create_and_bind is not True):
                raise HTTPException(409, '方案已失效、已使用或未明确确认，未派发创建。')
            task, env = check(row); idle(env['id'])
            row.update(state='checking'); h.store.put(KIND, row['id'], row)
        key = ''; old_key = ''
        try:
            adapter = h.DifyClient(env, h.store); app = row['app_id']; path = '/console/api/apps/' + app + '/api-keys'
            workspace = await adapter.workspace()
            if not isinstance(workspace, dict) or workspace.get('id') != row['workspace_id']:
                raise HTTPException(409, '原工作空间不匹配，未创建Key。')
            details = await adapter.request('GET', '/console/api/apps/' + app, credential='console_token')
            if not isinstance(details, dict) or details.get('id') != app or details.get('mode') != row['binding']['app_type']:
                raise HTTPException(409, '平台App身份或类型不匹配，未创建Key。')
            keys = await adapter.request('GET', path, credential='console_token')
            if not isinstance(keys, dict) or not isinstance(keys.get('data'), list):
                raise HTTPException(502, '无法核对现有运行Key，未创建。')
            if keys['data']: raise HTTPException(409, '目标App已有运行Key，不创建第二个；请在Dify核对并登记原Key。')
            with h.store.lock:
                check(row)
                row.update(state='creating', write_attempted=True); h.store.put(KIND, row['id'], row)
            result = await adapter.request('POST', path, credential='console_token', json={})
            if not isinstance(result, dict): raise ValueError()
            key = result.get('token'); key_id = result.get('id')
            if (not isinstance(key, str) or not re.fullmatch(r'app-[A-Za-z0-9_-]{8,256}', key) or not isinstance(key_id, str) or str(uuid.UUID(key_id)) != key_id): raise ValueError()
            after = await adapter.request('GET', path, credential='console_token')
            if (not isinstance(after, dict) or not isinstance(after.get('data'), list)
                    or len(after['data']) != 1 or sum(isinstance(k, dict) and k.get('id') == key_id and k.get('token') == key for k in after['data']) != 1): raise ValueError()
            with h.store.lock:
                task, current = check(row)
                if h.store.get(KIND, row['id']).get('state') != 'creating': raise ValueError()
                owner = current['id'] + ':app-runtime:' + app
                archive = {'id': owner, 'environment_id': current['id'], 'app_id': app, 'key_id': key_id, 'base_url': current['base_url'], 'dify_version': current['version'], 'workspace_id': row['workspace_id'], 'source': KIND, 'created_at': h.now()}
                records = [('app_runtime_credential', owner, archive)]
                secret_sets = {owner: {'service_api_key': key}, current['id']: {'service_api_key': key}}
                old_key = h.store.secret(current['id'], 'service_api_key')
                if old_key:
                    previous_owner = row['id'] + ':previous-runtime-key'
                    records.append(('runtime_key_previous_binding', previous_owner, {'id': previous_owner, 'environment_id': current['id'], 'app_id': current.get('service_app_id') or '', 'base_url': current['base_url'], 'origin_verified': False, 'source': row['id'], 'created_at': h.now()}))
                    secret_sets[previous_owner] = {'service_api_key': old_key}
                current = copy.deepcopy(current); current['service_app_id'] = app; current['connection_revision'] = str(uuid.uuid4())
                if not isinstance(current.get('capabilities'), dict): current['capabilities'] = {}
                current['capabilities']['runtime'] = 'registered_unverified'
                row.update(state='succeeded', key_id=key_id, completed_at=h.now(), message='已创建并加密保存当前App运行Key；原Key留档，仍需按已批准样例另行试跑。')
                records += [('environment', current['id'], current), (KIND, row['id'], row)]
                h.store.put_many_with_secret_sets(records, secret_sets)
        except BaseException as exc:
            row.update(state='unknown' if row['write_attempted'] else 'failed', completed_at=h.now(), message='创建可能已执行，请在Dify核对原结果；禁止重发。' if row['write_attempted'] else '创建前核对未通过，未发送创建；请核对连接及原记录。')
            if isinstance(exc, DifyError):
                row['diagnostic_code'] = console_failures.code(exc)
                row['message'] += ' ' + console_failures.error_message(exc)
            h.store.put(KIND, row['id'], row)
            if isinstance(exc, HTTPException) and not row['write_attempted']: raise
            if not isinstance(exc, Exception): raise
            raise HTTPException(502, row['message']) from None
        finally:
            key = ''; old_key = ''
        return public(row)

    def recover():
        with h.store.lock:
            for row in h.store.list(KIND):
                if row.get('state') in ACTIVE:
                    row.update(state='unknown' if row.get('write_attempted') else 'failed', message='服务重启时Key创建中断，请核对原记录；不会重发。', completed_at=h.now())
                    h.store.put(KIND, row['id'], row)
    h.app_runtime_key_creation_recover = recover
    h.app.include_router(router)
