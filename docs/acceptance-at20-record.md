# AT-20 执行中暂停并关闭程序：本地核对记录

日期：2026-10-21。对应 `docs/BACKLOG.md` 第 26 项及 `docs/requirements-v1.0.md` 的 AT-20：保存阶段及结果，恢复后不盲目重复外部操作。

结论：指定单文件验收通过，新增 13 个隔离用例，未修改产品实现。`final_acceptance_record` 表示本次本地核对已记录，不代表实际关闭进程、真实 Dify 或最终业务验收通过。

## 已有实现与核对范围

- `backend/app/main.py` 的暂停接口持久化 `paused`、递增 `pause_generation`，明确提示已派发请求可能仍在执行。活动访谈和预算预留仍阻止重复请求；暂停不保证取消外部请求。
- 访谈返回后先结算用量，再检查暂停状态。暂停后的迟到候选不写入需求，候选摘录、用量和未应用原因保留；活动访谈标识随后清除。
- `backend/app/task_budget.py` 的 `recover` 将 `reserved` 转为 `unknown`，保留原 ID、修订、单价和费用预留；未确认结束的访谈暂停并清除活动标识。设置累计预算时，费用未知会阻断后续调用，不能通过提高上限消除未知费用；须明确登记人工核对结果。
- FastAPI 启动生命周期调用预算、规划、外部操作和访谈进度恢复。外部导入／试跑的 `pending` 记录转为 `unknown`，保留检查点并提示到 Dify 核对，不自动重复派发；原忙碌任务转为 `error`，已暂停任务保持暂停。访谈进度转为 `interrupted`。

## 新增隔离检查

`backend/tests/test_task_budget.py` 新增 13 例：

1. 3 例：Workflow、Chatflow（接口值 `advanced-chat`）、Agent。通过公开暂停 API 暂停固定模型调用，重开 Store 读取暂停检查点；核对重复消息被拒绝、迟到候选保留但需求及修订不变、费用正常结算。
2. 6 例：三种应用类型 × 访谈执行中／已暂停。先保存一条已结算调用，在第二次真实本地 API 请求的固定模型替代函数内用 SQLite backup 获取在途数据库快照并复制临时凭据密钥。源请求随后正常结束；将宿主切换为快照的全新 Store，运行完整应用启动生命周期。核对原需求、类型、修订、已结算条目、未知费用预留和访谈中断状态；第二次启动不重复追加记录，不自动派发。未知费用阻止继续，提高预算不解除阻断；明确模拟人工账单核对后，只有显式继续才生成新的独立调用条目。
3. 4 例：模拟导入／试跑检查点 × 忙碌／已暂停。持久化固定完成结果和未完成检查点，重开 Store 并执行完整启动生命周期；核对完成结果原样保留，未完成记录转未知，输入、修订、成果及绑定保留，两次启动结果一致，不调用外部适配器。

文件级 autouse fixture 阻断同步／异步真实 HTTP transport、Dify 底层 `request` 和默认模型调用；只有显式固定模型替代可执行。所有数据库、密钥和快照均在 pytest 临时目录。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_task_budget.py -q
```

首轮退出码 1：`11 failed, 27 passed, 1 warning in 11.58s`。新增测试存在事件循环线程内同步嵌套调用 TestClient、使用展示名 `chatflow` 而非接口值 `advanced-chat`，以及未考虑读取接口补全 `planning_runs` 默认字段的问题；修正测试后仅重跑同一指定命令。

最终退出码 0。以下为工具分段返回的真实末段输出：

```text
.......                                   [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
38 passed, 1 warning in 11.72s
```

警告来自现有 FastAPI／Starlette TestClient 依赖。没有运行全量测试、重建、Docker、部署、真实 Dify 或付费模型调用，没有推送、删除目录、修改 `.venv`、`.gitignore` 或仓库设置。

## 修订绑定与尚未验收边界

产品代码基线：`ee68a1244c279904eba6dbb8ec424187728c0bd8`。验收时测试文件 SHA256：`27707a02fda4c427a8fef78cdc4f1d9ee8ec799ec3c0db5bcebfe75b643fe8c4`。相关实现或测试变化后须重新验收。

快照检查模拟进程内存丢失，但源请求正常结束，没有实际杀进程、关闭用户程序或模拟电源故障；不能证明所有磁盘故障时序与 OS 退出路径。访谈准备沿用旧 `create` fixture 的准入／计划复核豁免，不是新任务完整交互；预算门禁核对在显式设置上限的条件下进行，未设置上限时不承诺未知费用阻止手动继续。人工金额为模拟登记，不是供应商真实账单。导入／试跑记录直接构造，仅证明本地启动恢复和持久化，不证明真实在途资源终止、远端结果核对、幂等创建或恢复业务成功。规划、建库、图像、定时、人审等其他恢复分支及前端退出／重开体验未在本项新增用例中逐一验收。没有新增自动恢复或外部取消能力。

本次仅处理队列第 26 项，不表示 AT-20 最终业务验收或整个 136 项计划完成。
