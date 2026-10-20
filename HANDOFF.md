# HANDOFF — Sierra（2026-10-20）

## 1. 现状

- 项目：`E:\workSpace\dify-agent`（Sierra，FastAPI + Vue，目标 Dify 1.17.1）。本轮已确认在项目根目录执行。
- 验收基线：`f85a8bf`；本轮仅提交此交接文件，未修改产品源码、检查脚本或仓库设置。最新提交号以 `git log -1` 为准。
- 已执行 `powershell -ExecutionPolicy Bypass -File .\start.ps1`，并独立确认 `http://127.0.0.1:8765/api/health` 返回 200。
- 验收前后端已有 12 个任务，本轮未新建任务；后端保留运行。检查使用 `frontend/dist`，未另起 18760 服务。

## 2. 不可动前提

- 目标 Dify 固定 **1.17.1**，查 tagged source，不看 main。
- 用户选的 app type **不得静默更改**；不支持的功能返回精确限制。
- 静态 YAML 校验 **不等于** 真实 import/run，UI、API、下载三处都要标注。
- 真实外部写入前必须有具体的已批准资源方案；**不得静默覆盖**已有 Dify 应用。
- API key 不得进浏览器存储、日志、导出 DSL、Git。
- 产品 UI 与用户可见错误一律中文。

## 3. 下一步（本轮已验收）

**`work/workflow-progress-235.cjs` 已一次跑绿，退出码 0，14 项检查全部通过。此项无待修错误；下一轮等待用户指定新的单项验收目标，不重复执行本轮检查或自行扩大范围。**

本轮实际执行命令：

```powershell
cd E:\workSpace\dify-agent
powershell -ExecutionPolicy Bypass -File .\start.ps1
# 独立确认 /api/health 返回 200，且 /api/tasks 非空后执行：
node work\workflow-progress-235.cjs "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
```

- 结果：`work/workflow-progress-235-source.json`，`checks = 14`，`fake_progress_writes = 2`，`actual_writes = 0`，`external_requests = 0`，`original_task_unchanged = true`，`static_source = true`。
- 覆盖输入保护、明确恢复、历史只读、保存回执丢失后的只读核对、外国任务回执拒绝等行为；实际任务快照在检查前后相同。
- 结果中的“实际11任务”是脚本固定文案；本轮接口实查已有 12 个任务，检查仅比对其选中任务的前后快照，不代表逐一核对所有任务或真实 Dify import/run。
- 未修改源码、未重新 build、未重跑全量测试；结果文件在被忽略的 `work/` 中，本次验收摘要保存在此文件。

## 4. 证据指针（需要时再读，不要预先通读）

| 用途 | 路径 |
|---|---|
| 本轮定向检查 | `work/workflow-progress-235.cjs` |
| 本轮通过结果（本机文件） | `work/workflow-progress-235-source.json` |
| 对应界面实现 | `frontend/src/WorkflowMappingProgress.tsx` |
| 交付优先级与下一阶段目标 | `docs/core-delivery-focus.md` |
| 历史检查点（290KB，只按编号 grep 单段） | `work/development-resume.md` |
| 最近基线测试输出（本轮未重跑） | `work/backend-240-full.txt` |

## 5. 已知坑

- 后端必须用 `.venv\Scripts\python.exe`；全局 python 缺 `typing_extensions`。
- 本机没有全局 playwright，检查脚本必须传上述绝对模块路径。
- 检查脚本自行从 `frontend/dist` 提供静态文件，不需要另起 18760；需要真实后端至少一个任务。
- 本机没有 sh，不要用 bash 语法或 `&&`。
- 本轮 Git 遇到 ownership 检查，使用单次命令参数 `git -c safe.directory=E:/workSpace/dify-agent ...`；未改全局或仓库设置。

## 6. 边界

- 只修指定检查暴露的实质错误，不顺带重构、不重建项目、不重跑全量测试。
- 撞额度立即停，将当前进度写入本文件后报告；不重试、不换账号。
- 一次会话只交付一件可验收产物；完成后 commit 并整份重写本文件，不追加历史。
