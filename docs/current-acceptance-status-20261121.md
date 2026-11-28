# 363 当前需求与验收状态矩阵（2026-11-21）

2026-11-28最新：[395真实批](reviewed-run395-live-result-20261128.md)唯一执行后原版5/6规则及原生路径通过，缺号首轮误走范围外，4GET诊断后停止；无修改版/ZIP，完整双版与自主质量仍未闭合。新封存未来944、旧预算密文保持；396只读定位中，不重放已消费包。

2026-11-28最新：393精确脱敏适配器已验收，394独立剩余执行器源604e3c4/22组/实际run双生命周期隔离及原机只读冻结通过（190f3572/7aeb1bc0，12根926保持）。原391首例规则passed后技术停止不重放，完整双版真实/全自主质量仍未闭合；395后来获新直接批准并唯一执行停止；本机冻结本身没有真实Dify请求或真实Key读取。

2026-11-28真实补充：[391原版首次发布及首例Service规则通过](reviewed-run391-live-result-20261128.md)，随后原生诊断准备因读取搭建模型Key的脱敏范围冲突技术停止；13管理GET/登录1/资源各1/Service1，原生轨迹0/修改版0。926封存与旧预算保持，完整双版R仍未闭合，393/394本机修复和冻结完成，395已获新批准并因业务失败停止，396本机定位中。

2026-11-28补充：[390已审双图执行器本机实现](reviewed-dual390-local-result-20261128.md)通过根15组定向及实际两图编译/逐版13主题绑定；产品仍0.413，旧12根909保护。[原机只读冻结](reviewed-dual390-freeze-result-20261128.md)也已通过；[完整真实方案](reviewed-dual390-platform-plan-20261128.md)旧包后来在391获新批准并技术停止，完整两版仍未闭合，原R级不变。

2026-11-24当前补充：[0.413 Chatflow根Python手工样例](local-code-samples.md)已部署，147后端/构建/5界面/3真实受限本机容器核过；[388改版静态包](reviewed-candidate388-static-result-20261124.md)在新隔离副本正常保存r10/manual，与模型完整候选相同，原生workflow只两文案变化，原r8包保持。原版/改版静态交付已有；两版真实平台与完整自主原样质量仍未闭合，旧R不能因本次静态结果升级为业务通过。

2026-11-23后续：[385真实单句改版](isolated-modification385-live-result-20261123.md)已取得完整23节点候选，根严格核只改两处文案、其它图不变；0生产/Dify，未正式采纳或真实双版试跑。20已有新的真实内容证据、仍待采用和重确认；19原r7缺陷/manual纠正保持，21—22平台主线待完成，不把本次限定通过当全项目通过。未来909封存保护。

2026-11-23最新：[380已返回完整23节点原模型图](reviewed-planning380-live-result-20261123.md)，根发现类型错误被当缺号，未签收自主原样质量；[DS纠正后正常保存r8/manual](order-type-manual-correction-20261123.md)，原r7/model历史保留；[当前原图静态ZIP已下载核过](static-delivery384-result-20261123.md)。19仍R（完整生成已有真实证据，原样语义未过），20—22仍R（修改版和当前双版真实运行未完成）。后文377无图是旧轮结果，不覆盖本次进展。

2026-11-23当前产品：[379最终澄清核对](planning-clarification-consistency.md)由DeepSeek最小两文件实现，根58定向/三类型隔离API及保护部署过；当前0.412.0-4b3c27aad0a80a616364/298/PID34736，27Task/十二根/874/密文保持。真实模型是否减少重复澄清未观察；19—22仍按377无图结果保持R，不把新提示、本机检查或人工历史图当自主通过。

2026-11-23最新：[377实际调用](preserved-planning377-live-result-20261123.md)1模型返回needs_decision，无图停止；新settled0.003040692，原任务/账本/凭据及874历史封存保护过。自主19—22仍未闭合；下一379调查重复澄清实现选择，不把完整原文留存误当图或平台成功。

