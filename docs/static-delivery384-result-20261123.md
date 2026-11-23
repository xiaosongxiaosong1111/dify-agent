# r8纠正稿：正常静态交付完成

第384项，2026-11-23。DeepSeek只读会话1ca3bd90-16f2-47c5-9787-d8a7f0456402正常返回0，核现有配置确认/构建/下载、已有计划改版与留存候选的正常路径。根以真实r8副本在隔离API执行，再在原机正常入口执行；无需产品补丁或部署。

## 实际交付

r8/manual（原r7/model图完整保留）。根按常规本机委托确认当前静态配置，仅核本机字段/图、非远端资源可用或副作用授权；正常POST configuration confirm→POST build→GET artifact→GET delivery-bundle，共4次本机Sierra请求，0模型/Dify/登录/资源/运行。

- 23节点/24边，全部图及纠正代码保持；三个LLM/分类/提取节点均deepseek-flash、thinking=false、temperature0.2、max_tokens512。
- 原机DSL SHA04175a5b3225232d94767b6b1ff4ab88fcdc5522c7e35b0ee60bb97e6361c397，与隔离正常编译逐字相同。
- 原机ZIP SHAcfac1d670ae0643018a4b071a67722f070f16cdb44c43875f9ae0c1c5f68a019。
- 包内dify-advanced-chat-r8.yaml、report-r8.md、integration-guide.md、README.md、manifest.json共5文件；manifest所有字节长度和SHA实际核过，报告保留manual来源，指南明确order_lookup模拟替换位置。
- 当前artifact.verification=static_only；manifest platform_checked/business_verified/network_requested/task_changed均false。没有App或运行，不把模板/片段行为检查当Dify业务通过，不把人工纠正当原模型自主原样通过。

本机产物开发克隆work/static-delivery384-original/sierra-advanced-chat-r8-delivery.zip与artifact-r8.yaml；用户原任务也可在Sierra正常下载。工作资料/供应商原图/报告ZIP均不入Git。报告可能包含公开演示需求与样例，分享前须按使用场景核对。

## 保护证据

隔离work/static-delivery384-isolated/report.json核正常确认/构建/下载、模型参数/稿件/manifest，禁外部HTTP/模型/解密Key，无生产写入。原机work/static-delivery384-original/report.json及agent-decision.json记录实际配置确认和4请求，代理决定不是新直接人类答复。

另外26/总27任务、所有密文资产、11旧隔离根、892封存、原r7/model快照/原版本前缀/三规划记录及全部五账本保持。唯一新增生产文件为该Task的artifact-r8.yaml；追加r8构建快照及当前配置确认记录。当前Task SHAdf157950695c641990aa4ef3fa2fff130b05c43f150633a1809f08103b17a5c7，预算仍b2472f1c98a48418bded9a9a73c776a14cc0b56bf0a6f04c21d87b2fea94bad0。原机0.412/298/PID34736不重建重启。

## 下一步设计取舍

正常plan/generate会把相对现有完整图的变化保存为replanning_review/last_candidate，保留正式原图、旧成果和模型原文；明确预览后POST plan采纳时来源manual，旧模型候选与规划记录仍在。这是审阅采纳边界，不因active plan_source不是model就新增自动采纳后门。DeepSeek提出的“model来源路径缺口”未据此采纳为产品缺陷；保留原图/候选来源即可如实说明代理主动修改或采纳。

旧377/374执行器硬绑r6无图无artifact，不可直接重跑、改参冒充新范围或复制整套框架。下一385拟在新隔离数据目录复制当前r8公开演示快照，明确只改无答案文案为“知识库暂无相关信息，请联系人工客服并提供商品型号。”，用现有一次规划/变化候选保留原语核修改版；生产27任务和原包保持。仅本机准备/公开替身先行；真实模型仍需375余一槽/.100的新明确改授，不能凭本次继续或配置确认自动调用。当前双版真实六例七轮仍缺，须后续具体新整批范围。
