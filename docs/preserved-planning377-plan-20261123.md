# 单次原规划与耐久结果377：本机准备方案

日期2026-11-23。状态：DeepSeek实现与根14组公开定向检查已过；原机精确冻结及独立只读审计已过，未批准、无新真实调用。

375已在FAQ根复核等待300秒后停止，模型零派发；它的原范围与失败均保留，不续跑。下一步先生成完整模型图，不在图产生前登录Dify或等待根在线回执。

## 具体行为

复用现有Task1154f0c0-5e01-4492-b5c7-97bfbbbc2a61/r6、两份实际已过访谈和原预算。调用正常POST /plan/generate一次，保留完整模型原文、用量、输入来源和结果。正常原规划接口有效时会保存workflow_plan、plan_source=model、版本及消息，并递增修订；这是待根验收的模型建议，配置保持未确认，不表示根已采纳业务，也不build/import/发布或运行。执行子进程在持久结果写完后退出，根可之后只读复核，不存在等待根回执的300秒失败窗口。

execution_limits保持None，不为规划设置12/45。原三条settled与.600预算/policy1、旧messages/versions/planning_runs/intake_history及needs_decision完整前缀保留，只允许本次正常模型调用的Task和预算后缀变化。其余对象、配置、凭据、资产和十二根/859旧文件保持。

## 拟议范围

仅拟将375剩3槽中的1模型槽和0.100 USD预留明确改授新独立批，最多1HTTP/6000输出tokens/120秒/无重试或修复。预留非供应商账单硬限。Dify/登录/新Task/知识库/App/发布/Key/Service/运行/构建新增全部0。保守模型57/管理1730/登录50/资源各30/Service148/估算账本3.355473652不增；375其余2槽/0.200及未用Dify、读取和资源范围保留，不退借。

坏JSON、真正needs_decision、静态不通过、费用或用量未知都保留实际原文/操作/预留并停止，不通过额外模型或模板修补。生成有效图只证明这次模型规划与静态准入，不能推导完整售后业务或平台通过。迟到根复核只读取已保存结果，不能触发第二次请求。

## 本机交付和真实门

DeepSeek限定最小worker/工具/检查/README，优先复用已审查函数与正常API，不改产品后端或旧批。根实际核完整差异、公开成功/失败/未知/重复和越界拒绝，以及结果可耐久读取；再提交实现并在原机做只读精确冻结/单次准入，绑定Task/预算/provider/runtime/来源及859保护。

新直接批准必须绑定新plan/manifest及范围，不能将当前“继续”或旧375答复当成改授。当前没有这次新模型授权，不读取明文Key或生成真实批准/attempt。旧375源与封存不改，结果见docs/autonomous-dual375-live-result-20261123.md。

## 本机实现验收

限定tools/preserved-planning377四个Python文件和README；后端/前端/旧工具不改。首次DS do无最终输出退出，根保留改动；之后同一会话按明确返工修正漏导入、UUID生成、正常API两条消息、历史source pin、实际封存相对map及晚到回执识别，最后精确解析进程app-dir，避免旧快照被误认。未用Codex接手产品实现。

根实际命令：`E:/workSpace/dify-agent/.venv/Scripts/python.exe tools/preserved-planning377/checks.py`，14组过，日志work/preserved-planning377-root-check-v3.log；不是全量测试。覆盖真实main规划入口+假transport的成功、坏JSON、真正澄清及未知用量，完整图/原文/账本/修订和None保护；二次/其它endpoint/Dify/同步/错误provider与越界对象拒绝；真实函数验证来源字节、859同形索引及SHA/越界反例、两处迟到receipt识别、批准/消费/manifest篡改和精确venv/uvicorn/host/port/app-dir。全部物理请求0，合成来源明确标注，不当实际模型质量。

根另保存公开正常API证据：修订6→7、23节点、完整原文13892字符、旧三ledger后新增一条合成settled；旧history/对象/资产及None策略保持，根离线可继续读取。根原机冻结前独立只读核目标task/预算精确SHA、三旧settled和859文件均匹配、27Task/10环境/2provider不变；当前实际PID12020/原venv/指定快照相符，未重建服务。

原机pending只生成精确plan/manifest并读取保护摘要、历史及进程身份；不读取明文Key、不写approval/attempt，不派发模型/Dify。最终摘要见[精确冻结记录](preserved-planning377-freeze-result-20261123.md)，plan8ef81075/manifest7c9d6c37；下一步仅待一次新直接改授，不能自动续旧375。
