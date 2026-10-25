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

| 51 | 构建步骤完成标记依据当前有效成果，不因运行返回/暂停/错误状态丢失，也不沿用旧成果 | 定向隔离UI核对当前r21及旧成果/无效/未确认/过期分支，0写入 | codex | done | commit82fd994；先复现r21错误后修复，前端构建/定向UI5通过，覆盖运行状态及五类无效依据、六页只读切换。0.260部署12任务/模型/全部密文保持，静态成果不等于业务验收，0外部 |

| 52 | 冻结单次真实模型语义保留核对方案，隔离调用规划API、不覆盖原任务或触碰Dify | 先隔离演练单请求/保留图/原数据保护，再固定源码和输入哈希；未许可不外发 | codex | done | commit3bc00dc；冻结work/semantic-one-shot-260及计划摘要，三条API隔离演练：精确单字段通过、首请求失败停、非目标改动拒绝；第二HTTP发送前拒绝，未许可live门禁拒绝，全部原数据保持。真实模型/Dify0；仅准备，不称语义或业务验收 |

| 53 | 单次真实模型候选保留核对：公开售后仅改固定无命中提示，其余完整图精确保持 | 直接批准后冻结runner.py live一次退出0，receipt passed | codex | done | commitb2f5061；真实HTTP1/尝试1/Dify0，完整候选仅nodes[5].config.template变化且精确等于期望，不映射/人工改回/采纳。30089tokens，按配置价估算0.009580368USD非账单，单列后保守7/14；原全部对象/凭据/全局设置/旧账本回执保持，不当一般语义或主界面完整验收 |

| 54 | 第53项真实候选在隔离界面连续回放读取/载入未保存草稿/保存，核对修订和确认失效及单字段保留 | 临时Store与固定真实响应回放，HTTP/模型/Dify出站阻断；定向Playwright界面验证 | codex | done | commit25134fe；连续界面6项通过，完整真实候选只改固定文字，明确保存r22→r23后配置确认/成果/模拟App失效，刷新与历史只读通过；原全部对象/凭据/旧回执不变，模型/Dify0，临时服务清理，无产品版本变化 |

| 55 | 真实候选采纳后连续确认配置、静态构建并下载成果/交付报告，核对旧App与旧运行不被当作新修订验收 | 临时Store固定响应回放与定向Playwright；严格核对生成DSL及报告，模型/Dify出站阻断 | codex | done | commitb4f8412；15项隔离检查通过，过期准入正确拒绝后经界面重新复核/确认/构建/下载，完整DSL仅模板文字变化；模拟旧成功记录不计新修订，原全部对象/密文/旧回执保持，模型/Dify0，无产品版本变化 |

| 56 | 冻结修改固定回复后的真实验收新整批方案：独立本机任务、新App/首次发布/Key及两例；先验证完整预检和失败即停 | 同一未来flow在临时Store注入适配器，正常与阶段失败检查；冻结输入/脚本/源码/保护摘要，未许可入口拒绝 | codex | done | commit9697608；同一未来flow正常预演及三类失败准确停在资源前预检/发布502/首例502，原12任务及旧6次策略保持；未许可门禁在任务/回执/网络前拒绝，已冻结输入/DSL/脚本及原数据摘要，真实模型/Dify0 |

| 57 | 执行改文案后的独立任务真实验收新批；旧12任务及3个App保持，累计运行明确6→最多8 | 直接批准冻结docs/candidate-live-plan-20261023.md及对应摘要后，仅执行新包check.py一次；必须两例原生passed及保护证明通过 | codex | done | commit0eb4e81；直接批准后冻结新包一次passed，新独立r5/App/发布/Key及两例原生passed，307/0tokens，实际旧6+新2=8；原12任务/旧策略账本/其他密文主密钥保持，10项保护+只读UI6通过，读取保守上界173，Sierra模型0，禁止重放 |

| 58 | 集中交付当前公开售后案例：新旧任务/固定回复/两例结果/查看下载步骤/Key切换影响和未覆盖项 | 对照57保存事实及安全报告验证交付说明，无新增外部请求；不按测试数推算项目完成度 | codex | done | commit089dd5a；集中案例说明已对照57真实结果及只读UI核对，含查看/下载步骤、新旧任务与Key影响、旧失败及费用/未完成边界；README过期版本更正，模型/Dify0 |

| 59 | 构建页对已真实导入任务仍固定显示“未导入真实Dify”，修正静态结果说明以免误导当前案例 | 当前r5只读复现；定向前端构建/界面核对说明与导入门禁，快照部署保护13任务/全部密文 | codex | done | commitde0f161；当前真实r5先复现误述后只改一句，前端构建/源和部署界面通过，0.261快照匹配且全部13任务/对象/密文/主密钥保持，后端仅版本变化，模型/Dify0，导入门禁未改 |

| 60 | 准备全新公开自然要求经一次真实模型需求检查进入未确认草案的隔离UI方案 | 临时Store捕获冻结消息/输入及价格预留；固定响应预演与原13任务保护，禁止Dify和第二模型请求 | codex | done | commit8ec8cac；全新空需求正常/供应商失败UI各4项合成检查通过，第二HTTP发送前拒绝，未绑定决定live门禁在解密/回执/网络前拒绝；冻结预留0.0169365USD、消息/源码/原13任务与全部密文摘要，真实请求0 |

| 61 | 按常规委托在原14次/费用边界内单次核对全新公开自然要求的实际模型需求检查UI | 绑定委托下代理决定后仅启动新包live一次，实际UI发送1次；检查来源/未确认草案/原13任务保护并根代理核对内容，异常不重试 | codex | blocked | commit162f29a；本地queue.py遮蔽标准库导致uvicorn导入时中断，模型HTTP/调用器/解密/Dify0，真实UI未发送；原13任务/全部对象密文/旧文件保持，原receipt preflight及失败预留保留不重放；不是模型核对通过 |

| 62 | 修复隔离验证辅助脚本遮蔽标准库的启动错误，创建一次性回执前先核对完整依赖及临时Store启动 | 重命名冲突辅助文件；真实依赖完整启动只用临时数据/ASGI且禁网络，注入同名queue.py应在执行前拒绝；61原回执与所有源对象保持 | codex | done | commitda8fadc；冲突辅助queue.py已改名，标准库来源/完整依赖/临时ASGI启动通过，同名注入在执行前拒绝，原13任务/全部密文和61原receipt保持；模型/Dify0 |

| 63 | 修复后的新执行器在回执前完成依赖预检，并于原次数费用内继续这段尚未实际发送的需求检查 | 先冻结新执行器、正常/失败UI及旧失败包保护；如实记录委托决定后最多1真实HTTP，人工核对未确认草案及费用 | codex | done | commit0be89f1；修复启动后HTTP1/调用器1/UI4项、根代理11项内容核对通过，八项未确认草案/九项来源就绪，8711tokens/配置估算0.003895236USD；原13任务和全部对象密文/旧失败包保持，Dify0；实际Sierra8、保守9/14，旧失败预留保留 |

