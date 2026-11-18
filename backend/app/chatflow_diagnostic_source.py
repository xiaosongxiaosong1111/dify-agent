"""Resolve a Dify 1.17.1 blocking Chatflow message to its native workflow run."""
import uuid
from .dify import DifyError


def identifier(value):
    if not isinstance(value, str):
        raise DifyError('Chatflow消息来源标识无效，未猜测远端运行。')
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        raise DifyError('Chatflow消息来源标识无效，未猜测远端运行。') from None


def verify_turn_conversation(result, saved_conversation_id, turn_index):
    if type(turn_index) is not int or turn_index < 1:
        raise DifyError('无法确定所选对话轮次，不读取原生节点。')
    try:
        actual = identifier(result.get('conversation_id'))
        if turn_index > 1 or saved_conversation_id not in (None, ''):
            expected = identifier(saved_conversation_id)
        else:
            # An interrupted first turn may return an ID before any turn has been saved.
            expected = actual
    except DifyError:
        raise DifyError('所选轮次缺少可核对的会话标识，不读取原生节点。') from None
    if actual != expected:
        raise DifyError('所选轮次返回会话与原连续会话不一致，不读取其它会话的节点。')


def reference(result):
    if not isinstance(result, dict) or result.get('workflow_run_id') is not None:
        raise DifyError('已有原生运行标识无效，不能用消息查找绕过冲突。')
    if result.get('mode') not in (None, 'advanced-chat'):
        raise DifyError('保存结果不是可信Chatflow类型，不读取其它类型消息。')
    values = [result.get(k) for k in ('id', 'message_id') if result.get(k) is not None]
    normalized = [identifier(v) for v in values]
    if not normalized or len(set(normalized)) != 1:
        raise DifyError('保存结果缺少唯一消息ID或消息别名冲突；不能把task_id当消息或原生运行ID。')
    conversation = identifier(result.get('conversation_id'))
    return {'message_id': normalized[0], 'conversation_id': conversation}


async def resolve(client, app_id, source):
    app = identifier(app_id)
    message = identifier(source.get('message_id'))
    conversation = identifier(source.get('conversation_id'))
    # The tagged message controller scopes this exact message lookup to app_model.id.
    value = await client.request('GET', f'/console/api/apps/{app}/messages/{message}', credential='console_token')
    if (not isinstance(value, dict) or identifier(value.get('id')) != message
            or identifier(value.get('conversation_id')) != conversation
            or 'app_id' in value and identifier(value['app_id']) != app):
        raise DifyError('Dify消息身份或会话不匹配，未读取原生运行或节点。')
    rid = identifier(value.get('workflow_run_id'))
    return {'kind': 'chat_message_record', 'message_id': message, 'conversation_id': conversation,
        'workflow_run_id': rid, 'verification': 'message_identity_and_workflow_id_only',
        'message_body_saved': False, 'workflow_or_nodes_verified': False}
