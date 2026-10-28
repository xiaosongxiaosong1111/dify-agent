# 348直连与消费前就绪的独立C1续做方案（360）

2026-10-28，BACKLOG205实现/206真实范围待新直接批准。本轮已完成348产品修复部署和零HTTP路由核对；当前管理员上下文原Dify栈就绪，未发真实Dify/模型请求。旧357登录502/原失败、费用、暂停及全18固定文件保持，不能重放。

## 本批做什么

复用原Task aa827c91-b683-4a34-9e7f-fa0789f5c252/r3，8字段仍空、无图/成果/App/运行，原198失败与settled保持。正常界面继续：模糊目标追问→根代理复核→公开完整答复/逐项复核和需求确认→原版模型规划/复核/配置确认→构建、独立App首次发布及Key、命中/无命中和原生轨迹、第一ZIP→无命中固定文字加商品型号→修改访谈/复核/重新确认→修改规划原候选经复核主动采纳→第二App/发布/Key/两例轨迹与第二ZIP。

不新Task或库、不预置完整图或直接写Task。配置和轨迹沿用正常修订/诊断API，其余关键界面操作；不声称全鼠标。运行策略仍4次/20分钟/null报价阈值，不清零旧历史。五处真实内容由根代理按既有委托逐项阅读source/SHA后登记agent_delegated，不逐项再向用户确认，不冒充人类或Claude复核。语义不合格可拒绝并写stop，不能手改模型图当真实生成成功。

## 只需明确改授原未派发范围并新增一次登录

- 拟把357**零派发的5模型HTTP、48管理读取、App/首次发布/Key各2、4运行**明确改授新独立360；不是重放357。另新增最多**1次加密凭据登录**。旧所有失败/unknown/费用及其他预留保持，不自动退款、借槽或改写回执。
- 每次模型最多6000输出tokens/120秒，每阶段1次无自动修复重试，五次配置价预留各≤0.055/合计≤0.275 USD；Dify估算0.02、整批估算上界0.30，非账单硬限，宿主费用未知。30分钟准入，在途无法保证取消。
- 模型保守30/账本0.755473652、管理读取573、资源保守各12/运行22、Task18**均不增**；登录预留34→35。当前实际模型21/资源各9/运行17，完整执行最多模型26/各11/运行21。旧未释放预留仍记录；这里的明确改授不减少既有账本。
- 复用FAQ d12cf081-5c52-41e3-b869-e94e6f8d37b1，主模型deepseek-flash；回答温度0.2/max512/thinking=false、TopK3/无阈值无重排。专用连接仍原空间c3306c18-ceb2-4bee-b2d1-796ce2048f17，只解密原保存登录；新App各1专属运行Key切连接，旧Key加密归档，不覆盖旧App。
- 任一结构/语义/API/来源/空间/额度异常整批停止，不重连、不阶段重试或继续未派发部分。Claude网关旧318失败无恢复证据，不形式重试或加预算；实际Codex不足时写stop和整份交接，停止新请求，不换号/买额度/用券。

## 先就绪核对，后唯一消费

348 DifyClient对本机使用显式无代理运输，远程代理及HTTPS CA环境保持。新360的current/runtime_check先核18Task/模型价格/连接与消费357原文件，348快照287源码字节/所属进程，并在**实际执行权限**下只读核原dify-local栈16服务/5健康/版本和8080映射；未就绪不claim、不登录，不自动启动。此检查不是认证证明，也不能据受限上下文的不可访问断言引擎停止或唯一解释旧502。

之后attempt/worker-started独占；任何非成功HTTP立即halt，同时保留给原SDK安全分类，禁止下一出站。源目录/优化入口不能live。当前没有approval/attempt/worker-started，不可直接执行。

- work/c1-resume360，全19文件；源码tools/c1-resume360。
- plan SHA256：`cff740ae3e96c86f3a045e51455c66ae49bd84571db794d0630aabf12294aa32`。
- manifest SHA256：`b66d7bbcc26729cdc6970f21ecf18f217c602170abfc7d5f93c05d952b0566c6`。
- 新plan固定原357全18文件及plan/manifest/approval/attempt/worker-started/停止保护摘要，并保留更旧354/353等完整消费摘要。

```powershell
.\.venv\Scripts\python.exe .\work\c1-resume360\execute.py live --playwright C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright
```

## 已完成的隔离核对

66门禁/26临时Store旧历史账本保护、冻结正常及6停止的精确阶段与计数通过，额外HTTP200漏检索主题只1次替身后停，旧失败与费用保持。另直接检查冻结入口“未就绪不claim”和“先就绪后claim”两项顺序。正常替身5模型/32读/1登录/资源各2/run4、同Task两ZIP和核心仅固定无命中文字变化、轨迹LLM1/0/1/0通过；五次synthetic_structural_checker均非语义复核。所有物理Dify/模型HTTP0、生产18和消费旧包保持，不全量。

```powershell
.\.venv\Scripts\python.exe tools/check_c1_resume360.py --output work/新的独立输出 --playwright C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright
.\.venv\Scripts\python.exe tools/check_c1_rejected_intake360.py --output work/另一个独立输出 --playwright C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright
.\.venv\Scripts\python.exe tools/check_c1_admission360.py
```

[安全预检JSON](c1-resume-preflight-20261028.json)。当前C1仍未通过，C2仅固定公开继续已闭合，C3文档不等于25业务通过；原Chatflow订单模拟链和六组未适配扩展不由本批替代或删除。
