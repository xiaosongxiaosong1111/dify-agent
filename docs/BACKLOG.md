# BACKLOG — 可执行队列（2026-10-20 建立）

本文件是自动循环的**唯一待办来源**。每完成一项就改状态并写证据；不要用 `development-tasks.md` 的编号顺序代替本队列。

## 状态取值

`pending` 待做 ｜ `doing` 在做 ｜ `done` 已完成 ｜ `blocked` 受阻（必须写原因）｜ `need-user` 需用户操作

## 规则

- 一次只做**一项**，从第一个非 `done`/非 `need-user` 的 `pending` 开始。
- 每项必须有**本机可验证的验收命令**。验收不过不许标 `done`。
- 标 `done` 必须同时满足：验收命令通过 + `git commit` + 本表状态已改。
- 连续 2 项被判 `blocked` 就停止循环并报告，不要硬试。
- 不动 `live-state.json` 的 `initial_review_requests_used`；不重播初始访谈。
- 与 Dify 真实交互（导入/试跑/建库/建应用）一律单独门禁，不在本队列自动执行。

## 队列

| # | 任务 | 验收命令 | 执行者 | 状态 | 证据 |
|---|---|---|---|---|---|
| 1 | 为访谈契约失败补一个能复现的隔离回归：多余话题、无效素材ID、带未答问题就完成检查 | `.venv\Scripts\python.exe -m pytest backend/tests/test_intake.py -q` 新增用例通过，且该用例在断言被还原时必须失败 | codex | done | commit 9a8d781 |
| 2 | 用 claude 核对 `test_planning_decisions.py` 里是否已有等价断言，列出缺口 | 输出缺口清单到 `work/intake-gap-notes.md`；不改产品代码 | claude | done | commit 2ec4b98 |
| 3 | 核对 AT-12「DSL 变量引用错误」现状并补隔离检查 | `backend/tests/` 相关全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit c24453c |
| 4 | 核对 AT-14「批量任务部分失败」现状并补隔离检查 | 同上 | codex | done | commit 81958d9 |
| 5 | 核对 AT-24「用户恢复旧版本」现状并补隔离检查 | `.venv\Scripts\python.exe -m pytest backend/tests/test_version_restore.py backend/tests/test_version_node_changes.py backend/tests/test_runtime_snapshot.py -q` 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit cc7054e |
| 6 | 整理 `development-tasks.md` 状态列：136 项逐项标真实状态 | `.venv\Scripts\python.exe tools/check_development_task_status.py`；表内每行有状态，且不凭猜测填 | codex | done | commit d8da2f7 |
| 7 | 专用 Dify 环境登录 | 用户登录后 `/api/health` 与专用连接可用 | need-user | done | 用户已登录专用连接，真实导入/发布/轨迹读取成功；9daf074，历史阻断已解决 |
| 8 | 整批真实联调（已获批，限 14 次调用） | 有命中/无命中各一次真实运行回执 | codex | done | 9daf074：2个新App各命中/无命中共4次真实运行；v1原断言路径失败保留/离线核对，v2两个正式样例passed，人工纠正边界见真实记录 |

