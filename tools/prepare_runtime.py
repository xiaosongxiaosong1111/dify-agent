"""Create a content-addressed local runtime; never copy task data or credentials."""
import argparse,hashlib,json,re
from pathlib import Path

CONTRACTS=('agent-plan-contract.md','workflow-plan-contract.md','intake-model-contract.md','case-model-contract.md','configuration-model-contract.md','coverage-contract.md','conflict-contract.md')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def prepare(project):
    project=Path(project).resolve();destination=project/'.runtime'/'snapshots'
    if destination.resolve()!=destination:raise ValueError('运行快照目录不能指向其他位置。')
    files=[]
    for area in ('backend/app','frontend/dist'):
        root=project/area
        if not root.is_dir():raise ValueError('当前代码或前端构建缺失，不能创建运行快照。')
        for file in sorted(root.rglob('*')):
            if not file.is_file() or '__pycache__' in file.parts:continue
            if file.name.startswith('.'):continue
            if area=='backend/app' and file.suffix not in {'.py','.json'}:continue
            if not file.resolve().is_relative_to(root.resolve()) or not file.resolve().is_relative_to(project):raise ValueError('运行文件指向项目外，不能复制。')
            files.append((file,file.relative_to(project).as_posix(),file.read_bytes()))
    for name in CONTRACTS:
        file=project/'docs'/name
        if not file.is_file() or not file.resolve().is_relative_to(project/'docs'):raise ValueError('模型契约缺失或指向项目外，不能创建运行快照。')
        files.append((file,file.relative_to(project).as_posix(),file.read_bytes()))
    index={name:sha(raw) for _,name,raw in files}
    if 'frontend/dist/index.html' not in index or 'backend/app/main.py' not in index:raise ValueError('完整入口缺失，不能启动。')
    source=next(raw.decode('utf-8') for _,name,raw in files if name=='backend/app/main.py')
    match=re.search(r'version=["\']([0-9]+\.[0-9]+\.[0-9]+)["\']',source)
    if not match:raise ValueError('后端版本不明确，不能创建运行快照。')
    digest=sha(json.dumps(index,sort_keys=True,separators=(',',':')).encode());build_id=match[1]+'-'+digest[:20]
    runtime=destination/build_id
    manifest={'schema_version':1,'version':match[1],'build_id':build_id,'content_sha256':digest,'files':index,'shared_data_copied':False}
    manifest_path=runtime/'runtime-manifest.json'
    if runtime.exists():
        if not manifest_path.is_file() or json.loads(manifest_path.read_text(encoding='utf-8'))!=manifest:raise ValueError('已有快照不完整或身份不一致，不覆盖／复用，请检查后处理。')
        for _,name,raw in files:
            target=runtime/name
            if not target.is_file() or sha(target.read_bytes())!=index[name]:raise ValueError('已有快照文件变化，不覆盖／启动，请检查后处理。')
    else:
        runtime.mkdir(parents=True)
        for _,name,raw in files:
            target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    return {'runtime_root':str(runtime),'backend_path':str(runtime/'backend'),'data_path':str(project/'data'),'version':match[1],'build_id':build_id,'content_sha256':digest,'file_count':len(index)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project-root',required=True);args=parser.parse_args()
    try:print(json.dumps(prepare(args.project_root),ensure_ascii=False))
    except (ValueError,OSError) as exc:raise SystemExit('运行快照准备失败：'+str(exc))
