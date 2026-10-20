# Sierra AT-12 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 3 项「核对 AT-12『DSL 变量引用错误』现状并补隔离检查」。需求原文：定位并修复，再检查，不删业务分支。

结论：**本项本地隔离检查验收通过；AT-12 的真实平台及最终业务验收仍待完成。** 本次没有实现或声称通用自动修复，修正步骤由测试模拟用户显式手改。

## 现状及本次补充

- 原有 `test_workflow_plan.py` 已验证不存在变量、非上游和兄弟分支引用，`test_plan_inspection.py` 已验证缺节点、不保存检查及摘要/修订绑定；`test_dsl.py` 已验证最终 DSL 的提示词、终点、上下文及检索变量错误；`test_dsl_roundtrip.py` 已验证手改保留与坏引用拒绝。
- 原有用例缺少同一双分支样例的连续断言：定位错误 → 显式手动修正 → 再检查通过 → 两条业务分支及业务内容完整保留。
- 新增 `backend/tests/test_at12_variable_references.py` 共 20 例：Workflow/Chatflow × 计划检查接口/最终 YAML × 缺失节点、无效变量、兄弟分支、条件引用、终点输出引用五类错误。
- 错误检查断言失败状态及明确节点/字段诊断；修正只恢复包含该错误引用的节点配置，重检后完整计划/DSL 与原有效样例相等，含所有节点、条件、边及分支句柄、提示词、模型及布局。
- 计划接口额外核对修订、请求 nonce、原文 SHA256（修正后变化）、六节点计数、所有未执行/未验证标记为 false，以及任务、确认与产物状态不变；存储写入被禁止。最终 YAML 经实际解析及 `validate_preserved` 检查，检查前后输入文档不变。
- 临时存储由既有 TestClient fixture 提供，真实 HTTP 传输及模型入口被禁止；没有真实 Dify 资源操作或模型付费调用。

## 验收命令与真实结果

在项目根目录执行（仅相关文件，没有全量测试）：

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest backend/tests/test_at12_variable_references.py backend/tests/test_workflow_plan.py backend/tests/test_plan_inspection.py backend/tests/test_dsl.py backend/tests/test_dsl_roundtrip.py -q
```

退出码：`0`。输出末尾原文：

```text
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
112 passed, 1 warning in 16.50s
```

此前单独调试新增文件时，首次运行有 7 failed、3 passed、10 errors：测试网络护栏拦截了 Windows asyncio 内部回环 socket，且预期诊断遗漏 `reference` 字段后缀。修正测试护栏为禁止真实 HTTP 传输并对齐完整诊断后，新增文件运行结果为 `20 passed, 1 warning in 2.65s`，再执行上述五文件验收通过。未因此修改产品代码或依赖环境。

## 版本绑定与限制

验收基于提交 `67f763325b79995b096b7dfa5c26770faf3621b2` 的产品代码，加本项新增测试；没有修改产品实现。新增测试文件 SHA256：`91b22bf7bb1117cdda208fd8eaedb90072a348f61d67d82f30f725480d98fde5`。本记录、映射、队列与开发状态随本项同一提交归档。后续相关实现或测试变化须重新运行相应验收，不能沿用此结果。

目标仍为 Dify 1.17.1 / DSL 0.7.0；本次未改变 DSL 格式或兼容范围，也未查询/操作真实平台。静态 YAML/计划验证不等于真实 Dify 导入、试跑、语义业务正确或所有图类型都支持。通用自动修复及不删业务分支的真实闭环仍缺证据，未部署，未将 136 项计划整体标为完成。