| 64 | 将已存真实访谈草案、流程候选及售后输出接为全程连续界面隔离回放，核对各阶段衔接 | 固定响应与Dify替身、真实模型/HTTP出站禁止；Playwright连续操作到交付，原13任务保护，发现实质阻断才修 | codex | done | commit795a3ab；10项连续界面回放通过并修复实际2/2耗尽但按钮可点，0.262部署/容量分支/生产只读/全对象保护通过；真实模型/Dify0，源13任务及全部密文保持，非同次新需求真实平台验收 |

| 65 | 继续核对63新需求经实际规划模型生成业务图：隔离确认草案后单次UI规划，禁止Dify与源数据写入 | 先冻结输入/源码/费用及正常失败模拟；已有常规委托内最多1真实HTTP，根代理核对完整业务图，异常不重试，原13任务/旧账本保护 | codex | blocked | commit661e59a；首次HTTP1/27361tokens/估算0.00262638USD后needs_decision/422，无图候选，不重试；UI6和原13任务全部数据保护通过不代表规划成功，实际Sierra9/保守10/14；Dify0 |

| 66 | 修复65暴露的规划上下文缺失：说明Sierra本机required文本空白派发前校验，区分Dify直调；已有规则不重复索要实施确认 | 捕获真实规划API消息、与当前输入校验行为对照，未知边界仍可澄清；只用临时Store和固定模型替身，针对性验证后部署保护13任务 | codex | done | commite29b489；新4项/相关7项定向通过，实际API上下文与两类required空白拒绝/原文保留对照，真正缺条件仍停，Agent不继承；0.263部署全部13任务/密文/旧65失败及账本保持，模型/Dify0，实际模型改善待证 |

| 67 | 66实质修复后以新独立批次核对新需求实际规划；65失败包绝不重放 | 新0.263源码、消息/费用/完整启动与旧包保护冻结，正常/失败模拟先通过，常规委托内最多1新HTTP，原14次及估算边界保持；根代理核对完整结果 | codex | done | commit1cb4760；修复后新批首次HTTP1/尝试1/UI6项及根代理12项图核对通过，完整七节点新图未手改，配置未确认/无成果App运行；27709tokens/估算0.00281898USD，已知实际10/保守11/14，13任务密文及65失败保持，Dify0 |

| 68 | 67实际新图经连续界面确认配置、静态构建和下载，核对编译后完整DSL及空白输入/错误边界 | 临时Store加载67已存结果，真实模型/HTTP/Dify出站禁止；Playwright操作与生成包结构对照，原13任务与旧包保护，发现实质问题才修 | codex | done | commitb2b9c60；新图界面确认/构建/下载5项及完整DSL/本机输入/模拟失败边界6项通过，原13任务密文及67旧包保持，真实模型/Dify0；非节点故障实际传播或平台验收，无产品变化 |

| 69 | 冻结67新图真实交付的新批方案：独立任务、新App/首次发布/Key及两例，先验证资源前预检/完整流程和异常即停 | 同一未来API流程在临时Store以替身演练正常及阶段失败，冻结输入/源码/保护/费用，未批准时在回执和写入前拒绝 | codex | done | commit9cd9c92；同一未来flow正常2/2及容量前置/发布502/首例502三类停止通过，复制原13任务与真实各策略后保护、未许可门禁、全图DSL摘要/输入/源码冻结；真实模型/Dify0，扩大范围待70批准 |

| 70 | 执行69已冻结新图平台交付新批：独立任务/App/首次发布/Key及两例 | 直接批准绑定docs/fresh-graph-live-plan-20261023.md与plan/manifest后，仅首次执行work/fresh-graph-live-263/check.py，原生两例passed及全部保护证明 | codex | done | commit3c22b44；直接批准后冻结check首次passed，新r5任务/App/发布/Key及两例原生passed，268/0tokens且发布图匹配；11项保护/UI6通过，原13任务/旧策略账本密文保持，现14任务/实际10次/资源各5，Sierra0/管理读取保守221，不重放 |

| 71 | 隔离同一界面从空需求经实际访谈、根代理核对、实际规划到确认/静态构建/下载，补足分段模型证据连续性 | 先冻结完整启动/正常失败模拟/每阶段消息及内容核对门禁/费用；已有常规委托内最多2模型HTTP、各一次，无Dify和源生产写入，源14任务和旧包保护 | codex | blocked | commit091f5c9；首次HTTP1/9283tokens/估算0.004581636USD后rules needs_input且固定文案丢句号，UI准入停止、第二HTTP0；原14任务及密文/旧包保持，未手改放行、不重试；实际Sierra11/保守13，未用第二阶段0.05保留 |

| 72 | 修71暴露的访谈精确文字保留及未采纳建议混入需求/缺口的提示边界 | 捕获实际访谈消息与原文来源，定向本机检查仍保留真实缺口和模型返回原文，不伪造自动语义通过；0模型/Dify，原14任务/旧包保护，实质修改后部署 | codex | done | commit968d57b；提示/契约精确文字与建议边界修复，相关22项及两条实际API替身回放通过，旧71坏响应保持且确认仍422；0.264部署原14任务/全部密文/旧回执保护，模型/Dify0，实际效果待73 |

| 73 | 72实质修复后最后1保守模型槽内单次实际访谈核对，旧71不重放 | 先冻结新0.264输入/消息/费用/启动与正常失败模拟，已有常规委托内最多1HTTP/估算0.05USD，根代理核对精确输出/已知规则与来源，异常即停 | codex | blocked | commit4976ffe；首次HTTP1后精确文案含句号/规则建议分离局部改善，但input/knowledge/exceptions needs_input，整体未通过，不手改/不重试；9653tokens/估算0.004786968USD，实际12/保守14/14，14任务密文旧包保持，Dify0 |

| 74 | 补齐73暴露的访谈本机入口/错误返回与资源条件上下文，避免重复索要已有技术规则 | 定向API消息与最终DSL空白422/平台失败502实际本机行为对照，成功与错误输出区分；真正业务缺值仍澄清，源14任务/旧包保护，0模型/Dify后部署 | codex | done | commit189d065；共享入口契约进入访谈/规划，相关23项及空白422/平台失败502/unknown真实本机对照、旧73问题不自动解除回放通过；0.265部署源14任务/全部凭据/旧包保持，模型/Dify0，实际模型效果待新范围 |

| 75 | 准备0.265修复后独立两阶段同界面实际模型核对新范围：原14→最多16，静态交付止步 | 新临时Store/同浏览器、根代理两次内容门禁，正常与两阶段失败模拟/完整启动/输入与费用/旧包保护冻结；未有直接次数扩大批准时拒绝live | codex | done | commit8cc3ab0；正常UI6/首失败3/第二失败5和完整启动、第三HTTP发送前拒绝、源14任务/密文/旧71与73包保护通过；冻结plan/manifest/输入及阶段内容门禁，缺直接14→16批准在回执/Key/HTTP前拒绝，真实新增0，模型效果未验证 |

