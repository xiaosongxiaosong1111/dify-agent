"""Explicit one-shot reconnect using encrypted, origin/workspace-bound credentials."""
import copy
import hashlib
import json
import time
import uuid

from fastapi import APIRouter, HTTPException, Request

from . import console_failures
from .dify import DifyError
from .dsl_roundtrip import digest

KIND = 'saved_console_reconnect'
NOTE = '仅用已加密保存的资料向原实例登录1次并读取应用列表及原空间身份各1次；不创建资源、不发布、不试跑、不重放失败操作。'


def busy(store, environment_id):
    owner = getattr(store, 'connection_store', store)
    listing = getattr(owner, 'list', None)
    return bool(environment_id) and callable(listing) and any(r.get('environment_id') == environment_id and r.get('state') == 'executing' for r in listing(KIND))


def cipher_stamp(store, environment_id):
    value = hashlib.sha256((store.root / '.credential-key').read_bytes())
    with store.connect() as db:
        for name in ('console_login_email', 'console_login_password', 'console_token', 'csrf_token'):
            row = db.execute('SELECT value FROM secrets WHERE id=?', (environment_id + ':' + name,)).fetchone()
            raw = bytes(row[0]) if row else b''
            value.update(name.encode()); value.update(len(raw).to_bytes(8, 'big')); value.update(raw)
    return value.hexdigest()


def source(h, environment_id, *, skip=None):
    env = h.store.get('environment', environment_id)
    if not env: raise HTTPException(404, '环境不存在。')
    binding = env.get('console_login_binding')
    if (env.get('version') != '1.17.1' or not isinstance(binding, dict)
            or any(binding.get(k) != env.get(k) for k in ('base_url', 'version'))
            or not isinstance(binding.get('workspace_id'), str) or not binding['workspace_id']
            or binding['workspace_id'] != env.get('console_workspace_id')
            or not h.store.has_secret(environment_id, 'console_login_email') or not h.store.has_secret(environment_id, 'console_login_password')):
        raise HTTPException(422, '没有绑定此原实例和工作空间的已保存登录资料；请先明确连接并加密保存，不能复用其他目标。')
    attempts = sorted(r['id'] for r in h.store.list(KIND) if r.get('environment_id') == environment_id and r.get('attempted') and r['id'] != skip)
    snapshot = {'environment': {k: copy.deepcopy(env.get(k)) for k in ('id', 'base_url', 'version', 'connection_revision', 'console_workspace_id', 'console_login_binding', 'console_login_blocked', 'console_failure_id')},
                'cipher_stamp': cipher_stamp(h.store, environment_id), 'prior_attempts': attempts}
    return env, snapshot


def public(row):
    keys = ('id', 'environment_id', 'base_url', 'version', 'workspace_id', 'state', 'review_token', 'expires_at', 'created_at', 'started_at', 'completed_at', 'diagnostic_code', 'attempted')
    value = {k: row[k] for k in keys if k in row}
    if value.get('state') not in ('prepared', 'executing', 'succeeded', 'failed', 'unknown'): value['state'] = 'unknown'
    if 'diagnostic_code' in value and (not isinstance(value['diagnostic_code'], str) or value['diagnostic_code'] not in console_failures.CODES): value['diagnostic_code'] = 'unclassified'
    return value | {'login_posts': 1, 'console_reads': 2, 'new_resources': 0,
                'publish_posts': 0, 'runs': 0, 'model_calls': 0, 'automatic_retry': False, 'original_operation_replayed': False, 'note': NOTE}


async def body(request, keys):
    try:
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json': raise ValueError()
        raw = await request.body()
        if len(raw) > 4096: raise ValueError()
        def unique(pairs):
            out = {}
            for k, v in pairs:
                if k in out: raise ValueError()
                out[k] = v
            return out
        value = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != set(keys): raise ValueError()
        return value
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(422, '重新连接请求格式不完整；此入口不接收明文邮箱或密码，未派发登录。') from None


