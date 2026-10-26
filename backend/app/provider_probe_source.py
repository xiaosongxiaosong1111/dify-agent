"""Bind legacy text/JSON observations to their saved model configuration."""
import time
from fastapi import HTTPException
from .provider_tool_probe import identity,strict_json
from .providers import ProviderError,usage_summary


async def test(h,item_id,payload,kind):
    payload={} if payload is None else payload
    if set(payload)-{'expected_configuration_revision'}:raise HTTPException(422,'模型测试包含未支持字段，未派发。')
    expected=payload.get('expected_configuration_revision')
    if 'expected_configuration_revision' in payload and (type(expected) is not int or expected<0):raise HTTPException(422,'模型配置基准须为非负整数，未派发。')
    with h.store.lock:
        provider=h.store.get('provider',item_id)
        if not provider:raise HTTPException(404,'模型配置不存在。')
        revision=provider.get('configuration_revision',0)
        if 'expected_configuration_revision' in payload and expected!=revision:raise HTTPException(409,'模型配置已变化，请重新读取并核对后再决定测试，未派发。')
        source=identity(provider);key=h.store.secret(item_id,'api_key')
    start=time.monotonic();usage={};ok=True
    json_check=kind=='json';capability='structured_output' if json_check else 'text'
    preset=provider.get('preset_id','')
    limit=1024 if preset.startswith('claude-') else 512 if preset.startswith('openai-') else 128 if json_check else 64
    failure='JSON 输出检查未通过。可能是网络、权限、格式、截断或模型能力问题；没有输出服务返回正文。'
    try:
        kwargs={'max_tokens':limit,'timeout':30}
        if json_check:kwargs['json_mode']=provider.get('protocol')!='anthropic'
        text,reported=await h.call_model(provider,key,[{'role':'user','content':'只返回一个 JSON 对象 {"ok":true}，不要说明或 Markdown。' if json_check else '请只回复：连接成功'}],**kwargs)
        usage=usage_summary(reported)
        if json_check:
            try:
                parsed=strict_json(text)
                ok=isinstance(parsed,dict) and set(parsed)=={'ok'} and parsed['ok'] is True
            except (ValueError,TypeError,RecursionError):ok=False
    except ProviderError as exc:
        ok=False;usage=usage_summary(exc.usage)
        if not json_check:failure=str(exc)
    latency=int((time.monotonic()-start)*1000)
    with h.store.lock:
        current=h.store.get('provider',item_id)
        matched=bool(current and identity(current)==source)
        metadata={'source_configuration_revision':revision,'current_configuration_revision':current.get('configuration_revision',0) if current else None,'current_source':matched,'result_applied':False}
        if not matched:
            return {'ok':ok,'latency_ms':latency,'usage':usage,**metadata,'message':f'原配置v{revision}的本次'+('文本' if not json_check else 'JSON')+'测试'+('返回通过。' if ok else '未通过。')+'配置已变化或删除，结果未更新当前能力、未恢复旧配置，也未重发。'}
        if ok or json_check:
            current.setdefault('capabilities',{})[capability]='verified' if ok else 'failed'
            current.setdefault('checks',{})[capability]={'created_at':h.now(),'latency_ms':latency,'usage':usage,'source_configuration_revision':revision,'source_token':source,'scope':'single_json_object_only' if json_check else 'single_text_response_only'}
            h.store.put('provider',item_id,current);metadata['result_applied']=True
        if not ok:raise HTTPException(502,failure)
        return {'ok':True,'latency_ms':latency,'message':'真实 JSON 对象检查通过。工具、图片能力和复杂业务规划质量仍需分别验证。' if json_check else '真实文本调用成功。工具、结构化和图片能力尚未分别验证。','capabilities':current['capabilities'],'usage':usage,**metadata}
