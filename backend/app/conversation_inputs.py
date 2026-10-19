"""Stable custom Chatflow inputs with private local runtime provenance."""
import copy
import hashlib
import json
import sqlite3
from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from .run_diagnostics import binding

KIND = 'conversation_input_binding'


def input_digest(values):
    try:
        raw = json.dumps(values, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, '会话输入结构或编码无法固定，未派发；不显示原输入。') from None
    return hashlib.sha256(raw).hexdigest()


def cipher_blob(store, owner):
    try:
        with store.connect() as conn:
            row = conn.execute('SELECT value FROM secrets WHERE id=?', (owner+':service_api_key',)).fetchone()
    except sqlite3.Error:
        raise HTTPException(503, '本机运行凭据来源暂时不可核对，未派发；请检查本机存储后再操作。') from None
    if not row: return None
    if not isinstance(row[0], (bytes, bytearray, memoryview)):
        raise HTTPException(422, '本机应用运行凭据结构无效，请重新登记，未派发。')
    return bytes(row[0])


def credential_stamp(store, owner):
    blob = cipher_blob(store, owner)
    # Hash randomized ciphertext, never plaintext or a reusable credential.
    return hashlib.sha256(blob).hexdigest() if blob else None


class ServiceSnapshot:
    def __init__(self, store, owner):
        self.owner = owner
        with store.lock:
            blob = cipher_blob(store, owner)
            self.stamp = hashlib.sha256(blob).hexdigest() if blob else None
            try: self.value = store.cipher.decrypt(blob).decode('utf-8') if blob else ''
            except (InvalidToken, UnicodeError, ValueError):
                raise HTTPException(422, '本机应用运行凭据不可读，请重新登记；未派发。') from None
            if not self.stamp or not self.value:
                raise HTTPException(422, '请登记当前应用的Service API Key；输入已检查但尚未派发。')

    def secret(self, owner, key):
        return self.value if owner == self.owner and key == 'service_api_key' else ''


def custom_input_source(store, task, env, context, artifact_sha):
    rows = [r for r in task.get('runs', []) if isinstance(r, dict) and r.get('id') == context.get('source_run_id')]
    if len(rows) != 1: raise HTTPException(422, '原会话记录不唯一或缺失，请选择当前可信来源或开始新会话。')
    source = rows[0]
    try: proof = store.get(KIND, source['id'])
    except (ValueError, TypeError): raise HTTPException(422, '原会话输入绑定记录不可读，未复用。') from None
    except sqlite3.Error: raise HTTPException(503, '本机会话来源索引暂时不可读取，未复用或派发。') from None
    expected = {'schema_version':1, 'run_id':source['id'], 'task_id':task['id'],
                'revision':task['revision'], 'environment_id':env['id'], 'app_id':task.get('dify_app_id'),
                'environment_binding':binding(env), 'artifact_sha256':artifact_sha}
    result = source.get('result')
    cid = result.get('conversation_id') if isinstance(result, dict) else None
    if (source.get('kind') != 'run' or source.get('status') != 'success' or source.get('test_case') is not None or
        type(source.get('revision')) is not int or source.get('revision') != task['revision'] or source.get('environment_id') != env['id'] or
        source.get('app_id') != task.get('dify_app_id') or source.get('app_type') != 'advanced-chat' or
        source.get('environment_binding') != binding(env) or not isinstance(proof, dict) or type(proof.get('schema_version')) is not int or type(proof.get('revision')) is not int or
        any(proof.get(k) != v for k,v in expected.items()) or not isinstance(cid, str) or not cid or
        cid != context.get('conversation_id') or proof.get('conversation_id') != cid or
        not isinstance(source.get('input'), dict)):
        raise HTTPException(422, '原会话缺少当前App／环境／成果／成功自由运行的可信输入绑定，不能忽略参数后复用；请从新会话开始。')
    if proof.get('credential_stamp') != credential_stamp(store, env['id']) or not proof.get('credential_stamp'):
        raise HTTPException(422, '应用运行凭据已改变或缺失，未复用原会话；请在当前连接从新会话开始。')
    if proof.get('input_sha256') != input_digest(source['input']):
        raise HTTPException(422, '原会话输入记录已改变，未将新内容当原始参数复用。')
    return copy.deepcopy(source['input'])


def completed_binding(task, env, record, result, snapshot, artifact_sha):
    cid = result.get('conversation_id') if isinstance(result, dict) else None
    if not isinstance(cid, str) or not cid or len(cid) > 128 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in cid):
        return None
    return {'schema_version':1, 'id':record['id'], 'run_id':record['id'], 'task_id':task['id'],
            'revision':record['revision'], 'environment_id':record['environment_id'], 'app_id':record['app_id'],
            'environment_binding':record['environment_binding'], 'artifact_sha256':artifact_sha,
            'credential_stamp':snapshot.stamp, 'input_sha256':input_digest(record['input']),
            'conversation_id':cid}
