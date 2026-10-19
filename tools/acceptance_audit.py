"""Check the 25-scenario mapping and generate a report; never run or accept tests."""
import argparse,ast,hashlib,json,re,sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]


def local_file(value):
    if not isinstance(value,str) or Path(value).is_absolute():raise ValueError('引用须为项目内相对文件。')
    path=(ROOT/value).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():raise ValueError('引用文件缺失或超出项目范围。')
    return path


def load(manifest_path):
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest,dict):raise ValueError('映射须为对象。')
    if manifest.get('schema_version')!=1:raise ValueError('映射版本未适配。')
    baseline=local_file(manifest.get('baseline'))
    if hashlib.sha256(baseline.read_bytes()).hexdigest()!=manifest.get('baseline_sha256'):raise ValueError('需求基线已变化，须先人工复核映射，不自动沿用旧结论。')
    rows={}
    for line in baseline.read_text(encoding='utf-8').splitlines():
        match=re.match(r'^\| (AT-\d{2}) \| ([^|]+) \| ([^|]+) \|$',line)
        if match:
            if match[1] in rows:raise ValueError('基线验收ID重复。')
            rows[match[1]]=(match[2].strip(),match[3].strip())
    expected={f'AT-{n:02}' for n in range(1,26)}
    items=manifest.get('items')
    if set(rows)!=expected or not isinstance(items,list) or len(items)!=25 or {item.get('id') for item in items if isinstance(item,dict)}!=expected:raise ValueError('验收映射必须完整且唯一覆盖AT-01至AT-25。')
    for item in items:
        if (item.get('scenario'),item.get('expected'))!=rows[item['id']]:raise ValueError('验收文字与基线不一致，须人工复核。')
        for field in ('source','related_checks'):
            if not isinstance(item.get(field),list) or not item[field]:raise ValueError('每项须有明确实现及相关检查引用；引用不代表通过。')
            for ref in item[field]:local_file(ref)
        if not isinstance(item.get('known_gap'),str) or not item['known_gap'].strip():raise ValueError('每项须记录已知缺口或待验收条件，不能静默省略。')
        if item.get('final_acceptance_record') is not None:local_file(item['final_acceptance_record'])
    return manifest


def source_version():
    tree=ast.parse((ROOT/'backend/app/main.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='FastAPI':
            for kw in node.keywords:
                if kw.arg=='version' and isinstance(kw.value,ast.Constant) and isinstance(kw.value.value,str):return kw.value.value
    return '未识别'


def runtime():
    try:
        with urlopen('http://127.0.0.1:8765/api/runtime',timeout=3) as response:value=json.load(response)
        if not isinstance(value,dict):raise ValueError()
        if value.get('mode')!='snapshot' or not isinstance(value.get('version'),str) or not isinstance(value.get('build_id'),str):raise ValueError()
        if not re.fullmatch(r'[0-9.]+',value['version']) or not re.fullmatch(r'[0-9a-f.\-]+',value['build_id']):raise ValueError()
        return f"{value['version']}（{value['build_id']}）"
    except (OSError,ValueError,KeyError):return '未核对：本机服务不可读取或版本格式未适配'


def cell(value):return value.replace('|','\\|').replace('\n',' ')


def links(values):
    return '<br/>'.join(f'[{Path(value).name}](<{local_file(value).as_posix()}>)' for value in values)


def report(manifest,read_runtime):
    records=sum(item.get('final_acceptance_record') is not None for item in manifest['items'])
    lines=['# Sierra 项目验收映射审计','',f"生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}。源码版本：{source_version()}。",f"本机运行版本：{runtime() if read_runtime else '未读取（可显式加--runtime核对）'}。",f"目标：Dify {manifest['target_dify_version']}／DSL {manifest['target_dsl_version']}。",'',
           '本工具只核对需求基线、25项完整性及引用文件存在，不执行测试、不读取凭据、不判定代码正确或平台／客户验收通过。源码与运行版本可能不同。',
           f'映射25项，最终验收结论文件已登记{records}项；登记不代表本工具复核结论。未验收不等于没有开发，也不能用引用数量换算项目完成百分比。原136任务仍以具体成果与验收记录逐项核对。',
           f"需求基线SHA256：`{manifest['baseline_sha256']}`。",'',
           '| ID及原场景 | 原预期行为 | 实现入口 | 相关检查（不等于已运行） | 已知缺口／待验收条件 | 最终结论 |',
           '| --- | --- | --- | --- | --- | --- |']
    for item in sorted(manifest['items'],key=lambda row:row['id']):
        record=item.get('final_acceptance_record')
        conclusion=links([record])+'（只登记，需人工复核）' if record else '待最终验收，无结论记录'
        lines.append('| '+' | '.join([item['id']+' '+cell(item['scenario']),cell(item['expected']),links(item['source']),links(item['related_checks']),cell(item['known_gap']),conclusion])+' |')
    lines+=['','优先保留的整体缺口：真实复杂需求与语义质量、失败继续与嵌套、通用手改往返、触发／人审复杂环境、跨目标复现、受控多模型质量与成本对比及新电脑最终交付。专项隔离通过和技术样例运行不能替代这些验收。','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description='只读核对验收映射，不执行模型、Dify或测试。')
    parser.add_argument('--manifest',default='docs/acceptance-mapping.json');parser.add_argument('--runtime',action='store_true')
    args=parser.parse_args()
    try:
        manifest=load(local_file(args.manifest));text=report(manifest,args.runtime)
        target=ROOT/'work'/('acceptance-audit-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.md')
        if not target.parent.is_dir():raise ValueError('项目work目录不存在。')
        with target.open('x',encoding='utf-8') as handle:handle.write(text)
        print(json.dumps({'report':str(target),'scenarios':25,'final_records':sum(i.get('final_acceptance_record') is not None for i in manifest['items']),'tests_executed':False,'business_verified':False},ensure_ascii=False));return 0
    except (OSError,ValueError,TypeError,KeyError):print('验收映射核对失败：基线、引用、版本或条目结构不完整；未生成验收结论。',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