| 9 | 核对 AT-01「用户只给模糊目标」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_intake.py backend/tests/test_planning_capability_context.py backend/tests/test_planning_decisions.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 0594e1a |
| 10 | 核对 AT-02「用户不知道分类规则」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_intake.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 5cd1668 |
| 11 | 核对 AT-03「文档与参考 DSL 冲突」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_conflicts.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 262bc54 |
| 12 | 核对 AT-04「参考程度未明确」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_reference_dsl.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 27a6307 |
| 13 | 核对 AT-05「用户所选类型不适合需求」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_capabilities.py backend/tests/test_planning_capability_context.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 1acdf25 |
| 14 | 核对 AT-06「只有原始知识资料」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_knowledge.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 5d97fb8 |
| 15 | 核对 AT-07「多个知识库可选」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_configuration_proposals.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit ac2e9b0 |
| 16 | 核对 AT-08「资料业务事实矛盾」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_conflicts.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit dc1af40 |
| 17 | 核对 AT-09「模型简单聊天可用但工具能力不足」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_node_models.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 5b9167c |
| 18 | 核对 AT-10「接口未提供且用户接受模拟」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit c69350e |
| 19 | 核对 AT-11「未确认配置或资源操作」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 9de6002 |
| 20 | 核对 AT-13「已导入但关键样例失败」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_repair_verification.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 42417d3 |
| 21 | 核对 AT-15「连续对话信息不完整」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_conversation_cases.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 70cc6c4 |
| 22 | 核对 AT-16「自动触发或人工审核能力不足」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_human_runtime_execution.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit d5fbb44 |
| 23 | 核对 AT-17「切换到客户环境」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_conversation_source_read.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit a29ea0f |
| 24 | 核对 AT-18「用户在 Dify 手动修改后继续」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_dsl_roundtrip.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 5694dc3 |
| 25 | 核对 AT-19「修改配置或需求」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 036ef25 |
| 26 | 核对 AT-20「执行中暂停并关闭程序」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_task_budget.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 782ba21 |
| 27 | 核对 AT-21「同一错误反复无进展或到达上限」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_execution_limits.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 3b1c842 |
| 28 | 核对 AT-22「Dify 断开」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit b4f1107 |
| 29 | 核对 AT-23「需求需要新建外部系统」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_intake.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 1000112 |
| 30 | 核对 AT-25「启用轻量模型分工」现状并补隔离检查 | .venv\Scripts\python.exe -m pytest backend/tests/test_assistant_routing.py backend/tests/test_assistant_usage_groups.py -q 全绿 + 在 acceptance-mapping 填 final_acceptance_record | codex | done | commit 7502a5d |

## 已完成（本轮之前）

| 事项 | 证据 |
|---|---|
| workflow-progress-235 界面检查 14 项 | `work/workflow-progress-235-source.json`，2026-10-20 20:40 |
| 后端启动与健康 | `/api/health` 200，dify 1.17.1 |

## 禁止事项

- 不重跑全量测试（4861 项，600+ 秒）除非该任务明确要求
- 不重建项目、不改仓库设置、不改 `.gitignore`
- 不猜 136 项完成度；不确定就写 `blocked` 并说明缺什么证据
- 撞额度立即停，把进度写进本文件

| 31 | 已授权安全保存Dify邮箱密码及过期重新认证；只绑定原环境，不循环登录/重放写入 | `.venv\Scripts\python.exe -m pytest backend/tests/test_login.py backend/tests/test_dify_reauth.py -q`，相关UI检查 | codex | done | commit 1d69700；规定命令41 passed、6项隔离UI与构建通过；0.245专用连接实际加密记住200；自然到期续期仅隔离证据，无新工作流运行 |

| 32 | 重新生成现有流程时展示相对原方案的非目标变化摘要，保留完整候选供复核，不把提示词当自动保留证明 | `.venv\Scripts\python.exe -m pytest backend/tests/test_replanning_changes.py -q`，对应隔离UI检查 | codex | done | commit c347f4e；规定7项/相关共59项、5项UI与构建通过；0.246部署12任务/密文保持，变更候选不自动替换，0外部调用 |

| 33 | 修复知识准备及目录读取自动续期导致的假连接变化409，保留真实连接/旧job边界 | `.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_reauth.py backend/tests/test_knowledge.py backend/tests/test_resources.py -q` | codex | done | commit 18394dd；规定三文件76 passed；0.247最终快照部署12任务/全部密文保持，知识/模型/参数/库目录假409已修复，0外部调用 |

| 34 | 自动登录续期绑定原Dify工作空间；不同空间令牌不提交/不派发原请求，旧授权连接只读核对身份 | `.venv\Scripts\python.exe -m pytest backend/tests/test_dify_reauth.py backend/tests/test_login.py backend/tests/test_knowledge_reauth.py -q` | codex | done | commit c4ef9ae；规定三文件60 passed，0.248部署12任务/全部密文保持；已实际匹配原空间并启用自动登录。收口局部变量错误后独立核对，共2读取计入59/60，0登录/资源写入/运行 |

| 35 | 核对新候选复核门禁对Chatflow/原生Agent保持用户选择类型与原正式方案 | `.venv\Scripts\python.exe -m pytest backend/tests/test_replanning_changes.py -q -k other_app_types` | codex | done | commit b04a248；规定2 passed、7 deselected；类型/原正式方案保持、完整候选只读留存，0真实网络 |

