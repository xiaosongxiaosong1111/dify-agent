# 从售后订单图准备缺号后的两轮样例

第223补上原§11缺订单号与AT15连续对话中的使用缺口：过去快捷入口只能准备订单命中、未知编号和缺号的单轮草稿，后续补号要手写。现在正常读取合成订单样例后，用户可在“缺号后接续的合成订单（可选）”明确选择已有编号，再次读取，即在原单轮候选外增加一个两轮候选。默认不选，原单轮行为保持。

首轮“我想查询订单状态，但尚未提供订单号。”，预期取当前模板保存的缺号回复；第二轮只给所选编号，预期取同一合成表的模拟前缀及原说明。第二轮不填conversation_id，未来执行时由已有连续样例执行器沿用实际返回的同一会话。用户选中后只追加未保存样例，再经正常保存入口形成新修订并使需求/配置确认和成果失效。查看/准备/追加不运行、不改记忆或上限，不把已有单轮误当连续样例；完整轮次、输入和预期均相同才拒绝重复。

只支持当前已确认、已构建、无手改差异的售后Chatflow固定模板。接续单号必须在原合成表中，对话记忆须已明确启用保存；这里不自动启用记忆、转换类型、猜订单或修改图。Workflow拒绝并说明不切类型，也不会要求其启用不支持的记忆。原版本、成果字节/摘要、依赖绑定和完整图检查继续适用；坏响应/错单号/错轮次/变源不显示部分建议。

原`POST /api/tasks/{task_id}/after-sales-cases-preview`增加可选`continuation_order_id`（null默认不增加，1—64位已存在合成编号）。响应回显该选择，rows仍保留原单轮，额外一条missing_then_found:编号带一个followups；最多10个合成订单时共13条，不是自动全部运行。准备不调用模型、Dify或执行代码，原task_changed/network_requested/model_called/code_executed/business_verified仍false。

两轮完整执行计划包含两次Service请求，每轮可能调用分类、提取等多个模型并收费；记忆已声明不证明分类/提取或真实上下文质量通过。实际次数/费用与资源批准仍按原范围，不能因为增加样例自动扩大。当前固定C1 Workflow任务4/4已满，既不是适用的Chatflow模板，也没有新增试跑授权，旧任务/旧失败不重放。

19新增/13原单轮共32项定向后端、类型检查/正式构建、6实际界面场景及视觉通过：正常选择/追加/保存、与旧单轮并存、完整两轮重复拒绝、关闭记忆/错第二轮单号/坏行/变成果来源拒绝。正常保存只在公开临时Store，旧单轮和全部旧运行/费用保持、确认失效；所有真实模型/Dify HTTP0。最初辅助夹具在改名后未重建，原成果一致守卫因此拒绝；按新公开名称正常重建后通过，原日志保留，不归为产品或真实平台失败。

2026-10-29原归属脚本部署0.355.0-2737a3da0a7775be88ae，289源/快照文件匹配，新PID35752（旧354/PID31388核验后仅stop/start）。实际页面仅GET核当前r17 Workflow不误展示Chatflow接续控件，原四运行及两样例保持；18Task/六费用/密文资产主Key/全部消费回执保持，部署仅server.pid变化，health与前端200。没有实际执行新的订单连续对话，不升级原25、Chatflow订单完整链或模型质量验收。

[安全结果](after-sales-continuation-result-20261029.json)。定向验证：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_after_sales_continuation.py backend/tests/test_after_sales_cases.py -q --basetemp work/NEW-ORDER-CONTINUATION
# frontend内先tsc -b、vite build，再回项目根
.\.venv\Scripts\python.exe tools/check_after_sales_continuation_ui.py --output work/NEW-ORDER-CONTINUATION-UI --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
```
