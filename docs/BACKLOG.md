# BACKLOG — 可执行队列（2026-10-20 建立）

本文件是自动循环的**唯一待办来源**。每完成一项就改状态并写证据；不要用 `development-tasks.md` 的编号顺序代替本队列。

## 状态取值

`pending` 待做 ｜ `doing` 在做 ｜ `done` 已完成 ｜ `blocked` 受阻（必须写原因）｜ `need-user` 需用户操作

## 规则

- 一次只做**一项**，从第一个非 `done`/非 `need-user` 的 `pending` 开始。
- 每项必须有**本机可验证的验收命令**。验收不过不许标 `done`。
- 标 `done` 必须同时满足：验收命令通过 + `git commit` + 本表状态已改。
- 连续 2 项被判 `blocked` 就停止循环并报告，不要硬试。
- 不动 `live-state.json` 的 `initial_review_requests_used`；不重播初始访谈。
- 与 Dify 真实交互（导入/试跑/建库/建应用）一律单独门禁，不在本队列自动执行。

## 队列

| # | 任务 | 验收命令 | 执行者 | 状态 | 证据 |
|---|---|---|---|---|---|
| 1 | 为访谈契约失败补一个能复现的隔离回归：多余话题、无效素材ID、带未答问题就完成检查 | `.venv\Scripts\python.exe -m pytest backend/tests/test_intake.py -q` 新增用例通过，且该用例在断言被还原时必须失败 | codex | done | commit 9a8d781 |
| 2 | 用 claude 核对 `test_planning_decisions.py` 里是否已有等价断言，列出缺口 | 输出缺口清单到 `work/intake-gap-notes.md`；不改产品代码 | claude | done | commit 2ec4b98 |
| 3 | 核对 AT-12「DSL 变量引用错误」现状并补隔离检查 | `backend/tests/` 相关全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | 112 passed，1 warning，16.50s；[命令及结论记录](acceptance-at12-record.md)，随本项中文提交归档；仅本地隔离验收通过，真实平台/业务待验收 |
| 4 | 核对 AT-14「批量任务部分失败」现状并补隔离检查 | 同上 | codex | pending | — |
| 5 | 核对 AT-24「用户恢复旧版本」现状并补隔离检查 | 同上 | codex | pending | — |
| 6 | 整理 `development-tasks.md` 状态列：136 项逐项标真实状态 | 表内每行有状态，且不凭猜测填 | codex | pending | — |
| 7 | 专用 Dify 环境登录 | 用户登录后 `/api/health` 与专用连接可用 | need-user | blocked | `connection-stage-receipt.json`：credentials_copied=false |
| 8 | 整批真实联调（已获批，限 14 次调用） | 有命中/无命中各一次真实运行回执 | codex | blocked | 等第 7 项 |

## 已完成（本轮之前）

| 事项 | 证据 |
|---|---|
| workflow-progress-235 界面检查 14 项 | `work/workflow-progress-235-source.json`，2026-10-20 20:40 |
| 后端启动与健康 | `/api/health` 200，dify 1.17.1 |

## 禁止事项

- 不重跑全量测试（4861 项，600+ 秒）除非该任务明确要求
- 不重建项目、不改仓库设置、不改 `.gitignore`
- 不猜 136 项完成度；不确定就写 `blocked` 并说明缺什么证据
- 撞额度立即停，把进度写进本文件
