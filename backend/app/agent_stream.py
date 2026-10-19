"""Collect native Agent SSE once, with bounded output and no write retries."""
import asyncio
import json
import httpx


async def collect_agent(client, query, inputs, *, conversation_id=None, seconds=90, should_stop=None):
    from .dify import DifyError
    if conversation_id is not None and (not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 128 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in conversation_id)):
        raise DifyError('Agent 会话标识无效，本次未派发。')
    if should_stop and should_stop():
        raise DifyError('Agent 在派发前已暂停，本次没有发送运行请求。')
    key = client.store.secret(client.env['id'], 'service_api_key')
    if not key:
        raise DifyError('缺少该 Agent 应用专属运行 Key。')
    partial = {'answer': '', 'conversation_id': '', 'task_id': '', 'metadata': {}, 'transport': 'native_agent_sse', 'terminal': False}
    event_count, total_chars = 0, 0
    final_answer = None

    async def stop_remote():
        if not partial['task_id']:
            partial['stop_requested'] = False
            return
        partial['stop_requested'] = True
        try:
            await client.request('POST', '/v1/chat-messages/' + partial['task_id'] + '/stop',
                                 credential='service_api_key', json={'user': 'flowcraft-local'}, timeout=10)
            partial['stop_acknowledged'] = True
        except DifyError:
            partial['stop_acknowledged'] = False

    def consume(payload):
        nonlocal event_count, final_answer
        try:
            event = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise DifyError('Agent 流式返回无法解析，结果可能未知；请核对 Dify，禁止盲目重跑。', result=partial) from exc
        if not isinstance(event, dict):
            raise DifyError('Agent 流式事件形状不兼容，结果可能未知。', result=partial)
        event_count += 1
        if event_count > 5000:
            raise DifyError('Agent 事件超过本机采集上限，结果可能未知。', result=partial)
        for field in ('conversation_id', 'task_id', 'message_id'):
            value = event.get(field)
            if value is not None:
                if not isinstance(value, str) or not value or len(value) > 128 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in value):
                    raise DifyError('Agent 返回无效的运行标识，结果可能未知。', result=partial)
                if partial.get(field) and partial[field] != value:
                    raise DifyError('Agent 返回相互冲突的运行标识，结果可能未知。', result=partial)
                partial[field] = value
        if conversation_id and partial['conversation_id'] and partial['conversation_id'] != conversation_id:
            raise DifyError('Agent 返回的会话与请求来源不一致，结果可能未知；已保留实际标识，请先核对。', result=partial)
        name = event.get('event')
        if name in {'message', 'agent_message', 'message_replace'}:
            text = event.get('answer')
            if not isinstance(text, str):
                raise DifyError('Agent 文本事件格式不兼容，结果可能未知。', result=partial)
            # Native 1.17.1 emits agent_message previews AND a complete final
            # message. They are separate channels, not consecutive answer parts.
            if name == 'agent_message':
                if final_answer is not None:
                    raise DifyError('最终回答后又收到 Agent 过程文本，结果可能未知。', result=partial)
                answer = partial['answer'] + text
            else:
                final_answer = text if name == 'message_replace' else (final_answer or '') + text
                answer = final_answer
            partial['answer'] = answer[:100000]
            if len(answer) > 100000:
                partial['output_truncated'] = True
                raise DifyError('Agent 文本超过采集上限，结果可能未知；已明确截断并保留部分。', result=partial)
        elif name == 'error':
            partial.update(terminal=True, event_count=event_count, data={'status': 'failed'})
            raise DifyError('原生 Agent 返回执行错误；已保留标识和部分文本，本次不算通过。', result=partial)
        elif name == 'message_end':
            if final_answer is None or not partial['conversation_id'] or not partial['task_id'] or not partial['answer'].strip():
                raise DifyError('Agent 结束事件缺少明确会话或文本结果，结果可能未知；不能当作通过。', result=partial)
            meta = event.get('metadata')
            if isinstance(meta, dict) and isinstance(meta.get('usage'), dict):
                allowed = {'prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_unit_price', 'prompt_price_unit', 'prompt_price', 'completion_unit_price', 'completion_price_unit', 'completion_price', 'total_price', 'currency', 'latency', 'time_to_first_token', 'time_to_generate'}
                usage = {k: v for k, v in meta['usage'].items() if k in allowed}
                if all(isinstance(k, str) and len(k) <= 100 and (v is None or type(v) in (str, int, float, bool)) for k, v in usage.items()) and len(usage) <= 60:
                    partial['metadata'] = {'usage': usage}
            partial.update(terminal=True, event_count=event_count, answer_channel='final_message')
            return True
        elif name == 'agent_thought':
            # Do not copy observations or tool parameters into public results.
            partial['thought_events'] = partial.get('thought_events', 0) + 1
            tool = event.get('tool')
            if isinstance(tool, str) and 0 < len(tool) <= 200 and all(c.isalnum() or c in '_.:/-' for c in tool):
                names = partial.setdefault('tool_names', [])
                if tool not in names and len(names) < 30: names.append(tool)
        elif name not in {'ping', 'tts_message', 'tts_message_end'}:
            raise DifyError('遇到未适配的 Agent 事件（可能需要文件或人工参与），结果可能未知；不会省略后计为完成。', result=partial)
        return False

    request = {'query': query, 'inputs': inputs, 'response_mode': 'streaming', 'user': 'flowcraft-local'}
    if conversation_id:
        request['conversation_id'] = conversation_id
    try:
        async with asyncio.timeout(seconds):
            async with httpx.AsyncClient(timeout=httpx.Timeout(30), follow_redirects=False) as http:
                async with http.stream('POST', client.base + '/v1/chat-messages',
                                       headers={'Authorization': 'Bearer ' + key},
                                       json=request) as response:
                    if response.is_error:
                        status = response.status_code
                        phrase = '；结果可能未知' if status >= 500 else ''
                        raise DifyError(f'Agent 接口返回 HTTP {status}{phrase}。请核对权限、发布、API 开启及后端就绪状态。', result=partial, http_status=status)
                    if 'text/event-stream' not in response.headers.get('content-type', ''):
                        raise DifyError('Agent 接口没有返回 SSE，结果可能未知。', result=partial)
                    data = []
                    async for line in response.aiter_lines():
                        if should_stop and should_stop():
                            raise DifyError('已暂停 Agent 采集，将尝试停止远端；结果可能未知，请核对。', result=partial)
                        total_chars += len(line)
                        if total_chars > 2000000:
                            raise DifyError('Agent 返回超过采集上限，结果可能未知。', result=partial)
                        if not line:
                            if data and consume('\n'.join(data)):
                                return partial
                            data = []
                        elif line.startswith('data:'):
                            data.append(line[5:].lstrip(' '))
                    if data and consume('\n'.join(data)):
                        return partial
                    raise DifyError('Agent 流在结束事件前关闭，结果可能未知；保留部分结果并禁止盲目重跑。', result=partial)
    except asyncio.CancelledError as exc:
        await stop_remote()
        raise DifyError('Agent 采集被取消，结果可能未知；已尝试停止远端，请先核对。', result=partial) from exc
    except (TimeoutError, httpx.RequestError) as exc:
        await stop_remote()
        raise DifyError('Agent 连接中断或达到采集时间上限，结果可能未知；已尝试停止，请先核对 Dify。', result=partial) from exc
    except DifyError:
        if not partial['terminal']:
            await stop_remote()
        raise
