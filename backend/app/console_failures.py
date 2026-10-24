"""Allowlisted console diagnostics. Never persist exception text or credentials."""
from datetime import datetime, timezone
import hashlib
import json
import uuid

KIND = 'console_connection_failure'
CODES = {
    'login_unreachable': ('登录接口', '无法连接Dify登录接口。', '先核对Dify服务、地址和本机连接，再明确重新连接。'),
    'login_timeout': ('登录接口', 'Dify登录连接超时。', '核对服务响应；本次没有自动重试。'),
    'login_service_error': ('登录接口', 'Dify登录服务返回服务端错误，无法据此判断账号密码是否正确。', '先核对Dify服务和反向代理状态，再明确重新连接；原凭据保持，不自动重试。'),
    'login_rejected': ('登录接口', 'Dify未接受本次登录。', '核对登录方式、账号权限及服务端登录限制；不要循环尝试。'),
    'login_response_invalid': ('登录响应', 'Dify登录响应格式不兼容。', '核对实例版本及反向代理响应，不使用返回正文作为诊断。'),
    'login_cookies_invalid': ('登录响应', '登录没有返回完整有效的管理Cookie。', '核对Dify版本、登录方式及Cookie设置。'),
    'login_probe_unreachable': ('应用列表核对', '无法连接登录后的应用列表接口。', '核对Dify连接及权限；未提交新令牌。'),
    'login_probe_timeout': ('应用列表核对', '登录后的应用列表核对超时。', '核对服务响应；未提交新令牌，不自动重试。'),
    'login_probe_response_invalid': ('应用列表核对', '登录后的应用列表响应不兼容。', '核对实例版本和接口响应；未提交新令牌。'),
    'console_credentials_missing': ('管理凭据', '管理令牌已过期或缺失，且无法自动续接。', '查看已保存登录状态；在新的明确连接操作中处理，不重放原操作。'),
    'login_probe_failed': ('应用列表核对', '登录后的应用列表核对未通过。', '核对该账号的工作空间权限和接口响应，原凭据保持。'),
    'workspace_unreachable': ('工作空间核对', '无法连接工作空间身份接口。', '核对原实例连接；未提交新令牌。'),
    'workspace_timeout': ('工作空间核对', '工作空间身份核对超时。', '核对实例响应；未提交新令牌，不自动重试。'),
    'workspace_response_invalid': ('工作空间核对', '工作空间身份响应不完整或不兼容。', '核对实例版本和接口权限；未提交新令牌。'),
    'workspace_probe_failed': ('工作空间核对', '工作空间身份接口未成功返回。', '核对工作空间权限；未提交新令牌。'),
    'workspace_mismatch': ('工作空间核对', '新登录的工作空间与此连接绑定的空间不同。', '保持原连接；其他工作空间应另建连接，不切换原目标。'),
    'refreshed_token_rejected': ('续期后请求', '新令牌仍被Dify拒绝，自动登录已暂停。', '核对原空间权限和服务端认证状态，不循环登录或重发。'),
    'console_unreachable': ('管理接口请求', '无法连接Dify管理接口。', '先核对服务和地址，再在新的明确操作中连接。'),
    'console_timeout': ('管理接口请求', 'Dify管理接口请求超时。', '可能已派发的写入须先核对，不自动重发。'),
    'console_http_error': ('管理接口请求', 'Dify管理接口返回错误状态。', '按记录状态码核对权限和接口，不自动重发写入。'),
    'console_response_invalid': ('管理接口请求', 'Dify管理接口返回非预期JSON。', '核对代理、版本及登录状态，不记录返回正文。'),
    'reconnect_binding_changed': ('明确重新连接', '重新连接期间原目标或保存资料已变化。', '未提交旧登录结果，请读取当前连接并重新核对。'),
    'reconnect_interrupted': ('明确重新连接', '上次重新连接在服务重启前未确认结束。', '保持原凭据并暂停自动登录，不重放；需要新的明确连接操作。'),
    'reconnect_in_progress': ('明确重新连接', '此环境正在明确重新连接。', '等待并核对原记录，不并发派发管理请求。'),
    'automatic_login_paused': ('自动登录', '此连接的自动登录已暂停。', '先查看最近失败诊断；需要明确重新连接，原操作不会重放。'),
    'unclassified': ('连接核对', '连接操作失败，未取得可公开的细分原因。', '核对本机操作记录；不要据此猜测密码错误或服务停止。'),
    'legacy_unclassified': ('历史自动登录', '旧失败没有保留分类原因，当前无法追溯。', '保持暂停；新的明确连接操作会记录原因，不重放旧批次。'),
}


def code(exc):
    value = getattr(exc, 'code', None)
    return value if isinstance(value, str) and value in CODES else 'unclassified'


def status(value): return value if type(value) is int and 100 <= value <= 599 else None


def scope(env):
    value = {k: env.get(k) for k in ('id', 'base_url', 'version', 'console_workspace_id')}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def describe(exc):
    ident = code(exc); stage, message, action = CODES[ident]
    return {'code': ident, 'stage': stage, 'message': message, 'next_action': action,
            'http_status': status(getattr(exc, 'http_status', None))}


def error_message(exc):
    value = describe(exc)
    return value['message'] + ' 诊断代码：' + value['code'] + '。' + value['next_action']


def record(store, original, exc, *, automatic, mode=None):
    value = describe(exc)
    row = {'id': str(uuid.uuid4()), 'environment_id': original['id'], 'scope_digest': scope(original),
           'connection_revision': original.get('connection_revision'), 'code': value['code'],
           'http_status': value['http_status'], 'mode': 'saved_reconnect' if mode == 'saved_reconnect' else ('automatic' if automatic else 'manual'),
           'occurred_at': datetime.now(timezone.utc).isoformat()}
    with store.lock:
        current = store.get('environment', original['id'])
        entries = [(KIND, row['id'], row)]
        if automatic and current == original:
            current['console_failure_id'] = row['id']
            if automatic: current['console_login_blocked'] = True
            entries.append(('environment', current['id'], current))
        store.put_many(entries)
    return row


def public(store, env):
    ident = env.get('console_failure_id')
    try:
        valid_id = isinstance(ident, str) and str(uuid.UUID(ident)) == ident
    except (ValueError, AttributeError): valid_id = False
    row = store.get(KIND, ident) if valid_id else None
    if not isinstance(row, dict) or row.get('environment_id') != env['id'] or row.get('scope_digest') != scope(env):
        return (view({'code': 'legacy_unclassified', 'mode': 'automatic'})
                if env.get('console_login_blocked') else None)
    return view(row)


def view(row):
    ident = row.get('code'); ident = ident if isinstance(ident, str) and ident in CODES else 'unclassified'
    stage, message, action = CODES[ident]
    occurred = None
    try:
        raw = row.get('occurred_at')
        if isinstance(raw, str) and len(raw) <= 64: occurred = datetime.fromisoformat(raw).isoformat()
    except ValueError: pass
    return {'code': ident, 'stage': stage, 'message': message, 'next_action': action,
            'http_status': status(row.get('http_status')), 'occurred_at': occurred,
            'mode': row.get('mode') if row.get('mode') in ('automatic', 'manual', 'saved_reconnect') else 'unrecorded',
            'automatic_retry': False, 'credentials_exposed': False}
