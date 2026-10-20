# AT-22 Dify 断开：本地核对记录

日期：2026-10-21。对应 `docs/BACKLOG.md` 第 28 项及 `docs/requirements-v1.0.md` 的 AT-22：可以生成待验证成果，明确未完成导入和试跑。

结论：指定文件验收通过，新增 8 个隔离用例，未修改产品实现。`final_acceptance_record` 表示本次本地核对已记录，不代表真实 Dify 或最终业务验收通过。

## 已有实现与核对范围

- `backend/app/main.py` 的 `build` 不要求环境已连接；确认和静态检查通过后生成当前修订成果，记录 `verification=static_only`、`status=draft_ready`。下载与 DSL 文本接口读取该成果，不产生导入或运行记录；没有环境／尚未导入时，试跑入口明确拒绝。
- `backend/app/dify.py` 的真实请求适配器将连接错误转换为「无法连接目标 Dify 环境。可以继续生成待验证 DSL。」，将超时转换为结果可能未知的提示；不自动重试。`external_action` 分别保存 `failed`／`unknown`、错误及完成时间，不生成成功结果或样例判定。连接错误记为失败，并没有未知操作的强制防重试门禁；超时的未知操作则禁止同修订同类重复派发。
- 报告按当前修订和环境筛选匹配导入证据，无导入证据时明确说明编译只代表静态校验。试跑失败／未知不计成功运行，`acceptance.py` 的已声明样例汇总不计通过。重新生成静态成果会将任务总状态改为 `draft_ready`，但保留操作历史、原 App 绑定和未知操作门禁；总状态不能单独作为已导入／已试跑证明。

## 新增隔离检查

`backend/tests/test_api.py` 新增 8 例：

1. 4 例：Workflow／Chatflow × 未选环境／已配置但无凭据。验证静态生成、类型与修订保持、下载字节及修订文件名、DSL 文本、报告未导入声明、样例尚未试跑、临时数据库重开一致，以及试跑拒绝不追加操作记录。
2. 4 例：导入／Workflow 试跑 × `httpx.ConnectError`／`httpx.ReadTimeout`。保留真实 `DifyClient.request` 错误转换路径，仅将异步 HTTP transport 替换为必定抛错的传输层；断言请求路径和一次派发、502 提示、失败／未知证据绑定修订和环境、无输出及判定、原成果仍可下载、报告不计成功、样例不通过。
3. 上述 4 例同时核对存储重开与正常启动恢复函数不重复派发，以及故障后可重新生成相同成果且保留历史。超时两例还验证重建后同类重试返回 409，未知记录与派发次数保持不变。

文件级自动 fixture 持续阻断真实同步／异步 HTTP、Dify 底层请求及默认模型调用，仅向上述故障用例提供原请求方法；这些用例必须先安装必定抛错的异步传输层才调用原方法。所有任务、凭据及成果位于测试临时 Store，试跑准备使用明确标记的合成导入回执和 App ID，不触及真实资源。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q
```

首轮 `8 failed, 83 passed, 1 warning in 34.58s`：新增共用断言直接比较 Windows 文件 CRLF 与文本接口规范化后的 LF，8 例均在此失败。修正为文本换行规范化比较，下载接口仍逐字节核对；补齐故障后重建保护断言后，再运行同一指定命令，退出码 `0`。工具分段返回，以下为真实输出末段（不含此前进度点）：

```text
.......... [ 79%]
...................                                                      [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
91 passed, 1 warning in 34.47s
```

警告来自现有 FastAPI／Starlette TestClient 依赖。本次只运行上述单文件命令，没有全量测试、重建、Docker、真实 Dify、付费模型调用或推送，没有修改 `.venv`、`.gitignore` 或仓库设置。

## 修订绑定与未验收边界

产品代码基线：`0d8291d10b838b14d9208404fa1b5c97a0fd1915`。验收测试文件 SHA256：`f28c5eaeae71dac6fdc25f60cd24dd20ae20a7870f55cde933ee5ea2895dabd3`。相关实现或测试变化后须重新验收。

沿用 `create` 的旧需求准入／计划复核豁免；Workflow 使用显式代码计划，Chatflow 使用旧模板。本次没有真实模型规划、生成代码执行、前端操作、完整新任务准入、原生 Agent 断连、真实网络中断或重新连接成功后的业务恢复验收。存储重开和恢复函数检查不等于实际杀进程／重启服务。

API 成果元数据与报告保留静态／未导入／样例未试跑的边界；单独 YAML 下载没有统一记录实际导入／试跑状态，不能代替报告。当前适配器和报告也不会自动把测试提供的合成导入回执标为 mock，其中「真实导入」措辞不是平台证据。当前失败／未知分类依赖错误提示是否含「结果可能未知」，不证明所有故障阶段都能精确判定远端是否写入。真实断连完整交付、资源结果人工核对和恢复仍待专项验收；本次只处理第 28 项，不代表 AT-22 最终业务通过或整个 136 项计划完成。
