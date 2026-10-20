# Sierra AT-13 验收结论记录

日期：2026-10-21（Asia/Shanghai）。范围：BACKLOG 第 20 项「核对 AT-13『已导入但关键样例失败』现状并补隔离检查」。需求基线：`docs/requirements-v1.0.md` AT-13「标为需修复或阶段成果，不宣称完成」。

结论：**本项本地隔离检查通过；未进行真实 Dify 平台或最终业务验收。** 仅补测试及记录，不修改产品实现，不处理其他队列项。

## 现状核对

- `acceptance.summarize_acceptance` 将必选样例失败计入 `required.failed`，`all_required_passed=false`；仅有导入成功不能让样例通过。汇总带 `declared_checks_only` 及完整业务覆盖仍需人工确认的提示。
- `main.report` 分开列出导入记录、成功返回次数和必选样例通过数量，并保留业务验收待办。已有导入记录但关键样例失败时，报告显示 `0 / 1` 通过及完整业务覆盖仍需确认。任务总状态仍可能为 `imported`；当前没有统一改为“需修复”的总状态，失败在样例汇总及修复跟进中表达，本次保留这一缺口。
- `RepairVerification.summarize` 从保存的当前修订／环境绑定／应用 ID 运行中重新计算规则，不直接相信保存的 passed 标签。原失败仍在则为 `failed`；原错误已消除但其他样例失败、未跑或待人工复核则为 `needs_cases`；未结束或未知运行则为 `unknown`。最新失败不能继承早先通过。
- 全部现有样例通过且修复节点有匹配轨迹时，`verified` 也只表示修复跟进及已声明检查，仍需完整业务验收；有模拟依赖则为 `mock_only`，中文提示仅作阶段性成果。该接口读取和输入准备均不派发重跑。
- `RuntimeRepair` 自动小修复限于当前显式 Workflow／Chatflow 计划中的特定 `math`／`re` 缺失导入 NameError，要求明确失败与完整来源证据；成功返回但业务预期不匹配须人工核对，不是通用业务自动修复。原生 Agent、DSL 保留方案等另有明确限制。

## 新增隔离检查

`backend/tests/test_repair_verification.py` 新增 11 个用例：

1. 6 例在原失败样例及修复节点已经成功后，分别保留另一必选关键分支的未跑、运行失败、输出不符、人工待审、未完成和未知结果；核对具体状态、原错误已消除与整体不能通过的区别，并重开临时 Store，核对结果持久一致、任务及修复记录不被读取操作改写。
2. 2 例核对全部保存检查通过时，普通结果仅为有限范围的 `verified`，模拟结果为 `mock_only`；原失败记录保留，不提升为完整业务验收。
3. 2 例核对已有 verified 后最新运行失败或成功返回但输出错误，覆盖早先通过；即使保存的 evaluation 标记为 passed 或附有节点成功轨迹，也不得清除失败。
4. 1 例直接核对合成导入成功记录与关键样例失败并存时，公开 acceptance 接口和报告显示失败与验收边界，任务不被读取操作改写。

文件级 autouse fixture 阻断真实同步／异步 HTTP transport 及默认 `main.call_model`。所有任务、凭据和成果文件仅位于临时 Store／数据目录；导入 ID、运行返回和轨迹均为人工合成 fixture，**不是平台回执**。沿用旧测试准备函数关闭新任务准入／流程复核策略，隔离修复验证逻辑；不代表新任务端到端通过。新增样例及模拟声明在生成修复候选前设置，由正常采纳逻辑冻结验证契约，没有人为重写契约来绕过失效检查。

报告目前会将符合本地字段的导入记录描述为“真实导入记录”；上述合成记录仅测试该分支的文字和计数，不证明记录来源真实性。真实平台来源核验仍待验收。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_repair_verification.py -q
```

首次运行退出码 `0`，完整输出（工具分段返回，进度行合并）：

```text
.......................................                                  [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
39 passed, 1 warning in 25.49s
```

警告来自现有 FastAPI／Starlette TestClient 依赖，未修改 `.venv` 或依赖。只运行上述指定单文件验收，没有全量测试、项目重建、部署、Docker 操作、真实资源交互、付费模型调用或推送。

## 修订与未关闭边界

产品代码基线：`c91c0d8a36cbf64900be3420bb80bbc91b62f98a`。验收测试文件 SHA256：`2579378ca9040a9706ecdfa1a5dae47d55ffbed41ea1c42e08e30d7d3ecbdffa`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，仅表示本次本地核对结论已有记录。

统一需修复总状态、真实导入及轨迹来源、任意业务预期失败的修复能力、全部关键业务样例覆盖、前端操作体验及最终交付仍待验收。本次不代表 AT-13 最终业务通过，也不代表整个 136 项计划完成。
