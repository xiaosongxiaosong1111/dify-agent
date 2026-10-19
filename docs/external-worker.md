# 使用本机Claude Code分担开发

用户在2026-10-18明确要求将独立简单工作交本机Claude，我负责拆解、边界、审查、集成和验收。本文件描述开发协作，不是把Claude接入Sierra产品的模型服务，也不是Codex内置subagent换模型。

## 实际连接

本机Claude Code 2.1.302。现有用户配置指向局域网192.168.0.224，ANTHROPIC_MODEL=deepseek-flash；本次执行回执也为deepseek-flash。认证仍使用原客户端配置，不复制密钥、不改账户或全局设置。不能把客户端名称当作底层Claude官方模型或订阅额度。

--restricted会忽略这台机器依赖的用户env认证；首次任务API耗时和CLI估算费用均0，没有候选。排查后在safe-mode下保留原认证，工具清空、MCP清空、插件关闭、禁会话保存／自动更新与非必要流量，追加一次启动后成功。任务只有公开合同，不需要读源文件；执行器只能把代码返回为候选，不直接写生产或部署。使用短系统指令，避免复制长聊天。

## 第一次分工与审查

任务输入work/claude-delegation/history-node-details/task.md，3038字节；资源说明resource-plan.json。执行器编写VersionNodeChanges.tsx纯展示组件，主Agent编写节点比较API、边界测试和父组件集成。接口使用1基位置和固定字段标签，不传实际任务、材料或凭据。

回执authenticated/receipt.json：1轮、74.71秒、输入1103／输出18830 Token；型号deepseek-flash，成本依据unknown。CLI报告0.476265 USD仅为估值，不能当作网关账单，不声称实际便宜或省了多少总Token。主Agent也有拆解、审查、验收开销；后续须按实际成功率、返工和两边用量评估。

主Agent逐项阅读候选，确认无网络／工具／存储／HTML注入接口／副作用，合同、位置、枚举、整数及遗漏数校验完整。候选在Windows写盘CRLF，核对规范化原文本SHA再以原始LF安装；生产组件SHA与模型返回原文相同，见authenticated/review.json。27项本机组件验证／纯渲染和20项浏览器隔离检查通过，另有210项相关后台回归；尚不能把它当作真实Dify或客户验收。

## 后续任务方式

独立组件、样式、明确的小功能或文档可委派；每次给目标、精确接口、指定产物和验收条件，只给必要资料。复杂设计、共享契约、凭据、资源与确认机制由主Agent把关；不允许两边同改文件，不让执行器直接发布或操作Dify。候选先留E盘工作目录，审查后再采用。模型费用与Codex额度分开；本次CLI预算参数1 USD、180秒进程上限，不保证网关实际计价或订阅额度硬上限，不自动重发、买额度或更换账号。

