# 原批准范围的执行包技术修正（0.284）

状态：**原资源范围已直接批准，修正执行包已冻结，等待技术替换确认**。不新增任务、次数、资源或费用范围，不要求重新扩大原批准。

用户已直接批准[daa4686原方案](https://github.com/xiaosongxiaosong1111/dify-agent/blob/daa4686/docs/complete-mainline284-live-plan-20261025.md)，来源call_f5220c40793e44f38b02ce9c1b83a095。第一次仅Docker准入前停止，live调用0。用户随后“继续开发”，原Docker Desktop/服务已恢复，五个既有Dify容器均healthy及8080就绪，未创建容器或卷。

继续前只读核对发现：原冻结plan缺少`intake_messages_sha256`、`plan_first_system_sha256`、`plan_changed_system_sha256`，而执行器真实模式会读取它们。原离线模式跳过该段，因此此前“离线通过”没有覆盖这个实际阻断。尚未调用live入口，未发生新模型/Dify请求或账本条目；这是本机执行包遗漏，不是供应商、模型或产品业务失败。

## 具体修正

- 原批准目录`work/complete-mainline270-replacement`的12源文件、manifest、approval及原准入停止记录完全保持，不覆盖或重放。
- 新独立目录`work/complete-mainline284-identityfix`，补三项摘要，取自0.284实际消息构造的离线捕获。规划只约束原系统提示摘要，动态需求/配置仍按原三个内容门禁逐项核对。
- 新前置检查在接触Store、账本、凭据、receipt或网络前，验证所有静态读取的plan字段及三项摘要格式。可审查源码：[检查器](../tools/batch_identity_preflight.py)。包内副本与跟踪源码字节一致。
- 离线完整链也执行相同摘要门禁；新增针对`live=True`的原invoke AST检查，以实际构造消息和假末端覆盖三阶段及错摘要拒绝。[回归脚本](../tools/check_batch_live_identity.py)。物理网络禁止，缺字段/非法摘要通过实际live入口在SQLite/receipt/网络前拒绝。
- 只有根目录迁移与上述准入修复，原业务步骤、三个内容复核、严格原候选不手改图、失败停止、次数和费用保护均保持。

定向新13项、原17边界及同界面完整两版四例7项通过，临时Store清理，真实HTTP0；原16全部对象/密文主Key/旧回执/unknown/预留逐项不变。[证据与冻结清单](complete-mainline284-identity-fix-result-20261025.json)。不是平台或完整业务验收。

## 原范围完整保持

复用原空r2任务和旧消息/unknown；新任务0。模型最多3次、各6000输出tokens/120秒；新App/首次发布/Key各2、两版共4次Workflow运行、管理读取96/登录28。原保守模型上界23和管理预留413保持，不增加到26或509。

旧unknown0.0188541 USD原样保留，新模型预留合计最多0.1311459、Dify估算0.02，与unknown合并0.17 USD，非账单硬限；旧四槽0.20和已知+全部预留0.425473652保持。原91/95和所有已消费包不重放，任何异常整批停止，不阶段重试。

业务操作与固定两条回复、FAQ库、模型参数、同一工作空间、三内容门禁、两版命中/无命中和完整轨迹检查，全按原daa4686方案。专用连接只切换至两个新App Key，旧Key加密留档，不建库、不覆盖旧App。

## 修正后的冻结身份

- 产品仍为`0.284.0-af29d0879c3760e5d417`，未改产品代码或运行快照。
- 新plan SHA256：`f47555b705bb0b873cd1087811047683f854e08e58d31dc0fab27df6e97b16dd`。
- 新manifest SHA256：`b2a89956387303d6b277d2cb43589eed61e357c9cd445111fb1a103b71a8c586`，19文件，含捕获消息/阶段输入，避免检查依据漂移。
- 当前旧/新目录均无live receipt；旧approval保留，新目录无approval。
- 原批准方案明确“任何变化停止，不自动重新冻结再套旧答复”。因此仅请求确认改用这份修正冻结包，沿用已经明确改授的同一资源/费用范围；不把普通继续或代理自己的技术修复当新哈希的直接答复。
- 取得对应哈希的直接技术替换答复后，记录新答复真实原文及原资源批准来源，重新核对源码/运行/原16/旧批准包和原服务空闲后，最多首次执行一次：`powershell -ExecutionPolicy Bypass -File work\complete-mainline284-identityfix\run.ps1 live`。不使用旧目录live，也不复用合成review。

验收命令（本机已有冻结检查输入）：

```powershell
.venv\Scripts\python.exe tools/batch_identity_preflight.py work/complete-mainline284-identityfix
.venv\Scripts\python.exe tools/check_batch_live_identity.py work/complete-mainline284-identityfix
```

冻结之后不要重跑会改写捕获文件的rehearse；校验现有manifest即可。真实模式仍需根代理逐项审查intake、plan_first和plan_changed，任何失败停止。
