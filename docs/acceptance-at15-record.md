# Sierra AT-15 验收结论记录

日期：2026-10-21（Asia/Shanghai）。范围：BACKLOG 第 21 项「核对 AT-15『连续对话信息不完整』现状并补隔离检查」。需求基线：`docs/requirements-v1.0.md` AT-15「按规则追问，验证上下文行为」。

结论：**本项本地隔离检查通过；未进行真实 Dify 平台或最终业务验收。** 仅补测试及记录，不修改产品实现，不处理其他队列项。

## 现状核对

- `conversation.memory_configuration` 提供 Chatflow 显式历史开关与有限窗口，启用时将声明历史轮数加一以适配 Dify 当前轮占位；Workflow 不支持对话记忆。该配置本身不提供业务信息缺失识别或自动生成追问。
- `main.run_task` 对固定多轮样例执行结构校验；Agent／Chatflow 按各轮输入顺序调用，第一轮没有来源会话 ID，后续使用前轮实际返回 ID。Agent 还要求明确终态。Workflow 不接受多轮样例。
- `execute_conversation` 每轮派发前保存输入与来源检查点，返回后保存实际结果、输入／预期快照和规则检查。缺少非空回答、缺会话 ID、会话变化或调用异常时保留未知结果，不继续派发；自动规则失败停止后续轮次。未知运行禁止盲目重跑，已知结果的重新运行从新会话开始。
- `evaluate_conversation` 校对轮次、输入、预期、来源及实际会话一致性，再逐轮重新计算声明规则。`summarize_acceptance` 仅取当前修订／环境对应的最新样例运行，不直接相信原保存的 passed 标签；完整匹配且全轮完成才可通过。一条链只算一个样例。自动规则失败不能人工覆盖；人工规则仍需显式复核。
- 信息是否充分、如何按业务规则追问及补齐后是否正确使用历史，仍依赖实际应用提示词、记忆配置和模型行为。执行器负责按已声明输入和预期验证，不是通用信息补全引擎。

## 新增隔离检查

`backend/tests/test_conversation_cases.py` 新增 16 个用例：

1. 2 例分别对 Agent／Chatflow 执行三轮工单场景：初始请求缺编号时应询问编号，仅补编号后应询问手机号尾号，最后仅补尾号时应合并此前编号和尾号。每轮输入不重复提供先前信息，核对来源检查点及实际会话 ID；整条链运行两次，核对每次第一轮新建会话、两次使用不同返回 ID。重开临时 Store 后记录一致，汇总仍只算一个声明样例并提示完整业务覆盖待确认。
2. 2 例在第二轮成功返回但跳过必要追问、直接宣称工单完成时，核对规则失败、第三轮不派发、失败原文保留、汇总失败及人工强行通过被拒绝。
3. 6 例分别对两种应用在第二轮缺回答、缺会话 ID 或返回其他会话时，核对未知状态、第一轮保留、第二轮输入／来源／不完整结果检查点保留，第三轮不派发且重跑被阻止。
4. 6 例在已保存通过的三轮记录上，分别改变最终回答、来源会话、轮次编号、完成标记、运行修订和环境。核对重新判为失败／待复核／当前未跑，不沿用通过标签；读取不改写记录也不派发请求。这些直接修改是损坏／历史记录 fixture，不是产品编辑接口行为证明。

文件级 autouse fixture 阻断同步／异步真实 HTTP transport 和默认 `main.call_model`；现有流式超时检查继续使用 `httpx.MockTransport`。任务、凭据和成果文件仅在临时 Store／数据目录，应用 ID、会话 ID、回答与终态均为固定合成数据，**不是平台回执**。

沿用旧准备函数关闭新任务准入／流程复核策略，Chatflow 准备不设置真实业务提示词和启用记忆，不代表新任务端到端通过或 Dify 记忆实际生效。固定应答刻意模拟“按规则追问”和“不按规则追问”两种结果，只验证执行器与验收判定；不证明真实模型会自主追问、记住信息或查询工单。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_conversation_cases.py -q
```

首次运行退出码 `0`，完整输出（工具分段返回，进度行合并）：

```text
...........................................                              [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
43 passed, 1 warning in 14.66s
```

警告来自现有 FastAPI／Starlette TestClient 依赖，未修改 `.venv` 或依赖。只运行上述指定单文件验收，没有全量测试、项目重建、Docker 操作、真实 Dify 资源交互、付费模型调用或推送。

## 修订与未关闭边界

产品代码基线：`835edd9b783ad50d17e5cec332b52df489869d5a`。验收测试文件 SHA256：`3690dea8d6ba5cd7e7d13fd3a8f515d2624f272d06feaa6d24ecb57f1b944037`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，仅表示本次本地核对结论已有记录。

历史专项文档 `conversation-cases-contract.md` 记录过编号回忆技术验证，本次未重放，不能据此推定当前修订、三轮追问或真实客户场景通过。真实业务提示词／记忆配置、信息缺失与冲突的识别质量、长对话及多模型表现、前端操作体验和最终业务仍待验收。本次不代表 AT-15 最终业务通过，也不代表整个 136 项计划完成。
