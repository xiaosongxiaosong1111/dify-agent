# 自主双版337唯一真实批结果（2026-11-20）

状态为 stopped，未完成自主双版。直接用户批准来自 call_b4c700f1b4d24950a303b16fbe157440/q0“恢复并批准本批范围”，对应e09376a方案；实现2664eb7。新包只执行一次，无重放或续阶段。

## 实际记录

- 冻结plan：493122dd98eece938a53378a352d9b5010192afb191eb3e7783140a544ace4a5。
- manifest：321fc01ffe40917ed43abf3ff5f25535dedba3b4e8bfaee6f2c80621b636067c。
- 实际5次物理HTTP：POST登录200；GET应用列表200；GET当前空间摘要200；GET固定FAQ元数据200；GET该FAQ文档列表200。
- 计数：模型0、管理GET4、登录1、导入/发布/Key/Service均0。本机新Task0，26旧Task保持。没有进入FAQ片段、根内容复核或模型调用，没有产生双ZIP。
- 在faq_read阶段抛出RuntimeError并停止。旧执行器只保存异常类型和阶段，未记录安全栈位置，因此无法从已有回执认定具体拒绝分支；不追加外部读取补证。

## 已发现的本机协议缺陷

读取本机Dify Git标签1.17.1（8387590ace4a094de812b7847fc6a4c3a27cd52b）源文件而非重新请求平台：datasets_document.py构造has_more为len(documents)==limit，恰好满页也返回true；datasets_segments.py返回page/limit/total/total_pages，没有has_more字段。执行器却要求两类响应has_more严格false，公开替身也错误模拟相同字段，未暴露此兼容性问题。

这些是已确认的代码/协议差异，不把静态证据冒称已锁定本次真实异常的具体分支。第338项仅做本机修复与按实际协议的正负检查，不修改或续跑已消费337。

## 保护和账本

结束本机审计：26Task/10环境/2provider，原运行0.410.0-88f593682f0b5eb52500/297/PID44428保持；十一隔离根和733旧证据逐项通过。唯一授权变化是专用环境认证状态和两项Token密文，以及一条明确重连回执。旧任务、模型/费用/其它密文和素材保持，新App或Service Key0。

独立派发已发生，按批准保守上界登记模型51/管理1597/登录47/App发布Key各28/Service134、模型估算账本2.755473652（非账单硬限）。产品模型实际仍36，已观察settled0.214071000未增加；本批产品模型费用0，Dify应用内模型调用0，不推定宿主免费。8个未用模型槽和其它未派发资源/费用均保留，不自动退借或跨批使用。

原机证据位于 work/autonomous-dual337/{approval,attempt,post-stop-audit,seal-after-stop}.json 和 live-output/progress.json。封存副本和其摘要不提交Git，源码只记录脱敏结论。后续真实验证须先有新独立可审查范围并获明确改授或新增批准；用户已恢复本批不等于可重试失败阶段。
