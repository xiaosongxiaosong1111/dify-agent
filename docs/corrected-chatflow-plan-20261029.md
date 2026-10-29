# 修复上下文后的独立完整Chatflow批378（执行前冻结方案）

当前：已获call_ec642cce38c5403bb7a3535c0ffd7ad8 q0新直接批准并唯一执行/消费，首例条件完整性规则failed即停。下文未批准/拟议按冻结时点理解。[实际结果](corrected-chatflow-live-result-20261029.md)。

375首例失败后已停止，376新直接批准的10读1登录已完成诊断并消费：检索2片段、进入grounded_answer。229已离线复现并修复提示缺少Dify上下文占位符的问题，部署357。旧Task、App、失败规则及回答保持。[实际诊断](first-case-trace-live-result-20261029.md)、[代码修复与部署](after-sales-context-delivery.md)。

378是独立完整新范围，不重放375/376，不改授或借用旧未派发范围；当前只完成本机准备，没有新批准、attempt或真实请求。

## 要完成的实际链

复用357售后人工模板的17节点/16边，强制grounded_answer提示引用`{{#context#}}`并绑定retrieve.result；旧遗漏图在合同生成时拒绝。仍为人工模板平台核对，搭建模型0，**不是模型自主访谈规划、一次浏览器界面全链或全§11/25项验收**。

新Task1，原19保持。通过正常产品API保存原公开需求、明确配置、选择模板、复核确认、静态构建、新App首次发布及运行Key。复用原FAQ和专用空间，不建库或覆盖旧App。每版如下六例，期望不放宽：

| 例 | 输入及核对 |
|---|---|
| 政策资料命中 | ZXRET715签收七天未拆封，回答仍须包含ZXRET715/七天/未拆封 |
| 资料无答案 | 未收录编号ZXUNLISTED90371，须逐字固定无答案 |
| 范围外 | 预订火星机票，须固定说明可处理范围 |
| 模拟订单存在 | DEMO-001，合成表已发货，带明确模拟标记 |
| 模拟订单不存在 | UNLISTED-DEMO，固定模拟未找到文字 |
| 缺号后补号 | 先问订单状态但不提供号，固定追问；同一会话只补DEMO-001后返回模拟结果 |

最后一例两轮，每版6启动/7Service。不同样例新会话，第二轮仅复用对应第一轮会话；不跨用户或样例。每轮检查原期望后读取消息关联原生运行、节点、执行/发布/本地图；技术或规则失败整批停止，不能为诊断继续后续读写。空检索与有片段但不足的无答案分别记录，不把后者冒充空检索。

原版全部通过后，正常修改需求/复核/确认，把无答案回复的“订单号”扩展为“订单号和商品型号”；图只两处同步该文字（固定回复及回答系统提示），上下文引用保持。新第二App/发布/Key，重复六例、逐轮轨迹与双ZIP；本机打包flags=false，不因静态包改为平台/业务已通过。[完整公开输入](../tools/corrected-chatflow378/fixture.json)、[合同](../tools/corrected-chatflow378/contract.py)。

## 完整新增范围和费用

| 项 | 当前保守上界 | 本批全部新增最多 | 拟新保守上界 |
|---|---:|---:|---:|
| Sierra搭建模型HTTP | 30 | 0 | 30 |
| 管理GET | 701 | 128 | 829 |
| 加密登录 | 39 | 1 | 40 |
| App / 首次发布 / Key | 各14 | 各2 | 各16 |
| 物理Service | 36 | 14 | 50 |

新增Task1，若完成则20Task。新Task累计12启动/45分钟，整批60分钟。Sierra模型账本0.755473652 USD不增，六settled/旧unknown及所有旧费用预留保持。**Dify新增估算0.10 USD不是账单硬封顶，宿主费用未知**；Dify运行内部仍调用分类/提取/回答模型，单Service可能包含多个模型或节点，不能把Service次数当供应商内部HTTP封顶。

固定deepseek-flash/thinking=false/温度0.2/最大输出512、记忆最近5轮；FAQ d12cf081-5c52-41e3-b869-e94e6f8d37b1，TopK3/无阈值/不重排。只复用加密登录资料，原空间c3306c18-ceb2-4bee-b2d1-796ce2048f17；不从聊天复制密码。新Key切换专用连接，旧Key加密归档。

375剩105读/资源各1/13Service及旧费用全部保留，不借用或自动退还；376没有剩余读/登录。旧失败和unknown不重放、不清零，任何异常本批立即消费并停止，不重试或阶段恢复，未派发范围也不自动挪给下批。

## 本机验证和诚实边界

37门禁通过，包含缺批准/错误摘要/非canonical/优化模式/一次消费、错误来源/会话/请求类型/上限、旧资源/凭据保护，以及拒绝旧上下文遗漏图和两版仅两处文案变化。13个完整公开协议场景通过，正常精确0模型/80读/1登录/资源各2/14Service、14份逐轮轨迹/2ZIP；另含非空但不足、认证/导入/发布/Key/Service/规则/消息会话/主动停止等失败即停。公开临时原19数据，真实HTTP0，源前后摘要一致；不是实际业务效果。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_corrected_chatflow_boundary.py -q --basetemp work/NEW-CORRECTED-GATES
.\.venv\Scripts\python.exe tools/corrected-chatflow378/rehearse.py work/NEW-CORRECTED-REHEARSAL
.\.venv\Scripts\python.exe work/corrected-chatflow378/execute.py validate
```

本机只读预检原19/密文资产及304消费文件保持；357-c038db013b5e96bc4d3e/289文件/PID32940源与固定快照匹配，原Docker16服务健康。预检不登录或读取Dify HTTP，不代表届时认证或模型质量通过。[安全摘要](corrected-chatflow-preflight-20261029.json)。

## 最终冻结和直接批准

work/corrected-chatflow378，15个哈希条目另加manifest。plan SHA256 `fe213d6872661aad06bc144a5990ca7c33c5388f9d40432be510a6eb31211725`；manifest SHA256 `cb4f91d4bf8f459b34ae6174ce47e1cd930737e0fbdfb5cc0794b10f8dcf3b80`。

只有最终摘要、完整新增次数/资源/费用取得新直接用户批准后，根代理才写approval并唯一执行canonical非优化execute.py live。所有原数据/连接、冻结源、304旧证据或运行变化均拒绝；原Docker未就绪则不消费或登录。不把同快照新PID误当业务变更，但必须核归属。

这次全部新增范围超出既有明确边界，因此按[AGENTS.md](../AGENTS.md)“within existing explicit resource and cost bounds”需直接批准，常规委托或375/376批准均不能代替。未获新批准前只本机准备，不能执行真实批。
