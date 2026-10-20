# Sierra AT-16 验收结论记录

日期：2026-10-21（Asia/Shanghai）。范围：BACKLOG 第 22 项「核对 AT-16『自动触发或人工审核能力不足』现状并补隔离检查」。需求基线：`docs/requirements-v1.0.md` AT-16「说明环境缺口和替代方案，等待确认」。

结论：**本项本地隔离检查通过；未进行真实 Dify 平台或最终业务验收。** 只补测试和记录，不修改产品实现，不处理其他队列项。

## 现状核对

- `capabilities.catalog` 按用户选择类型返回编译范围，明确不证明目标环境或资源可用。Workflow 有受限定时／人工审核入口；Chatflow 和 Agent 不继承这些能力。Webhook／插件触发、强制指定审核人、邮件及复杂组合仍未适配。定时发布可能直接激活，无法保证失败后自动停用，也不能以手动运行冒充自然触发验收。
- `main.generate_plan` 将当前能力目录交给规划模型；模型返回缺口及 `needs_decision` 时，`planning_decisions.summarize` 保存理由、建议、体验、费用及人工影响，任务暂停等待用户决定，不把建议当确认，不自动删需求或改变应用类型。这依赖模型识别语义缺口，目录不是目标环境权限探测器，也没有确定性保证任意未支持需求都能被识别。
- 人工运行准备仅冻结本机方案，首批限 Dify 1.17.1 Workflow 的单个根审核、文字开始输入、固定模板与终点。指定身份不强制、实际平台尚未验收、可能遗留资源及宿主费用不能保证为零均有提示。通用导入／试跑不能绕过专用入口，准备也不等于资源批准。
- 专用执行需明确批准具体资源方案并绑定修订、成果、环境及凭据；仅新建独立应用／Key，四个写入阶段各记录一次尝试，不覆盖旧应用或环境 Key。等待表单和只读终态不计业务通过；原文件已有批准拒绝、旧方案、失败检查点、凭据轮换、来源核对与保密检查。本项沿用这些隔离检查，不重放真实资源操作。

## 新增隔离检查

`backend/tests/test_human_runtime_execution.py` 新增 10 个用例：

1. 3 例按 Workflow／Chatflow／Agent 核对能力目录、限制及确认提示，读取不修改任务、不准备或执行资源。
2. 2 例以 Webhook 自动触发、指定财务人员邮件审核为明确需求，给规划模型固定缺口／替代建议响应。核对真实本地 API 保存完整问题并暂停，原需求、类型、修订、确认、计划、成果、运行与版本保留，临时数据库重开一致，读取不继续规划或创建资源。
3. 2 例模拟目标版本为 1.17.0／unknown，核对在准备方案前以中文说明 1.17.1 基线并拒绝，任务不变、无方案或资源运行记录。直接修改临时环境记录仅为 fixture，不证明真实版本探测行为。
4. 2 例核对人工审核成果不能从通用 import／run 入口绕过独立资源批准，拒绝前不请求平台、不修改任务。
5. 1 例核对本机准备明确披露资源数量、身份／平台／费用及遗留限制，保存为 `prepared_unapproved`；省略明确批准字段时拒绝执行，记录与任务保持不变。

文件级 autouse fixture 阻断同步／异步真实 HTTP transport 和默认 `main.call_model`。任务、成果和加密凭据仅使用既有临时 Store／数据目录；规划响应、App／Run／Form ID、表单及平台状态均为替身，不是平台回执。两个规划用例用固定响应替换模型，不证明模型会自主判断环境缺口或提出合适替代方案。

沿用旧准备函数关闭新任务准入／流程复核策略；因此本次不是新建任务完整交互验收。未检查前端操作、真实环境权限、自然定时触发、真实表单提交／恢复或复杂客户业务。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_human_runtime_execution.py -q
```

首轮：`3 failed, 32 passed, 1 warning in 21.01s`。一例误用要求 Agent Plan 的批准准备函数，改用只创建任务的准备函数；两例预期了专用准备函数的版本文案，实际在公共环境门禁先拒绝，修正为精确匹配该中文提示。仅修测试准备与断言，产品实现未改。

修正后同一命令退出码 `0`，完整输出（工具分段返回，进度行合并）：

```text
...................................                                      [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
35 passed, 1 warning in 20.19s
```

警告来自现有 FastAPI／Starlette TestClient 依赖，未修改 `.venv` 或依赖。只运行上述单文件验收，没有全量测试、重建、Docker 操作、真实 Dify 资源交互、付费模型调用或推送。

## 修订与未关闭边界

产品代码基线：`4f56b808b675bbc75eebbb617d3abaa0f9999a34`。验收测试文件 SHA256：`eaa28365ad6108152d0dd44d593e6b19b71375410821707bd39a5e266767b24f`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，仅表示本次本地核对结论已有记录。

真实目标环境认证／角色权限及资源可用性、模型对能力缺口的识别质量、替代方案适用性、用户确认后的完整业务链、真实自然触发与人工审核仍待验收。Webhook／插件、指定身份、邮件及复杂组合保持未适配，不自动降级。本次不代表 AT-16 最终业务通过，也不代表整个 136 项计划完成。
