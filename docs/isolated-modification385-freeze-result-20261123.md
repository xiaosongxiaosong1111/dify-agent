# 385隔离改版精确冻结已核验

2026-11-23。实现9a1ab7f2c8b3342318bd5da6bf8aeab32b476766，根七组公开检查及原机prepare/独立after已实际通过。尚未新批准或真实派发。

## 冻结身份

- canonical：E:/workSpace/dify-agent/work/isolated-modification385。
- plan SHA256：6072ca425736389e822b2fd7fe56533f7a4d2fba1171dc15286bf10c44c57792。
- manifest SHA256：69c5502bed2befd6fa6c159f1ec7251a20202719a37b5ba8243af57039d36916。
- 七文件：tool.py、checks.py、README.md、source-pins.json、protected-892.json、plan.json、manifest.json；另有isolated-data。
- 没有approval.json/attempt.json/worker-started.json/live-output。没有模型Key读取、真实模型或Dify调用。仅原机快进工具文档，0.412服务未重建/重启。

## 独立原机核验

根私有audit-isolated-modification385.py before/after均通过，私有planning385-before.json和work/isolated-modification385-freeze-audit.json为exclusive实际证据，不覆盖重跑。

原27Task/10环境/2provider、原r8/manual/draft_ready的需求/配置/原图/静态artifact及五笔settled合0.037731216 USD、全部密文资产、11旧隔离根和892封存前后完全相同。当前生产无App/运行；服务0.412.0-4b3c27aad0a80a616364/298源与快照/原venv/PID34736一致。源三文件规范LF与实现Git blob/实际canonical逐字绑定，七文件清单实际哈希通过；892逐项、SQLite对象capture/12根、固定runtime源码+快照双份、实际进程归属都独立重核。

隔离数据只含Task/task_budget/provider/environment各1个对象、秘密表0；其本机新加密文件不是复制原credential-key，不包含模型Key。预算完整复制旧五条而不重算成新费用；只有未来唯一新增操作才算本批调用。Task仅修改output的一次无答案原句、唯一faq-no-answer期望、显式未确认/过期状态并保留旧intake到历史；完整原图、旧版本和三规划记录保持，生产不写。副本全部预期变更与原字段逐项独立比对通过。

根已实际逐项阅读13主题的拟代理准入回答：goal/audience/input/output/rules/knowledge/exceptions/tests/memory/dialogue/retrieval/external/conversation_state；新文案、模拟表、固定回复、五轮记忆、TopK3及两boolean状态均符合既定公开演示要求。私有planning385-reviewed-answers.json，SHAa4664708c612be80df75d2bd00e986cb619273a8ce80b7680aa389099a395f0c。是根代理受托审阅，不是模型新访谈或人类签收。

## 唯一拟改授范围

只把375剩余最后一槽和0.100 USD预留明确改授385，最多1模型HTTP/6000输出tokens/120秒，报价≤0.100（配置价预留，非供应商账单硬限）。原保守57模型/1730读/50登录/资源30/Service148/模型估算账本3.355473652不增，其余116GET/资源各2/14Service/Dify估0.100继续保留，旧unknown/settled/预留不自动借退。

在隔离副本正常手工准入后，唯一模型规划应保留完整变化候选及原文、usage、新费用；正式旧图不替换。仅no_hit_text.template与faq_llm.system_prompt内同一句变化：“知识库暂无相关信息，请联系人工客服。”→“知识库暂无相关信息，请联系人工客服并提供商品型号。”；其余完整图逐值/类型相同。正常replanning_review是留候选待根离线审阅，不能当模型语义/业务通过。

0生产写入/新生产Task/新库/Dify/登录/App/发布/Key/Service/构建/ZIP；Key只在新精确直接批准、全部门及唯一消费标记后在进程内存只读复用。坏JSON、未知用量、其它字段变化、真正澄清、截断及其它异常整批停，不修复、不重试、不接续。原r7模型图有类型缺陷、r8/manual已纠正，此批不是无错自主原图验收或当前双版平台证明。

旧375/377/380均消费，不接受旧问答引用、不重放。本记录依据AGENTS.md明确已消费批及资源费用边界，尚需新的直接答复，不能把“继续”自动当此具体改授。完整设计与公开检查失败/返工记录见[方案](isolated-modification385-plan-20261123.md)。
