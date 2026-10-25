"""On-demand source-byte inspection and attachment download, never file parsing."""
import hashlib
import os
import re
import stat
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

MAX_BYTES=20*1024*1024
NOTE='这是本次读取的原文件字节核对，不是解析完整、OCR、业务内容正确或需求已确认的证明；不修改材料、历史或确认。下载时会重新核对，不能用提取文字重建丢失原件。'


def download_name(material):
    name=material.get('name')
    if not isinstance(name,str):return '材料原文件'
    name=Path(name.replace('\\','/')).name
    name=''.join(c for c in name if ord(c)>=32 and ord(c)!=127 and c not in '<>:"/\\|?*').strip(' .')[:160].rstrip(' .')
    return name or '材料原文件'


def inspect_original(host,item_id,material):
    saved_sha=material.get('sha256')
    known_sha=isinstance(saved_sha,str) and re.fullmatch(r'[0-9a-f]{64}',saved_sha) is not None
    known_size=type(material.get('size')) is int and material['size']>=0
    value={'material_id':material.get('id'),'source_sha256':saved_sha if known_sha else None,
           'recorded_size':material['size'] if known_size else None,'observed_size':None,'observed_sha256':None,
           'sha256_matches':None,'size_matches':None,'downloadable':False,'state':'unavailable',
           'message':'原文件缺失、不可读取或路径归属无法核对；请重新上传，不会重建或改写原件。',
           'download_name':download_name(material),'note':NOTE}
    try:
        mid=material['id'];name=material.get('name','')
        if not isinstance(mid,str) or not isinstance(item_id,str) or not isinstance(name,str):raise ValueError('identity')
        if str(uuid.UUID(mid))!=mid or str(uuid.UUID(item_id))!=item_id:raise ValueError('identity')
        suffix=Path(name).suffix.lower()
        if len(suffix)>32 or any(ord(c)<32 or c in '<>:"/\\|?*' for c in suffix):raise ValueError('suffix')
        folder=(host.DATA_ROOT/item_id/'materials').resolve()
        if folder!=host.DATA_ROOT.resolve()/item_id/'materials':raise ValueError('redirected folder')
        path=folder/(mid+suffix)
        if path.is_symlink() or path.resolve().parent!=folder:raise ValueError('redirected source')
        if not known_sha:
            value.update(state='unknown',message='此记录没有可核对的原文件摘要；本次未读取原字节，不能确认或下载，需重新上传。')
            return value
        if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):raise ValueError('not regular')
        if path.stat().st_size>MAX_BYTES:
            value.update(state='oversized',message='当前原文件超过20MB读取上限，未读取或下载；请拆分后重新上传。')
            return value
        with path.open('rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):raise ValueError('not regular')
            raw=handle.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            value.update(state='oversized',message='当前原文件超过20MB读取上限，未继续读取或下载；请拆分后重新上传。')
            return value
        observed=hashlib.sha256(raw).hexdigest()
        value.update(observed_size=len(raw),observed_sha256=observed,sha256_matches=observed==saved_sha,size_matches=len(raw)==material['size'] if known_size else None)
        if observed!=saved_sha or value['size_matches'] is False:
            value.update(state='changed',message='本机原文件字节或记录大小与保存来源不一致，不能下载为原件；请重新上传核对，原记录保持。')
        else:
            value.update(state='verified',downloadable=True,message='本次读取的原文件字节与保存摘要一致。'+('记录大小未知，未猜测原大小。' if not known_size else ''),_raw=raw)
        return value
    except (OSError,ValueError,KeyError):
        return value


def register(host):
    def owned(item_id,material_id,revision):
        task=host.get_task(item_id);host.require_revision(task,revision)
        material=next((m for m in task['materials'] if m['id']==material_id),None)
        if material is None:raise HTTPException(404,'材料不属于当前任务或已移除，未读取保留的历史原件。')
        return material

    def inspect(item_id,material_id,revision):
        with host.store.lock:material=owned(item_id,material_id,revision).copy()
        value=inspect_original(host,item_id,material)
        # Do not return a source read under an obsolete task revision or removed membership.
        with host.store.lock:
            current=owned(item_id,material_id,revision)
            if current!=material:raise HTTPException(409,'材料来源在读取期间变化，未返回旧核对或下载；请重新读取当前材料。')
        value.update(schema_version=1,task_id=item_id,revision=revision,checked_at=host.now())
        return value

    @host.app.get('/api/tasks/{item_id}/materials/{material_id}/original')
    def original_status(item_id:str,material_id:str,revision:int):
        value=inspect(item_id,material_id,revision);value.pop('_raw',None)
        return JSONResponse(value,headers={'Cache-Control':'no-store'})

    @host.app.get('/api/tasks/{item_id}/materials/{material_id}/original/download')
    def original_download(item_id:str,material_id:str,revision:int):
        value=inspect(item_id,material_id,revision)
        if not value['downloadable']:raise HTTPException(409 if value['state']=='changed' else 422,value['message'])
        return Response(value['_raw'],media_type='application/octet-stream',headers={
            'Content-Disposition':"attachment; filename=\"material-original\"; filename*=UTF-8''"+quote(value['download_name'],safe=''),
            'X-Sierra-Source-Sha256':value['observed_sha256'],'X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':'sandbox','Cache-Control':'no-store',
        })
