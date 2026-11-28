# reviewed-dual390：两份已审图的平台收尾（拟议批次）

本目录只新增本机实现与公开合成检查。没有真实模型、Dify、登录、Secret、Docker、生产 Task 写入或真实
HTTP；不是 freeze、批准或平台回执。真实运行必须由根在原机独立冻结、审阅完整 diff、取得新的精确直接
答复后，才允许 `approve`/`run`。本批不放宽 375/385 旧消费包，也不把两图说成从空任务自主生成。

## 范围

- 复用生产 Task `1154f0c0-5e01-4492-b5c7-97bfbbbc2a61` 的 r8/manual 原图及其静态包；modified 固定只读
  `work/isolated-modification385/live-output/model-response-modified.txt` 的严格 JSON 候选（图 SHA
  `3940d849...`，源 r8 图 SHA `dd71f629...`），经 388 明确 manual 保存的 r10 两文案变化。两图来源分别标为
  `original=380 model + 383 DeepSeek code correction + root agent explicit manual save`、`modified=385 model + 388 manual save`，不伪造模型响应，也不把旧 r8/r10 文件说成可被本次 import 直接导入。
- prepare 只接受根代理内容审阅（`review_authority=standing_delegated_content_review`、`actor=root_agent`、
  `human_signoff=false`、`decision=proceed`）给出的 Task/budget/两图/cases SHA、两版显式
  `topic_answers` 与 trace expectations；该审阅不是直接副作用批准。标准主题 ID 由固定 backend 的
  `app.intake.topics` 在当版 requirements/图上纯推导，答案集合必须完全相等；八基础字段答案逐值等于当版
  requirements，额外主题由根显式文字提供，不接受 None/bool/list/空白/未知占位或用 rules 自动补缺。
  候选只允许固定路径，不再采用 `expected_changes`，拒绝路径覆盖/任意两字段；`fixture` 的
  requirements/configuration/cases/taskname 从当前 Task 派生，只有 requirements.output 与唯一
  no-answer expectation 的单句变化。`contract.native/core`
  由固定 runtime backend 的 `compile_workflow_plan` 与 `workflow_publication.core` 纯静态编译产生
  （不 exec 用户 code、不启 main、不读写生产 Store），并核 advanced-chat、无 http-request、实际模型
  provider/name 与 `.2/512/thinking=false`、KB TopK3/无阈值/不重排、对话状态声明原样。review 若重复提供
  fixture/contract 必须与派生结果严格相同，否则拒绝。
- 0 新 Task/库/访谈/搭建模型；两版各六例（最后两轮）、12 启动、14 Service、14 原生轨迹、双 ZIP；
  2 App/首次发布/Key；管理 GET ≤116（唯一失败轮最多 4 含内）、加密登录 ≤1。
- 新直接改授只拟使用 375 未派发 116 GET、App/发布/Key 各 2、14 Service、原 Dify 0.100 估算及新增
  1 次登录预留；Sierra 模型新增 0，旧 57/1730/资源各 30/Service 148/模型账本 3.355473652 不增。
- 原 27 Task、其它 26、12 旧根、909 封存、凭据/资产、原 r8 图/需求/历史/artifact 保护和专用连接
  新 Key 切连接、旧 Key 正常 API 加密归档；不改旧预算 5 settled/limit .600/policy1，不新增 Sierra 模型行。

## 文件

