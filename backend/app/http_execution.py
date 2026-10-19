"""Bounded native HTTP execution policy; no request is sent here."""
import copy

TIMEOUT_LIMITS = {'connect': 10, 'read': 600, 'write': 600}
TIMEOUT_METADATA = {f'max_{key}_timeout' for key in TIMEOUT_LIMITS}
DEFAULT_RETRY = {'retry_enabled': False, 'max_retries': 0, 'retry_interval': 0}


def validate(config):
    errors, warnings = [], []
    timeout = config.get('timeout')
    if timeout is not None:
        if not isinstance(timeout, dict):
            errors.append('HTTP timeout 必须是对象或 null。')
        else:
            if set(timeout) - set(TIMEOUT_LIMITS):
                errors.append('HTTP timeout 只支持 connect/read/write（秒）；max_*_timeout 是平台上限元数据，不是实际超时，不能当作请求设置。')
            for key, limit in TIMEOUT_LIMITS.items():
                value = timeout.get(key)
                if value is not None and (type(value) is not int or not 0 <= value <= limit):
                    errors.append(f'HTTP timeout.{key} 必须是 0—{limit} 整数或 null；0/null 继承目标 Dify 默认值。')
    ssl = config.get('ssl_verify', True)
    if type(ssl) is not bool:
        errors.append('HTTP ssl_verify 必须是布尔值。')
    elif not ssl:
        warnings.append('HTTP 已关闭 TLS 证书校验；请确认目标环境确有此需要，连接身份未受证书验证保护。')
    retry = config.get('retry_config', DEFAULT_RETRY)
    if not isinstance(retry, dict) or set(retry) != set(DEFAULT_RETRY):
        errors.append('HTTP retry_config 必须完整包含 retry_enabled、max_retries、retry_interval；不会隐式补齐重试。')
    else:
        enabled, count, interval = (retry[key] for key in DEFAULT_RETRY)
        if type(enabled) is not bool:
            errors.append('HTTP retry_enabled 必须是布尔值。')
        if type(count) is not int or not 0 <= count <= 10 or (enabled is True and count == 0):
            errors.append('HTTP max_retries 必须为 0—10 整数；启用重试时至少为 1，次数不包含首次请求。')
        if type(interval) is not int or not 0 <= interval <= 5000:
            errors.append('HTTP retry_interval 必须为 0—5000 整数毫秒。')
        if enabled is True:
            warnings.append('HTTP 已启用节点重试；首次请求之外可能再次发送，请核对接口幂等性、重复提交和额外费用。次数不是整次工作流的请求／费用硬上限。')
    for key in ('error_strategy', 'default_value'):
        if key in config and config[key] is not None:
            errors.append('HTTP 错误分支／默认结果尚未适配，不能删除该行为后通过。')
    warnings.append('HTTP 默认关闭节点重试；未启用重试或错误策略时，Dify 可将非 2xx 响应作为节点成功返回。业务成功须显式检查 status_code/body；网络错误仍可失败。')
    return errors, warnings


def native(config):
    return {'timeout': copy.deepcopy(config.get('timeout')),
            'ssl_verify': config.get('ssl_verify', True),
            'retry_config': copy.deepcopy(config.get('retry_config', DEFAULT_RETRY))}


def preserved(data):
    """Project metadata out for validation only, never edit the original DSL."""
    config = {key: copy.deepcopy(data[key]) for key in ('timeout', 'ssl_verify', 'retry_config', 'error_strategy', 'default_value') if key in data}
    timeout = config.get('timeout')
    if isinstance(timeout, dict):
        for key in TIMEOUT_METADATA:
            if key in timeout:
                value = timeout.pop(key)
                if type(value) is not int or value < 1:
                    raise ValueError('HTTP 平台超时上限元数据无效；不会删除后当作通过。')
    errors, _ = validate(config)
    if errors:
        raise ValueError('；'.join(errors))
    return config