| 76 | 执行75冻结的新两阶段同界面实际模型核对；明确扩大保守次数14→最多16 | 直接批准绑定8cc3ab0方案及plan/manifest后，仅首次运行work/continuous-model-ui-265/run.ps1 live；根代理逐阶段核对当前实际内容，完整图经界面确认/静态构建下载及源数据保护；异常停不重试 | codex | blocked | commit21c764c；直接批准后首轮HTTP1/10214tokens/估算0.004953804USD，固定回复与资源条件保留，但input/rules/exceptions仍needs_input，第二模型/规划/构建/Dify0；旧14任务密文/包保持、临时清理，不改答案不重试；已知实际13/保守16/16，新增未用第二阶段0.05/一槽保留 |

| 77 | 修复76暴露的访谈职责边界：已有技术契约与不改变明确业务的实现细节不被当作新增业务选择 | 实际访谈消息包含当前已知技术边界，旧76失败响应原样保留且准入仍拒绝；真正业务缺口不解除，定向检查/源14任务密文旧包保护后部署，0模型/Dify | codex | done | commit7ff001f；24项定向及旧76问题原样保留/正常草案两条API回放通过，0.266部署，当前技术事实进入系统消息且用户不能篡改；其他类型/只读讨论隔离，原14任务/全部凭据旧包保持，实际模型效果尚未验证 |

| 78 | 准备0.266修复后新的两阶段同界面模型验证独立方案，保守16→最多18 | 正常及两阶段失败模拟、完整依赖启动/费用与两次内容门禁/源14任务及旧76包保护冻结；无新直接批准时live在回执/Key/HTTP前拒绝 | codex | done | commit5350a1b；正常UI6/首失败3/第二失败5和完整依赖/临时ASGI、第三HTTP发送前拒绝、源14任务全部对象密文主Key及旧76与更早包保护通过；plan/manifest/消息冻结，未批准门禁拒绝，真实模型/Dify0，实际语义改善未证明 |

| 79 | 执行78冻结的新两阶段同界面实际模型验证，扩大保守16→最多18 | 直接批准5350a1b方案及新plan/manifest后，仅首次运行work/continuous-model-ui-266/run.ps1 live；逐阶段根代理内容核对后静态构建下载和源数据保护，异常停整批不重试 | codex | blocked | commit91b4d3d；HTTP1后实际访谈九主题/根代理12项内容通过，随后验证会话和进程中断，原因未证；临时r3未确认/无规划，第二模型/构建/Dify0。原request_dispatched回执保持，中断跟进/用量另存，源14任务密文保持、取证后临时清理、相同0.266已恢复；实际14/保守18/18、未用第二阶段0.05保留，不重放。整体连续链未完成 |

| 80 | 基于79已保存且内容通过的实际访谈草案，准备单次规划到静态交付的独立新批，不重复访谈 | 固定实际来源/完整规划消息与新包摘要；临时Store正常及规划失败模拟、根代理内容门禁/源14任务密文旧79包保护/未批准入口拒绝；0实际模型/Dify | codex | done | commitdf4f321；正常UI6/规划失败5、完整依赖/第二HTTP拒绝/源14任务密文及原79包保护通过；新辅助脚本finally清理在强制浏览器启动失败时验证，固定实际草案及完整消息、未批准入口拒绝，新增实际模型/Dify0；不称原79浏览器链完成 |

| 81 | 执行80冻结的仅规划新批，明确扩大保守18→19；复用实际访谈不重复调用 | 直接批准df4f321方案与plan/manifest后首次执行work/reviewed-intake-plan-266/run.ps1 live；来源草案和实际完整图两道核对后经界面静态构建下载，源数据保护通过，异常整批停不重试 | codex | blocked | commit6066f78；实际HTTP1/27913tokens/估算0.002925516USD，结构有效但回答提示硬编码政策事实作资料补充，违背只用检索资料；根代理拒绝，原图保持/配置未确认/无构建/Dify0，不重试。源14任务密文与原79包保持/临时清理；实际15/保守19/19，四项预留保持，整体未通过 |

| 82 | 补规划提示的检索事实来源边界：知识库内容描述不自动成为回答提示的静态补充 | 实际规划消息包含只据检索时不得嵌入知识描述事实的契约，用户明确允许静态来源或真实冲突仍需分别处理；旧81图原样保留、针对性检查/源14任务及凭据旧包保护后部署，0模型/Dify | codex | done | commita41ebd8；24定向及旧81候选原样保留/好图的API回放通过，未确认构建仍422，不做关键词自动语义改写；0.267部署源14任务全部对象密文及旧81包保持，源码匹配，新增模型/Dify0，实际效果尚未验证 |

| 83 | 准备0.267事实来源修复后的独立单次规划验证方案，复用79实际访谈而不重放81 | 新运行源码/完整规划消息与实际草案来源冻结，正常及规划失败/拥有者清理/第二HTTP拒绝/14任务密文和旧81包保护通过；无新批准时live在回执/Key/HTTP前拒绝 | codex | done | commit7c648e8；正常UI6/规划失败5/浏览器启动失败拥有者清理及完整启动、第二HTTP拒绝、源14任务全部对象密文与旧81/79保护通过；plan/manifest/完整消息冻结，未批准入口拒绝，真实新增0，实际语义效果尚未验证 |

| 84 | 执行83冻结的新单次规划验证，明确保守19→20；不重放81候选或重复访谈 | 直接批准7c648e8方案和新plan/manifest后，仅首次执行work/reviewed-intake-plan-267/run.ps1 live；根代理核对来源草案及实际图事实来源后静态构建下载，源数据保护通过；异常整批停不重试 | codex | blocked | commitca89379；HTTP1/28204tokens/估算0.008211432USD，提示硬编码政策事实已消失的局部改善，但条件布尔值是JSON字符串true而非布尔，校验422/无正式图、配置确认或构建。原候选保持/不自动转换/不重试，源14任务密文旧81和79保持/临时清理；实际16/保守20/20，四预留保持，整体失败 |

| 85 | 将模型候选的明确JSON布尔字面量格式错误与真正业务未决区分，保留严格类型和原候选 | 复现字符串true/false仅类型错误却误报需业务确认；定向测试证明新格式诊断一次停下/无转换或额外模型、混合未知错误与真实业务澄清保持；API/源14任务密文旧84保护后部署 | codex | done | commite3088f0；56定向及旧84原候选仍422/好图的API回放通过，格式错误无转换且只调用一次，混合未知错误/真实澄清不降级；0.268部署14任务密文旧84包保持、源码匹配，新增模型/Dify0 |

| 86 | 为84已保留候选制作独立离线单字段布尔格式修正预览，不改原图或回填原批 | 仅新副本value字符串true→JSON布尔true，精确差异与事实来源核对；临时Store经既有API保存为人工修正草稿、确认配置/静态构建下载，原14任务/密文/旧84保持，模型/Dify0 | codex | done | commit474efac；原84图仍422，独立副本仅value类型一处改变，plan_source=manual，API确认/静态构建/下载通过；已审查派生YAML及哈希提交。原14任务密文/旧84图回执保持，临时Store清理、代码未执行、模型/Dify0；不是原模型成功或业务签收 |