2026-11-23当前补充：[375实际批](autonomous-dual375-live-result-20261123.md)等根FAQ复核超时而停止，模型/资源/运行0；[377单次规划](preserved-planning377-plan-20261123.md)已由DeepSeek实现、根14组公开定向过，[精确冻结与独立审计](preserved-planning377-freeze-result-20261123.md)已过，只待一槽/.100的新直接改授。未真实验证新模型完整图，19—22仍未闭合。当前产品0.411.0-90c28f738d4306fbff75/298/PID12020；下面原0.410是历史矩阵当日版本。

2026-11-23补充：[独立371实际记录](autonomous-dual371-live-result-20261123.md)已核实：重连/FAQ和两访谈通过，第三规划needs_decision停止、无图/App/运行；当前自主19—22仍未闭合。程序保留了澄清与用量，不把模型误判当输入丢失，也不重放旧批。


2026-11-22补充：[独立366真实批](autonomous-dual366-live-result-20261122.md)获新直接批准后首次登录即停，登录1，管理/模型/新Task/资源运行0；未进入自主候选或两版试跑，下表R状态保持。旧337与本366均已消费，禁止重放。


- 运行版本：`0.410.0-23c94dbe89553f265c3b`；实现：`41ac27d`。本文件是当日摘要，不覆盖 `docs/acceptance-at01-record.md` 至 `docs/acceptance-at25-record.md`，也不修改旧 `docs/acceptance-mapping.json`。
- 依据：`docs/requirements-v1.0.md` 的 FR-01—48、AT-01—25、§6/§10/§11；`docs/deepseek-delivery-checklist-20261120.md` 的 32 项；`docs/BACKLOG.md` 339—365；HANDOFF 第 3 节；25 份 acceptance 记录头部。未通读源码、work/data、历史大报告。
- 级别沿用交付板：L=已有实现或部分本机/历史证据，须核当前项是否够用；O=指定离线/替身范围已验收，不计真实业务完成；R=当前真实链未闭合；U=需要有界核实缺口。级别不是完成率，L/O 不等于验收，R/U 不等于已确认缺陷。
- “交付项”是 32 交付板编号；多行可共用一个交付项，某行有证据不代表整项或整条真实业务通过。本机通过、替身通过和静态构建都不当实际模型质量。
- 下表只陈述当前证据边界；历史真实观察单独保留，但不能替代 19—22 当前自主双版。

## 第一张表：FR-01—48

