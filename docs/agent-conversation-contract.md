# 原生 Agent 连续自由试跑

0.9.0；基线 Dify 1.17.1，验证日期 2026-10-10。

## 输入与会话来源

原生 Agent 首轮仅接受 `input={query:string}`。追问同样提供 query，并在运行请求顶层提供 `conversation_from_run_id`。后端从本任务已保存记录解析实际 conversation_id，放入 Dify 请求顶层，不放入应用 inputs。前端在“运行”的“自由试跑会话上下文”中明确选择新会话或来源。

来源必须是同任务、当前修订、当前环境的成功自由试跑，不能使用固定验收样例、失败／未知／旧修订记录。不得同时指定 case_id 或手填另一 conversation_id；变量与文件输入明确拒绝。后台在派发前检查来源及输入，非法请求不产生运行调用。Workflow 不提供此入口。

运行记录保留实际输入及 conversation_context：source_run_id、conversation_id、revision、environment_id。复用同一会话当前已有历史，不回退到来源记录时间、不建立分叉。任务修改及环境变更使旧来源失效。重复选择较早记录仍续接同一实际会话。

## 结果和能力边界

继承 SSE 最终回答＋message_end 的终态要求。若返回会话与来源冲突，保留实际结果并标为未知，禁止盲目重跑；采集器知道远端 task_id 时尝试停止。未支持事件、连接中断、暂停与时间／输出上限仍按已有契约处理，没有自动请求重试。

Agent 的历史读取、上下文容量与压缩由 Dify 原生运行器管理。没有将 Chatflow 的 conversation_memory 或 memory_turns 编译为 Agent 设置，也不保证无限历史。继续对话增加输入费用。此次实现自由试跑；本版本正式多轮验收样例链、逐字实时展示、文件和人工介入尚未实现。0.10.0 已单独新增正式多轮验收，见 [多轮契约](conversation-cases-contract.md)；文件和运行时人工介入仍未实现。自由运行不计固定样例通过数。

## 真实验证

新建独立虚构技术任务 `3b517efe-fab5-4a1c-9b8d-aedb9c1e65ce`，修订 3；Dify App `5856ed13-06cd-4772-b50c-d217f78473df`。开发人员人工制定明确技术指令并确认后构建／导入，未请求自动规划，不修改既有应用，不连接客户系统，不请求工具。

真实 DeepSeek 首轮提供 AGENT-MEM-8632，仅返回“收到”；第二轮只问上一轮编号，实际返回 AGENT-MEM-8632。两轮 conversation_id 一致，第二轮正确记录首轮来源。后台实际用量共 5118 tokens（输入 5110，输出 8）；按登记峰值价保守估算 USD 0.0015426，不是供应商账单。Dify 插件返回费用 0 不意味着免费。验收汇总必选样例通过数仍为 0。

新增 15 项后台检查，真实记录的 5 项界面检查通过，不追加模型调用。证据：work/agent-conversation-live-result.json、work/agent-conversation-ui-result.json。

官方代码核对：本机标签 1.17.1 的 api/controllers/service_api/app/completion.py，ChatRequestPayload 支持 conversation_id；ChatApi 对 AppMode.AGENT 先检查会话归属，再将参数提交生成服务。