| 87 | 准备人工格式修正预览的独立平台验收新范围：新任务/App/首次发布/Key各1及两例，模型0 | 同一未来flow在临时Store正常/容量前置/发布失败/首例失败演练，原14任务/密文/旧84和人工预览保护；冻结源码/图/费用与范围，无批准入口在回执/写入/网络前拒绝 | codex | done | commit5c380d6；正常2/2及容量前置/发布502/首例502停止通过，缺两样例在任务/网络前拒绝；新r5/2次策略严格保持，原14任务与全部对象密文/旧84及人工预览文件保护，临时清理。冻结plan/manifest，未批准入口拒绝，真实模型/Dify0；非平台验收 |

| 88 | 执行87冻结的人工格式预览独立平台验收，Dify运行10→12/资源各5→6 | 直接批准5c380d6方案和新plan/manifest后，仅首次运行work/boolean-preview-live-268/check.py；两例原生passed/匹配新发布图，原数据与新旧Key归档配对证明、只读界面/报告核对，异常整批停不重试 | codex | blocked | commit086aa93；一次执行在明确重连返回502/login_rejected后停止，只新本机r5草稿/静态构建，新App/发布/Key/运行0，Sierra0。原14任务/全部旧密文主Key和旧包保持，现15任务；当前Key配对不变，自动登录暂停，未重试。读取预留269/登录14保持，实际Dify仍10/资源各5；OS检查Docker引擎未运行，502不等于密码错误 |

| 89 | 恢复已安装Docker Desktop与现有Dify服务，保留88失败和自动登录暂停，不重新登录 | 定位已安装Docker Desktop路径，启动已有引擎/现有容器；Docker本机状态/端口就绪及源15任务密文旧88保护，0管理请求/登录/App/Key/运行/模型；不重放批次 | codex | done | commit213a3a3；原Docker29.8.2及既有Dify API/数据库/缓存/沙箱健康、8080 TCP就绪，未新建/删除容器卷；15任务全部对象密文主Key与88失败文件相等，登录仍暂停，管理/登录/模型/资源/运行0，不当重新认证或验收通过 |

| 90 | 为已保留的r5草稿准备恢复服务后的独立剩余整批方案，不重复建任务或重放88 | 复用e764003b-00d4-404c-8b94-e22c29201823/r5现有成果与0/2策略，重连/新App首次发布/Key及两例同flow预演和失败停止，原14其他任务/全部密文/88旧文件保护与冻结，未批准入口拒绝，真实外部0 | codex | done | commit3b7445a；复用r5/新任务0的正常2/2和容量/发布502/首例502停止通过，15源对象密文主Key及88失败保持，临时清理；Docker健康/TCP前置在回执/凭据/HTTP前正反检查通过，plan/manifest冻结、未批准拒绝，实际外部0 |

| 91 | 服务恢复后执行90冻结的独立剩余整批，复用r5/新任务0，旧88不重放 | 直接批准3b7445a方案及新plan/manifest后首次执行work/existing-preview-live-268/check.py；服务就绪/容量/原空间重连、新App首次发布和Key、两例原生passed及原状态/Key归档/UI报告保护；异常停不重试 | codex | done | commit6683558；首次执行passed，新App/发布/Key各1、两例原生passed且匹配发布图，280/0tokens；14项保护和只读UI6通过，原14任务/旧密文主Key/旧失败保持，新旧Key只在内存核对；现15任务，实际Dify12/正式passed10/案例资源各6，读取保守317、Sierra0，不重放 |

| 92 | 将84实际候选的一处JSON布尔格式修正接入明确的只读预览及未保存草稿，保留原失败与严格类型 | 当前修订/候选摘要绑定，只允许恰好一处明确true或false字符串且其余图有效；实际候选及拒绝分支/API无写入定向测试、隔离UI载入与既有编辑保护、构建和部署数据保护，模型/Dify0 | codex | done | commitda7bda3；60相关定向+另1项Chatflow、构建、实际84 API回放、隔离UI12/完整本机API界面6/部署只读6通过；明确预览与人工保存/重新确认/静态下载，原失败保持，0.269部署15任务/全部对象密文主Key旧回执保持，模型/Dify0 |

| 93 | 修88真实502被标成login_rejected的误导诊断，区分登录服务故障与明确凭据拒绝 | 固定502/503与401/403隔离响应，登录暂停/单次请求/不重试/不回显/原空间及密文保护定向核对，必要本机API/UI及部署保护，真实登录/模型/Dify0 | codex | done | commitb1384d5；78定向及只读UI6通过，未来5xx记login_service_error，401/403保持login_rejected；失败暂停/重复确认409/单次登录/全部密文及原空间保持。0.270部署15任务/全部对象密文主Key、88/91回执及92证据不变，前端未改；真实登录/模型/Dify0 |

| 94 | 准备主线整批连续验收：新需求访谈/规划、首次平台两例，再改一条业务要求重新生成与平台两例；一次整批范围 | 当前0.270同一界面与同一未来流程隔离预演，逐阶段内容门禁/确认失效/旧App结果隔离、三模型及四运行上限、失败停止和源15任务密文旧回执保护；冻结可审查包，无新批准前真实HTTP0 | codex | done | commit46f23e8；正常UI7、六类失败停止、浏览器启动失败拥有者收尾及13项边界核对通过；两版输出/节点轨迹/三图匹配/交付说明下载，旧15任务/全部对象密文主Key旧回执保持、临时清理。固定替身模型3/资源各2/运行4/读取30，真实新增0；新plan/manifest冻结，不当实际连续链成功 |

| 95 | 执行94冻结的完整主线整批：模型保守20→23、任务1、资源各2、运行12→16，两版输出与节点轨迹验收 | 直接新整批批准绑定46f23e8方案与plan/manifest后，仅首次work/complete-mainline270/run.ps1 live；根代理三内容门禁、原候选主动采纳不手改图、两版四例及轨迹/三图/报告和全保护证明，异常整批停不重试 | codex | blocked | commit005ce46；直接批准后首次停止，执行包str(request.url())误调HTTPX属性，在上游前TypeError；调用器1/实际模型HTTP0/Dify0，仅新空任务r2，原15对象密文主Key及旧回执保持。无模型返回/非语义失败，不重试。原unknown0.0188541及本批0.15范围预留不退，实际模型仍16/保守23、共7槽预留，管理保守413/新增实际0 |

| 96 | 修95执行包运输层URL属性错误，补真正协议适配器到运输检查的离线预检，保留失败包不重放 | 对冻结失败源AST及真实providers.call_model+HTTPX Request离线复现0转发，再对新副本URL属性修正验证真实构造payload/消息摘要/次数上限与故障拒绝，全真实出站禁止；原16对象密文主Key/95文件逐项保持，模型/Dify0 | codex | done | commit3573161；原AST稳定复现URL属性调用TypeError/假转发0，两处属性修正副本穿过真实构造/HTTPX/解析3次假转发，第4及tokens/stream/消息/方法/地址拒绝，共8项通过；原16对象密文主Key/95失败包unknown账本完全保持。未改产品或重放95，真实HTTP0 |

