# preserved-planning377：一次原规划，保存未验收模型建议后退出

本目录只新增本机实现与公开检查，**没有**真实模型、Dify、登录、Task、资源或运行。
真实执行必须先把本目录提交并由 root 在 `E:/workSpace/dify-agent` 原机
`work/preserved-planning377` 冻结，再取得新的直接用户答复绑定精确 plan/manifest。

## 范围

- 目标只复用既有 Task `1154f0c0-5e01-4492-b5c7-97bfbbbc2a61`/r6：两已过真实访谈、
  旧 `needs_decision`、三条 settled 与 `.600` 预算原样保留；不新建/复制 Task，不重访谈。
- 一次正常 `POST /api/tasks/{id}/plan/generate`，`max_retries=0`、6000 输出 tokens、
  120 秒、单次配置价预估 ≤ `.100`，0 JSON 修复、0 重试、0 后阶段。
- 有效模型建议由正常产品代码保存为 `workflow_plan`、`plan_source=model`、
  revision+1、版本快照、计划系统说明与模型消息，配置仍未确认；worker 随即退出。
- 语义不自动通过；不 build/ZIP/import/发布/Key/Service/运行。root 之后离线读完整
  原文和完整图；worker 不等待 root 回执，也没有 300 秒复核时钟。
- 生产只允许写目标 `task` 与 `task_budget`；`execution_limits` 明确保持 `None`，
  不照搬 375 的 12/45 强制写入。旧对象、密文、文件、旧前缀、859 封存保持。

## 文件

- `common.py`：只读 SQLite/摘要/严格 JSON、历史前缀、859 封存合并、源 pin。
- `worker.py`：正常 API 单次调用、极窄 Store/模型守卫、完整原文归档、结果 JSON。
- `tool.py`：`sources` / `pending` / `approve` / `validate` / `live` 生命周期与互锁。
- `checks.py`：公开行为检查。
- `README.md`：本文件。

## 公开检查

```text
python tools/preserved-planning377/checks.py
```

检查使用新临时 `work` 子目录并清理；不读现有 `data`/`work` 原文、不发真实 HTTP。
它验证：完整图经真实 `main` 正常 API 保存并退出、完整原文 SHA、3+1 账本与
`execution_limits=None`、坏 JSON/`needs_decision`/未知用量每次仅一个 HTTP 停止、
第二次模型调用/其它 endpoint/Dify/同步 HTTP/错误 provider 或凭据在派发前拒绝、
错 Task/revision/旧前缀/预算写入拒绝、859 封存合并并交给实际 `validate_plan` gate
做计数/摘要/regrant 篡改反例、临时同形 27 相对 map 调实际
`load_sealed_map`/`verify_sealed_map`（含越界/SHA 反例）、live-output 与根
receipt 反例、runtime binding 实际 gate 拒绝 build/version/count/
hash/path 篡改、源 pin 等于工作树且可编译、旧 ref/非直接批准/篡改/重放拒绝；
保存后再次只读仍能取完整图。失败结果保存无凭据的 `failure_type`/`failure_reason`、
`stop_reason` 与实际 `stage_counts`/`model_http_started`/`physical_http`。
公开结果是 **synthetic_prior_shape**，不是真实访谈或模型质量证明。

## 真实生命周期（仅拟议）

```text
python tool.py sources
python tool.py pending
python tool.py approve --authorization <仓库外真实直接答复 JSON>
python tool.py validate
python tool.py live
```

- `pending` 只读原机摘要/密文哈希/存在信息、CIM/本机 runtime 与 859 旧封存；
  不登录、不解密、不发 paid 请求，不写 approval/attempt。
- `approve` 只接受仓库外 JSON：`authorization_source=direct_user_reply`、
  `scope=preserved-planning377`、新 `question_ref=call_ID/q0`、literal
  `允许将375剩余一槽及0.100 USD预留明确改授本次单规划批`，并绑定当前 plan/manifest
  与 one-model limits；拒绝旧 375 `call_f5b63df1752f441284ac9ee97f031930/q0`
  及旧 371 等引用。
- `live` 只认原机 canonical 目录；先核冻结源、批准、数据基线、runtime、859 封存与
  375 stopped/model0/read6/login1/其余0/physical7、无迟到 receipt，再 exclusive
  写 attempt 与 worker 标记；失败即消费，不重试/续阶段。
- 真实范围尚未授权；当前回答不构成新模型批准，旧未派发槽不自动借退。

## 375 封存读取

- `work/autonomous-dual375/seal-after-stop.json` 是 27 项
  `{包内相对名: sha256}` 直接 map，例如 `README.md`、`approval.json`、
  `live-output/progress.json`、`live-output/review-source-faq_read.json`。
- loader 给每个键加 `work/autonomous-dual375/` 前缀；索引项就是该 seal 文件自身
  `work/autonomous-dual375/seal-after-stop.json`，SHA
  `e3daff9307529b626b003d081035a601d9cc81f9a2420d88f2ddd6593fb4cdb6`。
- 旧 `plan.protected_files` 831 项保持 `work/` 项目相对路径；合并
  831+27+1=859。每个路径实际 SHA 比对；重复/冲突/越界/符号链接拒绝；
  旧 seal/plan 字节不动。
- stopped 回执检查根目录和 `live-output`：`review-*.json` 中明确排除
  `review-source-*`，其余即回执并拒绝；source 不被误当 receipt，也不读取内容。

## 已知限制

- 实现交付时未执行真实批或生成原机 plan/manifest；后续精确冻结及真实状态以根 docs/preserved-planning377-plan-20261123.md 和相应冻结/结果记录为准。本 README 不代表直接批准或已消费状态。
- 真实旧封存布局由 root 只读确认，后续真实 pending 才首次现场核验；
  当前 checks 只用临时同形 fixture 调实际 loader，不读真实 work/data。
- runtime 归属要求 `psutil` 或 PowerShell CIM 可查询；查不到即停止。
- 运行身份门要求实际 exe 为原 `.venv/Scripts/python.exe`、命令为
  `-m uvicorn app.main:app`、host `127.0.0.1`/port `8765`，并严格解析
  `--app-dir`（引用/非引用/`=`）规范化大小写/斜杠/绝对路径后等于固定 backend；
  只保存 PID/exe/选中 backend 与 hash，不保存完整 command。
- 源 pin 固定 `6fbd030`（375 `derivation.py` 纯 helper）与 `4ac8e32`
  （374 `reuse_policy.py`/`storage_guard.py`），只读 Git blob 并规范 LF；
  不动态修改旧 scope，不导入旧平台框架。
- 公开 green 不等于真实模型、Dify 平台或业务验收；完整模型主线仍未通过。
