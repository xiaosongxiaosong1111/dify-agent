# 访谈契约缺口核对：`test_planning_decisions.py` 是否已有等价断言

- 核对日期：2026-10-20
- 队列来源：`docs/BACKLOG.md` 第 2 项
- 比对基准：commit `9a8d781` 在 `backend/tests/test_intake.py:117-170` 新增的三组访谈契约失败隔离回归
- 核对方式：静态阅读测试与实现，只做断言比对；未修改产品代码，未运行全量测试，未调用真实模型或 Dify 资源
- 涉及实现：`backend/app/intake.py:99-124`（`validate_review`）、`backend/app/planning_decisions.py:8-48`（`summarize`）

## 1. 被核对文件的断言清单

`backend/tests/test_planning_decisions.py` 共 9 个测试函数，收集到 24 个用例：

| 行号 | 测试 | 覆盖的契约 |
|---|---|---|
| 12 | `test_rich_decision_survives_pause_without_another_call_or_validation` | 合法 `needs_decision` 暂停、不被当成计划校验、单次调用、问题字段归一化 |
| 25 | `test_invalid_error_does_not_coerce_or_apply[8]` | `error` 类型非法时不强制转换、候选不应用 |
| 33 | `test_bad_question_is_flagged_without_converting_it_to_text[9]` | 非法问题行被标记，合法独立问题仍可读 |
| 40 | `test_unrecognized_top_level_fields_never_hide_the_incomplete_response` | 未识别的顶层字段不能隐藏 `incomplete` |
| 46 | `test_question_limit_is_explicit_and_empty_error_only_remains_compatible` | 问题数量上限、非列表 `needs_decision` |
| 53 | `test_secret_like_or_invalid_unicode_is_not_expanded` | 疑似密钥/非法 Unicode 不展开 |
| 60 | `test_error_mixed_with_plan_stops_and_marks_incomplete` | `error` 与计划字段混写时停止 |
| 66 | `test_api_persists_questions_keeps_revision_configuration_and_previous_plan` | API 持久化澄清问题、修订/需求/配置/计划不变 |
| 92 | `test_documented_txt_example_contains_the_extractor_and_compiles_without_running_it` | 文档示例可校验、可编译 |

## 2. 结论

**没有等价断言。** `test_planning_decisions.py` 覆盖的是“规划阶段模型澄清报告”的格式、安全与暂停语义；队列第 1 项新增的三组断言覆盖的是“需求准入检查 `intake_review`”的主题集合、来源真实性和缺口/问题互斥。两者实现契约不同，不能互相替代，也不应把三组 intake 用例直接复制过去当作等价覆盖。

最接近的断言只有语义邻近，不构成等价：

- 未知字段白名单（`:33`、`:40`）只处理 JSON 形状，不处理“检查主题是否属于当前任务标准”。
- 安全文字检查（`:53`）只检查密钥/非法 Unicode，不验证来源素材 ID 或引文是否真实存在。
- `error` 与计划混写停止（`:60`）只说明“错误不能同时带计划”，不表达“检查全部 complete 时不得仍有待答问题”。

## 3. 三类契约失败逐项对照

| 编号 | 访谈契约失败 | intake 侧断言 | `test_planning_decisions.py` 最近断言 | 是否等价 | 缺口 |
|---|---|---|---|---|---|
| C-1 | 多余话题（`extra_topic`） | `intake.py:102` 要求检查项数量精确等于当前标准；`intake.py:106` 要求主题属于当前任务且不可重复 | `:33` 的 `action` 参数只拒绝问题行的未知字段；`:40` 只拒绝整份响应的未知顶层字段 | 否 | 没有“主题集合必须与当前任务标准精确相等”的断言。`planning_decisions.summarize` 不接收任务或期望主题，问题本身是自由文本，不存在主题白名单概念 |
| C-2 | 无效素材 ID（`invalid_material_id`） | `intake.py:112-115` 要求 `(kind,id)` 能在当前资料/需求来源中解析，且引文必须出现在来源正文中 | 无来源引用校验；`:53` 仅做安全文字检查 | 否 | 没有任何素材/来源 ID 或引文真实性断言。`planning_decisions` 的输出结构没有 `evidence` 字段，当前契约下无法做等价校验 |
| C-3 | 已齐全仍带未答问题（`complete_with_question`） | `intake.py:117-123` 要求 `gaps` 与 `questions` 互斥：有缺口才有 1—3 个问题，无缺口必须为空 | `:12` 断言 `needs_decision` 时暂停且不做计划校验；`:60` 断言 `error` 与计划字段混写时停止 | 否 | 没有“无缺口 ⇒ 无问题 / 有问题 ⇒ 必有缺口”的互斥断言。规划澄清没有 `complete`/`needs_input` 检查项状态，只有“继续/暂停” |

