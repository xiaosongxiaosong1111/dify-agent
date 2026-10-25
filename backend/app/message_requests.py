"""Persisted identities for opt-in message delivery; retries only read old outcomes."""
import hashlib,json
from fastapi import HTTPException


def key(task_id,request_id):return task_id+':'+request_id


def fingerprint(payload):
    value={'revision':payload.revision,'content':payload.content,'mode':payload.mode,'stream_response':payload.stream_response}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def record(host,task,payload,operation_id):
    if payload.request_id is None:return None
    return {'id':key(task['id'],payload.request_id),'task_id':task['id'],'request_id':payload.request_id,
            'revision':payload.revision,'payload_sha256':fingerprint(payload),'operation_id':operation_id,'created_at':host.now()}


def public(host,value):
    operation=host.store.get('interview_operation',value['operation_id']) if value.get('operation_id') else None
    state='unknown';result_revision=None
    if operation and operation.get('task_id')==value['task_id']:
        state='running' if operation.get('status')=='running' else operation.get('status','unknown')
        result_revision=operation.get('result_revision')
    elif value.get('outcome')=='no_provider':state='no_provider';result_revision=value.get('result_revision')
    return {k:value[k] for k in ('task_id','request_id','revision','operation_id','created_at')} | {
        'state':state,'result_revision':result_revision,
        'note':'只读原发送回执，不再派发。失败、中断或未知保留原用量，不把新标识当成原请求重试；核对任务历史和预算后才决定新消息。'}


def replay(host,task,payload):
    if payload.request_id is None:return False
    if payload.revision is None:raise HTTPException(422,'有发送标识时须同时提供发送时的已保存修订；未记录或派发。')
    existing=host.store.get('message_request',key(task['id'],payload.request_id))
    if existing is None:return False
    if existing.get('payload_sha256')!=fingerprint(payload):
        raise HTTPException(409,'此发送标识已绑定另一份内容、模式、流式选项或修订；未重复记录或派发。')
    result=public(host,existing)
    if result['state'] in {'running','unknown'}:
        raise HTTPException(409,'原发送仍在进行或结果尚未核实；请只读核对该标识的回执，不重复派发。')
    return True


def register(host):
    @host.app.get('/api/tasks/{item_id}/message-requests/{request_id}')
    def read(item_id:str,request_id:str):
        with host.store.lock:
            host.get_task(item_id)
            value=host.store.get('message_request',key(item_id,request_id))
            if value is None or value.get('task_id')!=item_id:raise HTTPException(404,'此任务没有该发送标识的本机回执；不会自动派发，请先核对对话历史。')
            return public(host,value)
