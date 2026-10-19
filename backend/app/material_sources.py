"""Read only an owned, unchanged source file; no file format processing."""
import hashlib,uuid
from pathlib import Path
from fastapi import HTTPException


def read_source(host,item_id,material):
    try:
        material_id=material['id'];uuid.UUID(material_id);uuid.UUID(item_id)
        folder=(host.DATA_ROOT/item_id/'materials').resolve()
        if folder!=host.DATA_ROOT.resolve()/item_id/'materials':raise ValueError('redirected folder')
        path=folder/(material_id+Path(material.get('name','')).suffix.lower())
        if not path.resolve().is_relative_to(folder):raise ValueError('redirected source')
        with path.open('rb') as handle:
            raw=handle.read(20*1024*1024+1)
        if len(raw)>20*1024*1024 or hashlib.sha256(raw).hexdigest()!=material.get('sha256'):
            raise HTTPException(409,'本机原文件内容已变化，未把文字或图像操作关联到旧来源；请重新上传核对。')
        return raw
    except HTTPException:raise
    except (OSError,ValueError,KeyError):
        raise HTTPException(422,'本机原材料文件不可读取或来源路径无法核对，未继续处理；请重新上传。') from None
