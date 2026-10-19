# 真实 DeepSeek 知识问答联调

日期：2026-10-09；Dify 1.17.1；DSL 0.7.0；工作台 0.5.0。

## 实际资源

- 官方插件：langgenius/deepseek，实际市场包 0.0.24。来源：[官方市场](https://marketplace.dify.ai/plugin/langgenius/deepseek)、[官方源码](https://github.com/langgenius/dify-official-plugins/tree/main/models/deepseek)。安装在现有 E 盘 Docker 数据中；助手与 Dify 使用同一个已授权 Key，但配置分开。不记录 Key 内容。
- 实际模型：langgenius/deepseek/deepseek / deepseek-flash，Console 声明 active、chat 模式；参数 Temperature 0.2、max_tokens 1024、thinking=false、top_p=1、response_format=text。
- 知识库：`27cd86df-4917-4942-a6f0-275c60e45b8f`；一份明确标注为开发联调用虚构商城政策的文档，经济关键词索引，1 个片段完成；不调用 embedding 或 reranker 模型。
- 知识库 Key 仅授权这一测试库。它能创建／读取该库文档，但不能列举全局目录；工作台采用管理目录显示已有库，不放宽 Key 权限。
- 任务：`48c91a68-eec9-47fe-a7be-13fd7d81cb5b`，r4；应用：`9f7a93fc-0432-429a-921f-b19d4c336986`。使用单独环境配置与应用 Key，原文本清理应用的 Key 和绑定不覆盖。

## 实际链路

真实 DeepSeek 生成六节点计划，复核固定业务与资源后确认本技术任务：start → knowledge-retrieval → if-else；空结果分支 → 固定 answer；非空分支 → LLM → 另一 answer。无 HTTP、代码、外部订单接口或额外模型。

Chatflow 开场白与两个建议问题、关闭思考及 1024 输出上限已在实际 Dify 导出中再次核对。此案例每个问题独立回答，不宣称多轮记忆已完成。

| 样例 | 实际回答 | 执行 LLM 数 | 结果 |
| --- | --- | --- | --- |
| 命中政策：退货期限 | 商品签收后 7 天内可以申请退货。 | 1 | 声明规则通过 |
| 无资料：固定分支 | 资料不足，请联系人工客服。 | 0 | 声明规则通过 |
| 订单进度需人工核实 | 具体订单和退款进度需要人工客服核实，不能根据本资料给出订单123的实际到账时间。 | 1 | 声明规则通过 |

## 费用证据

模型计划生成 1 次请求，按登记单价估算 USD 0.002885244。三次实际 Chatflow 运行中，两次调用 LLM，总返回用量 329 tokens（295 输入、34 输出）；按已登记 DeepSeek 峰值价、不计缓存折扣保守估算 USD 0.0001293。无资料分支实际执行轨迹没有 LLM 节点，模型 tokens 为 0。

Dify 插件返回的价格字段为 0，不能据此宣称供应商免费。这些数字不是实际账单或整轮总费用，不包含插件凭据验证可能发生的调用；供应商账单尚未核对。工作台的自动估算门禁只覆盖单次规划，不覆盖实际 Dify 运行预算。

## 安装修复

第一次文档上传实际上已创建文档，但 Celery Broker URL 的 Redis 密码仍是旧配置，导致索引派发失败。恢复中又发现 URL 序列化产生空地址，修正后用真实 Redis Ping 验证连接。只读确认现有唯一文档，并检查 worker 的 active/reserved/scheduled 及待处理队列没有该文档任务，再仅清理失败派发遗留的单个重试锁并恢复索引。未重复上传、未清空队列、未绕过认证。

## 验证与边界

- 三项必选规则实际通过，节点轨迹单独核对；declared_checks_only，不能推导为客户业务已交付。
- 193 项后台测试通过；前端 TypeScript／生产构建通过；7 项实际资源与结果界面检查通过，未保存浏览器测试草稿、未额外调用模型。
- 证据：work/rag-live-fixture.json、rag-dify-actual-export.yaml、rag-live-report.md、resource-ui-smoke-result.json。公开文档不包含连接凭据。
- 技术辅助脚本准备知识库、发布测试应用不等于产品已具备自动建库／索引／发布。Agent package、循环／迭代、复杂需求覆盖、多轮策略和手动 Dify 修改合并等仍未完成。
