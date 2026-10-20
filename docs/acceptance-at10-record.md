# Sierra AT-10 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 18 项「核对 AT-10『接口未提供且用户接受模拟』现状并补隔离检查」。需求基线：`docs/requirements-v1.0.md` 的「显式采用模拟方案，标记位置及真实接入待办」。

结论：**本项本地隔离检查通过；AT-10 完整业务闭环仍有缺口，未完成真实平台验收。** 本次仅修改测试与记录，不修改产品实现，不执行其他队列项。

## 现状核对

- 新任务的 `configuration.mock_dependencies` 默认为空，不自动认定用户接受模拟。配置接口只要求字符串列表；用户可手动保存，再确认当前修订的配置。直接 PATCH 不要求单独的模拟同意字段，普通配置确认也不检查声明是否包含有效模拟位置和接入待办。
- 集中配置方案路径会展示修改理由、体验、费用及人工影响。候选保存不等于采用；模拟依赖发生变化时，采纳接口须另外收到 `acknowledge_mock_changes=true`，并保存采纳修订及 acknowledgements。此保证只适用于该路径，不能推广到所有手动配置或自然语言同意。
- `backend/app/dsl.py` 的基础线性模板会把模拟声明、资源计划写入应用描述，静态校验附加“不能视为已连接或已验证”的警告。报告保留配置原文，附有通用“替换所有已确认的模拟依赖，并重新验证”待办。
- `main.compile_current` 优先选用 Agent／显式流程／基础模板。静态核对 `backend/app/workflow_plan.py` 和 `backend/app/agent_plan.py`：这两个编译路径没有统一读取 `mock_dependencies` 来附加模拟声明及专项警告。因此基础模板的标记检查不能证明新任务显式流程和 Agent 下载也满足 AT-10。前端配置页有模拟依赖输入框，集中方案面板有单独接受选框；本次没有运行前端体验验收。
- 当前声明是自由文本，不是可执行的模拟接口或结构化的位置／替换方案。系统不会据此生成固定响应节点，也不验证所述节点存在、业务样例正确或替换完成。本次合成声明提到 code 节点，但模板并不包含该节点；测试只证明原文保留，**不证明位置声明真实或模拟执行成功**。
- 模拟依赖变更或清空会增加修订、保留未变业务需求的确认、撤销配置确认及当前成果，旧下载不可再取，旧修订确认被拒绝；清空列表不等于已经接入真实服务。历史版本保留旧声明。

## 新增隔离检查

`backend/tests/test_api.py` 新增 11 个用例：

1. 3 例检查 Workflow／Chatflow（`advanced-chat`）／Agent 新任务没有默认模拟同意，应用类型保持，临时存储重开仍为空。
2. 2 例检查基础线性 Workflow／Chatflow 的显式模拟声明保存、当前修订重新确认、构建前门禁、DSL 下载描述及警告、报告中的原文和替换待办、版本快照及持久化。检查没有 HTTP 请求节点，没有导入或运行记录，成果仍为 `static_only`。
3. 3 例检查字符串、含空值及含对象的非法声明被精确拒绝，GET 前后任务一致，持久配置不变。
4. 2 例检查变更／清空模拟声明后确认、成果及旧下载失效，旧修订拒绝，历史快照保持。
5. 1 例使用无环境的本地资源发现路径及直接保存的合成候选，检查单独模拟同意缺失时拒绝且不变更任务／候选，显式接受后采纳但不自动确认配置，采纳回执和修订持久化，旧采纳请求不可重放。没有调用候选生成模型；合成理由不代表真实建议质量。

新增文件级 autouse fixture 阻断真实同步／异步 HTTP transport 和默认 `main.call_model`。现有指定用例仍可安装固定模型／Dify 方法替身；所有任务使用临时 Store 和数据目录。基础模板测试沿用旧 `approved` 辅助函数，它关闭新任务准入／流程复核门禁；不据此宣称新任务端到端通过。没有真实 Dify 资源访问或真实付费模型调用。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q
```

首次执行通过，退出码 `0`，完整输出（工具分两段返回，进度行合并如下）：

```text
........................................................                 [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
56 passed, 1 warning in 16.08s
```

唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未修改依赖环境。没有重跑全量测试、重建、Docker、修改 `.venv`／`.gitignore`／仓库设置、删除目录或推送。

## 修订与未关闭边界

产品代码基线：`ed730f0d9bf62d519ba4dbe28fffa605fbd93da3`。验收时 `backend/tests/test_api.py` SHA256：`0bf099b41c142491356ee6e754d997c6482c5d5cd25eca0df48e56e1a93534cd`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，仅记录此次本地核对结论。

仍缺少统一的各产物模拟标记、可核验的位置绑定、逐依赖真实替换接入待办与完成证据、实际模拟执行及关键业务样例交付链。自然语言同意识别、前端体验、真实接口鉴权、实际 Dify 导入／运行及最终业务验收未验证。不代表 AT-10 最终业务通过或整个 136 项计划完成。
