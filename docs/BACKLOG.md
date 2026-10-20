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
| 3 | 核对 AT-12「DSL 变量引用错误」现状并补隔离检查 | `backend/tests/` 相关全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit c24453c |
| 4 | 核对 AT-14「批量任务部分失败」现状并补隔离检查 | 同上 | codex | done | commit 81958d9 |
| 5 | 核对 AT-24「用户恢复旧版本」现状并补隔离检查 | `.venv\Scripts\python.exe -m pytest backend/tests/test_version_restore.py backend/tests/test_version_node_changes.py backend/tests/test_runtime_snapshot.py -q` 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit cc7054e |
| 6 | 整理 `development-tasks.md` 状态列：136 项逐项标真实状态 | `.venv\Scripts\python.exe tools/check_development_task_status.py`；表内每行有状态，且不凭猜测填 | codex | done | commit d8da2f7 |
| 7 | 专用 Dify 环境登录 | 用户登录后 `/api/health` 与专用连接可用 | need-user | blocked | `connection-stage-receipt.json`：credentials_copied=false |
| 8 | 整批真实联调（已获批，限 14 次调用） | 有命中/无命中各一次真实运行回执 | codex | blocked | 等第 7 项 |

| 9 | 核对 AT-01「用户只给模糊目标」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_intake.py backend/tests/test_planning_capability_context.py backend/tests/test_planning_decisions.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 0594e1a |
| 10 | 核对 AT-02「用户不知道分类规则」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_intake.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 5cd1668 |
| 11 | 核对 AT-03「文档与参考 DSL 冲突」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_conflicts.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 262bc54 |
| 12 | 核对 AT-04「参考程度未明确」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_reference_dsl.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 27a6307 |
| 13 | 核对 AT-05「用户所选类型不适合需求」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_capabilities.py backend/tests/test_planning_capability_context.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 1acdf25 |
| 14 | 核对 AT-06「只有原始知识资料」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_knowledge.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 5d97fb8 |
| 15 | 核对 AT-07「多个知识库可选」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_configuration_proposals.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit ac2e9b0 |
| 16 | 核对 AT-08「资料业务事实矛盾」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_conflicts.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit dc1af40 |
| 17 | 核对 AT-09「模型简单聊天可用但工具能力不足」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_node_models.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 5b9167c |
| 18 | 核对 AT-10「接口未提供且用户接受模拟」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit c69350e |
| 19 | 核对 AT-11「未确认配置或资源操作」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 9de6002 |
| 20 | 核对 AT-13「已导入但关键样例失败」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_repair_verification.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 42417d3 |
| 21 | 核对 AT-15「连续对话信息不完整」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_conversation_cases.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 70cc6c4 |
| 22 | 核对 AT-16「自动触发或人工审核能力不足」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_human_runtime_execution.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |
| 23 | 核对 AT-17「切换到客户环境」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_conversation_source_read.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |
| 24 | 核对 AT-18「用户在 Dify 手动修改后继续」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_dsl_roundtrip.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |
| 25 | 核对 AT-19「修改配置或需求」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |
| 26 | 核对 AT-20「执行中暂停并关闭程序」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_task_budget.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |
| 27 | 核对 AT-21「同一错误反复无进展或到达上限」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_execution_limits.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |
| 28 | 核对 AT-22「Dify 断开」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |
| 29 | 核对 AT-23「需求需要新建外部系统」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_intake.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |
| 30 | 核对 AT-25「启用轻量模型分工」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_assistant_routing.py backend/tests/test_assistant_usage_groups.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | pending | — |

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
