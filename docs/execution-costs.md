# Dify 试跑用量与报告金额

版本 0.26.1（首批 0.26.0）。接口 GET /api/tasks/{id}/execution-costs 只读取本机任务记录，不请求 Dify、不调用模型、不触发试跑、不修改任务或助手预算。运行页和下载报告均提供独立视图。

## 记录与金额依据

- 覆盖任务全部已保存修订的试跑，包括成功、失败、待返回和结果未知记录。多轮案例逐轮列出，已完成轮次及已派发的待返回轮次都保留；不把失败金额丢掉。
- Workflow 读取 data.total_tokens。目标 Dify 1.17.1 的 Workflow 返回没有可靠的整体金额字段，不从输出业务字段或助手模型单价推算价格。
- Chatflow／原生 Agent 只读取 metadata.usage 的 total_price、currency 和 token 字段。三个大写字母币种分别汇总，不做汇率换算。返回价格为零明确显示，但不能证明供应商免费。
- 金额／币种／用量缺失或格式不可信均为未知，不能按零费用结算。token 字段冲突也不任选一值。模型价格变化、缓存、其他工具和供应商最终账单未核对。
- 缺少应用类型快照的旧记录仍可展示其实际保存的 metadata.usage 报价或 data.total_tokens，来源明确标为 without_type、类型保持未知，不套用当前任务类型。只读核对本机历史记录发现此情况后补充兼容；旧身份快照缺失仍不跨记录去重。
- 保存结果具备完整环境绑定、App UUID 和远端 Workflow／Message UUID 时，重复采集记录按同一执行合并，保留全部本机来源；币种／金额矛盾则从已知合计中排除并显示报价冲突。没有这些快照则保留为独立记录，不猜测为当前实例或擅自去重。原生 Agent 当前采集未必保存 Message UUID，会明确缺少完整身份。
- 最多展示最新 5000 条逐次／逐轮记录。超限明确提示部分汇总，不称为完整累计；按已知金额和未知次数分别展示。

## 与预算的区别

本页是 Dify 已报告金额的只读汇总，不是供应商账单、真实支付金额或全任务费用硬上限。Sierra 助手预算只累计已登记的助手调用；本页不改变它的上限和记录。建库、连接测试、外部工具账单、未保存的 Dify 执行仍未计入，跨服务总费用控制尚待开发。节点价格与整个运行价格没有相加，避免重复计算。

核对依据为本机 Dify 1.17.1 标签代码：api/fields/workflow_run_fields.py、api/core/app/apps/advanced_chat/generate_response_converter.py、generate_task_pipeline.py，及 Sierra 的 agent_stream.py 用量白名单。读取当前任务结果的实际结构兼容性单独记录，不把本机隔离检查当作供应商账单验收。

## 验证

backend/tests/test_execution_costs.py 检查多币种、旧修订／失败／未知、多轮、Workflow 无报价、显式零、无效价格／token、来源去重／冲突、截断和只读 API／报告。最终测试数、浏览器证据和部署以 development-status.md 为准。
