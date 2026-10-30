from __future__ import annotations

import json
from urllib.parse import urlsplit
import httpx


class ProviderError(ValueError):
    def __init__(self, message, *, usage=None, finish_reason=None, partial_usage=None):
        super().__init__(message)
        self.usage = usage
        self.finish_reason = finish_reason
        self.partial_usage = partial_usage


def usage_summary(value):
    if not isinstance(value, dict): return {}
    allowed = {'prompt_tokens', 'completion_tokens', 'total_tokens', 'input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens'}
    result = {k: v for k, v in value.items() if k in allowed and type(v) is int and v >= 0}
    for key, child in [('prompt_tokens_details', 'cached_tokens'), ('completion_tokens_details', 'reasoning_tokens')]:
        detail = value.get(key)
        if isinstance(detail, dict) and type(detail.get(child)) is int and detail[child] >= 0:
            result[key] = {child: detail[child]}
    return result


def checked_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ProviderError("服务地址必须是有效的 http(s) 地址，不能在地址中包含凭据。")
    if parts.query or parts.fragment:
        raise ProviderError("服务基础地址不能包含查询参数或片段。")
    return value.rstrip("/")


async def call_model(provider: dict, key: str, messages: list[dict], *, max_tokens=2048, timeout=60, json_mode=False, allow_images=False, stream=False, on_delta=None, require_final_text=False):
    if type(stream)is not bool or (on_delta is not None and not stream):raise ProviderError('流式须明确启用；普通请求不接受增量回调。')
    if stream and allow_images:raise ProviderError('首批流式仅适配纯文字，不能复用图像出站确认。')
    if type(require_final_text)is not bool or require_final_text and stream:raise ProviderError('完整终稿守卫仅用于明确的普通请求，不静默切换流式。')
    reported_usage = {}
    finish_reason = None
    if not key:
        raise ProviderError("该模型尚未配置 API Key，请先在模型设置中填写并测试。")
    base = checked_url(provider["base_url"])
    protocol = provider.get("protocol", "openai-compatible")
    from .provider_presets import runtime_profile
    try:
        profile = runtime_profile(provider)
    except ValueError as exc:
        raise ProviderError(str(exc)) from exc
    from .image_messages import prepare_messages
    try:
        messages = prepare_messages(messages, protocol, allow_images=allow_images)
    except ValueError as exc:
        raise ProviderError(str(exc)) from exc
    if protocol == "anthropic":
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        payload = {"model": provider["model"], "max_tokens": max_tokens, "system": system, "messages": [m for m in messages if m["role"] != "system"]}
        endpoint = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        payload = {"model": provider["model"], "messages": messages, "max_tokens": max_tokens, "stream": False}
        if profile in {'openai-reasoning', 'openai-luna'}:
            payload['max_completion_tokens'] = payload.pop('max_tokens')
            payload['reasoning_effort'] = 'none' if profile == 'openai-luna' else 'low'
        elif profile == 'deepseek':
            payload['thinking'] = {'type': 'disabled'}
        elif profile == 'qwen':
            payload['enable_thinking'] = False
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        endpoint = base + "/chat/completions"
        headers = {"Authorization": "Bearer " + key}
    if stream:
        if protocol not in {'openai-compatible','anthropic'}:raise ProviderError('此协议尚未适配流式接收，不自动替换协议。')
        payload['stream']=True
        if protocol!='anthropic':payload['stream_options']={'include_usage':True}
        from .provider_stream import stream_completion
        return await stream_completion(endpoint,headers,payload,protocol,timeout,on_delta)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        if response.is_error:
            # Do not echo provider response bodies, which can contain credentials/user data.
            raise ProviderError(f"模型请求失败（HTTP {response.status_code}）。请核对地址、协议、模型名称、余额和凭据。")
        data = response.json()
        reported_usage = usage_summary(data.get('usage')) if isinstance(data, dict) else {}
        if protocol == "anthropic":
            if require_final_text:
                reason=data.get('stop_reason');finish_reason='length' if reason=='max_tokens' else 'tool_calls' if reason=='tool_use' else 'stop' if reason=='end_turn' else None
                if finish_reason!='stop' or data.get('role')!='assistant' or any(isinstance(block,dict) and block.get('type')=='tool_use' for block in data.get('content',[])):raise ProviderError('模型未明确返回完整助手终稿；截断/工具请求/未知终态不触发自动升级。',usage=reported_usage,finish_reason=finish_reason)
            text = "\n".join(x.get("text", "") for x in data.get("content", []) if x.get("type") == "text")
        else:
            choice = data["choices"][0]
            reason = choice.get('finish_reason')
            finish_reason = reason if reason in {'stop', 'length', 'tool_calls', 'content_filter'} else None
            if require_final_text and (finish_reason!='stop' or choice.get('message',{}).get('role')!='assistant' or choice.get('message',{}).get('refusal') or choice.get('message',{}).get('tool_calls')):raise ProviderError('模型未明确返回完整助手终稿；截断/拒绝/工具请求或未知终态不触发自动升级。',usage=reported_usage,finish_reason=finish_reason)
            text = choice["message"].get("content") or ""
        if not isinstance(text, str) or not text.strip():
            message = "模型达到输出上限但没有返回正文；已保留可用用量，请核对规划模型的思考模式或输出限制。" if finish_reason == 'length' else "模型未返回可用文本；可能仅返回工具调用或不支持当前请求。"
            raise ProviderError(message, usage=reported_usage, finish_reason=finish_reason)
        return text, reported_usage
    except httpx.TimeoutException as exc:
        raise ProviderError("模型请求超时。本次未自动重试，请检查服务或调整执行上限。") from exc
    except httpx.RequestError as exc:
        raise ProviderError("无法连接模型服务，请核对地址和本机网络。") from exc
    except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ProviderError("服务返回格式与所选模型协议不兼容。", usage=reported_usage, finish_reason=finish_reason) from exc


class DuplicateJSONFieldError(ValueError):
    def __init__(self):
        super().__init__('模型JSON包含重复字段，未合并或覆盖。')


MODEL_JSON_MAX_DEPTH = 60  # Same root-zero depth boundary as manual plan drafts.


class JSONStructureLimitError(ValueError):
    def __init__(self):
        super().__init__('模型JSON超出本机结构解析上限（根为0，最多60层），未展开或采纳。')


def _check_model_json_depth(value):
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > MODEL_JSON_MAX_DEPTH:
            raise JSONStructureLimitError()
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)


def _unique_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJSONFieldError()
        value[key] = item
    return value


def extract_json(text: str):
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1])
    try:
        try:
            value = json.loads(stripped, object_pairs_hook=_unique_json_object)
        except json.JSONDecodeError:
            start, end = stripped.find("{"), stripped.rfind("}")
            value = json.loads(stripped[start:end + 1], object_pairs_hook=_unique_json_object)
    except RecursionError:
        raise JSONStructureLimitError() from None
    if not isinstance(value, dict):
        raise ValueError("模型结构化结果不是对象。")
    _check_model_json_depth(value)
    return value
