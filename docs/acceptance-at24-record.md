# Sierra AT-24 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 5 项「核对 AT-24『用户恢复旧版本』现状并补隔离检查」。需求原文：保存历史，以恢复版本为基础重新确认／验证。

结论：**本项本地隔离检查验收通过；AT-24 最终业务验收仍未完成。** 本次只补测试和记录，没有修改产品实现、部署、访问真实 Dify 或发起模型付费调用。

## 现状与缺口

- `main.snapshot` 保存需求、配置、环境标识、材料、计划、样例、引用和检查等本地内容；`version_restore` 先比较，再用任务、应用类型、当前修订、当前恢复字段及确认／成果／绑定状态、唯一历史内容绑定确认。变化后旧预览拒绝。
- `main.restore` 在空闲与修订门禁内先保存“恢复前保存”快照，再增加修订、清除需求和配置确认、当前成果及应用绑定，最后复制历史内容。原运行、讨论、确认历史和费用账本保留；分歧确认清空，强制准入要求不降级。
- 原有恢复用例已覆盖预览只读／脱敏、恢复内容、重放拒绝、严格请求、坏快照和旧材料兼容；节点用例覆盖位置、字段、身份、顺序、边、截断和结构限制；运行快照用例覆盖代码／契约冻结、数据与凭据隔离及损坏拒绝。运行快照检查属于运行代码身份保护，不等于用户方案恢复或外部资源回滚。
- 原有用例缺少恢复、持久化读回、重新确认／构建和旧运行不沿用的连续检查，以及凭据与策略保留、未返回运行和预算预留的明确恢复拒绝断言，本次补齐这些本地证据。
- 需求基线明确：恢复首先是项目文件和方案恢复，外部覆盖／还原另列影响与操作。通用复杂手改、缺文件依赖、跨目标依赖重新核对及恢复后的真实 Dify 导入／试跑和业务验证仍未验收。本次没有重新执行前端界面检查。

## 本次新增隔离检查

`backend/tests/test_version_restore.py` 新增 4 例：

1. 固定 Workflow 样例：历史静态构建及人工植入的通过记录 → 修改目标和代码、确认 → 预览并恢复 → 重新打开临时数据库 → 旧修订确认拒绝、未确认构建拒绝、旧成果下载拒绝 → 新修订重新确认和静态构建。检查全部原历史及恢复前需求／计划保留，应用类型不变，旧运行和确认历史保留但旧通过不计入当前样例；新成果严格标为 `static_only`，原成果文件及账本不变，原恢复请求不能重放。通过运行是固定 fixture 数据，用于验证修订筛选，未实际运行 Dify 或用户代码。
2. 固定环境／供应商记录与假凭据：恢复历史环境标识，连接对象和加密凭据逐字节不变；保持当前强制计划复核与准入要求，清空历史分歧确认并保留原快照。历史快照中额外植入的确认与应用绑定不复活，不回显假凭据。此用例不证明跨目标依赖已经可用。
3. 当前运行处于 `pending`：可只读比较，恢复返回 409，任务／历史／账本不变。
4. 当前预算条目处于 `reserved`：同样阻止恢复并保持存储不变。

恢复测试文件增加自动 fixture，阻止真实同步／异步 HTTP 传输和 `main.call_model`；继续使用既有临时 Store 与进程内 TestClient。快照测试只在临时目录运行 `prepare`，没有重建实际项目或准备实际运行快照。没有修改 `.venv`、仓库设置或 `.gitignore`，没有运行全量测试。

## 验收命令与真实结果

在项目根目录执行用户指定命令：

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_version_restore.py backend/tests/test_version_node_changes.py backend/tests/test_runtime_snapshot.py -q
```

退出码：`0`。完整输出（两次工具读取的同一输出行合并）：

```text
......................................................                   [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
54 passed, 1 warning in 10.07s
```

警告来自现有 FastAPI／Starlette TestClient 依赖；本次未调整依赖环境。以上命令首次执行即通过，未运行全量测试。

## 修订绑定

产品代码基线：`5df7abbe364cba6947dbeb05a627ec2d7e5302ca`。验收时 `backend/tests/test_version_restore.py` 文件 SHA256：`b5f23f0e6545df25c36b7b141b45d54cd7170e5346942ff4a4502e7ab8921f91`。测试、本记录、验收映射、队列状态和开发状态随本项同一次提交归档。相关代码或测试变化后须重新验收；本记录不是 AT-24 真实业务通过或 136 项计划整体完成的证明。