- `tool.py`：公共只读/摘要/路径工具；`prepare` 只读原机元数据并创建新 canonical；`approve` 绑定新直接
  答复；`run` 一次消费。prepare 先核真实 909 seal，再固定读取 385 候选 JSON 并按冻结图 SHA 核对；根审阅
  必须有完整 actor/human_signoff/decision 与 Task/budget/两图/cases SHA，trace expectations 必须覆盖
  6 case/7 轮且 native node ID 存在、must/must_not/any_of 不冲突；fixture 由当前 Task 派生。两图 native/core
  只由固定 runtime 的纯编译产生，模型 data.model 的 provider/name/.2/512/thinking=false、KB TopK3 与
  对话状态逐值核；`validate_package` 还从 native.workflow 重新派生完整 core 并要求与冻结 core 全等
  （同 ID 但 prompt/edge/feature 变化也拒绝），并用固定 backend 重新实际编译两图，要求 native/core 与
  冻结值全等。构建后的 fresh Task 与 artifact 再与冻结 native/core 比对；
  当前 DSL 编译无 revision 元数据，故保留完整 native/artifact 严格同值比较。prepare/approve/run 共用严格
  package 校验：固定成员集合、schema/batch、精确
  LIMITS/current_upper/proposed_upper、执行/失败/60 分钟/Dify 0.10 非账单限、0 新模型/Task/库、源 commit
  与六文件 LF/Git/package 三方一致、reviewed/protected 摘要、派生 fixture/contract/native/core 摘要、真实
  909 seal 和 12 数据根；不把 manifest 自身当成员，空/删/多成员/同形伪包/旧 ref/布尔冒充整数均拒绝。
  `prepare` 全部只读验证成功后才原子落新 canonical；不覆盖现有包。真实 prepare/approve/run 只认固定原
  项目与 `work/reviewed-dual390`，非优化且父路径无 link。
- 12 数据根固定为 `data` 加 `tools/autonomous-dual375/derivation.py.ISOLATED` 的 11 目录，并核
  `work/autonomous-dual375/plan.json` 的实际集合；不采用 review 自填的任意 12 路径。每根记录
  SQLite objects/secrets 摘要及资产逐字节 SHA；仅排除根级 `flowcraft.sqlite3`/WAL/SHM/`server.*`，
  嵌套同名资产不全局跳过。文件、目录及父链不得 symlink 或越界。freeze 与 run 前 12 根均比对原快照；
  run 后只强制 11 个旧隔离根完全不变，生产目标 Task/连接/资源后缀仍由 `storage_guard.verify` 精确保护，
  不以生产 DB 整库 raw SHA 阻碍合法写入，也不跳过生产保护。
- 909 不从 review 的同条数或摘要字符串推定：固定严格读取
  `work/isolated-modification385/protected-892.json`（直接 892 map）和
  `work/isolated-modification385/seal-after-review.json`（直接 16 成员，固定 SHA `97f93e94...`）。
  先校 seal 实际 SHA/成员/无链接与旧 892 文件本体 SHA，再合并 892+16+seal 自身=909 去重、逐项真实
  SHA 核，并与 plan 逐项相等；旧 385 SQLite 只按封存文件 SHA，不打开 DB/Store。
- `approve`/`run` 在真正生产读、mkdir、attempt、worker 或 Secret 之前核完整 direct metadata：
  `authorization_source=direct_user_reply`、scope/batch、精确 literal、新非空 `call_*/q0`（拒绝冻结旧 refs）、
  plan/manifest SHA、LIMITS/failure/execution、single-use/no-retry、Dify/旧预留/新增计数；run 重新核同一套，
  不只信 approve。已批准/attempt/worker/live-output 一律拒绝。
- `run` 先在新临时 data 导入 backend，再接受保护生产 Store；`h.call_model`、`h.budgets.call` 与同步/模型
  transport 都实际拒绝，不只统计 0。固定 runtime `0.413.0-bdb32c6761fe3102d582`/298、snapshot backend、
  runtime manifest/全源文件、无重定向/代理 health、原 venv/CIM/app-dir/host/port 在准入前核验；
  CIM 命令按受限 Windows argv 解析，要求 `-m uvicorn app.main:app` 完整签名及固定
  `--app-dir/--host/--port`，拒绝 `script.py uvicorn ...` 或多余参数；运行后再核 11 旧根/909 与保护，
  失败保留 attempt/counts、恢复 transport，不吞原异常。
- `boundary.py`：零模型 Dify 正常路径门；只允许登录、workspace、App/草稿/发布/Key、六例 Chatflow
  Service、消息/原生运行/节点诊断；禁止模型、其它 URL、宽泛 GET、重复发布/Key、跨会话/重复轮次。
