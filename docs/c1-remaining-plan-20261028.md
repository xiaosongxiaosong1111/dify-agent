# C1保留首访谈的独立剩余链（362，第208）

206的360已经消费并停止。原空间认证和真实首轮追问通过；Task aa827c91-b683-4a34-9e7f-fa0789f5c252 现r5，九项needs_input未确认，第二轮候选未应用，旧失败和三笔settled全部保留。349已修搭建前逐项核对误触发batch；原候选另有同主题重复追问，仍然拒绝。不能重放360或把修复当真实主链通过。

本方案从当前r5继续，不重复已通过的首轮追问，不新建Task/知识库。旧首轮模型来源摘要419da27d1c128e6f06112c4c2f52143397607a5e62489f812ae0b31e85ed445c和原根代理复核逐字绑定，单列继承证据；不制造一次新调用、新复核或人类签收。

明确答复补齐三处范围：query可用于检索和回答的问题上下文，政策事实只能来自检索资料；订单号只是无命中固定提示，不增加订单号字段或查询系统；不增加分类器，仍由检索结果是否为空决定两条分支，不能宣称所有范围外问题必无命中。仅公共合成输入；Sierra会保存运行输入，不承诺任意输入不含个人信息或不落盘。

新的三次模型分别完成明确访谈、原版规划、修改规划。原版正常确认/构建/新App导入/首次发布/专属Key/两例及原生轨迹/ZIP后，只把**实际当前需求**output中唯一旧固定提示替换为增加商品型号的文字，其余字段逐字保持；多个或找不到旧文字就停。修改后用现有正常`intake/manual` API逐项说明八字段及检索专项，actor=agent_delegated、source=agent_declared，明确不是模型验证、人类声明或最终签收；根代理另读该当前来源后才确认需求。修改版仍由模型新生成，主动读取并采纳原候选，不手改模型图；完整核心图必须仅固定提示改变，再创建第二App、发布/Key、两例轨迹及第二ZIP。

新四处根代理内容复核为明确访谈、原版规划、代理逐项声明、修改规划。前后均需来源摘要/修订绑定，不能把结构替身写成语义通过。配置/代理复核/诊断用产品正常API，其余关键步骤同一界面，不声称全鼠标。固定fixture.plan只供隔离SDK替身，真实阶段禁止注入。

| 边界 | 本批及保留规则 |
|---|---|
| 明确改授 | 仅360未派发3模型、46管理读取、App/首次发布/运行Key各2、运行4；旧360永久消费，不重放 |
| 模型 | 每阶段一次，最多3 HTTP，各6000输出tokens/120秒；单次配置估算预留≤0.055 USD、合计≤0.165 |
| 认证 | 登录0；只读原空间身份一次，复用保存console/CSRF，过期/401/空间不符整批停，不自动登录，不改认证密文 |
| 平台 | 两版各命中/无命中及原生节点轨迹，最多46管理读取；新Key切专用连接，旧Key加密留档；不覆盖旧App |
| Task/执行策略 | 不新Task/库，保留18Task与所选旧历史，原4次/20分钟策略不变；本批30分钟准入 |
| 估算 | 模型≤0.165+Dify估0.02，整批估算上界0.19 USD；非供应商账单硬限，宿主费用未知 |
| 累计 | 实际模型23→最多26，保守30；读取预留573、登录35、资源各12/运行22、模型账本0.755473652不增加 |
| 失败/旧账 | 任一异常整批停、不重试；全部旧unknown、失败、费用及其余保留槽不退还、不借用 |

程序在tools/c1-remaining362，固定执行包work/c1-remaining362共22文件。plan SHA **b83ec3363e00943e2e47ed53e633835d5bf9717181f186f0942fed9ce077a6a0**，manifest SHA **887bbafc31b38944a8e8b363c229e1fc41f7f905ad041417e86abf7076c6da64**。目前没有approval/attempt/worker-started，真实HTTP及生产写入0。

已用冻结原包完成76门禁、26旧历史/费用保护、正常三模型/31读取/零登录两版四例及双ZIP、另6异常停止精确计数验证，包括过期与错空间均在1读取/0登录停止。代理声明与模型/人类来源分开，继承证据漂移拒绝。替身不是实际内容质量或平台通过。管理员上下文核既有dify-local16容器/5健康、349/287文件/PID5540及原快照归属，原18/所有密文资产及旧消费包不变；未全量测试。[安全结果](c1-remaining-preflight-20261028.json)。

```powershell
# 仅隔离检查，无真实请求：
.\.venv\Scripts\python.exe tools\check_c1_remaining362.py --output work\c1-remaining362-check-NEW --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
# 以下仅在该固定包获得新的直接明确改授并登记后唯一执行：
.\.venv\Scripts\python.exe work\c1-remaining362\execute.py live --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
```

真实前再次核固定源码/运行快照/PID及服务，服务未就绪不消费。真实过程到复核阶段由根代理实际读当前review-source，显式一次proceed/reject，不自动放行。原C1未完成，C2只固定公开继续策略已闭合，原25业务和Chatflow订单链等仍待其对应验收；本方案不删除或扩大这些需求。