| 97 | 完成95执行包纠错后的离线整链与边界预演，按用户新优先顺序保留未冻结替代草案，不继续扩充验收准备 | 同一SDK/HTTPX末端假响应正常两版四例、六失败/浏览器收尾、17边界通过；原16/旧unknown保持，真实HTTP0；不冻结或申请live改授 | codex | done | commitef4e9c1；docs/replacement-offline-preparation-20261024.json，正常UI7及逐次真实构造/假运输数量一致、协议预检模型3/Dify线缆7、失败准确停止/临时清理；明确根据用户最新要求收窄原97的最终冻结目标，草案不是可执行新授权。95旧包/unknown与四项预留不动 |

| 98 | 补显式Workflow/Chatflow及原生Agent导出遗漏模拟依赖声明的产品缺口 | 用现有三编译路径复现标记遗漏，只统一交付元信息/静态警告，不创建模拟节点或证明真实接入；定向导出/报告及原图保持检查，模型/Dify0 | codex | done | commitc2573fd；先复现6失败/2通过，修复后三编译路径说明/警告统一；新增8回归及既有62编译器检查通过，三种API构建/下载/报告保持声明，图/参数/提示词/类型未变。0.271部署health200，原16全部对象密文主Key/95失败unknown保持，真实模型/Dify0；非模拟位置绑定、真实接入或AT-10全验收 |


| 99 | 模拟依赖逐项关联节点与接入待办：配置界面保存、编译检查节点存在、导出和报告保留待办 | 定向API持久化/修订失效、未知节点/孤立依赖拒绝构建、全图与参数保持；隔离UI及构建通过，原16对象凭据旧账本不变，真实模型/Dify0；推送前写CHANGELOG | codex | done | commitaffe2c6；新增25回归，两组相关93/57通过（有重叠），隔离实际界面6/前端构建和窄栏截图通过；最终保留文件缺说明拒绝、齐全逐字交付且合并记录不变。0.272部署health/前端资源200，原16全部对象密文主Key/旧失败unknown保持，真实模型/Dify0；仅节点存在检查，不证明模拟行为/真实接入。根CHANGELOG及每次push规则已写入AGENTS |

| 100 | 售后订单查询模拟模板：公开合成订单表生成单个已选代码节点的可审查草稿 | 只读预览/严格输入与完整图校验/其余节点及连接保持，实际模板本机三结果及坏类型验证；同界面预览采纳保存构建，源16与旧账本保持，真实模型/Dify0；更新CHANGELOG后推送 | codex | done | commit904db5e；新增34/相关60通过，本机审查模板三种实际返回及坏类型/字面数据验证；隔离实际界面8/TS构建/截图通过。只读预览不动任务和预算、精确来源nonce绑定、主动采纳/保存确认构建下载，图保留。0.273部署health/新面板200，原16对象密文主Key/旧回执unknown保持，真实模型/Dify0；非真实订单接入、Sandbox或完整业务验收 |

| 101 | 参数提取结果接入订单模拟查询，保留显式成功检查及失败分支 | 复现提取文字无法选择，定向检查只接受已声明string业务参数、拒绝状态/数组/失败及汇合绕过；实际隔离界面从提取字段选择到预览采纳保存构建，完整图/原16与账本保持，真实模型/Dify0，更新日志后push | codex | done | commit831d1d0；原代码3失败/9通过复现，新增12/相关64通过，隔离完整Chatflow界面6/构建截图通过。已声明提取string可接成功查询，状态/非文字/失败/汇合绕过拒绝，提取配置/成功IF/失败回复和边精确保持。0.274部署health/新面板200，原16全部对象密文主Key/旧回执unknown保持，真实模型/Dify0；非实际提取质量、Sandbox或全业务验收 |

| 102 | Chatflow首次发布入口：类型绑定、当前草稿核对与一次确认发布，保留已有发布/未知拒绝重发 | 按Dify1.17.1固定tag确认协议；隔离后端完整发布和原生HTTPX协议、类型/记忆/变量变化/并发未知保护，实际界面确认/报告/刷新不重发，原16与旧账本保持；无真实Dify或模型新增，日志后push | codex | done | commit1298a45；新23/相关63通过，真实DifyClient/HTTPX至末端替身、正常界面8/未知界面5/构建截图通过。Chatflow App身份/类型及完整图绑定、已有发布/未知不重发，回执类型与在途缺result保护；Workflow常规5读/历史兼容。0.275部署health/资源200，原16全部对象密文主Key/旧回执unknown预留保持；真实Dify读/登录/发布/Key/运行/模型0，尚非真实平台验收 |

| 103 | 导入后导航按当前App引导发布、运行Key和试跑，未知发布优先核对原记录 | 定向状态/作用域/旧结果不重复派发/只读API不解密和令牌变化，隔离实际界面按已保存状态逐步导航且无外部动作；原16与旧账本保持，日志后push | codex | done | commit96e43b2；新增13/相关77、隔离实际界面9、构建截图通过；当前App发布/Key/试跑逐步导航，未知发布先原记录、已有结果直接复核，只读不解密不出站。0.276部署health/资源200及245文件匹配，原16全部对象密文主Key/旧回执unknown保持，真实模型/Dify0；不是实际平台或完整业务验收 |

| 104 | 同一保存修订一次下载DSL、交付说明与SHA256清单，保留模拟/未验证边界 | 定向后端核对三类型、旧修订/文件变化/敏感内容/路径拒绝和只读保护；隔离实际界面下载ZIP并核对成员及摘要、未保存禁用；构建、原16数据保护后更新日志并push | codex | done | commit23868e6；新16/相关44后端、隔离实际界面7及两个ZIP逐成员/摘要、构建截图通过。当前DSL/说明/README/清单同一后台读取，新构建落盘摘要防修改、旧成果仅导出字节，不解密不写库不出站。0.277部署health/资源200及246文件匹配，原16对象密文主Key/旧回执unknown保持；只补打包，不关闭完整T102或业务验收 |

| 105 | 显式选择修改前后两条已保存单轮试跑，对照输入/预期/输出和记录条件 | 定向三类型/严格类型/缺值/未知/敏感与超限内容/旧修订/归属拒绝及只读检查；隔离实际界面选择、差异/条件提示、迟到失效与未保存禁用；原16保持，日志后push | codex | done | commitce708d7；新19/相关32后端、隔离实际界面8、构建与输入/预期/输出截图通过。显式两记录对照及来源条件提示，严格类型/大整数文字保留，未知/缺值不当完成或相同；只读不解密不写库不出站。0.278部署health/资源200及247文件匹配，原16对象密文主Key/旧回执unknown保持；不代表受影响样例自动重跑、受控质量提升或完整业务验收 |