- `journey.py`：既有 Task 的两版正常 API 编排；original 只导入当前 r8 artifact，并在导入前用固定纯编译
  核对 native/core；modified 只改两文案及唯一 no-hit expectation，经正常需求/样例/计划保存、确认、build
  后，再对 fresh Task 与刚生成 artifact 纯编译核对冻结 native/core/参数/状态，然后才交 Boundary 与 import。
  需求准入按显式 side original/modified 取冻结两版答案，GET standard 必须与冻结 topic ID 集合完全相等，
  context_token 只用当次 GET 原值，全量直接 POST，不再用 requirements.rules 补缺或吞异常；标准漂移/缺增/
  错 token 立即停。代理 `agent_delegated` 复核后保存已审完整图、重确认/构建、新 App/发布/Key/六例/轨迹/ZIP。
  轨迹用显式 case/turn must/must_not，不硬编码旧模板 node id；import 只用当前 artifact，不声称直接导入
  旧 r8/r10 文件。
- `storage_guard.py`：只允许目标既有 Task/Budget/ExecutionLimits 与正常资源/登录/Key 归档。Task 的
  workflow_plan 必须始终是两份已审图之一（拒绝 None）；id/name/app_type/environment_id/configuration/
  materials 及未列入正常操作的用户字段按 presence/值保持；confirmations/messages/versions/intake_history/
  runs 只允许保留旧前缀后追加；planning_runs/interview_runs/interview_attempts/active_* 的 presence 和值
  必须完全不变，原缺字段不补 []/null；requirements/test_cases 只能是已审 original/modified 值。预算整个
  对象逐值/类型保持（用规范 JSON digest 比较，避免 bool 与 int 视同），旧 5 entries/limit/policy/
  history 不增不减不改。ExecutionLimits 只允许一次合法
  12/45/None 首写（policy_revision int 1、一个 history、before 全 None、after 匹配、source=user、note
  非空、updated_at/created_at 均为有效带时区时间；正常产品先取 updated_at 再取 created_at，因此不假设
  两者顺序），之后任何不同写入拒绝；同值重写通过。TaskBudgetManager 继续使用 `self.h.store`，
  Guarded 不添加 store 字段。其它 Task/对象/秘密/文件保持。
- `checks.py`：实际临时 backend API + 假 Dify transport 的公开全链、12 个临时 SQLite 根、合成
  892+16+seal 909 和 CLI 拒绝；只使用临时合成文件，不读真实 385 候选或原机数据，不使用真实网络/Docker。
  单元检查可临时替换 `SEAL_INDEX_SHA` 为合成 seal SHA；这仅限测试进程，真实 prepare/approve/run 始终
  使用硬固定 `97f93e94...`，review 字段不能覆盖 anchor，也没有 `--test-live/force/skip` 参数。
  `test_storage_guard_integrity()` 使用真实临时 SQLite 与真实 TaskBudgetManager store 路径，核
  confirmation/planning/interview/plan 抹除、ID/名称/缺字段、预算 metadata/entry/布尔与整数混淆
  （policy_revision=True、entries 0/False、1/True）、非法首写拒绝，并保留正常 message/confirmation/
  version 后缀、合法首次 policy、同值重写及产品 updated_at 略早于 created_at 的正常时间顺序通过。
  `test_explicit_topic_answers()` 用真实 `app.intake.topics` 与 reviewed_inputs/contract 拒绝缺/增主题、
  非字符串/空白/未知占位、错版 output、假 human/authority，并用真实 API 拒绝 standard 漂移和错误
  context_token，全程 0 外部派发。公开合成 `_review` 也只用八基础字段与 `PUBLIC_TOPIC_ANSWERS`，未知
  topic 直接拒绝，不用 requirements.rules 兜底；toy 图只用于编译/协议，假 Dify 固定返回，不宣称真实
  检索命中、无命中回答模型路径、模型记忆能力或业务质量。
- `README.md`：本文件。

## 生命周期与边界