| 编号 | 需求/现有行为概要 | 交付项 | 当前证据级别 | 证据 | 剩余/明确限制 |
|---|---|---|---|---|---|
| FR-01 | 创建任务须主动选类型和目标环境，支持尚未接通的环境 | 11、28 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[361复核](workspace-connection-recovery.md) | 真实环境切换、断连恢复和并发仅本机隔离；未接通环境只能产出待验证成果 |
| FR-02 | 每个任务独立保存需求、对话、材料、配置、运行、版本和成果 | 28 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[361复核](workspace-connection-recovery.md) | 临时任务不变、0写和真实HTTP 0是隔离证据；真实Dify断开后的任务隔离未观察 |
| FR-03 | 按用户指定类型生成、检查和导入，类型冲突提示且不静默替换 | 09、16 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[354能力边界](compiler-capabilities.md) | 类型适用性语义识别依赖模型；不能保证任意自然语言需求都被拦截 |
| FR-04 | 支持保存和继续单人任务，恢复阶段及待处理事项 | 24、27、28 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[361复核](workspace-connection-recovery.md) | 快照不是实际杀进程；真实关闭恢复、自然令牌到期和外部恢复未观察 |
| FR-05 | 文字及多形式材料入口，识别无法处理格式并说明替代输入 | 05 | L | [32交付板](deepseek-delivery-checklist-20261120.md) | 空表、纯图片Word等边界已修；OCR、图片理解和其它格式边界保留，上传不等于已理解 |
| FR-06 | 记录材料来源，区分用户要求、参考建议和助手假设 | 05、07、08 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[346来源新鲜度](material-source-freshness-review-20261120.md) | 真实语义来源判断、长材料截断和完整替换未验；合法引文不证明该条已被用户采纳 |
| FR-07 | 每份重要参考确认借鉴、保留指定部分或严格复现 | 06 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[344参考保留](reference-material-preservation.md) | 保留仅根code/template-transform节点完整配置；严格复现仅无容器、编译器完整表达的Workflow/Chatflow根图核心，节点/连接/features/变量/插件依赖须一致；容器/循环/定时/人工审核/原生Agent及未知结构明确拒绝；自动模型候选质量仍待真实核 |
| FR-08 | 使用标准说明单收集信息，按场景补问专项问题 | 01 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[340规则复核](rule-suggestion-adoption-review.md) | 真实模糊目标访谈稳定性未闭合；19当前自主原版候选仍为R |
| FR-09 | 关键规则缺失或矛盾时追问，给具体草案和例子，确认前标建议 | 01、02 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[340规则复核](rule-suggestion-adoption-review.md) | 建议和例子质量依赖模型；19自主真实访谈与完整候选仍为R |
| FR-10 | 材料、当前描述和历史确认冲突时指出影响、推荐并请用户裁定 | 07、08 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[345冲突撤销](conflict-source-dismissal.md) | 冲突检查须显式启用；长材料截断、真实语义冲突和事实正确未验 |
| FR-11 | 已确认内容可复用，新增要求只重新确认受影响部分 | 03、04、08 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[342连续改版](continuous-revision-review-20261120.md) | 真实连续改版语义保留未验；20当前自主改版候选仍为R |
| FR-12 | 形成可编辑最终需求说明，确认记录绑定具体版本 | 01、03 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[340规则复核](rule-suggestion-adoption-review.md) | 确认绑定和失效有本机证据；按用户委托由根代理逐项审查/主动采纳并留痕，不伪造人类决定；自主完整候选仍未闭合 |
| FR-13 | 集中展示模型、节点、参数、知识库和检索等具体配置 | 10 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[348配置理由](configuration-proposals.md) | 节点级理由语义质量未验；真实页面和平台配置未据此签收 |
| FR-14 | 每项关键选择说明理由，信息不足时建议并确认 | 10 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[348配置理由](configuration-proposals.md) | 结构校验不判断理由质量；单项修改和真实模型建议未现场验收 |
| FR-15 | 只引用目标环境已发现或用户明确提供的资源，未知标待建/待映射 | 11 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[349凭据来源](dify-credential-source-integrity.md) | 真实权限、资源存在性和ID核验未验；本机匹配不等于平台可用 |
| FR-16 | 新增、复用或修改资源前列动作、目标和影响并确认 | 03、21 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[349凭据来源](dify-credential-source-integrity.md)、[355导入暂停](import-pause-preflight.md) | 具体发布/Key/导入已有动作、目标、来源和变更保护，结构/来源本机已核；非结构化资源方案不据此推定逐项效果，当前自主真实批未闭合 |
| FR-17 | 发现版本或能力限制时说明可完成部分、缺口和替代方案 | 09、16 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[354能力边界](compiler-capabilities.md) | 能力目录不是目标环境权限探测；任意版本/资源组合未验 |
| FR-18 | 更换环境时重新核对类型、模型、库、插件、凭据和资源引用 | 11、24、26 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[359环境映射](workflow-environment-mapping.md) | 真实客户环境认证、版本探测、迁移和跨环境资源映射未验；登记版本不是实际探测 |
| FR-19 | 已明确知识库时核适用范围和可用性，多库时建议并确认具体库 | 12 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[350选库复核](multiple-knowledge-selection-review-20261121.md) | 真实选库理由、权限、正文和检索命中未验；固定指定FAQ不是选库质量证明 |
| FR-20 | 只有原始资料时承担可读性、重复、版本、矛盾识别和组织工作 | 13 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[351资料准备](knowledge-unsubmitted-refresh.md)、[知识库准备契约](knowledge-provisioning-contract.md) | 已具备原始资料可读性、重复/版本线索、分组与建库准备路线；真实整理/组织质量、成本和使用效果待观察，不把未证质量等同无实现 |
| FR-21 | 建议资料分组、知识库准备与检索配置，确认后执行可用操作 | 13 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[351资料准备](knowledge-unsubmitted-refresh.md) | 真实建库、索引、成本和客户知识命中未全面验收；ready不等于检索效果通过 |
| FR-22 | 业务事实冲突由用户裁定，不按文件日期静默决定 | 07、13 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[345冲突撤销](conflict-source-dismissal.md) | 真实语义识别和遗漏未验；来源合法不证明事实正确，不静默删除有本机证据 |
| FR-23 | 用代表性问题验证检索，区分检索无答案和检索失败 | 14 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[352检索复核](retrieval-grounding-review-20261121.md) | 四态和来源绑定有本机证据；真实片段相关性、资料不足判断和平台检索未验 |
| FR-24 | 按确认说明生成所选类型的流程、提示词、节点、变量和连接 | 04、06、15 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[342连续改版](continuous-revision-review-20261120.md) | 真实自主候选语义和平台质量未签收；19、20仍为R，不能以本地生成代替 |
| FR-25 | 支持目标Dify版本和类型的生成规则，并记录目标版本 | 15 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[353根图端口](root-edge-handle-validation.md) | 当前目标固定1.17.1/DSL 0.7.0；其它版本、复杂节点和任意DSL未验 |
| FR-26 | 检查YAML、字段、节点ID、连接、变量、类型和关键路径 | 15 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[353根图端口](root-edge-handle-validation.md) | 结构校验通过不等于可导入或运行正确；复杂分支和参考往返仍有边界 |
| FR-27 | 代码节点按业务规则生成并执行检查和样例验证 | 15 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[353根图端口](root-edge-handle-validation.md)、[固定C2真实观察](existing-batch-platform-live-result-20261027.md) | 已有固定C2等受控Workflow代码链真实观察和代码契约检查；当前自主售后完整链的真实Sandbox/执行仍待验，不写成全局没有代码执行证据 |
| FR-28 | 批量、分支、上下文、触发和审核采用目标环境支持结构 | 16 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[354能力边界](compiler-capabilities.md) | 仅已有受支持类型和受限执行能力；不宣称任意Agent插件、复杂嵌套或全组合通用成功 |
| FR-29 | 目标环境不可访问时可生成完整度明确的草稿或待验证DSL | 28、29 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[362交付包](delivery-bundle.md) | 静态成果不证明真实导入或试跑；当前自主主线未闭合 |
| FR-30 | 对真实数据、模拟依赖、待填配置和未验证节点保持标记 | 14、15、29 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[362交付包](delivery-bundle.md)、[模拟绑定](planning-mock-bindings.md) | 规划候选准入/发射已核模拟dependency与node_id存在，含容器ID和Agent位置；真实替换完成证据和订单接入资料仍待补，指南不等于已接入 |
| FR-31 | 有连接且获确认后在目标环境执行导入和资源操作，用实际回执 | 18、21 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[355导入暂停](import-pause-preflight.md) | 18仅指定页面替身O；21为历史技术证据，当前真实导入/发布/专属Key未验，需新批批准 |
| FR-32 | 对确认样例真实试跑，记录输入、预期、实际、状态和关键错误 | 18、22 | R | [32交付板](deepseek-delivery-checklist-20261120.md)、[AT-14真实C2](existing-batch-platform-live-result-20261027.md)、[337停止记录](autonomous-dual-chatflow-live-result-20261120.md) | 自主两版各六例七轮/原生轨迹/双ZIP未闭合；337停止包不是双版通过，人工386、受限410和固定C2不能替代19—22 |
| FR-33 | 信息不足、无检索结果、接口失败等行为建议确认并纳入样例 | 14 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[352检索复核](retrieval-grounding-review-20261121.md) | 异常处理有声明和本机检查；真实模型异常判断、资料不足和接口失败覆盖未验 |
| FR-34 | 根据错误自动修复明确小问题，并重跑受影响检查 | 23 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[355导入暂停](import-pause-preflight.md) | 特定自动修复和候选修复已有本机证据；成功返回但业务不符需人工；当前自主链真实效果待观察 |
| FR-35 | 反复无进展、需改方案或到投入上限时暂停并说明成败与下一步 | 23 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[355导入暂停](import-pause-preflight.md) | 阈值按任务已保存策略及具体批准范围生效；本轮未全面重验所有输入/类型，估算不保证账单硬限 |
| FR-36 | 支持暂停、补充信息后继续，暂停阻止新派发 | 23、28 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[361断连恢复](workspace-connection-recovery.md) | 不能取消在途请求；真实关闭进程、迟到结果和外部幂等恢复未观察 |
| FR-37 | 记录模型用量、耗时、重试和费用估算，说明依据或不可用项 | 21、24、32 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[AT-25用量分组记录](acceptance-at25-record.md) | 估算不是供应商账单硬限；真实轻量收益未实测；历史Dify报告金额0不当免费 |
| FR-38 | 当前任务可持续讨论、调整、生成和重新试跑 | 04、23、28 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[342连续改版](continuous-revision-review-20261120.md) | 20当前自主改版候选为R；真实连续语义保留、重新试跑和平台行为未验 |
| FR-39 | 以用户当前实际应用或最新DSL为基础，保留人工修改 | 25 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[358最新来源](latest-dsl-source.md) | 真实手改往返、发布和试跑未验；上传归属和最新性未在线核对 |
| FR-40 | 记录需求、配置、DSL、确认和验证结果之间的版本关联 | 04、08、25、26、27、29 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[362交付包](delivery-bundle.md) | 同版本关联有本机证据；真实外部副作用、跨环境关联和旧修订ZIP重下仍有边界 |
| FR-41 | 修改前保存可恢复版本，展示变化和受影响验证，旧通过不冒用新版本 | 04、25、27 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[360版本恢复](version-history.md) | 真实外部覆盖/还原另列；恢复后的真实导入、试跑和业务验证未验 |
| FR-42 | 环境或资源变化时重新核对依赖和测试状态 | 11、26 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[359环境映射](workflow-environment-mapping.md) | 配置失效和来源令牌有本机证据；真实目标资源、权限和迁移质量另验 |
| FR-43 | 模型服务可增删改名称、供应商、地址、模型和Key，后台实际调用 | 09 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[347配置完整性](provider-configuration-integrity.md) | 地址/Key/探测并发有本机修复；真实供应商各能力质量和连接错误体验未验 |
| FR-44 | 使用供应商适配器和自定义兼容接口，不兼容时报告 | 09 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[347配置完整性](provider-configuration-integrity.md) | 不承诺任意地址只填Key即可全功能；真实协议兼容和错误分类未验 |
| FR-45 | 分别验证文本、工具调用、结构化输出和图片处理能力 | 09 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[347配置完整性](provider-configuration-integrity.md) | 已有受控工具请求探测和独立能力回执，347修配置与Key同源捕获；探测不代表任意实际工具/插件执行，真实插件、图片能力和完整业务未验 |
| FR-46 | 区分搭建助手模型与Dify应用模型，费用和调用记录分别说明 | 10 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[348配置理由](configuration-proposals.md) | 模型分工和独立提醒有本机证据；节点级理由、费用展示和真实语义未验 |
| FR-47 | 考虑主模型、轻量任务和图片处理分工，失败按规则升级并留记录 | 32 | L | [32交付板](deepseek-delivery-checklist-20261120.md)、[轻量路由记录](acceptance-at25-record.md)、[365质量用量复核](quality-usage-review-20261121.md) | 当前仅cases可分工；默认不升级，已有可选限定一次JSON格式升级，默认关闭；真实路由、失败升级和优化收益未实测 |
| FR-48 | 控制上下文、重试和子任务数量，确定性检查优先由程序执行 | 32 | U | [32交付板](deepseek-delivery-checklist-20261120.md)、[AT-25用量分组记录](acceptance-at25-record.md)、[365质量用量复核](quality-usage-review-20261121.md) | 上下文/重试/子任务上限已有程序实现与本机检查：默认最近12条、compact历史24000字符/旧消息单项6000字符，不把字符当tokens；全链成功率、tokens、费用受控对比本轮未核；不承诺省Token或所有输入均有硬token上限 |