| 36 | 主链Workflow发布前核对及明确确认入口；绑定当前新建导入App/修订/环境/成果/草稿，未知不重发 | `.venv\Scripts\python.exe -m pytest backend/tests/test_workflow_publication.py -q`，前端构建与定向隔离UI检查 | codex（claude审查连接失败） | done | commit 4e8e523；规定27 passed、7项拦截UI与构建通过；0.249部署12任务/全部密文保持，0真实Dify调用。非首次真实发布验收 |

| 37 | 新批次只读核对发布准备入口拒绝覆盖现有售后2应用 | 用户批准固定方案后运行 `work/workflow-publication-249-live/check.py`，仅明确已有发布的409算通过 | codex | blocked | 用户已批准；一次执行返回502/自动登录暂停，非预期已有发布409，原回执保留、未重试；12任务保持/无发布资源模型运行。读取保守预留8保持，具体登录失败原因未证明；系统权限下Docker/8080正常 |

| 38 | 运行页直接绑定当前导入App的运行Key；本机状态与确认绑定修订/环境，密钥不回显/不进浏览器存储，不访问Dify | `.venv\Scripts\python.exe -m pytest backend/tests/test_task_runtime_key.py -q`，前端构建与定向隔离UI检查 | codex（claude任务预算失败） | done | commit df0f1db；规定26 passed、8项拦截UI与构建通过。0.250部署12任务/用户模型设置/全部密文保持；真实本机GET确认当前App已有配对Key，0外部调用/0实际凭据替换，不代表真实可用性验证 |

| 39 | 修复登录/空间核对失败诊断丢失：持久安全分类、界面显示原因及阶段，旧失败保持未知，不重试/不回显凭据 | `.venv\Scripts\python.exe -m pytest backend/tests/test_console_failures.py backend/tests/test_login.py backend/tests/test_dify_reauth.py backend/tests/test_workflow_publication.py -q`，相关隔离UI/构建 | codex（claude审查超时） | done | commit 060ad77；指定103 passed、诊断UI6/受影响发布UI7及构建通过；0.251部署12任务/模型设置/密文保持，旧失败实际只读呈现legacy_unclassified且暂停保留，0外部请求 |

| 40 | 用已加密保存的登录资料明确重新连接：单次登录/原空间核对，绑定当前凭据及连接，失败暂停、不重放原操作 | `.venv\Scripts\python.exe -m pytest backend/tests/test_saved_console_reconnect.py backend/tests/test_dify_reauth.py backend/tests/test_login.py backend/tests/test_console_failures.py -q`，对应隔离UI/构建 | codex | done | commit 40f7a9c；指定相关四文件101 passed、重连UI8及构建通过；0.252部署12任务/模型/密文保持，截图布局复核通过，真实重连0，实际暂停保持 |

| 41 | 新明确重连后单次核对售后2已有发布被拒绝；旧37失败不重放 | 用户批准docs/console-reconnect-live-plan-20261021.md后执行冻结新包check.py | codex | done | commit cdb3e12；直接批准后冻结check.py一次退出0/receipt passed：原空间重连成功、售后2已有发布409；12任务/模型/非管理凭据/旧计数保持，0发布资源Key模型运行；新10读取/3登录保守预留保持，合并上界77，旧37失败不改不重放 |

| 42 | 运行页明确确认后创建当前App运行Key并加密保存，绑定原空间/修订/成果/共享影响，未知结果不重发 | `.venv\Scripts\python.exe -m pytest backend/tests/test_app_runtime_key_creation.py backend/tests/test_task_runtime_key.py -q`，对应隔离UI与构建 | codex | done | commit 6fd5515；规定59 passed，新UI8/手工登记UI8及构建通过；0.253部署快照258fa6e815deb59a7f90，12任务/模型/全部密文保持，源码匹配快照。0真实Key创建；Claude设计审查超时未采用 |

| 43 | 对已保留的改动候选按字段明确选择，生成只包含选中变化的未保存草稿，避免手工还原非目标变化 | `.venv\Scripts\python.exe -m pytest backend/tests/test_planning_candidate_selection.py backend/tests/test_replanning_changes.py -q`，对应隔离UI和构建 | codex | done | commit4162464；规定34 passed，新UI8/原完整候选UI5及构建通过；0.254快照3d1031e5b1272ad6bd37部署12任务/模型/全部密文保持，源码匹配。节点ID改变只作整组，不猜配对；旧售后历史未自动修改 |