| 106 | 空白Chatflow显式准备售后资料问答/无命中/订单提取失败/合成订单查询分支草稿 | 定向完整图/三类固定回复/提取成功保护/资料来源/既有源拒绝/只读及静态编译；隔离实际界面预览→主动采用→保存确认→构建下载和草稿失效，原16保持，日志后push | codex | done | commit6b2619b；新19/相关35后端、隔离实际界面8及完整预览→主动采用→保存确认→构建下载/原生图核对、构建截图通过。17节点/16连接、检索非空与提取成功保护、精确固定回复和模拟标记；只复用原模型/库/声明，不覆盖已有源。0.279部署health/主包/面板200及249文件匹配，原16对象密文主Key/旧回执unknown保持，真实模型/Dify0；manual固定范围模板，不是模型纯生成或真实业务验收 |

| 107 | 从已有原生订单模拟模板载入合成表及原输入来源，支持继续修改并保留手改代码 | `.venv\Scripts\python.exe -m pytest backend/tests/test_mock_order_read.py backend/tests/test_mock_order.py backend/tests/test_after_sales_starter.py -q`、`npm --prefix frontend run build`及隔离UI载入编辑保存构建/旧历史保护，原16保持，日志后push | codex | done | commitfaba3d1；新20/相关73后端、隔离实际界面9和刷新载入→修改→保存确认→构建下载通过；仅选中代码配置变化，旧成果文件/历史及其它分支保持。匹配v1当前代码/声明才载入，手改/重复键/表达式拒绝，有界AST不求值不执行，迟到读不覆盖编辑。0.280部署health/主包/面板200及249文件匹配，原16对象密文主Key/旧回执unknown保持，真实模型/Dify0；不是通用Python解析或真实业务验收 |

| 108 | 历史单轮输入显式预览并载入当前自由试跑草稿，避免修改后手工复制或沿用旧会话/样例 | `.venv\Scripts\python.exe -m pytest backend/tests/test_saved_run_input.py -q`及前端构建/隔离UI；只读、数字无损、来源/上下文/旧修订拒绝，原16保持，日志后push | codex | done | commitcb26626；新22/相关41、UI6、构建截图及0.281部署通过，输入文字无损/来源上下文拒绝/迟到失效和旧选择清除；原16全部对象密文主Key/旧回执unknown保持，真实模型/Dify0；不代表实际重跑验收 |

| 109 | 将已选择的两次试跑对照导出为绑定观察快照的说明，供修改交付核对 | `.venv\Scripts\python.exe -m pytest backend/tests/test_run_comparison_report.py -q`及前端构建/隔离下载核对；输入/输出需脱敏仍不回显，变化409，原16保持，日志后push | codex | done | commita7e3c5e；新13/相关32、UI5/两个文件与变化409/错标识/迟到拒绝及构建截图通过；0.282部署250文件匹配/health200，原16对象密文主Key/旧回执unknown保持，真实外部0；只读记录说明，非质量提升或业务签收 |

| 110 | 将匹配售后草稿中的合成订单分支生成待复核样例草稿，避免逐例手工填写预期 | `.venv\Scripts\python.exe -m pytest backend/tests/test_after_sales_cases.py -q`及构建/隔离UI；精确模板/当前成果/模拟范围绑定，主动追加未保存样例，不运行，原16保持 | codex | done | commitec3f085；新13/相关52后端、UI6/构建截图通过；0.283部署251文件匹配/health200，原16对象密文主Key/旧回执unknown保持，真实外部0；仅模板订单支路草稿，不是FAQ覆盖或业务通过 |

| 111 | 显式选择已保存单轮样例后依次试跑，首个失败/未知/需人工即停止，保留每条新记录 | 新批预览绑定完整来源、有限次数和加密Key指纹；每次原run入口重新核对快照/顺序/原门禁，同一请求不重复派发；前端主动启动、不刷新续跑；定向后端及隔离UI/构建，真实外部0 | codex | done | commitd73b8d7；新24/相关65及UI7/构建截图通过，来源/Key/策略/顺序并发与首例非通过停止、暂停/离开不续跑；每例与未启动项保留。0.284部署252文件匹配，原16与旧账本保持，真实外部0；非自动影响分析或完整业务验收 |

| 112 | 将97已纠错的完整售后替代草案绑定当前产品，完成具体可审查的单次范围改授方案 | 只对最新运行版做必要定向离线整链、保护快照/原95未知和预留；冻结新plan/manifest及源码哈希，缺少直接改授时live入口零动作拒绝；真实HTTP0，不执行整批 | codex | done | commitdaa4686；0.284同界面整链7项/边界17项通过，12文件plan/manifest冻结，缺直接改授live零动作拒绝，原16与95 unknown/预留精确保持，真实HTTP0；docs/complete-mainline284-live-plan-20261025.md，非平台验收 |

| 113 | 按112冻结方案执行新的完整售后连续真实批，并保留旧95失败和全部未知预留 | 必须直接批准daa4686方案与plan db973882/manifest54be77b1，明确改授旧95零出站范围；0新任务/模型至多3/资源各2/运行4/读取96/登录28，保守23及413不增加，异常整批停不重试；无批准不得live | codex | blocked | commit4fed25b；直接答复call_f5220c40793e44f38b02ce9c1b83a095已保存为新approval，冻结/运行/原16保护匹配；原Docker服务Stopped、Desktop/backend不在、8080无监听，准入前停止，live入口0/无receipt/所有外部0/无新账本，未重试或启动Docker。原批准保留；用户随后继续，原服务已恢复，但启动前发现三项真实消息摘要缺失，原包禁止live，转114修复/115仅技术替换确认，不扩大付费范围 |

| 114 | 修冻结替代包漏三项真实消息摘要的实质准入错误，增加真实模式身份分支的零出站检查 | 保留113批准包不改；新副本前置严格字段检查，离线完整链也执行同一消息身份检查；真实invoke AST替身验证三阶段/错摘要/缺字段在回执或出站前拒绝，原16/旧未知与外部范围保持 | codex | done | commit202e8a6；新13真实分支及前置字段拒绝/原17边界/同界面完整UI7通过，修正19文件已冻结；原批准包及原16/unknown保持，Docker恢复healthy，所有真实请求0；仅等待新哈希技术替换，非扩大范围或真实验收 |

| 115 | 用114修正冻结包执行原已批准完整售后范围 | 需直接确认202e8a6技术替换及新plan f47555b7/manifest b2a89956；沿用call_f5220c4原明确改授，0新任务/模型3/资源各2/运行4/管理96/登录28/估算范围不增，核原包/新包/运行/原16/服务后最多首次live一次，三个内容门禁亲审，异常即停 | codex | blocked | commit07e3aed；直接技术批准后首次live，模型HTTP1/Dify0，在首轮9→10主题严格检查停止，候选未应用且另有retrieval追问。新增11788tokens/配置估算0.005404572非账单；原15/所有密文旧回执/原unknown保持，保守23/两个未派发阶段预留保持，包已消费禁止重放 |

