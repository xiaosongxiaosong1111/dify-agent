# Chatflow 对话记忆与连续自由试跑

基线：Dify 1.17.1；验证日期：2026-10-09。适用于 `advanced-chat`，不自动套用到 Workflow 或原生 Agent。

## 明确配置

`configuration.conversation_memory` 为布尔值，默认关闭；`memory_turns` 为 1—50 的整数，默认 5。只有主动启用、保存并确认配置后，编译才给 LLM 节点加入有限历史。关闭时不输出 `memory` 对象。Dify 的 `memory.window.enabled=false` 表示不限制窗口，**不表示关闭记忆**。

当前 Dify 会先查包含本轮尚未回答消息的记录，再移除该记录。因此历史窗口 N 映射为 `window.enabled=true,size=N+1`。运行时还受模型上下文容量限制，不能保证读取全部 N 轮；历史会增加输入 tokens。单纯开启记忆不会为知识检索自动改写指代问题，例如“它多久能退款”，这项策略需要另行规划和验证。

## 复用范围

`POST /api/tasks/{id}/run` 可提交 `conversation_from_run_id`。只允许当前任务、当前修订、当前环境的成功 Chatflow 自由试跑记录（排除固定样例运行），且结果必须有实际 `conversation_id`。不得与固定 `case_id` 或输入中的另一个 `conversation_id` 混用。

后端从保存记录解析会话 ID，并在本次记录中保留 `conversation_context`（来源记录 ID、会话 ID、修订、环境）。复用的是同一会话**当前已有历史**，不是回退到来源记录的时间，也不是创建分叉。任务变更或换环境后，旧记录不再可作为来源。固定连续对话样例链已在 0.10.0 单独实现，见 [多轮契约](conversation-cases-contract.md)；自由试跑不计入固定样例通过数。

缺少有效回答或会话标识的 Dify 返回记为未知，保留结果且禁止盲目重复派发，不能仅凭部分文本算成功。

## 实际证据

独立技术 Chatflow：`04a402bb-d51c-4036-8efa-4f3e06805865`；Dify App：`d731897e-cd0f-45b1-89ef-c7257282b360`。仅包含开始、DeepSeek LLM、回答，不连接客户系统。启用 5 轮历史，实际 Dify 导出为窗口 6。

首轮提供虚构编号 ALPHA-4796，回复“收到”；第二轮通过保存记录复用同一会话，实际回答 ALPHA-4796。两个请求共 216 tokens（输入 209、输出 7）。按已登记峰值价格保守估算 USD 0.0000711，不是供应商账单或整轮总费用；插件价格为 0 不代表免费。

四项实际界面检查通过：配置恢复、有效来源选择、会话及来源显示、自由试跑不冒充固定验收。证据位于 `work/memory-live-result.json`、`work/memory-live-ui-result.json`、`work/memory-dify-export.yaml`。单元测试的受控响应不算外部验证。

原生 Agent 的连续自由试跑已在 0.9.0 单独实现；不使用上述 Chatflow 记忆窗口设置，见 [原生会话契约](agent-conversation-contract.md)。