### 3.1 为什么不能直接等价

- `intake.validate_review(task, value)` 依赖任务上下文：固定主题集合、可用来源表、基础字段缺口；`planning_decisions.summarize(value)` 只接收模型 JSON，不依赖任务。
- intake 的失败结论是“候选未应用、准入不可确认”；规划澄清的失败结论是“本次计划生成暂停、报告不完整”。断言对象分别是 `interview_attempts` 与 `decision_report`。
- 因而上述三项在 `test_planning_decisions.py` 中是**契约不存在**，而不是单纯的测试遗漏；如果未来规划澄清也引入固定主题、来源引用或“已齐全”状态，才需要补对应断言。

## 4. 隔离语义缺口（队列第 1 项同一用例的其余断言）

除三类契约失败本身，第 1 项用例还断言了失败隔离。`test_planning_decisions.py` 对这些维度的覆盖同样不完整：

| 编号 | 隔离断言 | `test_planning_decisions.py` 现状 | 缺口 |
|---|---|---|---|
| I-1 | 失败时只调用模型一次、不自动重试 | `:12`、`:25`、`:60` 在 unit 层断言 `len(calls)==1`；`:66` 走 API 但针对合法澄清 | 三类非法输入没有 API 端到端“仅一次调用”断言 |
| I-2 | 候选不应用，`requirements`/`revision` 不变 | `:66` 只对合法澄清暂停检查 `revision`、`requirements`、`configuration`、`workflow_plan` 等不变 | 没有针对非法 `error`/非法问题/错误混写的原件不变断言 |
| I-3 | 失败尝试留痕（`applied=False`、具体 `reason`、原始响应摘录） | `:12` 检查 `attempts[0]['status']=='needs_decision'`；`:66` 检查 `status`、`revision`、`stop_reason`、`usage`、成本 | 规划侧没有 `applied` 语义，也未断言失败原因文本和原始响应摘录的持久化 |
| I-4 | 向用户显示 `source=system` 的具体失败消息 | 无；测试只检查 `decision_report` 与运行记录 | 没有用户可见失败消息的内容/来源断言 |
| I-5 | 失败后确认门禁仍拒绝（intake 为 `confirm` 422） | 无；规划流程没有需求确认端点 | 无等价确认门禁；规划侧可考虑断言运行保持 `paused` 且不可继续 |

## 5. 缺口清单

- **GAP-01（C-1，规划侧）**：若规划澄清引入固定主题/能力项，补“主题集合精确相等、未知主题拒绝”的断言；当前 `summarize` 无此契约，不应复制 intake 断言。
- **GAP-02（C-2，规划侧）**：若规划澄清允许引用资料/来源，补“来源 ID 可解析、引文必须出现在来源正文”的断言；当前无 `evidence` 字段。
- **GAP-03（C-3，规划侧）**：若规划澄清引入 `complete`/`needs_input` 状态，补“无缺口时问题必须为空”的互斥断言；当前只有暂停语义。
- **GAP-04（I-1）**：为非法澄清输入补 API 级“只调用一次、不自动重试”断言，而不只在 `draft_plan` unit 层断言。
- **GAP-05（I-2）**：为非法澄清输入补 API 级“需求、修订、配置、既有计划均不变”断言；现有 `:66` 只覆盖合法暂停。
- **GAP-06（I-3）**：补失败尝试的 `reason`、`status`/等价状态和原始响应摘录持久化断言，防止错误被静默吞掉。
- **GAP-07（I-4）**：补用户可见 `source=system` 失败消息的内容断言，确保失败原因不只存在于内部报告。
- **GAP-08（I-5）**：补失败后运行/确认门禁保持关闭的断言；规划侧当前没有 `confirm` 端点，应使用 `paused`/不可继续作为等价门禁。
- **GAP-09（边界）**：不要把 intake 的三组契约断言搬进 `test_planning_decisions.py`。两者契约不同；等价的正确做法是随规划契约扩展新增针对 `summarize`/规划运行记录的断言。

## 6. 验收证据

- 目标文件测试收集：`24 tests collected`（`backend/tests/test_planning_decisions.py`，1.05s）。
- 本次核对未修改任何产品代码；`backend/`、`frontend/` 无改动。
- 未运行全量测试、未调用真实模型、未访问 Dify、未写入任何真实资源。
- 结论仅为静态断言覆盖核对，不代表任何业务验收或 136 项计划完成。
