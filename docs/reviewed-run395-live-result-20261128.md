# 第395项真实结果：原版五例通过，缺号首轮误走范围外（2026-11-28）

用户call_0821a5e8b8c64956bc8d63d2acd7901c/q0直接批准后，使用独立reviewed-remaining394包，正常approve/run各执行一次。绑定源604e3c4、plan190f357228611bcb7ffd87dd7da496709763fab1ab754a785148025d12003a02、manifest7aeb1bc0b6cdd2e1bcbdd0480c1adb6084d1e86c230d0c3182cd5ad791055d39。本批已消费、业务失败停止，不重试、续阶段或重放。

## 实际完成与停止

- 复用现有App/Key/首例，首例Service未重发，已成功补其原生轨迹；正常内存脱敏/原生读取/执行图与发布图/身份链在实机可用。
- 原版六例中的前五例（含复用首例）规则和要求节点路径通过。最后missing-then-order首轮输入“我想查询订单状态，但尚未提供订单号。”技术success却返回范围外答复，未索取订单号；多轮自动规则failed，DEMO-001后续轮按正常停止规则没有发出。
- 已按同批批准的唯一业务失败例外读取该轮4GET并保存诊断，随后停止。原生图matched、远端succeeded；实际路径start→entry_probe→consume_wait→pre_route→classify→out_of_scope_text→answer_out_of_scope。没有ask_order_no/request_wait。失败run c571cefa-e2b7-4200-a285-3c19104aa3fd，native914d1531-08a9-4303-92e2-7723a6bff115。
- 实际26管理GET（含失败轮4）、登录1、新Service5/新启动5、物理HTTP32；所选助手Key仅内存脱敏6次，Sierra模型0、新Task/资源0。共6份原生诊断，其中5成功路径和1失败轮报告；修改版未开始，ZIP0。不能把前五例当完整双版或业务验收。

仅从路径无法断言模型为何这样选择。根已独立核已保存公开配置与实际编译节点：instruction/query selector/类别ID与名称及faq→retrieve、order→extract、out_of_scope→out_of_scope_text逐值保留。下一396交DeepSeek核分类文字与前置query/状态，区分代码问题、语义冲突和未知模型理由；不改期望或新发模型/平台请求。

## 保护与费用

独立本机只读审计通过：原27Task/其他旧对象/Provider与运行Key及保存登录凭据密文/资产、原policy1/12启动45分钟/None、整个五项Sierra账本、11旧隔离根与926封存保持。只有本批允许的连接console token/csrf密文更新及1认证回执；旧首例除唯一来源绑定diagnostic外完整摘要保持，原图/需求/配置/案例/旧消息前缀保持，原始import/publish不重做。工作进程保护结果也已保存，非失败后的推测。

当前r8/manual/run_completed，Task SHA `6225fa08b9918d69fa8ac537651aea3d73b00b5a44bef54df2516fd1515f6909`，预算`b2472f1c98a48418bded9a9a73c776a14cc0b56bf0a6f04c21d87b2fea94bad0`，环境`0e196f559d71b9a542fe905914d0a26220c6ac9dfd466e67af69c7d48cca868b`。累计该Task已有6次启动/12上限，不重置。旧391/395均保持消费状态。

五个新Service报告共5465tokens（prompt5243/output222），各total_price="0" USD；这是Dify报告，不代表免费或完整供应商账单。旧391估0.100与本395新增估0.100都保持，不释放或借用。保守模型57/读取1730/登录52/资源各30/Service148/模型估算账本3.355473652 USD；剩77GET/资源各1/8Service/6启动及8次仅内存读取许可不自动跨批使用。

原机`work/reviewed-run395-after-live-audit.json`及克隆同名JSON/log，私有audit-reviewed-run395-stopped.py已成功执行一次，不覆盖回执或重跑。P/work/reviewed-run395-seal-after-review.json直接17成员（16canonical+审计），SHA `d8711a5a6fe2ed8203856476f0507b4c72db27a91f9fe499d864f62e81764083`；加自身18及旧926，未来944保护。新索引在canonical外，旧包不加成员；批准/attempt/worker/进度/失败、旧图和历史原文均保留。不再发送任何失败批远端诊断请求。
