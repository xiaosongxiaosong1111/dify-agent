# Sierra AT-01 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 9 项「核对 AT-01『用户只给模糊目标』现状并补隔离检查」。需求基线：追问目标、输入输出和规则；不提前搭建。

结论：**本项本地隔离检查通过；AT-01 真实模型及最终业务验收仍未完成。** 本次仅补测试和记录，未修改产品代码或部署。

## 现状及本次补充

- `intake.topics/base_gaps/summary` 提供按应用类型生成的标准、空白／待确认字段缺口与优先追问；模型检查通过来源校验后保存为准入记录，`needs_input` 会阻止需求确认。人工逐项复核与需求确认是独立操作，需求／来源变化会使旧检查失效。
- 现有测试已覆盖空白任务、非空字段不等于已复核、来源和响应契约、人工复核及过期检查；规划上下文用例按三种类型核对当前能力目录，规划决定用例检查追问持久化、不重试、不覆盖已有方案。但规划旧 fixture 关闭了新任务准入要求，缺少新任务的模糊目标连续检查。
- `test_intake.py` 新增 3 例：通过真实新任务 API 分别选择 Workflow、Chatflow、Agent，仅填写模糊目标；两轮固定模型响应先追问目标／输入／输出，再追问规则。逐轮从 API 读回追问与全部缺口，验证准入已检查但不能确认、需求和配置确认拒绝、八项不齐时自动规划拒绝、构建拒绝及无成果下载；拒绝操作不修改任务或费用账本，无计划、成果、Dify 应用绑定或运行，无自动重试。两轮只记录两笔固定模型替身的测试用量。
- `test_intake.py` 另增 4 例：八项字段均非空时，分别将目标／输入／输出／规则标为需补充，验证来源检查有效但需求确认仍拒绝，原需求和修订不变。此处验证程序执行固定语义判断结果，不证明真实模型能正确判断模糊程度。
- `test_planning_decisions.py` 新增 3 例：新任务完成人工准入复核后，三种类型的固定规划响应返回目标／输入输出／规则追问，保存为同修订的 `paused/needs_decision` 和 `model_clarification_only`；只有一次替身调用，无候选采纳，需求、配置、确认、计划、成果、运行、历史版本及应用类型不变，构建与下载拒绝，拒绝操作不新增费用。Agent 沿用独立计划规则；Workflow/Chatflow 沿用显式流程复核规则。
- 三个指定测试文件启用隔离 fixture，禁止真实同步／异步 HTTP 传输和默认 `main.call_model`；需要响应的用例仅使用显式替身。沿用临时 Store 和进程内 TestClient，不接触本地真实任务、Dify 资源或真实付费模型。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_intake.py backend/tests/test_planning_capability_context.py backend/tests/test_planning_decisions.py -q
```

最终退出码：`0`。同一执行的分段输出合并如下：

```text
.................................................................        [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
65 passed, 1 warning in 11.56s
```

首次运行：`1 failed, 64 passed, 1 warning in 12.05s`。失败是新增测试错误地要求 Agent 启用 Workflow/Chatflow 的 `plan_review_required`，修正为按用户选择的应用类型核对后重跑上述命令全绿。没有改产品实现或依赖。唯一警告来自现有 FastAPI／Starlette TestClient 依赖。未跑全量测试、重建项目、操作 Docker、修改 `.venv`／`.gitignore`／仓库设置或推送。

## 修订与未关闭边界

产品代码基线：`8083d2972567bb893174beca9ee0ae8add8fb1d1`。验收时测试文件 SHA256：

| 文件 | SHA256 |
| --- | --- |
| `backend/tests/test_intake.py` | `7ae4e8af0aa48189c123e45e2243fd31534b47f208842a31280958cc23d1532c` |
| `backend/tests/test_planning_capability_context.py` | `52b918b6f4ffa948bdc5698c4f4b23b154f09c5d0d1c1a1b738befc42cea79bd` |
| `backend/tests/test_planning_decisions.py` | `c23b636f89aad1951e28722501f0648c1b23554e365b2add0aa8ad6748cdbb91` |

相关实现或测试变化后须重新验收。本记录与测试、映射、队列第 9 项状态、开发进度同次提交；不修改队列其他任务状态。

语义模糊不能仅靠字段非空判断。当前自动规划允许八项均非空时生成待确认草稿，不要求先完成需求确认；本次检查的是八项缺失时不派发规划、模型返回追问时不采纳计划，以及准入和构建门禁，不宣称所有模糊描述都能在模型调用前拦截。固定响应不能证明真实模型稳定识别语义缺口、持续追问质量或完整业务正确；前端人工体验、真实 Dify 导入／试跑及多需求业务验收仍未验证。保留原 0.199／0.200 真实语义验收缺口，不把本次 65 个本地通过计为 AT-01 最终业务通过或 136 项计划完成。