## 第二张表：AT-01—25

| 编号 | 需求/现有行为概要 | 交付项 | 当前证据级别 | 证据 | 剩余/明确限制 |
|---|---|---|---|---|---|
| AT-01 | 模糊目标时追问目标、输入输出和规则，不提前搭建 | 01、19 | L | [AT-01记录](acceptance-at01-record.md)、[32交付板](deepseek-delivery-checklist-20261120.md) | 新任务追问和拒绝有本机隔离证据；真实模糊访谈和19完整原版候选仍为R，386/410不能替代 |
| AT-02 | 用户不知道分类规则时提出规则和例子，确认后采用 | 02 | L | [AT-02记录](acceptance-at02-record.md)、[340规则复核](rule-suggestion-adoption-review.md) | 建议身份、来源和明确采用有本机证据；程序支持正常根代理采纳并留痕；实际模型建议质量和当前自主链未闭合 |
| AT-03 | 文档与参考DSL冲突时指出冲突并确认最终依据 | 07、08 | L | [AT-03记录](acceptance-at03-record.md)、[345冲突撤销](conflict-source-dismissal.md) | 本地上传和参考摘要链路有隔离证据；真实混合资料识别、长材料截断和完整冲突覆盖未验 |
| AT-04 | 参考程度未明确时询问借鉴、保留或复现并记录选择 | 06 | L | [AT-04记录](acceptance-at04-record.md)、[344参考保留](reference-material-preservation.md) | 三种选择、持久化、变更失效及96定向/正常API/实际App上传/选code/重编辑/重新准入/构建/保护部署已观察；严格复现和无容器根图核心的受支持构建已实现。容器/循环/定时/人工审核/原生Agent和任意DSL不在保证范围；真实模型候选语义质量仍待核 |
| AT-05 | 所选类型不适合需求时说明原因方案，等待决定且不自动换类型 | 09、16 | L | [AT-05记录](acceptance-at05-record.md)、[354能力边界](compiler-capabilities.md) | 类型边界和固定响应有隔离证据；真实语义识别、界面协商和Dify业务未验 |
| AT-06 | 只有原始资料时检查、提出整理建库方案，确认后执行可用操作 | 05、13 | L | [AT-06记录](acceptance-at06-record.md)、[351资料准备](knowledge-unsubmitted-refresh.md) | 上传、方案、确认和索引状态有本机证据；真实整理、索引、成本和知识命中未全面验收 |
| AT-07 | 多个知识库可选时提出选择理由并确认具体库 | 12 | L | [AT-07记录](acceptance-at07-record.md)、[350选库复核](multiple-knowledge-selection-review-20261121.md) | 具体ID选择、理由结构和跨任务拒绝有隔离证据；真实授权、正文、检索和选库质量未验 |
| AT-08 | 资料业务事实矛盾时保留来源、请用户裁定，不静默选一份 | 07、08、13 | L | [AT-08记录](acceptance-at08-record.md)、[345冲突撤销](conflict-source-dismissal.md) | 来源保留、裁定和持久化有本机证据；真实语义识别、事实正确和完整替换未验 |
| AT-09 | 简单聊天可用但工具能力不足时标记能力不足并给建议 | 05、09、16 | L | [AT-09记录](acceptance-at09-record.md)、[347配置完整性](provider-configuration-integrity.md) | 文本/JSON成功不提升工具状态、受控工具请求探测和独立能力回执有隔离证据，347修配置与Key同源捕获；探测不执行任意工具/插件，真实工具、插件执行和Dify运行未验 |
| AT-10 | 接口未提供且用户接受模拟时显式采用，标位置和真实接入待办 | 15、17、19 | O | [AT-10记录](acceptance-at10-record.md)、[32交付板](deepseek-delivery-checklist-20261120.md)、[模拟绑定](planning-mock-bindings.md) | 17指定离线双版路径为O；规划候选准入/发射已核dependency与node_id存在，含发射后容器ID和Agent位置，未填写不猜；语义真实接入未证明，订单接入资料仍待补，19仍为R |
| AT-11 | 未确认配置或资源操作时程序阻止执行并显示待确认内容 | 03、10、19、21 | L | [AT-11记录](acceptance-at11-record.md)、[32交付板](deepseek-delivery-checklist-20261120.md)、[355导入暂停](import-pause-preflight.md) | 确认缺失、资源变更失效、旧修订拒绝和具体发布/Key/导入的来源保护有本机证据；非结构化方案无统一逐字段明细，当前自主真实批和并发未闭，19为R |
| AT-12 | DSL变量引用错误时定位并修复、再检查，不删业务分支 | 15、23 | L | [AT-12记录](acceptance-at12-record.md)、[353根图端口](root-edge-handle-validation.md) | 双分支定位、手改后重检和分支保留有隔离证据；通用自动修复、真实导入和试跑未验 |
| AT-13 | 已导入但关键样例失败时标为需修复或阶段成果，不宣称完成 | 14、17、21、23 | O | [AT-13记录](acceptance-at13-record.md)、[32交付板](deepseek-delivery-checklist-20261120.md) | 17指定离线双版路径为O；任务总状态仍可能imported，真实全样例、导入轨迹和最终交付未验 |
| AT-14 | 批量任务部分失败时按确认策略继续或停止，输出失败项 | 16 | L | [AT-14记录](acceptance-at14-record.md)、[固定C2真实观察](existing-batch-platform-live-result-20261027.md) | 固定C2受控异常继续3成功/1预期失败已得真实观察；原生停止完整失败清单、并发在途取消、混合/嵌套通用继续未验，不写成全部批量通过 |
| AT-15 | 连续对话信息不完整时按规则追问并验证上下文行为 | 15、17 | O | [AT-15记录](acceptance-at15-record.md)、[32交付板](deepseek-delivery-checklist-20261120.md) | 17指定离线双版路径为O；固定响应只验执行和声明，真实模型追问、记忆配置、前端和最终业务未验 |
| AT-16 | 自动触发或人工审核能力不足时说明缺口和替代方案，等待确认 | 09、16 | L | [AT-16记录](acceptance-at16-record.md)、[354能力边界](compiler-capabilities.md) | 能力目录、缺口保存和专用人工入口有隔离证据；Webhook/插件/指定审核/邮件未适配，真实Dify未验 |
| AT-17 | 切换到客户环境时重新核对版本、认证和资源映射 | 11、24、26 | L | [AT-17记录](acceptance-at17-record.md)、[359环境映射](workflow-environment-mapping.md) | 本机失效和来源一致性有隔离证据；真实版本探测、认证/角色权限、资源映射和迁移未验 |
| AT-18 | 用户在Dify手动修改后继续时获取最新版本并保留改动 | 25 | L | [AT-18记录](acceptance-at18-record.md)、[358最新来源](latest-dsl-source.md) | 三方合并、冲突选择和来源重核有本机证据；真实手改往返、发布、试跑和上传最新性未验 |
| AT-19 | 修改配置或需求后相关确认与测试失效，重新确认和试跑 | 03、04、08、17、20、26 | O | [AT-19记录](acceptance-at19-record.md)、[32交付板](deepseek-delivery-checklist-20261120.md)、[355暂停](import-pause-preflight.md)、[360恢复](version-history.md)、[361恢复](workspace-connection-recovery.md)、[362交付](delivery-bundle.md) | 17/18指定Chatflow离线双版路径为O；当前证据还含355/360/361/362相关失效、恢复和交付复核；Agent、全部入口及并发本轮未全面重验，真实平台和20仍未闭合 |
| AT-20 | 执行中暂停并关闭程序时保存阶段和结果，恢复后不盲目重复外部操作 | 23、24、28 | L | [AT-20记录](acceptance-at20-record.md)、[361断连恢复](workspace-connection-recovery.md) | 暂停状态、预算unknown和重开恢复有隔离证据；快照不是实际杀进程，真实资源取消/幂等/结果核对未验 |
| AT-21 | 同一错误反复无进展或到上限时暂停、汇报证据和下一步 | 21、23、24 | L | [AT-21记录](acceptance-at21-record.md)、[355导入暂停](import-pause-preflight.md) | 重复失败阻断、一次许可和任务已保存阈值有隔离证据；只暂停匹配输入，本轮未全面重验所有输入/类型，估算不保证账单硬限 |
| AT-22 | Dify断开时可生成待验证成果，明确未完成导入和试跑 | 28 | L | [AT-22记录](acceptance-at22-record.md)、[361断连恢复](workspace-connection-recovery.md) | 连接失败/超时、成果下载和报告有隔离证据；分类依赖提示文字，真实断连完整交付和恢复未验 |
| AT-23 | 需求需要新建外部系统时提出方案和接入条件，不擅自扩大范围 | 16 | L | [AT-23记录](acceptance-at23-record.md)、[354能力边界](compiler-capabilities.md) | 关键词识别、方案待确认和来源门禁有隔离证据；真实范围判断、方案质量和外部接入未验 |
| AT-24 | 用户恢复旧版本时保存历史，以恢复版本重新确认和验证 | 20、27 | L | [AT-24记录](acceptance-at24-record.md)、[360版本恢复](version-history.md) | 恢复前快照、旧修订排除和重确认有本机证据；外部覆盖/还原另列，恢复后真实导入/试跑未验，20仍为R |
| AT-25 | 启用轻量模型分工时比较全链路成功率、总用量和费用，计入重试 | 32 | U | [AT-25记录](acceptance-at25-record.md)、[轻量路由记录](assistant-routing.md)、[365质量用量复核](quality-usage-review-20261121.md) | 仅cases可分工，默认不升级；已有可选限定一次JSON格式升级，默认关闭；同案例全链成功率、tokens、重试开销和真实费用受控对比未完成，节省未证明 |

