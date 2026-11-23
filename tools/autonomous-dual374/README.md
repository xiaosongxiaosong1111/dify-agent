# 374 既有真实访谈复用的三阶段执行器（仅本机）

> 状态：**仅本机实现与隔离验收**。不提供 live 入口；`worker.run('live', ...)` 在任何 DB/Secret 读取前无条件拒绝。本目录不是批准、冻结或真实执行回执，也不代表真实模型质量、Dify 平台或业务验收。

## 范围

- 只复用 Task `1154f0c0-5e01-4492-b5c7-97bfbbbc2a61` 的既有两真实访谈与既有 3 条 settled 账本；不重复付费访谈、不新建 Task、不续跑旧 371 阶段。
- 本批只允许三个新模型阶段：`original_plan` → `modified_interview` → `modified_plan`，各一次；成功后两版 App/发布/Key、12 启动/14 Service/14 原生轨迹/双 ZIP。
- 公开 fixture 全部是合成替身。本机 seed 的任务状态明确标记 `synthetic_prior_shape`，不复制真实访谈原文/回执/凭据，也不把公开 seed 冒充本次模型调用或人类签收。

## 文件与构建

- 只新增本目录。`prepare.py` 的 `sources --output <当前项目 work 直接新子目录>` 从固定 `tools/autonomous-dual337` 复制已核未改模块，并精确替换 `common.py` 的 BATCH_ID/`LIMITS`/`MODEL_STAGES`/`MODEL_TOTAL_USD`，再覆盖本目录的窄改动模块。输出必须是 new、非 symlink、直接位于 `work` 下；不读 DB/Secret、不提供任意 source/patch 输入。
- 源集固定：未改 337 模块 `boundary.py/candidate.py/reviews.py/pagination.py/runtime_reference.py/fixture.json/boundary_checks.py/reviews_checks.py/pagination_checks.py`；本目录覆盖 `worker.py/journey.py/storage_guard.py/synthetic.py/reuse_policy.py/rehearse.py/synthetic_seed.py/reuse_checks.py/README.md/prepare.py`。
- 本批 `common.py` 派生值：`new_tasks=0, model=3, reads=122, login=1, import/publish/key=2, run=14`；`MODEL_STAGES=('original_plan','modified_interview','modified_plan')`；单次 0.100、本批 0.300。

## 准入与保护

- `reuse_policy.validate_start` 绑定既有 Task revision 6、paused、advanced-chat、两真实访谈/versions/planning_runs/intake_history 计数、6 样例、0 材料、`requirements_confirmed=true`/`configuration_confirmed=false`、模型 intake source、无图/App/artifact/run、旧 paused `needs_decision` 及 decision_report；不要求真实 requirements 逐字等于 fixture。真实 Task 的 `interview_attempts` 键可缺省且计数为 0；显式 `None`/映射不允许，其他历史键仍必须为 list 且固定计数。完整 task/budget 摘要照旧绑定。
- 旧预算必须 `limit=0.600`、`policy_revision=1`、3 条全 settled 合计 `0.020125524`、同 provider、无 unknown/reserved；旧 ledger 与其它字段完整保持，最多追加 3 条（总 6），每条 ≤0.100、合计 ≤0.300；旧 3 条不从“新 3 次调用”计数。
- `execution_limits` 实际允许缺失；首次必须通过正常 API 设为 12/45/None；已存在时只允许同值并保持原 policy。
- `storage_guard` 只放开目标 `task`/`task_budget`/`execution_limits`，其余 26 Task、旧对象、旧密文/资产不变；拒绝新 Task、其他 Task 预算、历史前缀缩短、旧 decision_report/ledger 改写。
- 旧 371 的 831 封存与旧批准/attempt 不在本批构建中改动；375 才增加 pin/manifest/批准门。

## 本机验收边界

- `python reuse_checks.py`：用真实 Guarded Store/策略行为测试目标绑定、旧消息/版本/planning_runs/decision_report/账本被改或删、其他 Task/预算、新 Task、预算策略/上限、第 4 模型/第 123 GET/第 2 登录、旧 seed 不计新调用、缺目标/缺摘要/同计数历史变化、`interview_attempts` 缺省与空 list 的区别、早停 policy 和 live 早拒绝。`--check` 由根固定只调用本检查；本文件不声称该检查已经由本目录运行。
- `python rehearse.py --all --output <work 新目录>`：三个子进程 `success`、`invalid_model_json`、`second_turn_business_failure`；物理 HTTP 0。是否实际运行及计数以根日志为准，本文件不代替回执。
- 未在本目录执行真实模型、Dify、登录、Task、资源或文件回执；本目录也**没有**完成 freeze/pin/manifest/批准门。根后续独立运行 sources/checks/rehearse 并做完整 diff 与 375 冻结。
