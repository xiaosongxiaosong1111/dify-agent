# 仅内存诊断脱敏许可范围（reviewed diagnostic redaction scope）

## 定位

`tools/reviewed_diagnostic_redaction.py` 是一个小 helper，不是执行入口：没有新的批次 runner、审批系统或 CLI。导入它不会创建 Store、读取本机配置或访问网络。它只供后续独立剩余执行器在**新冻结计划明确包含所选模型服务的仅内存诊断脱敏范围并获得直接批准之后**调用。本单不用于真实 Key；后续启用仅在新冻结计划得到明确直接批准后进行。helper 本身不证明任何人类批准，不能用于第 391 项，也不会自动批准任何新范围。

第 391 项已真实停止并封存，原包不得重放或修改。实际根事实是：首例 Service 成功、`contains` 规则通过，随后普通 `backend/app/run_diagnostics.py` 约 219 行在任何原生 GET 之前，会按 `Task.configuration.assistant_provider_id` 读取模型 `api_key` 做 `safe_text` 脱敏；旧 `tools/reviewed-dual390/storage_guard.py` 的 `secret` 仅允许 Dify 连接与本批 Key，于是抛出 `Other credential read forbidden`。根已只读确认真实 Task 有模型绑定，并用无 Key Stub 证明在解密前即拒绝。本 helper 只解决这一条“为既有脱敏而读所选模型 Key”的许可，不恢复 391，也不代表任何真实 Key 已获授权。

## 范围对象

只有显式 `scope` 才启用新许可；`scope=None` 完全保持旧行为。

启用时字段固定且严格：

| 字段 | 约束 |
| --- | --- |
| `provider_id` | 合法 UUID，必须等于 `initial_task.configuration.assistant_provider_id` |
| `purpose` | 精确为 `run_diagnostic_redaction` |
| `memory_only` | 必须严格 `True` |
| `model_calls` | 必须严格整数 `0` |
| `max_reads` | 严格整数，范围 1..14，累计上限 |

`owner` 取 `boundary.owner`。任何多余/缺失字段、错误类型、错误 UUID、非所选 provider、越界预算都会在 `extend_guard` 调用时拒绝。

## 允许的唯一新增动作

`extend_guard(parent_guard, base_store, boundary, initial_task, scope)` 返回 `parent_guard` 的子类。该子类只重写 `secret`：

- 仅当 `item == scope.provider_id` 且 `key == 'api_key'` 时进入新分支；
- 只有在 `ScopedDiagnosticClient` 建立的精确 ContextVar 上下文中，才通过未守卫的基础 Store 只读解密一次；
- 其它所有 `secret(item, key)` 仍然交给 `super().secret`，即旧 Guard 的规则。

因此：

- 旧 Guard 原有的 provider 写、模型 HTTP、其它 secret 规则都没有放宽；
- 没有上下文时（包括 `scope=None`、普通请求、未授权的诊断），仍由旧 Guard 抛出 `Other credential read forbidden`，发生真实解密前即拒绝；
- 解密结果只作为返回值交给既有 `safe_text`，helper 不输出、不缓存、不持久化、不复制该 Key。

## 上下文身份校验

`ScopedDiagnosticClient(api, store, boundary)` 只包装 `.request`。普通请求原样转发。只有同时满足下列条件才建立上下文：

- 方法为 `POST`，路径精确为 `/api/tasks/{owner}/runs/{run}/diagnose`；
- 请求体 `json.read_remote is True`（严格布尔）；
- `owner` 等于 `boundary.owner`，`owner` / `run` 均为合法 UUID；
- `json.revision` 等于当前 Task revision；
- 存储中的 run 存在且 `kind == 'run'`，其 `app_id` / `revision` / `environment_id` 等于 owner 当前 App / revision / environment，且 App / environment 标识均为合法 UUID；
- run 与 Task 的 `app_type` 相同，且属于当前支持类型 `workflow` / `advanced-chat`；
- run 状态不是 `pending`；
- run 的 `environment_binding` 与当前环境一致。

上下文最终仍由守卫在 API 自身的存储锁内重新核对：上下文所属 store / boundary、用途、`boundary.halted`、Task 所有者、`boundary.phase ∈ {original_cases, modified_cases}`、当前 App、Task/run revision、App、environment、所选 provider、run 来源、run 非 pending、三方环境绑定一致（上下文建立时的环境绑定快照、run 的 `environment_binding`、当前 `binding(env)`）。任何一项不符都拒绝，且不会“只按阶段就全部放开”。

上下文使用 `ContextVar`，在 `finally` 中复位，不能跨请求或跨实例泄漏。`ScopedDiagnosticClient` 只在读取身份时短暂持有存储锁，随后释放再调用真实 API，避免跨 TestClient 线程死锁。

## 明确不做

- 不新建完整批执行器、审批系统或 CLI；
- 不调用模型，不改全局提供方，不把 Key 补进配置、报告或日志；
- `scope` 不是直接人类答复，本次不能用于 391、任何真实 Key 或已封存的旧批；后续启用必须来自新冻结计划的明确直接批准，不会自动放宽或复用旧批；
- 不弱化现有诊断脱敏，不跳过 native 校验，不改冻结的 390 六源、旧 tools、产品 backend/frontend、根文档、AGENTS 或配置。

## 公开回归

`backend/tests/test_reviewed_diagnostic_redaction.py` 只使用公开合成 fixture：临时 Store、一个真实存在的假 assistant provider 与加密假 Key、真实 `POST /diagnose`、假 Dify transport。覆盖：

- 旧 Guard 无新许可、`scope=None` 时期望与 391 相同的拒绝，0 次假 Key 解密、0 次原生 GET；
- 新 helper + 明确 scope + `ScopedDiagnosticClient` 通过真实诊断 API：正例 Task/run 均为 `advanced-chat`，保存合法 `message_id` / `id` / `conversation_id` / `mode` / `answer` 且不预置 `workflow_run_id`；假 Dify 按消息记录映射原生运行，断言 `remote_id_resolution` 的 message / conversation / workflow run 身份三元组与 3 次 GET（消息记录、运行详情、节点轨迹），报告与持久记录都不含假 Key（假 node.error 中放入假 Key 验证实际脱敏）；
- 其它 provider / secret 字段 / 阶段 / halted / Task / run / App / revision / env / `app_type` 不支持或 Task 与 run 不一致 / 普通或本地请求 / 错误 scope 类型 / 预算超限均拒绝；
- 上下文建立后环境绑定来源变化（环境与 run 一致地改到新绑定）仍因绑定快照不一致被拒绝；
- 成功与异常后上下文复位，预算、旧对象与密文保持不变。

正例只使用小合成图验证消息到原生运行的映射，不代表完整业务 graph 来源核验。

固定检查（只跑此新增测试）：

```powershell
E:/workSpace/dify-agent/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_reviewed_diagnostic_redaction.py
```

本地隔离通过不等于真实 Dify 平台或业务验收通过；本范围不声明 391 已恢复、真实 Key 已授权或两版平台已通过。
