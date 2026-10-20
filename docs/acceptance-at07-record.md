# AT-07 多个知识库可选：本地隔离核对记录

日期：2026-10-20。对应 `docs/BACKLOG.md` 第 15 项。产品为 Sierra；适配目标保持 Dify 1.17.1。本次仅核对现有实现、补隔离检查及记录，没有修改产品实现或部署。

## 现状与结论

基线要求：`docs/requirements-v1.0.md` AT-07「多个知识库可选：提出选择及理由，确认具体库。」

- `backend/app/configuration_proposals.py` 读取模型及知识库目录元数据，知识库最多读取 3 页、每页 100 条；来源失败与截断有明确状态。读取不会改变任务配置，也不执行 Dify 资源写入。
- 生成入口向助手传递需求、当前配置、用户讨论、流程与目录快照。`docs/configuration-model-contract.md` 要求结合业务范围说明选择理由，不以名称推断内容正确、索引完成或检索效果；现有真实联调记录曾读取多库但未选择库，不能替代 AT-07 选库验收。
- 方案使用具体 `dataset_ids`，每个拟议字段须有理由和体验／费用／人工影响；ID 须唯一且属于当前任务已读取目录或原配置。遗漏字段保留原值，删除原选库须显式提议。校验器检查结构与来源，不判断理由的语义质量，也不机械要求逐库比较。
- 待决定事项阻止采纳；用户须明确接受变化，目录未核对的原有 ID 或文档为空／未就绪的库另需明确接受限制。采纳只持久化本地配置，增加修订并使配置确认失效，不自动确认、构建、导入或运行。
- 快照有效期为 15 分钟，绑定目标环境；方案绑定任务修订、配置、需求、流程、对话、连接及快照。已有用例覆盖需求／连接变化、重新读取及过期后的拒绝，以及跨任务方案拒绝。

## 新增隔离检查

在指定 `backend/tests/test_configuration_proposals.py` 新增 15 例。整个文件增加自动 fixture，阻断同步／异步真实 HTTP transport 和默认模型调用；模型测试显式替换为固定响应。沿用临时数据库，不读取真实资源或付费调用模型。

1. Workflow、Chatflow（接口标识 `advanced-chat`）、Agent 各一例：正常 API 新建、人工准入复核及显式需求确认后，只读获取两页、三个同名但不同 ID／描述的库。固定建议选择产品与退货库、排除人事库，核对模型输入与具体 ID、理由和三类影响完整传递；生成不应用配置。重开临时数据库保留快照和方案，未接受变化时拒绝且任务不变；明确采纳后精确保留所选 ID 顺序、应用类型及需求，增加修订且配置未确认、无成果／应用绑定／运行，重开数据库仍保持；拒绝重复采纳。此处尚未保存流程，不证明三种应用的实际检索或运行能力。
2. 重复 ID、空白 ID、用库名代替 ID、混入伪造 ID 共四例：确定性校验拒绝，无方案或配置写入。
3. 两例对照：省略 `dataset_ids` 时保留原有两库；显式移除退货库并说明范围影响后，只采用具体剩余 ID。
4. 两例拒绝缺少选库理由或费用影响的方案，不自动保存或应用。
5. 当前任务不能借用另一任务的目录作为选库依据，即使该 ID 在另一任务有效。
6. 未核对的原有库、可用文档数为零的库各一例：与正常库混选仍保留具体警告；缺少单独接受时配置不变，接受后仍保留未验证警告和未运行状态。
7. 尚未确认是否加入退货库时，保留明确问题、建议及影响，采纳受阻且任务不变。

其他门禁沿用该文件原有 32 例，包含过期／刷新／修订变化、空库、目录失败与截断、跨任务方案、旧计划复核、暂停及预算记录。

## 指定命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_configuration_proposals.py -q
```

首轮退出码 1：`3 failed, 44 passed, 1 warning in 19.64s`。三种应用类型的新测试在人工复核增加修订后仍用旧修订确认需求，触发真实 409 门禁；已改为使用复核接口返回的新任务修订，并补齐连贯的售后需求样例。未放宽产品门禁。

第二轮同一指定命令退出码 0，完整输出：

```text
...............................................                          [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
47 passed, 1 warning in 21.90s
```

唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未修改依赖。

## 修订与未关闭边界

核对代码基线：`7f3ab58b285d9471b86f57f4e3483d06e3586323`。验收时 `backend/tests/test_configuration_proposals.py` SHA256：`b9cf715250816e321aded0030a18d75d278a57f0ccc68e46a081263f883e38f3`。相关实现或测试变化后须重新验收。

本记录登记为 acceptance-mapping 的 `final_acceptance_record`，只表示本次本地核对已记录。固定响应不证明真实选库理由合理、资料授权／正文正确、索引就绪、检索命中、费用比较或前端操作体验通过；目录只反映有界时间点元数据，不能证明全部候选已比较。独立检索节点另有配置，本方案不自动改写节点；三种应用类型不等于三种真实业务运行已验收。真实多库选择质量与最终 Dify 业务验收仍待验证，不代表 AT-07 最终业务通过或整个 136 项计划完成。

未运行全量测试、重建、Docker、真实 Dify 资源操作或真实模型调用；未修改 `.venv`、`.gitignore` 或仓库设置，未删除目录或推送。只处理队列第 15 项。
