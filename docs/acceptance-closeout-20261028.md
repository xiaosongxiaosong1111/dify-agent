# 原25项验收的当前收尾结论

2026-10-28，BACKLOG200；运行0.347。根代理按既有委托核对原25项和已有回执，未新增测试、模型或Dify请求。逐项结论已整理；**当前不能宣告项目全部验收或交付完成**，也没有伪造人类签收。

C2固定公开继续策略及失败项下载已有真实证据。C1新空任务真实链在198首轮结构校验停止，199仅离线修复并部署，真实新链尚未重验。C3本页消除“待C3”循环占位，逐项记录本次可支持的结论及未覆盖条件；它不把全部隔离记录升级为业务通过。C4当前未启用产品轻量路由，不宣称节省。

原需求§11的Chatflow、订单模拟、缺订单号和订单查询完整链仍未验证；当前优先的Workflow知识问答是先行案例，不能代替或删除原始要求。六组未适配扩展仍按RELEASE-CLOSEOUT列为明确限制，不自动开发。

| 原项 | 当前结论 | 已观察的范围 | 尚欠观察或明确限制 | 依据 |
| --- | --- | --- | --- | --- |
| AT-01 用户只给模糊目标 | 真实空任务候选结构失败；0.347修复尚未真实重验 | 198首轮未提前搭建，模型8项漏retrieval；199严格拒绝及替身追问链通过 | 独立批准的新空任务真实访谈能覆盖候选主题、只追问且不提前搭建 | [acceptance-at01-record](acceptance-at01-record.md)、[c1-blank-task-live-result-20261028](c1-blank-task-live-result-20261028.md)、[intake-candidate-topics](intake-candidate-topics.md) |
| AT-02 用户不知道分类规则 | 规则建议质量未验收 | 隔离建议→主动采纳→确认门禁通过 | 真实缺规则输入能给可选规则及例子，用户明确采用后才进入需求 | [acceptance-at02-record](acceptance-at02-record.md) |
| AT-03 文档与参考 DSL 冲突 | 语义冲突识别未验收 | 隔离来源与冲突裁定门禁通过 | 真实混合文档与DSL冲突能定位两处来源，裁定前不选边 | [acceptance-at03-record](acceptance-at03-record.md) |
| AT-04 参考程度未明确 | 三种参考方式的真实修改链未验收 | 借鉴/保留/复现选择和来源记录隔离通过 | 相同参考DSL分别核三种选择，修改范围与明确选择一致 | [acceptance-at04-record](acceptance-at04-record.md) |
| AT-05 用户所选类型不适合需求 | 类型协商质量未验收 | 三应用类型缺口提示和不自动换类型隔离通过 | 真实不适合需求能说明理由/替代，操作者未选择前类型不变 | [acceptance-at05-record](acceptance-at05-record.md) |
| AT-06 只有原始知识资料 | 限定建库路线，未覆盖任意整理与高质量索引 | 经济索引有真实库/文档技术证据；整理方案及确认隔离通过 | 只对批准资料验证可用路线/索引状态/命中，未适配路线明确受限，不重复旧创建 | [acceptance-at06-record](acceptance-at06-record.md)、[knowledge-provisioning-contract](knowledge-provisioning-contract.md) |
| AT-07 多个知识库可选 | 真实选库理由质量未验收 | 具体库ID选择及确认已有隔离记录；124复用指定FAQ取得命中/无命中 | 多个真实候选库须有可审查的选择理由/权限/资料范围，固定指定FAQ不代替模型选库质量 | [acceptance-at07-record](acceptance-at07-record.md)、[after-sales-two-version-delivery-20261025](after-sales-two-version-delivery-20261025.md) |
| AT-08 资料业务事实矛盾 | 真实事实矛盾识别未验收 | 来源保留/显式裁定/未知项阻止确认隔离通过 | 真实两来源相互冲突能同时列证据、追问裁定且不擅自合并 | [acceptance-at08-record](acceptance-at08-record.md) |
| AT-09 模型简单聊天可用但工具能力不足 | 工具能力有界，聊天可用不证明任意工具可用 | 0.291固定工具请求形状探测/来源绑定/失败标记隔离通过；无工具执行/回注/Agent循环，未以真实Key测试 | 选定模型/工具须有实际能力证据，未适配工具只报告条件，不能借聊天成功升级能力 | [acceptance-at09-record](acceptance-at09-record.md)、[RELEASE-CLOSEOUT](RELEASE-CLOSEOUT.md)、[工具请求探测](provider-tool-request-probe.md) |
| AT-10 接口未提供且用户接受模拟 | 订单模拟标记已实现，原始Chatflow订单整链仍未验收 | 0.271—0.274补标记/位置/接入待办及订单建议；隔离记录通过 | 原要求§11的Chatflow缺订单号/查询模拟/接口接入指南须在同一链验收，当前纯Workflow知识问答不能替代 | [acceptance-at10-record](acceptance-at10-record.md)、[core-delivery-focus](core-delivery-focus.md) |
| AT-11 未确认配置或资源操作 | 程序门禁隔离通过，当前真实新链未贯通 | 确认/修订/资源计划隔离门禁；124及196按显式确认发布 | C1当前新任务真实链检查需求/配置/资源确认，未确认时不派发，变源后旧确认不生效 | [acceptance-at11-record](acceptance-at11-record.md)、[after-sales-two-version-delivery-20261025](after-sales-two-version-delivery-20261025.md)、[existing-batch-platform-live-result-20261027](existing-batch-platform-live-result-20261027.md) |
| AT-12 DSL 变量引用错误 | 受限变量检查/修复，非通用自动修复 | 变量引用诊断及显式修正/重检隔离通过 | 代表错误图定位至变量/节点，显式修正后保留业务分支，并在批准平台核对结果 | [acceptance-at12-record](acceptance-at12-record.md) |
| AT-13 已导入但关键样例失败 | 阶段成果与成功分离有证据，真实失败修复链未验收 | 隔离关键样例失败不完成；198真实结构拒绝未建图且费用保留 | 独立真实关键样例失败→明确需修复→针对修复后重确认验证，导入/节点成功不能替代业务结果 | [acceptance-at13-record](acceptance-at13-record.md)、[c1-blank-task-live-result-20261028](c1-blank-task-live-result-20261028.md) |
| AT-14 批量任务部分失败 | 固定公开继续策略已核实，整体批量能力受限 | 196四项真实3成功/1预期失败，原索引1失败JSON/发布图绑定通过 | 固定C2缺证关闭；原生停止完整失败清单/在途取消/混合与嵌套继续不得宣称支持，扩展须另定范围 | [existing-batch-platform-live-result-20261027](existing-batch-platform-live-result-20261027.md)、[acceptance-at14-record](acceptance-at14-record.md) |
| AT-15 连续对话信息不完整 | 复杂对话缺参及上下文质量未验收 | 早期两轮真实技术链及隔离上下文/缺参检查 | 代表真实连续会话含指代/缺信息，须观察追问及上下文隔离；Workflow单次问答不替代Chatflow | [acceptance-at15-record](acceptance-at15-record.md) |
| AT-16 自动触发或人工审核能力不足 | 仅限定根触发/人工路线，复杂组合明确受限 | 环境缺口和等待确认隔离通过，有限根节点能力已有实现 | 限定路线需真实环境核对；复杂身份/邮件/表单/恢复和组合不默认可用，不把模板当已送达 | [acceptance-at16-record](acceptance-at16-record.md)、[RELEASE-CLOSEOUT](RELEASE-CLOSEOUT.md) |
| AT-17 切换到客户环境 | 真实客户环境迁移未验收 | 版本/认证/资源重新绑定隔离通过；当前原空间重连不是迁移 | 另一明确批准环境复核版本/权限/资源映射，旧确认失效，登记版本不当探测 | [acceptance-at17-record](acceptance-at17-record.md) |
| AT-18 用户在 Dify 手动修改后继续 | 受限代码/标题/布局往返有技术证据，非任意DSL保留 | 读取最新DSL及三方差异/冲突/保留隔离通过，受限独立App已有真实技术链 | 约定适配范围内验证外部手改后新要求保留，复杂未知节点/跨环境冲突明确阻止或协商 | [acceptance-at18-record](acceptance-at18-record.md)、[dsl-roundtrip-contract](dsl-roundtrip-contract.md) |
| AT-19 修改配置或需求 | 真实单文案修改有证据，非所有配置变更通过 | 124两版规划/显式采纳/新发布和四例轨迹；199隔离正常确认链 | C1新任务链重验当前修改失效/重新确认；其它配置变更按影响重验，不泛化固定单文案 | [acceptance-at19-record](acceptance-at19-record.md)、[after-sales-two-version-delivery-20261025](after-sales-two-version-delivery-20261025.md) |
| AT-20 执行中暂停并关闭程序 | 未知状态保留有真实证据，各阶段关闭恢复未验收 | 350发布unknown保留；196独立恢复没有重写旧unknown，198停止不重放 | 受控各阶段中断/重启核持久化与唯一派发；未知不得自动重发，已入队请求不保证取消 | [acceptance-at20-record](acceptance-at20-record.md)、[existing-batch-platform-live-result-20261027](existing-batch-platform-live-result-20261027.md)、[c1-blank-task-live-result-20261028](c1-blank-task-live-result-20261028.md) |
| AT-21 同一错误反复无进展或到达上限 | 次数/无进展门禁有隔离证据，非供应商费用硬封顶 | 各预算与停止隔离记录；198首次异常整批停，未用槽保留 | 业务进展须真实内容复核；在途/宿主费用未知，配置估算和Sierra试跑阈值不当供应商硬限 | [acceptance-at21-record](acceptance-at21-record.md)、[c1-blank-task-live-result-20261028](c1-blank-task-live-result-20261028.md) |
| AT-22 Dify 断开 | 真实登录失败停止有证据，恢复后的完整业务未验收 | 180/189登录或重连失败停，离线可保存待验证成果；196原App单次恢复成功 | 完整当前断连场景核未导入/未运行标记和恢复后的业务结果，不把连通当业务通过 | [acceptance-at22-record](acceptance-at22-record.md)、[public-batch-closeout-live-result-20261027](public-batch-closeout-live-result-20261027.json)、[existing-batch-platform-live-result-20261027](existing-batch-platform-live-result-20261027.md) |
| AT-23 需求需要新建外部系统 | 真实模型范围判断/方案质量未验收 | 新系统接入条件/范围外讨论及确认隔离通过 | 代表未知外部系统需求，实际方案须列条件/费用/人工影响，确认前不扩开发或创建资源 | [acceptance-at23-record](acceptance-at23-record.md) |
| AT-24 用户恢复旧版本 | 旧版恢复隔离通过，当前真实应用恢复整链未验收 | 版本历史、来源确认和失效规则隔离通过 | 当前界面选旧版恢复后保留现历史，重确认/新运行绑定恢复版本，不覆盖旧成绩 | [acceptance-at24-record](acceptance-at24-record.md) |
| AT-25 启用轻量模型分工 | 未启用，不宣称轻量路由质量或费用节省 | 本机无assistant_routing记录，默认enabled=false；隔离路由和用量含重试通过 | 仅若明确启用产品轻量路由，才按相同案例对比全链质量/全部调用和费用；Claude CLI委派不代替产品比较 | [acceptance-at25-record](acceptance-at25-record.md)、[lightweight-upgrade](lightweight-upgrade.md) |

下一步只针对可复现的现有问题开发。当前已知C1提示/诊断缺陷已修，尚欠真实模型遵从及主链质量证据；已消费354及全部旧批不重放，未派发4槽也不能自动借出。不存在可重复使用的真实批许可；新真实范围须先有可审查独立方案及明确批准。此页不申请新调用、不新造执行包，也不把预算尚未耗尽当作继续付费调用的理由。

机器可读的同一结论见[安全JSON](acceptance-closeout-20261028.json)。原历史25条记录与测试引用保留，各自只证明文中限定范围；引用数和结论数不能换算完成百分比。
