# 受托代理的全项需求复核

修改需求后，代理可在正常全项复核接口明确声明来源，避免被记录成用户新答复：

`POST /api/tasks/{id}/intake/manual` 在原revision、context_token、answers、acknowledge_review之外，支持actor和actor_note。actor为agent_delegated时必须有最多1000字的非空复核依据；默认local_operator保留原人工表单行为。

代理记录为agent_declared，保留review_actor、actor_note和完整答案。界面及系统消息明确显示“代理受托复核，非模型验证或人类签收”。后续规划来源带代理标识，答案及依据进入上下文摘要；再次修改或复核会保留原归档。actor是请求方声明，不是认证身份，也不自动证明业务含义正确。

保存仍产生未确认修订，需求和配置各自确认；不调用模型、Dify或运行应用。原主题、材料、修订及明确保存校验继续适用。默认用户复核不会被自动改成代理来源。

本次依用户常规可逆工作委托，将现有售后任务r4整理至r6：按原说明保存命中/无命中样例，选择原DeepSeek模型、thinking=false、温度0.2、最大512及FAQ/TopK3，并确认已齐全的需求。配置仍未确认，无正式计划、成果或新应用；资源文字仅是待审批方案，不是外部执行批准。原15任务、旧失败/回执、全部账本及凭据保持。
