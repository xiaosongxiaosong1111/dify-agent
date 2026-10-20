# Sierra AT-05 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 13 项「核对 AT-05『用户所选类型不适合需求』现状并补隔离检查」。基线：`docs/requirements-v1.0.md` 的 AT-05「说明原因与方案，等待决定，不自动换类型」。

结论：**本项本地隔离检查通过；真实模型的类型适用性判断、自然语言协商及 Dify 业务验收仍待完成。** 本次只修改测试和记录，没有修改产品实现或部署；不继续其他队列项。

## 现状核对

- `backend/app/capabilities.py` 按 Workflow／Chatflow／原生 Agent 分开返回当前 Sierra 编译能力。未知类型返回明确限制，不默认当 Workflow；说明用户类型不自动改变，缺条件或超范围须先讨论替代方案、费用与人工工作。能力目录不是目标资源可用或已运行的证明。
- `backend/app/main.py` 的规划上下文同时传入用户所选类型与对应能力目录；系统提示要求不擅自换类型、不删需求来冒充完成，澄清须给具体条件／能力差异，可含建议、理由、体验、费用和人工工作。保存计划按当前任务类型选用确定性校验器，跨类型计划拒绝；普通任务 PATCH 不接受 `app_type` 改写。
- 模型返回 `error`／`needs_decision` 后，规划暂停并保留输入修订、单次固定用量及 `model_clarification_only` 报告，不当作计划采纳或用户确认。HTTP 422 的详情是通用暂停提示，具体原因和方案在规划记录的 `decision_report` 中，不直接用模型原文作 HTTP 详情。
- `frontend/src/PlanningDecision.tsx` 展示原因、问题、建议与各项影响，提示尚未核实；历史修订不能放入讨论框，当前修订也只填入未发送的只读讨论输入，须用户修改需求／配置后主动规划。此次只核对该组件源代码，没有运行前端验收。

## 新增隔离检查

指定两个文件共新增 12 例：

1. 三种所选类型分别尝试 PATCH 成另两种合法类型，均 422；完整任务和预算不变。
2. 六种所选类型与外来计划的组合均拒绝，核对具体中文字段／终点／范围限制，完整原任务、已存计划与预算不变。
3. 三种类型分别模拟 Workflow 需要持久对话状态、Chatflow 需要定时触发、Agent 需要自定义工具与人工审核。核对原始需求和所选类型进入正确上下文，固定响应含具体原因、保留类型的人工方案和另选类型新建任务的选项；单次调用后暂停，完整澄清字段与输入修订持久化，重开临时 Store 后一致。类型、需求、配置、原计划、确认、版本、成果及运行不被自动改写，读取不追加调用或预算；用户明确修改需求后修订增加、确认失效，旧修订再规划 409，不追加调用。

修正 `test_planning_capability_context.py` 引用的旧 fixture 名 `forbid_at01_external_calls` 为当前实际存在的 `forbid_intake_external_calls`，并在能力测试文件引入同一自动 fixture。两个指定文件均阻断真实同步／异步 HTTP 传输及默认 `main.call_model`，需要模型的测试显式安装固定响应。使用临时 Store 和进程内 TestClient，不接触真实任务、Dify 或付费模型。

测试准备沿用 `approved`／Agent `prepare` 的既有隔离 fixture，关闭新任务准入／流程复核门禁以单独检查类型与规划暂停行为；不能据此推定新任务完整门禁或业务已端到端通过。保存的旧计划是固定技术计划，不表示它能满足新增不适用需求。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_capabilities.py backend/tests/test_planning_capability_context.py -q
```

首轮退出码 1，`3 failed, 16 passed, 1 warning in 4.17s`：新增三例错误地断言 HTTP 详情等于模型原文；实际返回通用暂停提示。修正测试断言，保留对持久澄清报告中具体原因和方案的完整核对，没有修改产品行为。随后同一指定命令退出码 0，真实完整输出：

```text
...................                                                      [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
19 passed, 1 warning in 4.27s
```

唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未修改依赖。

## 修订与未关闭边界

产品代码基线：`1cf858845dade116b339b50eb0652b4e4b4a2763`。验收时测试 SHA256：

| 文件 | SHA256 |
|---|---|
| `backend/tests/test_capabilities.py` | `fdebc59f7e00d4337e4abc880e1204e56a982b73cb1a8e34c454a9c9d723b7af` |
| `backend/tests/test_planning_capability_context.py` | `7c89b929e87c0e0bfd3a4b3a7c3439f943c127265b82a012afeb6460f080019c` |

相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，只记录此次本地结论。

不适用需求的识别和方案内容仍依赖模型，固定响应只证明收到这类响应时能记录并等待决定；它不证明任意自然语言不适用需求都会被识别，也不证明另一个格式合法的计划必然符合业务。真实模型协商质量、前端完整体验、另选类型后的新建任务交互、真实 Dify 导入／试跑及最终客户业务验收未完成；不代表 AT-05 真实业务通过或 136 项计划完成。

未运行全量测试、重建、Docker、真实资源操作；未修改 `.venv`／`.gitignore`／仓库设置，未删除目录或推送。队列仅更新第 13 项。