本次CLI行为参考官方文档：[CLI参数](https://code.claude.com/docs/en/cli-reference)、[环境变量](https://code.claude.com/docs/en/env-vars)，并用本机help与真实回执核对。实际部署状态以development-status.md为准。


本轮已部署0.191.0-a5ba91622fd3bd94dcfe，冻结组件SHA与候选一致；部署10个历史GET及实际页面20项全fixture、原11Task保持通过。主Agent最终接受记录见authenticated/review.json。


## 第二次独立任务：对象结果Schema输入

object-outcome-schema/task.md为2566 UTF-8字节公开组件合同，未发项目源码或客户资料；执行器仍空工具／空MCP／safe-mode和原用户配置，一次18.26秒返回1948字节候选。回执真实型号deepseek-flash，输入915／输出4274 Token，CLI估0.111425 USD、costBasis=unknown，不当网关账单或总Token节省结论。receipt已存在，不自动重放run.py。

主Agent实现对象协议、共享API、父组件与确认失效，审阅原组件并以原始LF字节安装，SHA为a6878bc29afac154ec7af75cd4ada7a0cebe7558337b50152cd08fa3b6148d65。组件9项校验／渲染通过；对象57项界面隔离、旧文字及数值102项界面回归、254相关后端检查通过。视觉发现textarea默认宽度不合面板，主Agent准备独立集成CSS，保持候选源码原文；最终视觉、完整4092回归及实际0.192部署已通过，原文SHA保持，authenticated/review.json已接受；本轮对象58GUI及实际页面另58全fixture，原11Task保持。

这轮复用现有字段构建器的后续工作不需要额外派发模型；不为遵循分工而制造无意义调用。


0.193复用既有字段构建器，主Agent按对象协议接入safeIntegerBounds模式，未额外调用执行器；原Schema输入候选继续保持SHA，API／执行合同与完整192相同。实际部署与92GUI范围见状态页。


## 第三次独立任务：检查状态提示

schema-check-notice/task.md只含公开展示合同。执行器一轮19.91秒返回1205字节SchemaCheckNotice.tsx，原文SHA为9ff4a784fb7564c9cb70c2457f8db46292a4e43308f1f75b05ca104e21e7cf18；实际deepseek-flash，输入767／输出4342 Token、CLI估0.112385 USD，costBasisunknown不当账单。主Agent逐行审阅，组件9项检查通过，主Agent负责安全诊断API、来源与回执校验、请求失效、父组件及95GUI/230相关验证，实际0.194.0-91c18a8aef110bf5e71a部署37GUI/固定6本机无状态检查/11Task保持通过。模型只返回候选，无工具、项目源码、客户资料或凭据正文；run.py已有回执，不自动重放。


## 第四次独立任务：多步计算链步骤清单

chain-stage-list/task.md仅为公开纯展示合同。执行器一轮43.26秒返回3848字节候选，型号及用量按原配置回执：输入779／输出9476，CLI估0.240795 USD、costBasisunknown，不当实际账单或省总Token证据，没有自动重派。

本次不能直接接受原文：执行器误将类型标签string/number当JS运行时类型，导致任意文字或数字可通过、所有正常标签显示为文字。主Agent审查后改四处为字面量枚举、首项输入和类型标签展示，并用16项本机校验／渲染检查覆盖，原候选SHA与修正安装SHA独立存于authenticated/review.json，明确installed_verbatim=false。主Agent负责失败传播语义、五字段合同、API/严格回执、确认失效和集成；36GUI与268相关检查通过。完整4167项回归及最终视觉/实际0.195部署已通过，修正后组件SHA核对保持，review.json已接受；旧95GUI保持，新最终37及实际页面另37全fixture通过。

仅从客户端拿到候选不等于交付；本次类型错误说明应保留主Agent对接口含义、功能行为和测试的独立把关。没有为流程形式重复调用模型，也没有发送客户数据、项目源码或凭据正文。


## 第五次独立任务：准备步骤错误提示

chain-stage-diagnostic/task.md只含公开纯组件合同，执行器一轮33.70秒返回3432字节候选；实际deepseek-flash，输入785／输出7953，CLI估0.20275 USD、costBasisunknown非账单。原候选SHA9652194d5f44a3106d596b54de9c27ef7c86210500a1e32f747bbfbe310e6324；遗漏公开类型导出，主Agent只补export并分别存候选及安装SHA，installed_verbatim=false。26组件检查通过，主Agent负责安全错误定位、API归属和SHA绑定、状态失效、234相关／74GUI及实际0.196部署37GUI验收，11Task保持。无工具、项目源码、客户资料或凭据正文，已有receipt不可重派，不因形式制造额外模型调用。


## 第六次独立任务：任务草稿标记

0.212已部署 **0.212.0-58073a6ee4b73a1bb376**（211运行文件）：侧栏按任务显示“未发送对话”和“试跑输入”，返回有草稿任务继续；两标记可共存，发送／清空只清对应类别及任务，恢复默认运行输入清除运行标记。标签明确当前页面暂存，不冒称后台保存或运行。主Agent负责Map状态／接入／CSS与验收；本机Claude独立纯展示组件一轮候选657B，原始LF字节安装SHA4b6267b9dcd3fa34d2e5e9bdc419182d73b8f35596494a89769a006d93d2ae45，逐行审阅无工具／存储／网络／事件副作用。实际底层deepseek-flash，623入／1919出，CLI估0.05109USD、costBasisunknown，非网关账单／总Token节省结论。

10组件及23隔离GUI、部署页面另23通过，截图复核；构建主534.11KB体积提示保留。原11Task、密文及密钥文件保持、源码快照和资产200见work/task-drafts-212-deployed-check.json；后台只有版本变化、7模型契约保持，不重复211的39新增／215相关或206完整4380回归。worker回执及审查见work/claude-delegation/task-draft-badges/authenticated，已有回执禁止重派。


候选源按原文安装，生产版本与组件SHA、10组件／23GUI和实际23全fixture记录在authenticated/review.json。只发送1244字节公开合同，不发项目源码、客户Task或凭据；没有工具／MCP／直接生产写入，无自动重派。


2026-10-18／原生文本Agent保留展示：第7独立公开契约 `work/claude-delegation/agent-preservation-note`，一轮工具／MCP禁用请求因连接EACCES失败，177.13秒，CLI报告输入／输出0、估0USD，非账单证明。未返回候选、不采纳、无自动重发；主Agent补齐展示并审查集成。不能记作Claude成功开发或Token节省。


2026-10-18／第8独立公开包agent-knowledge-contract-tests：新任务，不重放第7失败。工具/MCP关闭、180秒/CLI估1USD上限。154.63秒返回8405B候选，deepseek-flash，3701输入／37603输出，CLI估0.959028USD，非网关账单。根审查发现current knowledge与selected方向颠倒、资源不匹配却自动增删的错误预期，原候选rejected_as_submitted，原回执保持；只提取结构夹具，修正参数方向并将资源不匹配改为明确拒绝，集成语义/API测试根另写，不能为候选放宽实现。214相关172通过15.10秒，补充后新模块两文件64通过1.31秒；完整214进行中。candidate未原文安装，不声称总Token节省。

后续新独立小包优先使用本机已核对CLI --effort low（--help实测支持）并缩小契约/输出，保留每包费用和根审查成本；不改用户全局配置。网关是否按effort生效尚未验证，CLI预算不是供应商账单硬上限。不得自动重放已有receipt；连接权限不足须走正常提权，不等待无意义重试。第7EACCES和第8返回是不同任务，均保留事实。


2026-10-18／第9agent-model-comparison：公开50行内纯展示契约，--effort low，工具/MCP关，120秒/CLI估0.25USD预算；一轮1153B、5.29秒、deepseek-flash580输入/847输出，CLI估0.024075USD非账单。根去unused React import适配noUnusedLocals，原候选保持；根做所有比较语义/API/CSS与接线，116相关/6组件/9源＋9生产GUI过。0.216.0-f5a0a956565416b8beee已部署。局部Token较第8短，不外推网关保证、未来模型effort支持或整个项目必省。


2026-10-18／第10agent-model-adoption-history：纯元数据函数公开契约，low effort/工具关/120秒与CLI估0.25USD预算，30.64秒/2451B，deepseek-flash777入7532出，CLI估0.192185USD非账单。根收紧日期时间格式防fromisoformat任意分隔符，非原文安装；原SHA b1ca254846a14e40230482e929504be28f45cb30b7c33257a0b5428cd71bfac7，现SHA5e8d6286a2bf6bc18dfc83765564f44415ca4937850b9ae392c237f9a70dc9c6。95相关/实际报告读取过，0.218.0-831eaeea00f612cfbb38已部署；根处理报告/验收语义，不外推总Token节省。
