# 原生 Agent Plan v1

缺条件时仅返回 `{"error":"缺少什么条件","needs_decision":[{"question":"请用户选择什么","recommendation":"可选建议","reason":"可选理由","experience":"可选体验变化","cost":"可选费用影响","manual_work":"可选人工工作"}]}`。`needs_decision` 可省略或为问题文字数组，最多20项、各文字最多2000字；不附加 `type`、`code`、`details`、`note`，不混入计划字段。建议不是用户确认，不改变应用类型或资源。

目标 Dify 1.17.1；App DSL 0.7.0。输出原生 `app.mode: agent` 及 `agent_packages`，不能输出 Chatflow 或旧 `agent-chat` 替代。

文本范围只允许以下三个字段：

```json
{"schema_version":1,"scope":"text","system_prompt":"明确任务、规则、缺条件处理和输出要求。"}
```

资料问答范围必须显式使用以下形状（示例中的 ID 不能当作实际资源）：

```json
{"schema_version":1,"scope":"knowledge","system_prompt":"回答资料问题前检索政策资料；仅用实际检索支持的事实，无资料时明确说明。","knowledge_sets":[{"name":"政策资料","description":"用于回答本次已明确的政策问题。","dataset_ids":["这里必须使用 configuration.dataset_ids 中的实际 ID"],"query_mode":"generated_query","top_k":3}]}
```

知识集 1—5 个，各集名称非空、唯一且最多 100 字；用途非空且最多 2000 字。各集知识库 ID 非空、唯一；全部知识集 ID 的并集必须与配置页所选 `dataset_ids` 一致，不能漏掉所选库或编造新库。`top_k` 为 1—20 的整数。当前明确采用多库检索、关闭重排、不设阈值／元数据过滤；这些额外策略字段未适配，不能带入后忽略。模型自主生成检索词，检索是 Agent 可调用能力，**不是每轮必检索的确定性节点**；如业务要求必检索及确定性空结果分支，应先说明这项差异，必要时由用户主动选择 Chatflow，不能自动改类型。

支持系统指令、实际插件模型与参数、开场白、建议问题和上述知识集方案。需求仍须明确八项，方案必须保存并由用户确认配置。计划变更推进修订、失效配置确认和旧产物；需求／材料变更令计划过期。模型建议不等于业务完成。

自定义 Dify／CLI 工具、文件、Skills、人工介入和自定义记忆预算尚未适配。发现这些必要条件应返回 `error` 说明限制，不能删掉或改成纯文本任务。文本范围中的非空知识库配置、知识集范围中的未确认 ID、Chatflow 记忆开关、资源提及、Workflow 变量引用及额外计划字段会阻止构建。

**部署内建能力**：Dify 1.17.1 原生 Agent 配置层会提供配置 CLI，并由部署控制沙箱终端。因此空自定义工具列表不代表完全没有运行时工具。DSL 不包含主机执行命令、凭据或虚构资源；代码不会由本工作台在主机执行。导入后仍须核对目标部署内建能力、发布应用、开启该应用 API 并配置专属 Key。

模型 Provider 必须是实际的 `author/plugin/provider`。`response_format` 的 `text`／`json_object` 映射为原生对象 `{type:...}`，其他已明确扩展参数保留；无法适配的值报错，不能忽略。

静态检查、真实导入、真实运行和固定样例验收分开记录。当前没有完整 Agent 自主工具循环和费用硬限制，不能据此声称复杂 Agent 全覆盖。
