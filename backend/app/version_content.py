"""Explicit, paged reading of saved history values, independent of restore."""
import hashlib
import hmac
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from .delivery_bundle import check_text
from .version_restore import select, token

Section = Literal['requirements', 'configuration', 'workflow_plan', 'agent_plan', 'test_cases']
LIMIT = 2_000_000
NOTE = ('仅显示所选历史保存值的JSON文本，不是原文件字节或当前草稿；'
        '不恢复版本、不更改确认或应用绑定，不执行代码、模型或平台请求，也不证明业务通过。')


class ContentRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def guarded(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={
                    'detail': '历史正文请求无效，请核对分区、页范围及当前比较来源；未读取或恢复，不回显输入。'})
        return guarded


def read_content(task, version, section, snapshot_token, offset=0, limit=4000):
    if not hmac.compare_digest(token(task, version), snapshot_token):
        raise HTTPException(409, '当前内容或历史快照已变化，请重新比较后读取；未返回旧正文。')
    if section not in {'requirements', 'configuration', 'workflow_plan', 'agent_plan', 'test_cases'}:
        raise HTTPException(422, '历史正文分区无效，未读取其它记录。')
    if section not in version:
        raise HTTPException(404, '此快照没有保存所选内容；不以当前版本补齐历史。')
    try:
        text = json.dumps(version[section], ensure_ascii=False, indent=2, allow_nan=False)
        raw = text.encode('utf-8')
        check_text(raw, LIMIT)
    except (HTTPException, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise HTTPException(422, '历史正文超限、编码或结构无效，或疑似含明文凭据；未返回部分内容，不回显原文。') from None
    if type(offset) is not int or type(limit) is not int or not 0 <= offset < len(text) or not 1 <= limit <= 4000:
        raise HTTPException(422, '历史正文页范围无效，未返回内容。')
    chunk = text[offset:offset + limit]
    end = offset + len(chunk)
    return {'schema_version': 1, 'task_id': task['id'], 'revision': task['revision'],
        'app_type': task['app_type'], 'version_id': version['id'],
        'historical_revision': version.get('revision') if type(version.get('revision')) is int and version['revision'] > 0 else None,
        'section': section, 'snapshot_token': snapshot_token,
        'content_sha256': hashlib.sha256(raw).hexdigest(),
        'page_sha256': hashlib.sha256(chunk.encode('utf-8')).hexdigest(),
        'total_chars': len(text), 'total_utf8_bytes': len(raw), 'offset': offset,
        'next_offset': end if end < len(text) else None, 'text': chunk,
        'source_kind': 'historical_saved_value_json', 'verification': 'local_history_content_read_only',
        'task_changed': False, 'network_requested': False, 'platform_checked': False,
        'business_verified': False, 'note': NOTE}


def register(host):
    router = APIRouter(route_class=ContentRoute)

    @router.get('/api/tasks/{item_id}/versions/{version_id}/content')
    def read(item_id: str, version_id: UUID, section: Section,
             snapshot_token: str = Query(pattern=r'^[a-f0-9]{64}$'),
             revision: int = Query(ge=1), offset: int = Query(default=0, ge=0),
             limit: int = Query(default=4000, ge=1, le=4000)):
        with host.store.lock:
            task = host.get_task(item_id)
            host.require_revision(task, revision)
            return read_content(task, select(task, str(version_id)), section, snapshot_token, offset, limit)

    host.app.include_router(router)
