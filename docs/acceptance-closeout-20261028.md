# 原25项验收的当前收尾结论

2026-10-28，初始BACKLOG200，最新219只按206/213/214既有公开回执更新AT-01/11/19/21/22；当前运行351，其它20项保留200原结论。本次未重新验收全部25项。根代理按既有委托核对原25项和已有回执，未新增测试、模型或Dify请求。逐项结论已整理；**当前不能宣告项目全部验收或交付完成**，也没有伪造人类签收。

C2固定公开继续策略及失败项下载已有真实证据。C1已观察206真实模糊输入追问；213原版r9新App/发布/Key及命中、无命中两例通过；214修改版r13从完整原模型候选正常采用并静态交付，第二App/两例尚未执行，217待新直接范围。旧失败、unknown和费用不改判。C3逐项记录当前可支持结论及未覆盖条件，不把隔离记录升级为业务通过。C4当前未启用产品轻量路由，不宣称节省。

原需求§11的Chatflow、订单模拟、缺订单号和订单查询完整链仍未验证；当前优先的Workflow知识问答是先行案例，不能代替或删除原始要求。六组未适配扩展仍按RELEASE-CLOSEOUT列为明确限制，不自动开发。

| 原项 | 当前结论 | 已观察的范围 | 尚欠观察或明确限制 | 依据 |
| --- | --- | --- | --- | --- |
| AT-01 用户只给模糊目标 | 真实模糊输入追问已观察，完整新任务两版链尚未闭合 | 206首轮真实模型返回九主题待补充及三个优先问题，根代理实际读源通过，未提前搭建；后续完整需求轮的batch误判已离线修复，213原版完成发布和两例 | 固定公开模糊目标的追问已有证据；不能扩展为任意模糊目标质量通过，修改版平台收尾仍待217新直接范围 | [acceptance-at01-record](acceptance-at01-record.md)、[c1-blank-task-live-result-20261028](c1-blank-task-live-result-20261028.md)、[intake-candidate-topics](intake-candidate-topics.md)、[c1-resume-live-result-20261028](c1-resume-live-result-20261028.md)、[c1-planning-live-result-20261028](c1-planning-live-result-20261028.md) |
| AT-02 用户不知道分类规则 | 规则建议质量未验收 | 隔离建议→主动采纳→确认门禁通过 | 真实缺规则输入能给可选规则及例子，用户明确采用后才进入需求 | [acceptance-at02-record](acceptance-at02-record.md) |
| AT-03 文档与参考 DSL 冲突 | 语义冲突识别未验收 | 隔离来源与冲突裁定门禁通过 | 真实混合文档与DSL冲突能定位两处来源，裁定前不选边 | [acceptance-at03-record](acceptance-at03-record.md) |
| AT-04 参考程度未明确 | 三种参考方式的真实修改链未验收 | 借鉴/保留/复现选择和来源记录隔离通过 | 相同参考DSL分别核三种选择，修改范围与明确选择一致 | [acceptance-at04-record](acceptance-at04-record.md) |
| AT-05 用户所选类型不适合需求 | 类型协商质量未验收 | 三应用类型缺口提示和不自动换类型隔离通过 | 真实不适合需求能说明理由/替代，操作者未选择前类型不变 | [acceptance-at05-record](acceptance-at05-record.md) |
| AT-06 只有原始知识资料 | 限定建库路线，未覆盖任意整理与高质量索引 | 经济索引有真实库/文档技术证据；整理方案及确认隔离通过 | 只对批准资料验证可用路线/索引状态/命中，未适配路线明确受限，不重复旧创建 | [acceptance-at06-record](acceptance-at06-record.md)、[knowledge-provisioning-contract](knowledge-provisioning-contract.md) |
| AT-07 多个知识库可选 | 真实选库理由质量未验收 | 具体库ID选择及确认已有隔离记录；124复用指定FAQ取得命中/无命中 | 多个真实候选库须有可审查的选择理由/权限/资料范围，固定指定FAQ不代替模型选库质量 | [acceptance-at07-record](acceptance-at07-record.md)、[after-sales-two-version-delivery-20261025](after-sales-two-version-delivery-20261025.md) |
| AT-08 资料业务事实矛盾 | 真实事实矛盾识别未验收 | 来源保留/显式裁定/未知项阻止确认隔离通过 | 真实两来源相互冲突能同时列证据、追问裁定且不擅自合并 | [acceptance-at08-record](acceptance-at08-record.md) |
| AT-09 模型简单聊天可用但工具能力不足 | 工具能力有界，聊天可用不证明任意工具可用 | 0.291固定工具请求形状探测/来源绑定/失败标记隔离通过；无工具执行/回注/Agent循环，未以真实Key测试 | 选定模型/工具须有实际能力证据，未适配工具只报告条件，不能借聊天成功升级能力 | [acceptance-at09-record](acceptance-at09-record.md)、[RELEASE-CLOSEOUT](RELEASE-CLOSEOUT.md)、[工具请求探测](provider-tool-request-probe.md) |
| AT-10 接口未提供且用户接受模拟 | 订单模拟标记已实现，原始Chatflow订单整链仍未验收 | 0.271—0.274补标记/位置/接入待办及订单建议；隔离记录通过 | 原要求§11的Chatflow缺订单号/查询模拟/接口接入指南须在同一链验收，当前纯Workflow知识问答不能替代 | [acceptance-at10-record](acceptance-at10-record.md)、[core-delivery-focus](core-delivery-focus.md) |
| AT-11 未确认配置或资源操作 | 原版真实确认到发布运行已观察，修改版仍仅静态 | 213恢复需求/原版模型计划/改单句代理声明实际复核；原版r9在确认后新App首次发布及两例通过。214修改版r13正常保存/配置确认/静态构建，未平台发布 | 当前修改版仍欠新独立平台阶段；隔离未确认拒绝门禁不等于已真实执行所有负例，原资源/修订边界不扩大 | [acceptance-at11-record](acceptance-at11-record.md)、[after-sales-two-version-delivery-20261025](after-sales-two-version-delivery-20261025.md)、[existing-batch-platform-live-result-20261027](existing-batch-platform-live-result-20261027.md)、[c1-planning-live-result-20261028](c1-planning-live-result-20261028.md)、[retained-plan-static-delivery-20261028](retained-plan-static-delivery-20261028.md) |
| AT-12 DSL 变量引用错误 | 受限变量检查/修复，非通用自动修复 | 变量引用诊断及显式修正/重检隔离通过 | 代表错误图定位至变量/节点，显式修正后保留业务分支，并在批准平台核对结果 | [acceptance-at12-record](acceptance-at12-record.md) |
| AT-13 已导入但关键样例失败 | 阶段成果与成功分离有证据，真实失败修复链未验收 | 隔离关键样例失败不完成；198真实结构拒绝未建图且费用保留 | 独立真实关键样例失败→明确需修复→针对修复后重确认验证，导入/节点成功不能替代业务结果 | [acceptance-at13-record](acceptance-at13-record.md)、[c1-blank-task-live-result-20261028](c1-blank-task-live-result-20261028.md) |
| AT-14 批量任务部分失败 | 固定公开继续策略已核实，整体批量能力受限 | 196四项真实3成功/1预期失败，原索引1失败JSON/发布图绑定通过 | 固定C2缺证关闭；原生停止完整失败清单/在途取消/混合与嵌套继续不得宣称支持，扩展须另定范围 | [existing-batch-platform-live-result-20261027](existing-batch-platform-live-result-20261027.md)、[acceptance-at14-record](acceptance-at14-record.md) |
| AT-15 连续对话信息不完整 | 复杂对话缺参及上下文质量未验收 | 早期两轮真实技术链及隔离上下文/缺参检查 | 代表真实连续会话含指代/缺信息，须观察追问及上下文隔离；Workflow单次问答不替代Chatflow | [acceptance-at15-record](acceptance-at15-record.md) |
| AT-16 自动触发或人工审核能力不足 | 仅限定根触发/人工路线，复杂组合明确受限 | 环境缺口和等待确认隔离通过，有限根节点能力已有实现 | 限定路线需真实环境核对；复杂身份/邮件/表单/恢复和组合不默认可用，不把模板当已送达 | [acceptance-at16-record](acceptance-at16-record.md)、[RELEASE-CLOSEOUT](RELEASE-CLOSEOUT.md) |
| AT-17 切换到客户环境 | 真实客户环境迁移未验收 | 版本/认证/资源重新绑定隔离通过；当前原空间重连不是迁移 | 另一明确批准环境复核版本/权限/资源映射，旧确认失效，登记版本不当探测 | [acceptance-at17-record](acceptance-at17-record.md) |
| AT-18 用户在 Dify 手动修改后继续 | 受限代码/标题/布局往返有技术证据，非任意DSL保留 | 读取最新DSL及三方差异/冲突/保留隔离通过，受限独立App已有真实技术链 | 约定适配范围内验证外部手改后新要求保留，复杂未知节点/跨环境冲突明确阻止或协商 | [acceptance-at18-record](acceptance-at18-record.md)、[dsl-roundtrip-contract](dsl-roundtrip-contract.md) |
| AT-19 修改配置或需求 | 原版与修改候选及静态差异已有证据，修改版平台结果未取得 | 124两版真实四例保持；213新空任务原版两例通过，第二模型只同步改两处相同固定提示，其余完整图保持，过窄执行包按约定停止。214正常采用完整原候选并静态交付r13 | 不修改旧批规则后续跑；217仅在新范围批准后验证修改版平台及两例，不能泛化为任意需求或配置修改通过 | [acceptance-at19-record](acceptance-at19-record.md)、[after-sales-two-version-delivery-20261025](after-sales-two-version-delivery-20261025.md)、[c1-planning-live-result-20261028](c1-planning-live-result-20261028.md)、[retained-plan-static-delivery-20261028](retained-plan-static-delivery-20261028.md) |
| AT-20 执行中暂停并关闭程序 | 未知状态保留有真实证据，各阶段关闭恢复未验收 | 350发布unknown保留；196独立恢复没有重写旧unknown，198停止不重放 | 受控各阶段中断/重启核持久化与唯一派发；未知不得自动重发，已入队请求不保证取消 | [acceptance-at20-record](acceptance-at20-record.md)、[existing-batch-platform-live-result-20261027](existing-batch-platform-live-result-20261027.md)、[c1-blank-task-live-result-20261028](c1-blank-task-live-result-20261028.md) |
| AT-21 同一错误反复无进展或到达上限 | 真实异常整批停止已有证据，非供应商费用硬封顶 | 198/206/209/213各已消费批按异常停止；213第四处根代理实际读源reject后未派发第二App，保留失败/settled/unknown及剩余槽，不自动重放 | 固定停止事实不证明任意自动修复的业务进展；在途和宿主费用未知，配置估算不当账单硬限，新范围不得借旧预留 | [acceptance-at21-record](acceptance-at21-record.md)、[c1-blank-task-live-result-20261028](c1-blank-task-live-result-20261028.md)、[c1-resume-live-result-20261028](c1-resume-live-result-20261028.md)、[c1-planning-live-result-20261028](c1-planning-live-result-20261028.md) |
| AT-22 Dify 断开 | 加密重连及原版后续平台链已观察，非任意断点恢复验收 | 180/189登录失败停止；196原App恢复成功；213一次加密重连证明原空间后，新原版App首次发布及命中/无命中两例通过，修改版停止不伪造通过 | 同空间该次重连不证明自然令牌到期自动续期或所有阶段断连恢复；当前修改版仍只静态，不把health200当业务通过 | [acceptance-at22-record](acceptance-at22-record.md)、[public-batch-closeout-live-result-20261027](public-batch-closeout-live-result-20261027.json)、[existing-batch-platform-live-result-20261027](existing-batch-platform-live-result-20261027.md)、[c1-planning-live-result-20261028](c1-planning-live-result-20261028.md)、[retained-plan-static-delivery-20261028](retained-plan-static-delivery-20261028.md) |
| AT-23 需求需要新建外部系统 | 真实模型范围判断/方案质量未验收 | 新系统接入条件/范围外讨论及确认隔离通过 | 代表未知外部系统需求，实际方案须列条件/费用/人工影响，确认前不扩开发或创建资源 | [acceptance-at23-record](acceptance-at23-record.md) |
| AT-24 用户恢复旧版本 | 旧版恢复隔离通过，当前真实应用恢复整链未验收 | 版本历史、来源确认和失效规则隔离通过 | 当前界面选旧版恢复后保留现历史，重确认/新运行绑定恢复版本，不覆盖旧成绩 | [acceptance-at24-record](acceptance-at24-record.md) |
| AT-25 启用轻量模型分工 | 未启用，不宣称轻量路由质量或费用节省 | 本机无assistant_routing记录，默认enabled=false；隔离路由和用量含重试通过 | 仅若明确启用产品轻量路由，才按相同案例对比全链质量/全部调用和费用；Claude CLI委派不代替产品比较 | [acceptance-at25-record](acceptance-at25-record.md)、[lightweight-upgrade](lightweight-upgrade.md) |

下一步是217待直接批准的独立零搭建模型收尾：复用r13图，正常确认校验构建后仅补修改版平台及两例，不重新访谈或规划。216执行器已隔离冻结，218流程页已有图引导已开发并独立验证、为保留217固定运行版尚未部署。已消费365及全部旧批不重放、不自动借退；原25项质量验收、Chatflow订单链及条件C4仍按各自缺证保留，不因本表更新宣告全项目完成。

机器可读的同一结论见[安全JSON](acceptance-closeout-20261028.json)。原历史25条记录与测试引用保留，各自只证明文中限定范围；引用数和结论数不能换算完成百分比。
