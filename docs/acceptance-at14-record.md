# Sierra AT-14 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 4 项「核对 AT-14『批量任务部分失败』现状并补隔离检查」。需求原文：按已确认策略继续或停止，输出失败项。

结论：**本项本地隔离检查验收通过；AT-14 最终业务验收仍未完成。** 本次只新增测试和记录，没有修改产品实现、部署或操作真实 Dify 资源。

## 现状与缺口

- `iteration.py` 目前只接受原生 `error_handle_mode=terminated`；顺序与显式并发策略均须保留，不能静默改为继续或丢弃失败项。并发已派发项不能保证即时取消。
- `iteration_outcomes.py` 对受限纯 Python 计算提供显式接受后的替代方案：将六类计算异常封装为 `index/ok/value/error_category` 对象，继续后续项；父迭代仍为 terminated。文字、数值、明确 Schema 对象均有严格合同，输入/输出合同错误与未知错误仍终止。
- `iteration_summary.py` 生成成功/失败列表和计数，严格核对原输入数量、连续索引及逐项合同；保存改变的结果协议会使旧需求与配置确认失效。
- 原有相关用例已分别检查异常类别、合同错误、空输入/重复值、缺尾项拒绝、保存门禁及纯计算链首次失败步骤和后继跳过；缺少单一样例贯通生成的解析、逐项封装、汇总代码和最终 End 输出绑定的回归。
- **停止路径当前没有完整失败项清单输出证据**：检查只证明最终 YAML 保留 terminated、原始代码异常向外抛出及原 End 绑定，不能证明平台真的停止、取消已派发项或输出失败清单。不得据此认定 AT-14 的“停止并输出失败项”已满足。
- 真实 Dify 1.17.1 导入/运行、真实业务确认到执行的闭环、混合模型/HTTP/DAG/嵌套正文的通用失败继续、恢复执行及其它下游消费者仍未验收。静态 YAML 和固定样例执行不能替代平台或业务验证。

## 本次新增隔离检查

`backend/tests/test_at14_partial_failures.py` 共 21 例：

- 15 例：文字/数值/对象 × 首项失败、中项失败、末项失败、全部失败、空批次。生成逐项结果与汇总方案后，编译最终 YAML 并检查保留验证；仅执行该固定开发样例生成的解析/封装/汇总代码，解析实际 End 选择器，精确断言完整结果、成功和失败清单、原始索引、成功值类型、重复值、空文字与计数。失败不复制私有异常正文；输入与原计划不被修改，未验证标志保持 false。
- 3 例：检查原生停止计划在文字/数值/对象结果下保留原代码、顺序策略及 End 绑定，固定计算的 ValueError 不被转成成功。这是 Python 函数及原生配置检查，不是 Dify 迭代执行模拟或平台停止证明。
- 2 例：原生 continue-on-error / remove-abnormal-output 策略拒绝，精确诊断且不重写原计划。
- 1 例：临时存储与进程内 TestClient 连续验证未接受协议时拒绝、预览不保存、任务/修订/nonce 对应、显式保存后需求和配置重新确认、旧修订预览拒绝、未确认时构建拒绝、拒绝前后持久化状态相同。没有绕过新合同的业务复核去声称执行成功。

新增文件禁止真实 HTTP 传输及模型调用，使用既有临时存储 fixture；只执行新建固定开发样例及确定性生成代码，不加载任务中保存的用户代码。相关既有测试使用其固定样例与隔离依赖。全程没有真实 Dify 或模型付费调用。

## 验收命令与真实结果

队列的“同上”指 `backend/tests/` 相关全绿，并在 acceptance-mapping 填 `final_acceptance_record`。本次运行 AT-14 映射中的全部 10 个相关文件，加基础迭代文件和新增隔离文件；未运行全量测试、重建或修改依赖环境。

在项目根目录执行：

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest backend/tests/test_at14_partial_failures.py backend/tests/test_iteration.py backend/tests/test_parallel_iteration.py backend/tests/test_iteration_outcomes.py backend/tests/test_iteration_summary.py backend/tests/test_iteration_numeric_outcomes.py backend/tests/test_iteration_object_outcomes.py backend/tests/test_schema_inspection.py backend/tests/test_iteration_chain.py backend/tests/test_iteration_chain_diagnostics.py backend/tests/test_iteration_chain_upstream.py backend/tests/test_iteration_chain_objects.py -q
```

退出码：`0`。完整输出：

```text
........................................................................ [ 16%]
........................................................................ [ 32%]
........................................................................ [ 49%]
........................................................................ [ 65%]
........................................................................ [ 82%]
........................................................................ [ 98%]
.......                                                                  [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
439 passed, 1 warning in 18.64s
```

首次同命令为 `1 failed, 438 passed, 1 warning in 18.99s`：新增测试最后直接比较保存响应与 GET 响应，忽略保存接口附带的 `plan_text` 投影。改为拒绝操作前后两次 GET 结果比较，并检查保存计划与修订一致后，上述最终验收通过。没有修改产品代码或放宽门禁。

## 修订绑定

产品代码基线：`c5d4c8d9717f8fefac07223173dec88b6d6284db`。新增测试 SHA256：`c7fc407b3c8fa056173920892fc7ec3fa028f8a83a1c157da5a5edf33f3be2c6`。本记录、映射、队列状态与开发状态同一次提交归档。相关代码或测试变化后须重新验收；本结果不代表 AT-14 最终业务闭环、真实平台通过或 136 项计划整体完成。
