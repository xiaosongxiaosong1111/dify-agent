"""Execute approved multi-turn cases once in a fresh, verifiable conversation."""
import asyncio
import copy
import time
from .evaluation import evaluate_output
from .dify import DifyError


def case_turns(case):
    return [{'input': case['input'], 'expectation': case['expectation']}, *case.get('followups', [])]


def matched_turns(case, result):
    from .acceptance import same_json
    if not isinstance(result, dict) or result.get('conversation_case') is not True:
        return False
    steps = result.get('turns')
    expected = case_turns(case)
    if not isinstance(steps, list) or not steps or len(steps) > len(expected): return False
    cid = None
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get('index') != index + 1 or step.get('status') != 'success': return False
        if not same_json(step.get('input'), expected[index]['input']) or not same_json(step.get('expectation'), expected[index]['expectation']): return False
        actual = step.get('result')
        if not isinstance(actual, dict) or not isinstance(actual.get('answer'), str) or not actual['answer'].strip() or not isinstance(actual.get('conversation_id'), str) or not actual['conversation_id']: return False
        if index == 0: cid = actual['conversation_id']
        if actual['conversation_id'] != cid or step.get('source_conversation_id') != (None if index == 0 else cid): return False
    return result.get('conversation_id') == cid


def evaluate_conversation(case, result):
    if not matched_turns(case, result):
        return {'status':'needs_review','mode':'conversation','details':'多轮输入、预期或实际会话记录不一致，不能计为通过。'}
    evaluations = [evaluate_output({'answer':step['result']['answer']}, step['expectation']) for step in result['turns']]
    failed = [i + 1 for i, value in enumerate(evaluations) if value['status'] == 'failed']
    if failed:
        return {'status':'failed','mode':'conversation','details':f"第 {'、'.join(map(str,failed))} 轮自动规则未通过；停止后续调用，本次多轮样例不通过。"}
    if len(evaluations) != len(case_turns(case)) or result.get('complete') is not True:
        return {'status':'needs_review','mode':'conversation','details':'轮次尚未全部完成，不能按多轮样例通过。'}
    manual = [i + 1 for i, value in enumerate(evaluations) if value['status'] == 'needs_review']
    if manual:
        return {'status':'needs_review','mode':'manual','details':f"自动规则已通过；第 {'、'.join(map(str,manual))} 轮需按各轮标准人工复核整个对话。"}
    return {'status':'passed','mode':'conversation','details':f'{len(evaluations)} 轮已在同一实际会话完成，逐轮声明规则通过；不代表全部业务覆盖。'}


async def execute_conversation(case, send, checkpoint, should_stop, *, seconds):
    result = {'conversation_case':True,'complete':False,'turns':[],'conversation_id':'','answer':''}
    deadline = time.monotonic() + seconds
    for index, turn in enumerate(case_turns(case)):
        if should_stop():
            result['stop_reason'] = 'paused'
            raise DifyError('多轮验收已暂停；已完成轮次保留，剩余轮次未派发。重新运行将从新会话首轮开始。', result=result)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result['stop_reason'] = 'time_limit'
            raise DifyError('多轮验收达到总采集时间上限；剩余轮次未派发。', result=result)
        source_cid = result['conversation_id'] or None
        result['pending_turn'] = {'index':index+1,'input':copy.deepcopy(turn['input']),'source_conversation_id':source_cid}
        checkpoint(copy.deepcopy(result))
        try:
            async with asyncio.timeout(remaining):
                actual = await send(turn['input'], source_cid, remaining)
        except TimeoutError as exc:
            raise DifyError('多轮验收调用达到总采集时间上限，当前轮结果可能未知；禁止盲目重跑。', result=result) from exc
        except DifyError as exc:
            result['pending_turn']['result'] = copy.deepcopy(exc.result)
            raise DifyError(str(exc), result=result, http_status=exc.http_status) from exc
        except Exception as exc:
            raise DifyError('多轮验收调用被意外中断，当前轮结果可能未知；已保留检查点，禁止盲目重跑。', result=result) from exc
        if not isinstance(actual,dict) or not isinstance(actual.get('answer'),str) or not actual['answer'].strip() or not isinstance(actual.get('conversation_id'),str) or not actual['conversation_id'] or (source_cid and actual['conversation_id'] != source_cid):
            result['pending_turn']['result'] = actual
            raise DifyError('多轮验收没有返回匹配来源的明确对话结果，结果可能未知；已保留实际信息。', result=result)
        evaluation = evaluate_output({'answer':actual['answer']}, turn['expectation'])
        result['turns'].append({'index':index+1,'status':'success','input':copy.deepcopy(turn['input']), 'expectation':copy.deepcopy(turn['expectation']), 'source_conversation_id':source_cid,'result':actual,'evaluation':evaluation})
        result.update(conversation_id=actual['conversation_id'],answer=actual['answer'])
        result.pop('pending_turn',None)
        result['complete'] = index == len(case_turns(case)) - 1
        if evaluation['status'] == 'failed':result['stop_reason'] = 'rule_failed'
        checkpoint(copy.deepcopy(result))
        if evaluation['status'] == 'failed': break
    return result