## 当前真实主线与历史边界

- 当前真实未闭合的主线是 19—22：自主模糊需求访谈、完整原版模型候选、自然语言改版、真实导入/首次发布/专属Key、两版各六例七轮、14条Service/轨迹、逐轮原生诊断和双ZIP。FR-32为R，AT-01/10/11/19/24的剩余列指向20或19，不能把 L/O 行拼成通过。
- 337已消费stopped：直接批准后1登录、4 GET全200，FAQ文档列表后停止，产品模型、Task、资源、Service和运行均为0，具体拒绝分支未记录；338只修FAQ分页协议，不重放337。新真实批需独立范围批准，开发DS重发不扩大产品范围。
- 历史真实观察保留但不替代当前自主双版：人工386双版（[stateful-chatflow-live-result-20261029.md](stateful-chatflow-live-result-20261029.md)）、受限模型410单版（[complete-answer-platform-live-result-20261102.md](complete-answer-platform-live-result-20261102.md)）、AT-14固定C2公开继续策略（[3成功/1预期失败](existing-batch-platform-live-result-20261027.md)）和既有公开Workflow批次。它们证明当时链路，不证明当前自主售后双版；337停止包不是双版通过。
- 仍待真实证据：代表性材料和冲突语义、模型选配与独立理由、多库选择质量、检索相关性、环境迁移/客户权限、Dify手改往返、自然令牌到期观察；真实订单接口接入资料也仍待补，现有方案/指南不等于已接入。
- 能力边界：只按已有受支持类型和受限执行能力陈述；不宣称任意Agent插件、Webhook、复杂嵌套、全部批量模式或所有应用类型通用成功。
- 轻量分工：AT-25/FR-48为U；路由仅覆盖cases，默认不升级，已有可选的限定一次JSON格式升级（默认关闭）；真实全链成功率、总用量、重试和费用对比未做，优化收益未实测，也不承诺省Token。

## 后续队列（364已完成，365待根验收）

1. 364安装启动交接已完成实现e9459d8，按干净受控目录实际安装40锁包/前端构建，8脚本场景及缺venv中文、6快照过；原数据与同一运行快照保持。见[安装启动复核](installation-check-20261121.md)，不扩为所有平台或每种网络问题的证明。
2. 365质量、用量、费用与演示收口已提交[质量用量复核](quality-usage-review-20261121.md)，待根验收；验收并提交后关闭，无产品改动或新增等价测试。
3. 静态部分如无新可行动缺口，不新造代码或复制测试；本轮有界复核未发现新的可行动代码缺口，已知下一步集中真实主线和质量缺证，真实核验若暴露问题仍须修复，不代表所有代码已全验收。真实19—22仍按独立范围批准，新真实批先冻结独立范围再按既有批准规则执行，不重放337。矩阵不计算完成率。
4. 本文件结构/链接检查只核形式，语义结论另经Codex复核；矩阵不代表产品全验收。
