# Sierra AT-09 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 17 项「核对 AT-09『模型简单聊天可用但工具能力不足』现状并补隔离检查」。基线：`docs/requirements-v1.0.md` 的 AT-09「标记能力不足，提供调整建议，不继续当全能模型使用」。

结论：**本项本地隔离检查通过；AT-09 完整业务能力尚未实现和验收。** 本次只补测试与记录，不修改产品实现，不执行其他队列项。

## 现状核对

- `backend/app/main.py` 创建模型配置时，text、tools、structured_output、vision 均为 untested。`/api/providers/{id}/test` 只更新 text，提示工具、结构化和图片能力须分别验证；`/test-json` 只更新 structured_output，成功仍提示工具、图片及复杂业务规划质量待验证。JSON 失败不等于工具能力失败。
- 已存的 tools=failed 不会因文本／JSON 成功而被覆盖。**当前没有通用工具能力探测来生成这个失败状态**；新增用例中的 failed 是直接写入临时 Store 的合成数据，仅证明状态隔离，不代表产品已经能自动诊断工具能力不足。
- 模型型号、供应商、基础地址、协议或密钥变化，配置修订增加，旧能力状态和 checks 被清除。新增检查验证顺序配置变更，不据此宣称并发中的旧探测回执也已绑定修订。
- `backend/app/providers.py` 适配文本调用；仅返回 OpenAI tool_calls 或 Anthropic tool_use、没有正文时明确报错，不执行工具，不自动重试，并保留可用用量。错误不回显工具参数；OpenAI finish_reason 可保留 tool_calls，Anthropic 当前未保留该结束原因。
- `backend/app/agent_plan.py` 只接受 text／knowledge 范围，拒绝自定义工具字段或 tools 范围。有效计划的提示说明自定义工具尚未配置、Dify 部署内建工具须另行核对。空工具列表不能证明运行时没有内建工具；静态计划有效不能证明模型实际能调用它们。
- 当前没有通用工具探测、自动标记能力不足和针对该诊断的调整建议，也未建立所有工具依赖执行路径的统一能力门禁。已有范围限制提示不能抵作这些能力已交付；不得把聊天连通或这次测试通过表述成“全能模型可用”。真实工具／插件场景仍是未关闭缺口。

## 新增隔离检查

`backend/tests/test_node_models.py` 新增 13 个用例：

1. 4 例组合 tools 为 untested／合成 failed、JSON 成功／失败。固定模型替身先返回文本成功，再返回 JSON 结果；检查公开提示、独立能力状态、临时 Store 重开持久化、密钥不回显及恰好两次调用。没有工具请求或真实付费调用。
2. 5 例分别改变型号、供应商、地址、协议、密钥，检查 configuration_revision 增加、旧能力及 checks 失效且持久化。
3. 2 例经 httpx.MockTransport 分别模拟 OpenAI 和 Anthropic 的仅工具响应，运行真实文本适配函数，检查明确拒绝、用量保留、参数不回显、没有重试或后续工具请求。
4. 2 例经进程内 API 保存有效文本 Agent 计划，再提交工具范围／自定义工具字段，检查具体错误、GET 前后完整任务一致、原计划持久保留、应用类型仍为用户选择的 Agent，没有替换为 Workflow 或生成成果／运行。

文件级自动 fixture 阻断真实同步／异步 HTTP 及默认 main.call_model；只有指定用例安装固定模型替身或 MockTransport。API 沿用临时 Store 的 TestClient fixture；旧 create 辅助函数关闭新任务准入／流程复核门禁，本项不据此宣称全新任务端到端验收。合成密钥和用量仅用于测试，不代表真实凭据或账单。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_node_models.py -q
```

最终执行退出码 `0`，完整输出：

```text
..........................................                               [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
42 passed, 1 warning in 2.10s
```

首次执行为 `2 failed, 40 passed, 1 warning in 2.27s`：两例将计划保存接口附带的 plan_text 与普通任务 GET 返回直接比较。修正测试为同一 GET 接口拒绝前后的完整状态比较，再运行同一指定命令通过；未修改产品行为。唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未修改依赖。

## 修订与未关闭边界

产品代码基线：`7efc3a2b112d85f3068a754e6ba0071d3208c9c6`。验收时 `backend/tests/test_node_models.py` SHA256：`ac3ae2575a5cd7a6edd2a140621e27b8c86fd88d5ccf6d7fdf52b30d40ab3bb1`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 final_acceptance_record，表示此次本地验收结论，不表示 AT-09 最终业务通过。

真实工具能力、针对性调整建议、统一执行门禁、并发探测修订隔离、实际 Agent 内建工具运行、前端体验及客户业务验收仍待验证或实现。没有真实 Dify／付费模型调用、部署、全量测试、重建、Docker、修改 `.venv`／`.gitignore`／仓库设置、删除目录或推送，不代表 136 项计划完成。