| 44 | 节点重命名后明确从候选选择一个文字字段映射到原方案同类型字段，只替换该值形成未确认草稿 | `.venv\Scripts\python.exe -m pytest backend/tests/test_candidate_text_mapping.py backend/tests/test_planning_candidate_selection.py -q`，对应隔离UI及构建；旧公开案例只读离线回放 | codex | done | committedf12b7；规定42 passed，新UI8/相邻字段UI8及构建通过，0.255快照ca5665da30a37a507deb部署12任务/模型/全部密文保持。旧公开r18候选no_hit/template到原answer_miss/template的只读离线合成精确等于人工r20计划；不改旧记录，不当新平台验收 |

| 45 | 新一批完整入口真实验收：现有售后任务另存新修订、新建App首次发布、创建Key及两例试跑 | 已批准冻结check.py只执行一次，异常即停 | codex | blocked | 重连/r21/新App导入/首次发布/新Key均成功；首个试跑入口因本机累计4/4上限409，未派发Dify，无r21运行记录，不重试。receipt stopped_needs_review；原计划/旧记录/其余11任务/模型/非允许密文/旧计数保护通过。48读/14登录预留保持，合并上界125；预演遗漏持久策略，需补本机预检后另批准仅运行批次 |

| 46 | 在创建资源前只读预检本批试跑次数与已保存执行限制，界面提前显示累计上限，策略/历史不自动调整或重置 | `.venv\Scripts\python.exe -m pytest backend/tests/test_run_batch_preflight.py backend/tests/test_execution_limits.py -q`，对应隔离UI/构建与真实本机只读4/4核对 | codex | done | commita5ba1de；规定44 passed、新UI7/构建/截图通过；0.256快照72871c7742f0993dd782部署12任务/模型/全部密文保持。真实本机只读预检明确4/4+计划2需最小6；0外部，原策略和45失败回执保持 |

| 47 | 仅完成r21现有新App两例：明确调整累计次数4到6、耗时10分钟保持，预检后命中/无命中各运行一次 | 直接批准后冻结check.py一次退出0，receipt passed，保护证明全部通过 | codex | done | 证据commit b4490ee；两正式例succeeded且原生evaluation passed，workflow_id匹配当前发布，报告306/0tokens。累计实际6/6、策略v2，原4次及10分钟/报价阈值保持；其余11任务/模型/全部密文/旧计数资源回执保持，0管理读取/登录/新App/发布/Key/Sierra模型，旧45不重放。未读节点轨迹、不当完整连续界面或最终业务验收 |

| 48 | 样例汇总及交付报告按当前App归属运行，防止同修订重导入沿用旧App通过记录 | 定向acceptance与API报告隔离用例；现有r21本机只读和界面核对，不发外部请求 | codex | done | commit9e2974c；9项隔离复现后修复，定向汇总/报告24、导航28通过，只读UI5通过；0.257部署12任务/模型/全部密文保持，当前r21仍2/2正式例通过、累计6/6。旧App或缺App归属不计入当前汇总，原记录不改，0外部 |

| 49 | 运行页从已保存当前App记录恢复导入/发布/Key/样例进度，避免刷新后引导重复创建或发布 | 前端构建、定向隔离UI与现有r21本机只读核对，不新发模型或Dify操作 | codex | done | commit2d9e703；新UI9/发布7/Key8共24及构建通过，0.258部署12任务/模型/全部密文保持。刷新恢复当前App事实，已有发布/Key停用重复入口，旧App/修订/环境/未知结果不沿用，0外部，不当完整新需求连续验收 |

| 50 | 交付说明待办按当前App保存证据更新，不再统一要求重做已完成发布/Key/样例 | 定向报告隔离检查及现有r21本机只读报告核对，保留未知与业务边界 | codex | done | commita9ec25a；20定向隔离检查及真实r21只读报告6项通过，0.259部署12任务/模型/全部密文保持。已有匹配证据不重复要求操作，未知不重发、旧目标不沿用，类型/模拟/费用/全业务边界保持，0外部 |
