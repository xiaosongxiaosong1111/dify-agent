# 独立 375 执行器：复用已过实际访谈的剩余主线（仅本机）

> 状态：**未冻结、未批准、未真实派发**。本目录只新增本机实现与公开检查；不恢复 371 阶段、不重放旧批准、不创建真实 Task/知识库/资源。任何真实模型、Dify、登录、Secret、approval、attempt 或外部写入都必须等本机 pending 完成并由外部给出新的直接批准。

公开方案见 [`../../docs/reviewed-mainline375-plan-20261123.md`](../../docs/reviewed-mainline375-plan-20261123.md)。本文件只说明使用边界，不替代方案、冻结结果或批准。

## 范围

- 只复用 Task `1154f0c0-5e01-4492-b5c7-97bfbbbc2a61` 的 r6、两次已过实际访谈、旧 `needs_decision` 和全部历史；0 新 Task、0 新知识库、0 重复访谈。
- 只新增三个模型阶段：`original_plan` → `modified_interview` → `modified_plan`，各一次；成功后两版 App/首次发布/Key、12 启动、14 Service、14 原生轨迹、双 ZIP。
- 每模型 6000 输出 tokens/120 秒/估算预留 ≤0.100 USD，模型 ≤0.300，Dify 估 ≤0.100，整批 ≤0.400；均非账单硬限。仅新增 1 次加密登录，保守 49→50；其他保守账本 3.355473652 不增。
- 旧预算 0.600/policy1/三条 settled 合 0.020125524 不 PATCH；旧执行策略实际 None，只有新批获准后才经正常 API 首次设置 12/45/None。旧槽、unknown、settled 与预留不退不借。
- 任意异常整批停，不自动重试/修复/续阶段。唯一 Service 成功但 business failed 轮的 ≤4 GET/1 报告例外必须由新批准明确包含。

## 固定 CLI

使用项目 `.\.venv\Scripts\python.exe` 或原机绝对 venv：

- `prepare.py sources --output <当前项目 work 下直接新子目录>`：只从固定可信 Git commit 读取已审查源码，LF 规范化后精确复制/派生；不读 DB/Secret、不发 HTTP。输出 root 必须新、非 symlink，名称含 `autonomous-dual375`。
- `prepare.py pending --project-root E:/workSpace/dify-agent`：仅在原机执行；只读 DB 摘要/存在信息、实际 runtime/CIM、831 旧封存和十二隔离根，生成待批 plan/manifest；不登录、不解密、不写 approval/attempt/worker-started。
- 冻结包内 `execute.py validate-pending`：只读核验待批包，不读 Secret、不发产品/Dify 请求；有 approval 或 attempt 即拒绝。
- 冻结包内 `execute.py approve --authorization <仓库外真实直接批准 JSON>`：只在真实新直接答复后 exclusive 追加绑定精确 plan/manifest 的 approval。
- 冻结包内 `execute.py validate`：有批准后的准入只读校验。
- 冻结包内 `execute.py live`：只对唯一 canonical 包执行一次；失败即消费，不 reset/force/重签/续阶段。
- 公开三阶段替身由根另跑 `rehearse.py`；本目录不声称已运行。

## 源 pin 与派生

- `source_pins` 固定为两个可信 Git commit + 精确文件/路径：337 共享源 `f0e7beefb331db0b9c07f24cf19786b85d05b13c`，374 已验收叠加源 `4ac8e3282093fe0ba6a5298fcac9cc279e3e03bf`。读取使用 `git cat-file blob <commit>:<path>`，只源码 CRLF→LF；工作树必须与同一 blob 一致。数据、旧 seal、runtime 原字节不规范化。
- 337 只复制 `common.py/boundary.py/candidate.py/reviews.py/pagination.py/runtime_reference.py/fixture.json`；374 只复制 `reuse_policy.py/storage_guard.py/synthetic.py/synthetic_seed.py/rehearse.py/journey.py`。`common.py` 只精确改 BATCH_ID/旧 LIMITS/六阶段/0.600；`journey.py` 只精确增加 live 来源/文字/报告标签，不把真实 FAQ 或真实访谈写成 synthetic。
- 冻结 plan 记录每个源文件的规范 LF SHA-256、包内文件 SHA-256、runtime manifest/process 摘要及 proposal/scope 摘要。

## 冻结、批准与保护

- pending 精确绑定 r6 完整 Task/预算/需求/配置/cases/历史前缀/旧 `decision_report`/两份实际访谈 `review-source`+receipt 摘要；`interview_attempts` 缺省保持缺省，不补写生产字段。
- 旧 831 文件 = 733 + 337 封存 24 及索引 1 + 366 封存 26 及索引 1 + 369 封存 2 及索引 1 + 370 封存 6 及索引 1 + 371 封存 35 及索引 1。371 索引 SHA 固定 `d5d248d5a6ac06afffbb67cc664787332db8c9663b7c44e0d075a589c6e93092`；pending 逐成员核 SHA，并从已封存 progress/attempt 实际验证 stopped、model3/reads6/login1/import0/publish0/key0/run0、physical10、固定 Task、无新图/资源。
- 十二旧隔离数据根、其他 26 Task、旧 App/密钥/费用/封存保持；只有目标 Task、正常新账本后缀/执行策略和连接合法变更。
- 批准 literal 必须为“允许将371剩余范围明确改授375并新增1次登录，执行独立批”，scope `autonomous-dual375`，question_ref 必须是新的 opaque `call_ID/q0`；拒绝旧 337/366/371 等 ref、旧回执或 agent 决定冒充。
- live 只认原机 canonical `E:/workSpace/dify-agent/work/autonomous-dual375`；先认证 plan/manifest/approval/attempt，再读 DB/Secret。每 HTTP 前复核 frozen/approval/stop/time/预算；同步 HTTP 禁止，物理请求逐次计数，失败也保存进度并恢复 transport。
- live 使用 plan 固定 backend 快照、原 data Store、指定 environment/provider 和目标 Task；不调用公开 seed，不手改真实 Task，不把解密 Key 写入文件。Reviews live 要求根 `agent_delegated` 实际复核回执，不自动生成。

## 公开检查边界

- 固定检查：`python tools/autonomous-dual375/checks.py`。覆盖 profile/source pin/精确派生、plan/authorization 摘要与计数/费用/runtime/target/831 保护、反例、旧 371/366 封存门、canonical/symlink/已消费标记、无批准 live 早停，以及真实 `_write_package`→`_make_plan`→manifest→`verify_frozen_files` 的 pending 接线。
- 公开替身与反例只证明本机协议和边界，不证明真实模型质量、Dify 平台或业务验收；本批成功也不能声称 0.411 新空白从头访谈全流程独立通过。是否实际运行、计数和真实结果以根日志/原机冻结包为准。
