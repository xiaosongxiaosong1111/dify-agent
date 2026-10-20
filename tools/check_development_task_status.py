"""只读核对 136 项任务状态及证据引用；不执行产品测试或外部请求。"""

from collections import Counter
import hashlib
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "docs/development-tasks.md"
STATES = ("未开始", "进行中", "等待输入", "等待验证", "已完成", "受阻")
# 整理前 136 行的五列原文，防止通过更改交付物、验收条件或前置缩减范围。
BASELINE_SHA256 = "403033ac1672e21be4c94ed1333add6b5e65d0f4c3053fc86c3a44c82bc688cc"


def check():
    rows = []
    originals = []
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\|\s*T\d{3}\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            raise ValueError(f"{cells[0]}：应有原五列、状态、证据与未关闭条件共七列")
        task_id, _, _, _, _, state, evidence = cells
        if state not in STATES:
            raise ValueError(f"{task_id}：状态缺失或不合法")
        if not evidence or (state != "已完成" and "缺：" not in evidence):
            raise ValueError(f"{task_id}：缺少证据或未关闭条件")
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", evidence)
        if not links:
            raise ValueError(f"{task_id}：缺少可回查的本地证据引用")
        for link in links:
            filename, _, anchor = link.partition("#")
            source = (TABLE.parent / filename).resolve()
            if not source.is_relative_to(ROOT) or not source.is_file() or source == TABLE:
                raise ValueError(f"{task_id}：证据缺失、越界或自引用：{link}")
            if anchor:
                headings = re.findall(r"^#+\s+(.+)$", source.read_text(encoding="utf-8"), re.M)
                if anchor not in headings:
                    raise ValueError(f"{task_id}：证据标题不存在：{link}")
        rows.append((task_id, state))
        originals.append("| " + " | ".join(cells[:5]) + " |")
    if [row[0] for row in rows] != [f"T{number:03}" for number in range(1, 137)]:
        raise ValueError("任务必须为 T001—T136 各一次且保持原顺序")
    baseline = ("\n".join(originals) + "\n").encode("utf-8")
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA256:
        raise ValueError("原任务五列内容已变化，须人工复核，不能沿用本次基线")
    print("PASS：T001—T136 共 136 行，状态完整、无重复或遗漏。")
    print("PASS：136 行均有本地证据引用及未关闭条件，引用文件和标题有效。")
    print("PASS：原任务、交付物、验收条件及前置五列保持不变。")
    counts = Counter(state for _, state in rows)
    print("状态统计：" + "，".join(f"{state} {counts[state]}" for state in STATES) + "。")
    print("边界：命令检查表结构与引用；状态语义依据逐项人工核对，不代表产品验收通过。")


if __name__ == "__main__":
    try:
        check()
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"FAIL：{exc}", file=sys.stderr)
        sys.exit(1)
