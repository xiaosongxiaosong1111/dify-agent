"""Bounded text-only SSE accumulation; partial events never apply business state."""
import asyncio,json,re
import httpx
from .providers import ProviderError,usage_summary

MAX_WIRE=2*1024*1024
MAX_EVENT=65536
MAX_TEXT=512000


async def sse_events(response):
    buffer=b'';data=[];event='';wire=0;event_bytes=0
    async for chunk in response.aiter_bytes():
        wire+=len(chunk)
        if wire>MAX_WIRE:raise ValueError('模型流超过本机接收上限，未截断后当作完整结果。')
        buffer+=chunk
        while True:
            match=re.search(rb'\r\n|\r|\n',buffer)
            if not match or (match.group()==b'\r' and match.end()==len(buffer)):break
            line=buffer[:match.start()].decode('utf-8');buffer=buffer[match.end():]
            event_bytes+=len(line.encode('utf-8'))
            if event_bytes>MAX_EVENT:raise ValueError('模型流单事件超出接收上限。')
            if not line:
                if data:yield event,'\n'.join(data)
                data=[];event='';event_bytes=0
            elif line.startswith('data:'):data.append(line[5:].removeprefix(' '))
            elif line.startswith('event:'):event=line[6:].strip()
        if len(buffer)>MAX_EVENT:raise ValueError('模型流单行超出接收上限。')
    if buffer==b'\r':
        if data:yield event,'\n'.join(data)
        buffer=b'';data=[]
    if buffer or data:raise ValueError('模型流事件不完整，未把残段当作完成。')


async def stream_completion(endpoint,headers,payload,protocol,timeout,on_delta):
    usage={};text=[];size=0;finished=False;reason=None;started=False;blocks={}
    def fail(note):return ProviderError(note,usage=usage if finished else {},finish_reason=reason,partial_usage=usage if not finished else None)
    async def append(value):
        nonlocal size
        if not isinstance(value,str):raise ValueError('模型流文字字段格式不兼容。')
        if not value:return
        size+=len(value)
        if size>MAX_TEXT:raise ValueError('模型流正文超过本机接收上限，未截断采纳。')
        text.append(value)
        if on_delta is not None:await on_delta(value)
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream('POST',endpoint,headers=headers,json=payload) as response:
                    if response.is_error:raise fail(f'模型流请求失败（HTTP {response.status_code}），未自动改为普通请求或重试。')
                    if response.headers.get('content-type','').split(';')[0].strip().lower()!='text/event-stream':raise fail('模型未返回约定的SSE流，未自动回退或重复调用。')
                    async for event,raw in sse_events(response):
                        if protocol!='anthropic' and raw=='[DONE]':finished=True;break
                        value=json.loads(raw)
                        if not isinstance(value,dict):raise ValueError('模型流事件不是对象。')
                        if 'error' in value or event=='error' or value.get('type')=='error':raise fail('模型流返回错误事件，已收正文未作为完整结果；没有重试。')
                        if protocol=='anthropic':
                            kind=value.get('type')
                            if event and event!=kind:raise ValueError('模型流事件类型与正文不一致。')
                            if kind=='message_start':
                                if started:raise ValueError('模型流重复开始，未合并不同消息。')
                                started=True;usage=usage_summary(value['message'].get('usage'))
                            elif kind=='content_block_start':
                                if not started:raise ValueError('模型流正文早于消息开始。')
                                index=value['index'];block=value['content_block']
                                if type(index)is not int or index in blocks or block.get('type')!='text':raise ValueError('首批流式仅支持文字内容，不执行工具或公开思考段。')
                                blocks[index]='open';await append(block.get('text',''))
                            elif kind=='content_block_delta':
                                if blocks.get(value.get('index'))!='open' or value.get('delta',{}).get('type')!='text_delta':raise ValueError('模型流增量不属于开放文字块。')
                                await append(value['delta']['text'])
                            elif kind=='content_block_stop':
                                if blocks.get(value.get('index'))!='open':raise ValueError('模型流文字块结束不匹配。')
                                blocks[value['index']]='closed'
                            elif kind=='message_delta':
                                usage.update(usage_summary(value.get('usage')));reason=value.get('delta',{}).get('stop_reason');reason=reason if reason in {'end_turn','max_tokens','stop_sequence','tool_use','pause_turn','refusal'} else None
                            elif kind=='message_stop':
                                if not started or any(v!='closed' for v in blocks.values()):raise ValueError('模型流未完整关闭正文。')
                                finished=True;break
                            # Unknown non-content events and ping are ignored, within byte limits.
                        else:
                            if value.get('usage') is not None:usage=usage_summary(value['usage'])
                            choices=value.get('choices')
                            if not isinstance(choices,list) or len(choices)>1:raise ValueError('首批模型流只支持单候选。')
                            if not choices:continue
                            choice=choices[0]
                            if choice.get('index',0)!=0:raise ValueError('模型流候选编号不匹配。')
                            delta=choice.get('delta',{})
                            if not isinstance(delta,dict):raise ValueError('模型流delta格式不兼容。')
                            if delta.get('tool_calls') or delta.get('function_call') or delta.get('audio'):raise ValueError('首批流式仅支持文字，不执行工具或音频。')
                            if choice.get('finish_reason') is not None:reason=choice['finish_reason'] if choice['finish_reason'] in {'stop','length','tool_calls','content_filter','function_call'} else None
                            if delta.get('content') is not None:await append(delta['content'])
                    if not finished:raise fail('模型流中断或缺少完成标志，部分正文未采用；用量可能不完整。')
                    result=''.join(text)
                    if not result.strip():raise fail('模型流未返回可用正文，已保留可确认用量。')
                    return result,usage
    except ProviderError:raise
    except (TimeoutError,httpx.TimeoutException):raise fail('模型流达到时间上限，已收正文未作为完整结果，不自动重试。') from None
    except httpx.RequestError:raise fail('模型流连接中断，请核对结果和费用，不能直接当作未派发。') from None
    except (ValueError,KeyError,TypeError,AttributeError):raise fail('模型流格式无效或超过接收范围，未应用部分正文；没有自动重试。') from None
