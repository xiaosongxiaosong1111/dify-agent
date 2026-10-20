# Sierra AT-25 验收结论记录

日期：2026-10-21（Asia/Shanghai）。范围：BACKLOG 第 30 项「核对 AT-25『启用轻量模型分工』现状并补隔离检查」。基线：`docs/requirements-v1.0.md` 的 AT-25「比较全链路成功率、总用量和费用，计入重试开销」。

结论：**本项本地隔离检查通过；AT-25 同案例全链路质量、用量、重试开销及真实费用受控对比仍未完成。** 本次只补测试与记录，没有修改产品实现或部署，仅处理队列第 30 项。

## 现状核对

- `backend/app/assistant_routing.py` 只将 `kind=cases` 的验收样例建议路由到用户明确选择的轻量服务。访谈、流程、配置、冲突、覆盖仍使用任务主模型，不是通用多 Agent 分工。设置只保存本地独立策略及确认历史，不修改业务修订或业务确认，不自动调用模型或 Dify。
- 启用需绑定当前任务修订、策略修订、服务快照 token 和当前范围版本 18，并明确确认范围和原因。旧范围、服务缺失／缺密钥、角色或服务快照改变阻止派发，不自动回退主模型。范围说明明确不保证低价、更少 tokens 或质量，也不将助手密钥、管理凭据或知识全文加入提示。
- `backend/app/bounded_suggestions.py` 在本轮固定服务与凭据，调用 `planning.py` 的有界修复逻辑。JSON 解析失败在允许次数内可再次请求同一服务；相同问题重复出现停止，无自动升级。每次派发经 `task_budget.py` 预留、保存独立条目并结算，保留操作 ID、修订、型号、价格及最终用量。供应商失败可记录已报告用量；没有最终用量时保持未知，不能当作免费。
- `backend/app/assistant_usage_groups.py` 从本机历史账本按服务、型号、用途、资料类别及价格快照汇总，覆盖已登记重试、失败及旧修订，不按当前单价重算。`returned` 表示模型返回正文，其中可包含格式错误的候选；不能将它当成全链路成功数。`business_quality_verified`、`savings_verified` 为 false。
- 原有指定文件已有基础路由、版本／服务配置变化门禁、无回退、候选来源，以及分组精度、未知值和只读接口检查；本次补足重试与主／轻量共享账本的串联证据等缺口。

## 新增隔离检查

`backend/tests/test_assistant_routing.py` 新增 7 例：

1. 范围版本 1、17 各一例：旧策略阻止生成且不解密、不新增调用或费用、不改任务；提交旧范围返回 409，明确按当前范围重新确认后解除阻止，历史保留旧范围。
2. 一例核对策略按任务隔离，临时 SQLite Store 重开后轻量选择与确认历史一致，另一任务仍使用自己的主模型；任务、业务确认和账本不受设置影响。
3. 一例移除所选轻量服务密钥，生成返回 422，不回退、不改任务、不产生费用条目。
4. 三例固定第一次返回无效 JSON，第二次分别为合法建议、重复无效 JSON、带用量的供应商失败。每例恰好两次轻量替身调用，修复消息追加诊断，主模型从未被调用；成功保存候选，重复错误按 `no_progress` 暂停，供应商错误按 `provider_error` 暂停。两次尝试共享操作 ID、逐次计费，累计输入 200、输出 20、total 220，费用估算 0.000024 USD；失败不丢账，不自动采纳、运行或绑定 Dify。即便重复无效正文被统计为两次返回，业务质量与节省仍未验证。

`backend/tests/test_assistant_usage_groups.py` 新增 1 例：从主模型生成一次，启用轻量后经历一次 JSON 修复的两次调用，关闭轻量并调整主模型单价后再生成一次。核对调用顺序为主／轻／轻／主，四次调用进入同一账本；改变业务修订、删除已停用轻量服务并重开临时 Store 后，旧修订读取返回 409，当前修订汇总仍保留全部旧条目和三组原价快照。读取阶段禁止查询当前服务配置、解密或模型调用；输入 400、输出 40、total 440、估算 0.000484 USD，账本和任务保持不变。这些数字均来自固定测试用量，不是供应商账单或受控模型比较。

两文件新增自动 fixture，阻断同步／异步真实 HTTP、DifyClient 底层请求和默认模型调用；需要响应的用例才显式注入固定替身。任务使用临时 Store 和进程内 TestClient，沿用既有测试辅助函数的旧模板／准入兼容准备，不代表新任务完整准入或真实平台验收。没有接触真实任务、Dify 资源或付费模型。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_assistant_routing.py backend/tests/test_assistant_usage_groups.py -q
```

本次指定验收一次通过，退出码 `0`。同一次执行的分段输出合并如下：

```text
.................................................                        [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
49 passed, 1 warning in 11.07s
```

唯一警告来自既有 FastAPI／Starlette TestClient 依赖，未改依赖。

## 修订与未关闭边界

核对代码基线：`bbba3e1a37bd2ef36c7558a838263451e42cbc7d`。最终验收时测试文件 SHA256：

- `backend/tests/test_assistant_routing.py`：`aacf8cb5d16d88130f24036e1d8320095186ab2504f7e6a0297c969f36b377e9`
- `backend/tests/test_assistant_usage_groups.py`：`33d6391677dd661b0c12fce2a56cfc8394c926eaed7535a6ba4731b0f1936598`

相关实现或测试变化后须重新验收；提交号由 BACKLOG 第 30 项绑定。

本次未进行同案例、相同业务标准下的主／轻量受控运行；没有真实成功率、供应商总账单、全链路总用量或质量对比结论。未验收前端操作、真实模型生成／重试、Dify 导入／运行及业务交付；本地静态候选有效不代表建议语义正确或真实业务通过。历史账本只覆盖开始记账后的助手调用，不包含 Dify 执行、建库等平台开销。轻量角色和历史分组均不能证明费用或 token 节省。

未跑全量测试、重建、Docker 操作、修改 `.venv`／`.gitignore`／仓库设置、删除目录或推送；不把本次本地通过计为 AT-25 最终业务通过或 136 项计划完成。
