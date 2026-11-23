# 385隔离单句改版：独立一次模型核对方案

2026-11-23。本机实现与根七组公开检查已通过，[原机精确冻结及独立审计](isolated-modification385-freeze-result-20261123.md)已通过，没有新的真实调用批准。本项不是旧375/377/380批的续阶段。

## 当前基础与目的

原生产Task1154f0c0-5e01-4492-b5c7-97bfbbbc2a61为r8/manual/draft_ready，已生成23节点静态图和5文件ZIP；原r7模型图及类型错误、DS单字段纠正的来源和五笔费用都保留。原模型无错自主原样质量未通过。本项只验证当前纠正图的自然语言单句改版，不把它重新包装为原模型无错生成。

仅把两处无答案文案从“知识库暂无相关信息，请联系人工客服。”同步改为“知识库暂无相关信息，请联系人工客服并提供商品型号。”：no_hit_text.config.template整句替换，faq_llm.config.system_prompt内原句恰好一次替换，其余完整提示、图结构/顺序/类型/边/代码/状态/配置逐值不变。尤其保持已纠正的订单类型检查，不把其它改动解释为等价后放宽。

## 拟议真实范围

拟将375仍保留的最后1个模型槽及0.100 USD预留明确改授本独立批，最多1模型HTTP、6000输出tokens、120秒、配置价预留≤0.100；预留不是供应商账单硬上限。不增加保守57模型/1730管理读/50登录/资源各30/Service148及模型估算账本3.355473652。其余375的116GET/资源各2/14Service/Dify估0.100保持、不自动借退，旧unknown/settled和其它预留不动。

0生产写入/新生产Task/知识库/Dify/登录/App/发布/运行Key/Service/构建/ZIP。本机先在新独立数据目录复制公开演示Task、原预算及provider/environment元数据，模型Key不复制；只有新的直接批准绑定最终plan/manifest、通过全部门且写唯一消费标记后，才将原选定provider加密Key只读解密到进程内存。

隔离副本仅明确修改需求output及唯一无答案样例期望，旧intake记录保留；正常agent_delegated逐主题准入和需求确认，是代理复核，不是新模型访谈或人类签收。完整旧图为改版基线。正常plan/generate对变化候选应保存完整last_candidate、原文/usage及唯一新账本记录，replanning_review是预期停留状态；不替换正式图、不自动采纳、无后续阶段。根在进程退出后离线核全文/候选语义。坏JSON、未知用量、真正澄清、超两字段改动、截断或其它异常整批停止，不修复/重试/接续，费用或unknown保留。

## 来源与保护

仅新增tools/isolated-modification385的tool.py/checks.py/README.md，固定复用ec8d7b7中377的只读capture及单次Boundary；没有复制旧整套执行器或改产品。固定0.412.0-4b3c27aad0a80a616364/298源与快照、完整content SHA及所属原venv/正确app-dir/PID；prepare与实际准入核相同来源。旧377的859+14+索引=874，再加380的17+索引=892全部实际哈希保护；原生产和11旧隔离根按数据库对象/密文/资产capture核，不忽略WAL对象变化。

当前Task SHAdf157950695c641990aa4ef3fa2fff130b05c43f150633a1809f08103b17a5c7；budget SHAb2472f1c98a48418bded9a9a73c776a14cc0b56bf0a6f04c21d87b2fea94bad0；现图SHAdd71f629c0d6a1e82d8e88aa424341fbe751369fbe0cedf19a9f1b5f44198c69。原27Task/全部凭据/原静态包/旧失败与费用保持。专用canonical为E:/workSpace/dify-agent/work/isolated-modification385；提交后先只读prepare、独立审原机clone与实际源绑定/保护，再公布精确摘要请求一次直接改授。尚未冻结的摘要不预先批准。

## 实际本机验收与未完成项

DeepSeek同会话1ca3bd90-16f2-47c5-9787-d8a7f0456402：首do38503可能超时exit2只留两文件，fix1终端91151正常0但CLI自修后检查仍失败；根发现并交fix2（69498正常0/CLI检查过）及CLI退出码fix3（21743正常0/CLI一次过）。根完整差异/源与七组公开检查work/isolated-modification385-root-v4.log实际通过：来源与提交/伪造canonical拒绝、SQLite与892门、审批互锁、严格两文案/runtime双源、目标预算前缀/最多一条、正常API与四类失败、真实子进程CLI拒绝。合成传输物理外部请求0。初次失败及旧CLI拒绝却exit0的反例日志保留，不当一次通过。

原机prepare/独立freeze审计及最终plan6072ca42/manifest69c5502b已通过，七文件/隔离四对象/0秘密表，13主题拟代理回答根已实际逐项审阅；直接新批准及唯一真实调用尚未发生。七组通过不等于模型能保留完整图，更不等于Dify或双版业务通过。源码实现约924行（运行/源/保护/单次适配），检查约348行，超过最初预计，已核必要的具体守卫而不以压缩代码删检查换数量。后续优先闭合改版及平台主线，不继续扩工具框架。
