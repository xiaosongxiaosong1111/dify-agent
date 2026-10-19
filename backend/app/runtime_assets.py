"""Retain known hashed JS/CSS for open pages; never serve other snapshot files."""
import hashlib,json,re
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse

ASSET=re.compile(r'[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{6,}\.(?:js|css)')


class SnapshotAssets(StaticFiles):
    def __init__(self,directory,snapshots):
        super().__init__(directory=directory);self.snapshots=Path(snapshots)

    async def get_response(self,path,scope):
        try:return await super().get_response(path,scope)
        except HTTPException as exc:
            if exc.status_code!=404:raise
        if not ASSET.fullmatch(path) or scope.get('method') not in {'GET','HEAD'} or not self.snapshots.is_dir():raise HTTPException(404)
        key='frontend/dist/assets/'+path
        for snapshot in sorted(self.snapshots.iterdir(),reverse=True)[:100]:
            if not snapshot.is_dir() or snapshot.resolve().parent!=self.snapshots.resolve():continue
            manifest=snapshot/'runtime-manifest.json'
            try:
                value=json.loads(manifest.read_text(encoding='utf-8'));files=value.get('files')
                if value.get('schema_version')!=1 or value.get('build_id')!=snapshot.name or not isinstance(files,dict):continue
                expected=files.get(key)
                if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected):continue
                target=snapshot/key
                if not target.is_file() or not target.resolve().is_relative_to(snapshot.resolve()):continue
                if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:continue
                return FileResponse(target,headers={'Cache-Control':'public, max-age=31536000, immutable','X-Sierra-Asset-Source':'retained-snapshot'})
            except (ValueError,OSError,AttributeError):continue
        raise HTTPException(404)