| 116 | 修需求检查把已明确Sierra本机入口/HTTP错误区分说明误判为业务外部接口的缺口 | 仅排除明确本机入口判空/已知平台错误声明及成功result与HTTP错误分开表达；真实调用/API/URL/数据库/http-request节点仍触发；定向来源检查/needs_input保留/无重试，原115失败和生产数据保持 | codex | done | commitc589215；先复现3失败/10通过，修后新13/相关63、UI5/问题卡截图通过，HTTPS正例和真实调用/native节点仍触发；原真实候选仅离线来源重核九主题，retrieval追问仍阻止确认。0.285部署252文件匹配/health200，115停止后数据精确保留，修复额外真实HTTP0，不改判或重放旧失败 |

| 117 | 保存的需求检查失败候选可在当前规则下本地复核，并显式恢复为未确认草稿，避免再次付费访谈 | 完整同修订/源时序/严格契约/引用/敏感及截断拒绝，预览只读；主动采纳产生新修订，原失败和费用不变、追问仍阻断确认，0外部；定向后端/隔离UI/部署/日志后push | codex | done | commit0e87122；新29/相关92、UI8/构建截图通过，0.286部署253文件匹配。代理按常规委托单独恢复现有任务r2→r3未确认草稿，九主题/资料追问保持，旧失败及全部账本/其它15/密文主Key/旧回执保持，外部新增0；不是原115重放或业务通过 |

| 118 | 按原始用户说明逐项补充待答专项，保留其它检查及基础需求，区分操作者/代理来源 | 严格当前检查与用户原话引用、显式预览保存、来源/答案绑定及并发拒绝；新修订不确认，不改旧失败/费用或业务门槛，模型/Dify0；定向后端/隔离UI/部署后日志push | codex | done | commit5fd5bf4；新22/相关114、UI9/构建截图通过，0.287最终254文件匹配。仅依据原话补充retrieval，现任务r4待确认，八需求/其它八检查/旧失败及全部费用/其它15密文保持，外部0。补查修复后续人工/模型复核立即过期；非人类答复或业务通过，不续跑115 |

| 119 | 修改版全项需求复核保留代理来源，避免将代理的受托复核记为用户声明 | 默认人工行为兼容；代理必须明确actor及说明，进入后续来源和摘要、界面可辨，确认仍独立；定向验证/部署，随后按原说明整理现有售后任务到规划就绪，外部0 | codex | done | commit1bb5b83；后端80/UI4/构建通过，0.288部署254文件匹配；默认人工兼容、代理来源及归档摘要有效。现有任务r4→r6保存原两例/模型/FAQ/参数并按委托确认需求，配置未确认；其它15/所有其它对象/密文主Key/旧回执/账本保持，外部0 |

| 120 | 复用已复核真实访谈和r6配置，准备仅两次规划的完整售后独立批 | 不重复首访谈；原版/单文案修改版全图复核、两版发布及四例轨迹方案；零实际请求的完整隔离演练和字段/范围门禁，冻结新包，旧115不改不重放；执行改授另需明确批准 | codex | done | commit46cc6ea；新19文件冻结plan c82bbb29/manifest9df4265f，复用真实访谈只两次规划，正常UI7/首失败2/改版失败5、真实分支8/边界17及协议替身通过，真实HTTP0。现r7仅选原环境，其它对象/凭据/旧115及账本保持；待121明确改授，非平台验收 |

| 121 | 按120冻结方案执行复用访谈的完整售后独立批 | 需直接批准46cc6ea并明确改授115未派发两规划及零Dify范围；模型2/资源各2/运行4/读取96/登录28/新估算0.12，保守23及413保持，异常整批停不重试；原115不重放 | codex | blocked | commita937f70；直接改授后首次规划模型HTTP1/Dify0，互斥分支共用end且重复result/跨分支引用，422严格拒绝，r7 paused且候选未应用；28743tokens/配置估算0.002954352非账单。旧15/密文/95及115/原unknown和settled保持，第二阶段及Dify预留保持，本包禁止重放 |

| 122 | 补齐新流程生成的互斥分支输出规则及完整示例，减少共用终点重复字段/跨支读取 | 不改严格校验或自动修图；新规划契约明确分支独立终点和单节点唯一输出，示例完整可编译，现有手改基线保持；定向模型请求/候选拒绝/编译验证，原121失败与生产数据保持，真实外部0 | codex | done | commit42d354a；新增实际规划请求/完整六节点示例保存确认构建、原错误一次拒绝并保留及既有分支/终点/聚合共10项定向通过。0.289部署254文件匹配，生产r7 paused/原16数据和121冻结包/回执/候选/全部费用精确保持，修复额外HTTP0；未证明真实生成质量，121仍禁止重放 |

| 123 | 准备0.289修复后的独立两版主链续接批，复用已核对需求而不重复访谈 | 保留121失败不重放；仅两规划的正常界面隔离链、严格身份/次数/旧数据保护，核算保守23→24及剩余估算调配，冻结新包；0真实出站，执行需新的明确范围批准 | codex | done | commit455c45c；新19文件冻结plan63358030/manifestd0515b79，正常隔离UI7/身份8/边界25及协议替身通过，实际HTTP0。明确拟单阶段0.055且合计0.10、模型23→24和余量调配；旧规划/访谈/恢复记录写前保护，原16/密文/账本/旧121及原候选精确保持；等待124直接批准，非真实验收 |

| 124 | 按123冻结方案执行0.289修复后的完整两版主链 | 需直接批准455c45c：改授121未派发一规划及零Dify范围、新增一模型槽23→24、从未释放包明确调配模型0.10；模型2/各6000输出tokens/120秒，单次0.055且合计0.10，资源各2/运行4/读取96/登录28/Dify0.02，整体估算0.12非硬账单；异常整批停、不重试 | codex | done | commit074301a；首次live passed，真实模型2/61292tokens/配置估算0.013001028非账单；Dify43 HTTP（登录1/读取32/资源各2/运行4）。原版r8/修改版r12四例与完整轨迹passed，LLM路径1/0/1/0，候选只变一处提示，界面显式保存未手改；旧15/密文主Key/失败账本保持，4/4用满。复用旧访谈，非全25签收 |

| 125 | 成功运行的诊断展示不再误报“尚不能可靠归因”，保留原验收和历史证据 | 本地成功与完整成功轨迹分层说明；失败/未知/规则不符/空或截断轨迹不假称无故障，节点观察提示保留；已保存旧报告只读展示不重写，定向API/报告/UI验证，0真实请求 | codex | done | commitf0a3409；本地成功/完整成功轨迹分层说明，失败/未知/验收不符和不完整证据不改判；后端62/UI6/构建通过，0.290部署254文件匹配。四份实际旧报告只读展示纠正并在下载报告保留原文；生产16任务/原轨迹验收/全部账本密文主Key及124包/回执精确保持，额外模型/Dify0 |

| 126 | 将136项原工作表分离实现与验收口径，建立当前证据与明确能力缺口索引 | 全136编号/原条件保留，未复核明示未知，不把验收缺口当未实现；核当前能力目录和模型测试入口，列出真实开发优先项，0外部/生产不变 | codex | done | commitc6f4ef6；136原编号/条件保持，分105实现工作/31验证交付，65未重核明确保留；现有结构校验通过。核实F01工具请求探测入口缺失，另6组范围扩展不自动当必须承诺；0外部/生产不变，非完整功能审计或完成百分比 |

