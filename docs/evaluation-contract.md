# 试跑规则接口 v1

“运行”页面可新增、移除、编辑和保存样例，选择已保存样例试跑，查看当前修订汇总以及逐次运行记录。样例支持关键词、等值、JSON 字段和人工判断。规则检查通过不等于全部业务需求已验收；真实试跑需要目标 Dify 环境及对应应用的运行凭据。

`GET /api/tasks/{id}/test-cases` 返回 `cases` 与 `revision`。

`POST /api/tasks/{id}/test-cases` 接收当前 `revision` 与完整 `cases` 数组。保存推进修订，需求和配置确认失效；已有流程计划标为过期。每个样例为：

```json
{"id":"warranty","name":"保修回答","input":{"query":"保修多久"},"expectation":{"mode":"contains","target":"result","expected":["一年"]},"required":true}
```

`id` 可省略，由后台生成；`required` 默认 true。样例 ID 不得重复。

| mode | 规则 |
| --- | --- |
| contains | 指定输出路径为字符串，并包含 expected 的全部关键词。 |
| equals | 指定输出与 expected 严格等值，区分数值和布尔。 |
| json_keys | 输出为对象或严格可解析 JSON，含 expected 中全部字段。 |
| manual | description 必填；结果始终为 needs_review，交给人工复核。 |

`target` 使用点分路径，例如 Workflow 的 `result`、`data.summary`，Chatflow 的 `answer`。

`POST /api/tasks/{id}/run` 可传 `{"revision":当前修订,"case_id":"warranty"}`。后台使用保存的样例输入；若同时传入 input，它必须与样例一致。运行记录保留样例快照、实际输入、外部运行结果及 evaluation。规则失败记录为 failed；人工规则为 needs_review；规则通过为 passed。任务最多记为 run_completed，不自动改为全量业务验证通过。

`GET /api/tasks/{id}/acceptance` 返回当前修订和环境的样例检查汇总，只采用每个样例最近一次匹配记录。旧修订、其他环境、输入或预期不匹配的记录不算通过；后续失败或未知结果会替换之前的通过状态。没有必选样例不能视为全部样例通过。`all_required_passed` 只指必选样例声明的规则；`verification` 固定为 `declared_checks_only`，不自动确认完整业务覆盖。

`POST /api/tasks/{id}/runs/{run_id}/review` 接收 `revision`、`decision`（passed / failed）和非空 `reason`。仅可复核当前修订、当前环境中成功返回并匹配当前人工样例的记录。原始 evaluation 保持 needs_review，人工意见保存到 manual_review 和 review_history；修改意见保留历史。自动检查规则不能用人工意见覆盖。

编辑中的样例草稿会阻止构建、导入、运行及确认；切换面板保留草稿，刷新恢复已保存版本。保存相同样例不推进修订，保存修改后的样例须重新确认需求、配置并复核已有流程计划。自由试跑不计入样例通过数。
