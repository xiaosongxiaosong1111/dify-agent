"""One local snapshot for artifact/report delivery; never dispatch external work."""
import hashlib
import io
import json
import re
import zipfile

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .dsl import TARGET_DIFY_VERSION, DSL_VERSION
from .dsl_roundtrip import parse, MAX_BYTES
from .plan_drafts import _SECRET, _ASSIGNMENT
from .mock_integration_guide import render as integration_guide

REPORT_LIMIT = 8_000_000
NOTE = ('本包仅打包同一已保存修订的本机成果和记录；静态校验、规则通过及文件摘要不证明平台实时状态、'
        '完整业务验收或文件来源可信。模拟依赖、未知结果和旧费用预留保持；不含材料原件、凭据或运行Key。')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def task_digest(task):
    return sha(json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def check_text(raw, limit):
    if not raw or len(raw) > limit:
        raise HTTPException(422, '交付文件为空或超过本机打包上限，未返回部分文件；请分别核对原成果和说明。')
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise HTTPException(422, '交付文件不是有效UTF-8，未打包，不回显内容。') from None
    scanned = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text).replace('\\"', '"').replace("\\'", "'")
    if _SECRET.search(scanned) or _ASSIGNMENT.search(scanned):
        raise HTTPException(422, '交付内容疑似包含明文凭据，未打包；请先核对来源并使用秘密变量，错误不回显原文。')
    return text


def register(h):
    router = APIRouter()

    @router.get('/api/tasks/{item_id}/delivery-bundle')
    def download(item_id: str, revision: int = Query(ge=1)):
        with h.store.lock:
            task = h.get_task(item_id); h.require_revision(task, revision)
            artifact = task.get('artifact')
            if (not isinstance(artifact, dict) or artifact.get('revision') != revision
                    or (artifact.get('validation') or {}).get('valid') is not True
                    or not task.get('requirements_confirmed') or not task.get('configuration_confirmed')
                    or task.get('plan_stale')):
                raise HTTPException(422, '请先保存并确认当前方案，生成本修订的有效静态成果，再下载交付包。')
            mode = task.get('app_type')
            if mode not in {'workflow', 'advanced-chat', 'agent'}:
                raise HTTPException(422, '当前应用类型没有可打包的DSL，不改变用户选择。')
            folder = (h.DATA_ROOT / task['id']).resolve()
            # Keep the existing credential-scan-before-hash order for this bundle.
            path = h.artifact_path(task, verify=False)
            if path.is_symlink() or path.resolve().parent != folder or folder.parent != h.DATA_ROOT.resolve():
                raise HTTPException(422, '成果路径不属于当前任务，未读取或打包。')
            try:
                with path.open('rb') as source:
                    raw = source.read(MAX_BYTES + 1)
            except OSError:
                raise HTTPException(404, '当前成果不可读取，请核对文件后重新生成。') from None
            content = check_text(raw, MAX_BYTES)
            try:
                native=parse(content, mode)
            except (ValueError, TypeError, RecursionError):
                raise HTTPException(422, '当前DSL的类型、版本、结构或秘密变量不符合无凭据交付条件，未打包。') from None
            recorded_hash = artifact.get('sha256')
            if recorded_hash is not None and recorded_hash != sha(raw):
                raise HTTPException(409, '成果内容已偏离本次构建记录，请核对原文件并重新构建；未打包或修补文件。')
            before = task_digest(task)
            report = bytes(h.report(item_id).body)
            check_text(report, REPORT_LIMIT)
            try:
                guide=integration_guide(task,native)
            except (ValueError,KeyError,TypeError,AttributeError,RecursionError):
                raise HTTPException(422,'模拟依赖绑定或节点契约不可读取，未打包，不猜测或回显内容。') from None
            extra=[]
            if guide:
                guide_raw=guide.encode();check_text(guide_raw,REPORT_LIMIT)
                extra.append(('integration-guide.md',guide_raw))
            if task_digest(h.get_task(item_id)) != before:
                raise HTTPException(409, '打包期间保存记录已变化，请重新核对当前进度后下载；未返回混合版本。')
            artifact_name = f'dify-{mode}-r{revision}.yaml'
            report_name = f'report-r{revision}.md'
            captured_at = h.now()
            manifest = {'schema_version': 1, 'task_id': task['id'], 'revision': revision,
                'app_type': mode, 'environment_id': task.get('environment_id'), 'app_id': task.get('dify_app_id'),
                'target_dify_version': TARGET_DIFY_VERSION, 'dsl_version': DSL_VERSION,
                'captured_at': captured_at, 'task_snapshot_sha256': before,
                'artifact_integrity_basis': 'recorded_build_sha256' if recorded_hash else 'legacy_export_bytes_only',
                'artifact_verification': artifact.get('verification'), 'platform_checked': False,
                'business_verified': False, 'network_requested': False, 'task_changed': False,
                'mock_dependencies': task.get('configuration', {}).get('mock_dependencies', []),
                'files': {name: {'sha256': sha(value), 'bytes': len(value)} for name, value in
                    ((artifact_name, raw), (report_name, report), *extra)}, 'note': NOTE}
            readme = (f'# Sierra 本机交付包 · r{revision}\n\n{NOTE}\n\n'
                'DSL、报告及有模拟声明时的integration-guide.md在同一后台锁定读取中打包；manifest.json记录各文件原始字节的SHA256与大小，'
                '清单自身不作签名或来源认证。解压后请先核对类型、版本、待办和验证边界。\n\n'
                '旧成果若没有构建摘要，仅记录导出当时字节；不能反推它从构建以来从未变化。'
                '新成果有构建摘要时内容不符会拒绝打包。报告可能含需求及样例等业务文字，分享前请自行核对。\n').encode()
            manifest['files']['README.md'] = {'sha256': sha(readme), 'bytes': len(readme)}
            manifest_raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            check_text(manifest_raw, REPORT_LIMIT)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, value in ((artifact_name, raw), (report_name, report), *extra, ('README.md', readme),
                        ('manifest.json', manifest_raw)):
                    archive.writestr(name, value)
        return Response(buffer.getvalue(), media_type='application/zip', headers={
            'Content-Disposition': f'attachment; filename="sierra-{mode}-r{revision}-delivery.zip"',
            'Cache-Control': 'no-store', 'X-Sierra-Revision': str(revision)})

    h.app.include_router(router)