def register(h):
    router = APIRouter()

    def idle(environment_id):
        if h.environment_busy(environment_id): raise HTTPException(409, '该连接有操作执行中，请等待或核对原记录，不并发重新连接。')
        for task in h.store.list('task'):
            if task.get('environment_id') == environment_id: h.require_idle(task)

    @router.post('/api/environments/{item_id}/saved-login/reconnect-plan')
    async def prepare(item_id: str, request: Request):
        await body(request, ())
        with h.store.lock:
            idle(item_id); env, binding = source(h, item_id)
            row = {'id': str(uuid.uuid4()), 'environment_id': item_id, 'base_url': env['base_url'], 'version': env['version'],
                   'workspace_id': env['console_workspace_id'], 'binding': binding, 'state': 'prepared',
                   'attempted': False, 'created_at': h.now(), 'expires_at': time.time() + 900}
            row['review_token'] = digest(row); h.store.put(KIND, row['id'], row)
            return public(row)

    @router.get('/api/environments/{item_id}/saved-login/reconnections')
    def history(item_id: str):
        env = h.store.get('environment', item_id)
        if not env: raise HTTPException(404, '环境不存在。')
        rows = [r for r in h.store.list(KIND) if r.get('environment_id') == item_id
                and r.get('base_url') == env.get('base_url') and r.get('version') == env.get('version')
                and r.get('workspace_id') == env.get('console_workspace_id')]
        return {'records': [public(r) for r in rows[:10]], 'note': NOTE}

    @router.post('/api/environments/{item_id}/saved-login/reconnect')
    async def confirm(item_id: str, request: Request):
        data = await body(request, ('plan_id', 'review_token', 'confirm_reconnect'))
        if (type(data['confirm_reconnect']) is not bool or data['confirm_reconnect'] is not True
                or not isinstance(data['plan_id'], str) or not isinstance(data['review_token'], str)):
            raise HTTPException(422, '请核对原目标并明确确认单次重新连接。')
        with h.store.lock:
            idle(item_id); row = h.store.get(KIND, data['plan_id'])
            if (not row or row['environment_id'] != item_id or row['state'] != 'prepared'
                    or row['review_token'] != data['review_token'] or row['expires_at'] < time.time()):
                raise HTTPException(409, '重连方案已使用、过期或归属不符，请重新准备；未派发登录。')
            env, current = source(h, item_id)
            if digest(current) != digest(row['binding']): raise HTTPException(409, '连接、保存资料或最近尝试已变化，请重新准备，未派发登录。')
            row.update(state='executing', attempted=True, started_at=h.now()); h.store.put(KIND, row['id'], row)
        email = password = ''
        try:
            email = h.store.secret(item_id, 'console_login_email'); password = h.store.secret(item_id, 'console_login_password')
            adapter = h.DifyClient(env, h.store)
            tokens = await adapter.login(email, password)
            if await adapter.login_workspace(tokens) != row['workspace_id']:
                raise DifyError('工作空间不匹配。', code='workspace_mismatch')
            with h.store.lock:
                latest, stamp = source(h, item_id, skip=row['id'])
                saved = h.store.get(KIND, row['id'])
                if digest(stamp) != digest(row['binding']) or not saved or saved.get('state') != 'executing':
                    raise DifyError('连接期间状态改变。', code='reconnect_binding_changed')
                latest['console_checked_at'] = h.now(); latest['console_auth_mode'] = 'email_password'
                latest.setdefault('capabilities', {})['console'] = 'verified'
                latest.pop('console_login_blocked', None); latest.pop('console_failure_id', None)
                row.update(state='succeeded', completed_at=h.now())
                h.store.put_many_with_secrets([('environment', item_id, latest), (KIND, row['id'], row)], item_id,
                                             {k: tokens[k] for k in ('console_token', 'csrf_token')})
        except BaseException as exc:
            if isinstance(exc, HTTPException): problem = DifyError('连接期间状态改变。', code='reconnect_binding_changed')
            else: problem = exc
            ident = console_failures.code(problem)
            row.update(state='failed' if isinstance(exc, Exception) else 'unknown', diagnostic_code=ident, completed_at=h.now())
            console_failures.record(h.store, env, problem, automatic=True, mode='saved_reconnect')
            h.store.put(KIND, row['id'], row)
            if not isinstance(exc, Exception): raise
            raise HTTPException(502, console_failures.error_message(problem) + ' 未提交本次新凭据，不自动重试或重放原操作。', headers={'X-Sierra-Dify-Code': ident}) from None
        finally:
            email = password = ''; tokens = None
        return {'record': public(row), 'environment': h.env_public(latest), 'message': '已用保存资料重新连接原工作空间，管理令牌已加密更新；没有重发任何原操作。'}

    def recover():
        with h.store.lock:
            for row in h.store.list(KIND):
                if row.get('state') != 'executing': continue
                try:
                    current, stamp = source(h, row['environment_id'], skip=row['id'])
                    if digest(stamp) == digest(row['binding']):
                        console_failures.record(h.store, current, DifyError('重连中断。', code='reconnect_interrupted'), automatic=True, mode='saved_reconnect')
                except HTTPException: pass
                row.update(state='unknown', diagnostic_code='reconnect_interrupted', completed_at=h.now())
                h.store.put(KIND, row['id'], row)
    h.saved_console_reconnect_recover = recover
    h.app.include_router(router)
