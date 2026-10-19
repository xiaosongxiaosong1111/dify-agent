"""Local expiry hint only. Decoding a claim never verifies authentication."""
import base64
import binascii
import json
import math
import re
import time
from datetime import datetime, timezone


def expiry(token):
    if not isinstance(token, str) or len(token) > 16384:
        return None
    parts = token.split('.')
    if len(parts) != 3 or any(not part or not re.fullmatch(r'[A-Za-z0-9_-]+', part) for part in parts):
        return None
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate claim')
                result[key] = value
            return result
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)), object_pairs_hook=unique)
        value = payload.get('exp') if isinstance(payload, dict) else None
        if type(value) is not int or not 0 <= value <= 253402300799:
            return None
        datetime.fromtimestamp(value, timezone.utc)
        return value
    except (ValueError, TypeError, OverflowError, OSError, binascii.Error, UnicodeError, RecursionError):
        return None


def summary(token, csrf_present, at=None):
    now = time.time() if at is None else at
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError('本机时间不可用。')
    exp = expiry(token)
    remaining = max(0, math.ceil(exp - now)) if exp is not None else None
    if not token:
        state, message = 'missing', '尚未配置管理连接。请在 Sierra 环境列表使用邮箱密码连接。'
    elif exp is not None and exp <= now:
        state, message = 'expired', 'Sierra 保存的管理登录令牌已过期，请重新使用邮箱密码连接；在 Dify 页面登录不会更新此连接。'
    elif not csrf_present:
        state, message = 'incomplete', '管理 Token 已配置，但缺少 CSRF Token；请重新使用邮箱密码连接。'
    elif exp is None:
        state, message = 'unknown', '凭据已配置，无法从本机记录判断到期时间；需要真实测试才能确认当前连接。'
    elif exp - now <= 300:
        state, message = 'expiring', '管理令牌将在 5 分钟内到期；开始导入或资源操作前建议重新连接。'
    else:
        state, message = 'present', '管理令牌记录尚未到期；当前权限和连接状态仍需真实测试，不能只看历史验证。'
    return {'state': state, 'expires_at': datetime.fromtimestamp(exp, timezone.utc).isoformat() if exp is not None else None,
            'seconds_remaining': remaining, 'message': message, 'verification': 'local_expiry_hint_not_authentication'}
