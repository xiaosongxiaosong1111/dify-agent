# isolated-modification385：隔离单句改版核对

本目录只新增本机实现与公开检查。**没有**真实模型、Dify、登录、Task、资源、运行、凭据读取或生产写入。
当前状态不等于真实批准、模型自主通过或业务验收。`prepare` 须由根提交本目录、独立审阅后，在本机授权范围内
先执行只读冻结/隔离准备；只有 `approve`/`run` 需要绑定精确 plan/manifest 的新直接用户答复后执行。
原 r7 模型图存在订单号类型错误；r8/manual 是
正常 POST 保存的人工修正版，原 r7 model 快照和费用保持。本项只核对“r8 完整图 + 单句无答案文案改版”
能否由一次正常模型规划保留为待复核候选，不修改生产图。

## 文件

- `tool.py`：`prepare`、`approve`、`run` 与保护/准入逻辑；默认只打印帮助，无副作用。
  当前约 924 行，超出 650 行预期；超出部分全部用于本轮要求的固定 runtime snapshot/project 同源与 298 源、
  固定 content SHA、进程核验、新三源 Git/LF/父目录链接与 canonical 源绑定、892 独立逐项哈希、dict 形式
  11 root + SQLite capture、申请/审批/消费互锁、预算前缀/最多 1 条守卫、异常后生产与预算前缀复核、
  topic-specific intake answers 及严格两字段 clone/diff，没有复制旧大执行器或产品镜像。
- `checks.py`：临时合成目录、合成 Git/Task/budget/provider、假 Key、假 transport 的公开检查。
- `README.md`：本文件。

## 固定检查

```text
E:/workSpace/dify-agent/.venv/Scripts/python.exe tools/isolated-modification385/checks.py
```

检查不读真实 `work`/`data`/`.runtime`、真实凭据或供应商候选，不调用真实模型/Dify/登录。
它使用合成夹具覆盖：新三源 Git/LF 与旧 377 pin、892 独立逐项哈希、root 的 SQLite capture、
审批完整引用/scope/literal/limits、消费标记、两字段严格 diff、模板/子串两类提示、runtime 进程参数、
Store 只写目标 Task/budget、正常 API 候选保留、坏 JSON/未知用量/额外字段/第二请求停止。

## 最小真实生命周期（prepare 可先做只读冻结；approve/run 尚待新直接批准）

```text
python tool.py --project E:/workSpace/dify-agent prepare --source-commit <40-hex>
python tool.py --project E:/workSpace/dify-agent approve --authorization <仓库外直接答复.json>
python tool.py --project E:/workSpace/dify-agent run
```

- `prepare`：在根提交本目录并确认授权范围后，可在**没有新直接模型批准前**执行；它只读生产
  Task/budget/provider/environment/artifact、892 旧封存和 12 根，创建隔离冻结包，不读 Key、不发模型/
  Dify/登录/生产写入。校验新三源 Git 提交/worktree LF、固定 377 pin、固定
  `.412.0-4b3c27aad0a80a616364` 快照 manifest/298 源及 project+snapshot 同一 rel 字节、固定
  content SHA、`data/server.pid` 与 CIM/psutil 所属原 venv、正确 `--app-dir`；创建
  `work/isolated-modification385` 和独立 `isolated-data`。只复制公开 task/budget/provider/environment
  元数据，不复制任何 secret 或 `.credential-key`。隔离需求 `output` 必须含原句恰好一次并替换；同步
  唯一的 faq-no-answer 样例期望；原 intake 记录保留到 `intake_history`；所有副本变更写入
  `plan.isolated.clone_changes` 供根逐项审。
- `approve`：核包、canonical 三源 LF 与已提交 Git blob/`plan.source_files`、旧 377 pin、固定 runtime
  manifest、完整新 ref/literal/scope/limits/single-use/no-retry；授权文件必须在原项目之外且非链接。
  拒绝旧 375/377/380 ref、已批准/已尝试/worker-started/live-output；只有本步需要新的直接用户答复。
- `run`：先通过源/包/审批/生产 capture/12 根/892/隔离 Task/budget/runtime 进程准入，之后才写
  `attempt.json`/`worker-started.json`，再于内存解密唯一 provider Key。只允许一次 chat 端点、6000 输出、
  120 秒、报价 ≤0.100；Store 只写目标隔离 task/task_budget，其它类型/ID/秘密一律拒绝，并在每次预算
  写入前核旧元数据/完整 entries 前缀且最多追加 1 条；同步 HTTP、Dify、额外 URL/模型、repair、第二请求
  全拒。成功/坏 JSON/未知用量/额外字段/第二请求均走正常 API；已知或 unknown 用量、完整响应和失败
  报告耐久保留。异常后独立重核生产 capture/11 旧根/892/隔离预算前缀并写 `failure.json`，不重试、
  不清理结果。Key 只在内存，不写入包、stdout 或异常正文；CLI 只打印安全分类，不打印供应商正文。
  377 `Boundary` 的内部阶段标签仍是 `original`；本批外部角色明确记为 `modified`，不得把旧标签当作
  本项模型自主改版通过。

## 范围与不改动项

- 唯一模型槽拟明确改授 375 最后 1 槽及 0.100 USD 预留；不自动释放差额、不借退旧槽。
- 其余保守上界保持：57 模型 / 1730 读 / 50 登录 / 资源 30 / 148 Service / 模型估算账本 3.355473652 不增。
- 375 保留的 116 GET、资源各 2、14 Service、Dify 估算 0.100 不是本批允许执行的操作；本批只拟 1 模型、
  0 生产写入/Dify/Task/资源/登录/运行。
- 生产 27 Task、全部密文资产、原静态包/ZIP、十二根、892 旧封存和旧 isolated 预算前缀均保持。
- 模型候选只保留为 `planning_runs.last_candidate`（`retained_candidate_unverified`）；正式 r8 图不替换；
  不自动采纳、构建、ZIP、导入或运行。人工采纳仍须正常 `POST /api/tasks/{id}/plan` 并记 `manual`。
- 这不是模型自主无错生成验收；真实语义和平台质量仍待根离线审完整原文/图后另定。