```text
python tool.py --project E:/workSpace/dify-agent prepare --source-commit <40-hex> --review <根审阅JSON>
python tool.py --project E:/workSpace/dify-agent approve --authorization <仓库外直接答复JSON>
python tool.py --project E:/workSpace/dify-agent run
```

- `prepare`：只读生产 Task/Budget/Environment/artifact、真实 909 封存、固定 12 数据根和根已审完整
  r8/固定候选图/trace expectations；创建新 `work/reviewed-dual390`，不读 Secret、不写 approval/attempt、
  不执行旧 375/385 canonical。original 必须等于当前 r8/artifact SHA；modified 只从固定 385 候选 JSON 读取，
  必须恰好两字段单句变化且状态声明不变；fixture/contract 必须由当前 Task 和纯编译派生，review 重复副本
  只能严格相同。sealed 385 candidate 不把 sealed DB 以 Store 打开；review 不能自行决定 12 路径、909 anchor
  或覆盖候选路径。
- `approve`：核 package/manifest/plan 和新三源、直接答复 literal/scope/plan/manifest/limit/失败例外、
  single-use/no-retry；拒绝旧批引用、已批准/已消费/worker/输出标记。
- `run`：先核 source/package/approval/production capture/27 Task/12 数据根/909/预算 5 settled/
  ExecutionLimits None、固定 runtime；再写 attempt/worker 并一次执行。零模型在 `h.call_model`、
  `h.budgets.call` 和同步/模型 transport 同时拒绝；只允许正常 Dify 管理路径和 `/v1/chat-messages`。
  一次加密登录，两版各新 App/发布/Key，旧 service Key 由既有 API 加密归档；异常整批停、不重试/续阶段/
  修复。运行后的 roots 只要求 11 个旧隔离根不变，生产写入由 `storage_guard.verify` 核。
- 唯一允许例外：Service 技术成功但业务 failed 的唯一轮，停止后续外部写入/Service，最多 4 管理 GET/
  1 本机诊断报告后封存，计入 116；技术/认证/来源错误直接停，不诊断、不追加。
- 原生轨迹：根在冻结前按当前 r8/r10 图给出逐 case/turn must/must_not；运行只与冻结源比较。所有实际
  资料命中/无命中/answer 仍由 Service 和原生轨迹核，资料变动或期望不符立即失败，不改期望。

## 固定检查

```text
E:/workSpace/dify-agent/.venv/Scripts/python.exe tools/reviewed-dual390/checks.py
```

本单 Guard 定向检查（更短往返）：

```text
E:/workSpace/dify-agent/.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'tools/reviewed-dual390');import checks;checks.test_storage_guard_integrity();print('storage_guard_integrity passed')"
```

本单显式主题定向检查：

```text
E:/workSpace/dify-agent/.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'tools/reviewed-dual390');import checks;checks.test_explicit_topic_answers();print('explicit_topic_answers passed')"
```

公开 check 使用临时数据、真实 backend API 和假 Dify transport；覆盖正常双版全链、0 模型入口/预算、
2 App/2 发布/2 Key/12 启动/14 Service/14 轨迹/双 ZIP、一次登录、≤116 读、预算/历史/artifact/Task
前缀保持、固定 12 个临时 SQLite 根（对象/秘密/资产）、根替换与对象/秘密/资产/嵌套同名改变、
生产允许写入后 11 旧根保持、合成 892+16+seal=909 及 seal/旧文件篡改、跨会话/错源/重复/越界拒绝、
CLI 未批准/不存在 canonical 拒绝；另在临时合成 Task/candidate/review 上核固定候选缺失/错误/路径覆盖、
任意两字段、假 actor/签收、外部 fixture/contract 注入、case/轮次缺/未知 node、native/core 与模型参数/
KB/状态注入拒绝，并以真实 backend 编译核 native data.model 参数、KB TopK3、state 及 core 完整派生，
全程 0 物理 HTTP。公开结果不等于真实 Dify 平台、模型质量、业务验收或从空任务自主生成。