| 127 | 补模型设置的单次工具请求能力探测入口（F01首批OpenAI兼容） | 明确用户单次付费选择、固定公开样例/受限输出/超时、不执行工具；严格返回名/参数校验、用量未知保留、来源变更与重复/并发保护，普通文本路径不变；API/界面隔离验证后部署，0真实调用 | codex | done | commitbc5e462；首批OpenAI兼容单次固定工具请求测试，本机准备/费用确认/持久回执/同UUID不重发/并发及配置来源保护，严格名称参数检查，不执行工具。新增30/相关76后端、UI8/构建截图通过，0.291部署255文件匹配；真实模型/Dify0且无新回执，原16数据/设置能力/账本密文与124包保持。其他协议及实际账号能力未验证 |

| 128 | 任务级暂停同步停止知识库准备的后续步骤，保留在途结果和显式继续 | 先隔离复现任务暂停后仍建Key/上传；`.venv\Scripts\python.exe -m pytest backend/tests/test_task_knowledge_pause.py backend/tests/test_knowledge.py -q`；三写入阶段/其他任务隔离/未知保留/重启及主动继续，原16数据保护后部署，0真实调用 | codex | done | commit26ab37d；原5失败/1通过复现，新增8/相关59后端、UI5/构建截图通过。任务与同任务可派发知识库作业原子暂停，保留在途结果/资源、主动继续复用；暂停pending重启转未知，页面重开只读跟踪而不自动写入。0.292部署255文件匹配，原16/设置能力/账本密文主Key与124冻结证据保持，真实模型/Dify0，非全部恢复验收 |

| 129 | 上传JSON/YAML材料校验语法并定位编码/语法错误，避免坏文件假称已解析 | 先复现坏JSON/YAML仍parsed；`.venv\Scripts\python.exe -m pytest backend/tests/test_material_parsing.py backend/tests/test_material_text.py backend/tests/test_conflicts.py -q`；真实上传/原文与原文件保留/错误不泄正文/引用确认门禁/人工文字来源，隔离UI及部署保护原16，0真实调用 | codex | done | commit26488a6；原12失败/11通过复现，新23/相关89后端、UI5/截图通过，前端未改复用构建。新上传JSON/YAML校验语法/UTF-8并给行列，坏材料不进已解析来源或绕过确认；原文/文件及人工文字来源历史保持。0.293部署256文件匹配，生产16/设置能力/预算密文主Key与124冻结证据保持，真实模型/Dify0；不追改旧材料，不等于Schema/业务语义/PDF/OCR完成 |

| 130 | PDF未读页明确保留待处理及部分文字，Word按段落表格原顺序提取 | 先复现混合PDF误报成功和Word表格重排；`.venv\Scripts\python.exe -m pytest backend/tests/test_material_documents.py backend/tests/test_material_parsing.py backend/tests/test_material_text.py -q`；真实文件上传/页码范围/引用门禁/原字节/嵌套及合并表格、隔离UI及构建部署保护原16，0真实调用 | codex | done | commitcb4e765；原9失败/2通过复现，新15/相关54后端、UI6/构建截图通过。PDF列未读页、部分文字单独预览仍待处理，Word按正文/嵌套顺序且合并不重复；限定文字范围进入来源说明。0.294部署257文件匹配，原16/设置能力/账本密文主Key及124冻结证据保持，真实模型/Dify0；旧材料不追改，无OCR/全部Word结构或客户业务验收 |

| 131 | 本机资料检查入口，区分原摘要重复/正文逐字重复/同名不同版线索和业务冲突 | `.venv\Scripts\python.exe -m pytest backend/tests/test_material_review.py -q`；只读/归属/修订/未知及有界列表，明确不自动去重或裁定事实；隔离UI、构建及部署保护原16，0真实调用 | codex | done | commit5bb75f4；新增12/相关60后端、UI6/构建截图通过，0.295部署258文件匹配。原摘要/逐字正文重复及同名版本线索分开，已有业务分歧保持；只读当前修订/未知与前100份界限，不自动去重/裁定或重读原文件。原16/账本密文主Key及124冻结证据保持，真实模型/Dify0 |

| 132 | 参考DSL采纳后原文件路径及字节与保存摘要保持一致 | 复现.yml/.json原路径缺失及Windows换行改变；`.venv\Scripts\python.exe -m pytest backend/tests/test_reference_dsl_source.py backend/tests/test_reference_dsl.py -q`；精确字节/原后缀/修改拒绝/旧文件不重写，0真实调用，部署保护原16 | codex | done | commit9f16941；原13失败复现，新15/相关56后端、UI5及两份实际源文件字节读回通过。新采纳保留原后缀及收到文本的精确UTF-8字节，不安全后缀拒绝；改动仍拒绝，旧文件不猜测/改名。0.296部署258文件匹配，资料检查生产r12只读GET200，原16/账本密文主Key与124证据保持，真实模型/Dify0；不是严格业务复现 |

| 133 | Python代码节点入口参数与节点输入的静态绑定核对，拒绝明确矛盾 | 先复现漏main/必填缺失/多余输入仍valid；`.venv\Scripts\python.exe -m pytest backend/tests/test_code_entry_contract.py backend/tests/test_workflow_plan.py backend/tests/test_planning.py -q`；默认/关键字/仅位置参数、动态入口明确未核实、嵌套节点及API/界面不执行，部署保护原16，0真实调用 | codex | done | commit951e5e8；原11失败/8通过复现，新25/相关270定向及UI5/构建截图通过。显式Python入口按关键字核对输入，明确矛盾拒绝保存，动态入口/通配符等保留未核实警告；不执行代码/默认值或自动改名补值。0.297部署259文件匹配，原16/账本密文主Key及124证据保持，真实模型/Dify0；非T078受限执行/返回值/业务验收 |

| 134 | 模型材料正文直接绑定ID与摘要，消息记录输入/结果修订并区分历史上下文 | `.venv\Scripts\python.exe -m pytest backend/tests/test_message_provenance.py backend/tests/test_discussion_mode.py backend/tests/test_interview_progress.py -q`；同名材料/跨任务/当前修订/旧消息不追写/原话证据与讨论语义保持，隔离UI及构建部署保护原16，0真实调用 | codex | done | commit348f87d0f8578b2d76c42fae17a387337a01b5a3；新18/相关151定向、UI5/构建截图通过；同名材料正文绑定ID/摘要、新消息输入/结果修订、旧记录/证据/讨论保持，0.298健康259文件匹配。原CIM/Git拒绝记录保留，后续管理员实际核验所属进程并登记PID，交接后push以finalization-proof为证；真实模型/Dify0，非全部语义隔离验收 |

| 135 | 核对并更新README当前交付，提供更新日志和范围入口 | 核对0.298 health、124/134真实回执及Markdown本机链接；不更改历史回执或运行代码 | codex | doing | 原首页仍写0.270/旧95失败；已按当前真实交付重写概览并明确历史范围，待链接检查与提交 |
