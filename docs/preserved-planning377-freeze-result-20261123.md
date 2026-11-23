# 单次原规划377精确冻结结果（2026-11-23）

状态：已完成本机实现、14组根独立检查、原机精确pending与独立只读审计；**未批准、未消费、未真实派发**。

## 已提交与冻结身份

- 实现提交：ec8d7b706fb12b98230eb1ec33e14933d5fcb2e9；DeepSeek会话6f19d95a-893e-4ccc-919b-131d26e53809实现及按根反馈返工，Codex未接手产品代码。
- 唯一原机目录：E:/workSpace/dify-agent/work/preserved-planning377；五个源文件加plan/manifest，共7文件，无approval/attempt/worker-started/live-output。
- plan SHA256：8ef81075e59a60b9544e0c188e052c07c3bdd5ba3ae08ecbae2dc93564ec2c9f。
- manifest SHA256：7c9d6c37ddbb8076a7ad213cf313b7f86696c5ecd4471b1dfe76b1c12496ac8f。
- 运行0.411.0-90c28f738d4306fbff75/298文件，PID12020/原venv/精确snapshot backend匹配；未重建部署。可信源375 derivation.py@6fbd030与374 reuse_policy.py/storage_guard.py@4ac8e32，Git blob和当前源一致；五文件复制字节与已提交源规范LF一致，冻结自身按原字节校验。

## 实际验证

根固定命令`E:/workSpace/dify-agent/.venv/Scripts/python.exe tools/preserved-planning377/checks.py`完成14组：正常main API+假模型transport完整图保存退出；坏JSON、真正澄清、unknown用量各一次停止；二次/其他endpoint/Dify/同步/错provider拒绝；Task/旧prefix/预算/对象、来源/manifest/批准/消费保护；859同形封存loader实际SHA/越界反例、根及live-output迟到receipt识别；固定快照和精确venv/uvicorn/host/port/app-dir身份。不是全量测试，物理请求均0，合成来源不称真实模型通过。

另有耐久公开证据：r6→7/23节点/完整原文13892字符/三旧账本加一合成settled、None保持；退出后完整原文与图仍可读。根审查全部新代码，保留首次DS无最终输出与两次根检查失败，返工修复后才通过。

原机pending后根独立审计与实际verify_package/validate_start全部通过：生产27Task/10环境/2provider、其余对象、十二根/所有资产密文完全匹配冻结前基线；859各SHA相符。目标原r6完整task SHA4285b59a9f63d651d4869893fb460ec273b0c822250664248c36976140b10a84，budget SHAe1ac5db2cc3fca7ec1bde57a2fc5762f95c33b8b63c00fd0aa5a2a6c43306c4b不变；三settled合0.020125524、预算.600/policy1、execution_limits None、interview_attempts缺省均保持。没有解密Key、登录、模型或Dify请求，也没写真实Task。

本机证据不提交Git：work/preserved-planning377-root-check-v3.log、root-public-v1、pending.log、freeze-audit.json及before/after-audit.log；私有E:/workSpace/sierra-delegation/planning377-before.json和audit-planning377.py不含明文凭据，不覆盖重跑exclusive写入动作。

## 待直接改授的一次范围

拟仅把已消费375未派发三槽中的一槽及0.100 USD配置价预留明确改授这个独立批；最多1模型HTTP/6000输出tokens/120秒，0JSON修复/重试/后阶段。累计保守模型57/读1730/登录50/资源各30/Service148/模型估算账本3.355473652不增；375其它两槽/.200、116GET、资源各2、14Service、Dify估.100继续保留，不退借。预留不是账单硬限，实际调用仍计费。

复用既有r6和已存访谈，不新Task/库；正常API有效时会保存workflow_plan与model来源、revision+1/版本/两消息及一条新预算记录，配置仍未确认。仅目标Task与其ledger可变，旧需求/config/cases/所有历史和三settled保持；运行策略None不改，其余对象/资产/凭据/859保持。Provider唯一加密Key只在新直接批准和所有门核过后读取于进程内存；不读登录/Service Key。

完整原文/用量/图和安全失败原因保存后退出，根随后离线语义核对，无在线等待复核。坏JSON、needs_decision、静态失败、用量未知及任何异常立即停并保留实际账本，不重试/修图或续阶段。0Dify/登录/新资源/构建/ZIP/运行；有效原图不等于业务、双版或平台通过。

旧375已停止、封存且不可续跑；新直接答复必须精确绑定上述plan/manifest，当前“继续”和旧375批准不构成改授。具体方案见[preserved-planning377-plan-20261123.md](preserved-planning377-plan-20261123.md)。
