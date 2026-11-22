# 自主双版366执行器（本机准备，2026-11-21 制定，2026-11-22 复核）

> 状态：**未批准、未真实派发**。本目录不是批准回执，不恢复真实范围，不重放 337；真实模型、Dify、登录、新 Task、资源与外部写入在明确新直接批准前均为 0。本机结果以独立冻结记录为准，不能据本文件推导真实通过。

方案见 [`../../docs/autonomous-dual366-plan-20261121.md`](../../docs/autonomous-dual366-plan-20261121.md)；冻结包内另有 `approved_scope.md`，本文件只说明使用边界，不替代方案或批准。

## 固定 CLI

使用项目 `.\.venv\Scripts\python.exe`（PowerShell，由 `setup.ps1` 创建）或原机绝对 venv；不要求全局 python。动作与参数不变，固定如下：

- `.\.venv\Scripts\python.exe tools/autonomous-dual366/prepare.py sources --output <当前项目 work 下直接子目录>`：只核/复制已 pin 的源码与 profile，不读真实 DB、Secret 或 Dify；输出 root 只准新目录。
- `.\.venv\Scripts\python.exe tools/autonomous-dual366/prepare.py pending --project-root E:/workSpace/dify-agent`：只读本机 DB 摘要/存在信息、固定快照、本机 runtime 与 CIM，派生待批 plan/manifest。
- 冻结包内 `.\.venv\Scripts\python.exe <包>/execute.py validate-pending`：只读核验待批包，不解密 Secret、不发模型或 Dify。
- 冻结包内 `.\.venv\Scripts\python.exe <包>/execute.py approve --authorization <仓库外真实直接批准记录 JSON>`：仅在收到实际新的直接答复后，exclusive 追加一条绑定精确 plan/manifest 的 approval。
- 冻结包内 `.\.venv\Scripts\python.exe <包>/execute.py validate`：有批准后的准入只读校验。
- 冻结包内 `.\.venv\Scripts\python.exe <包>/execute.py live`：只对唯一 canonical 包执行一次；禁止覆盖、force、reset、重签或旧批重放。

`prepare.py` 只放在 `tools/autonomous-dual366`；冻结时复制为 `freeze.py`，以兼容原文件清单。`sources` 输出 root 与 canonical 均只准新目录，不覆盖、不删除旧文件。`validate-pending`/`validate` 前的准备动作保持 0 Secret 解密、0 模型、0 Dify、0 approval、0 attempt、0 worker-started。

## 批准与冻结

- `approve` 只接受实际新的直接答复：literal reply 必须为“允许独立366完整新范围”，scope 为 `autonomous-dual366`，question_ref 必须是新的 `call_ID/q0`；拒绝旧 337 的 ref、旧回执或代理决定冒充的答复。不得改写或覆盖已有 approval，只能 exclusive 追加绑定本次 plan/manifest 摘要的新记录。
- pending 只读已有本机信息；源码、配置或数据一旦变更必须拒绝，不得 refresh 新包来沿用旧批准。
- 没有批准时 `live` 必须拒绝；即使有 approval，也不允许重放任何旧 `attempt.json` / `worker-started.json` 标记。
- 冻结产生的真实 plan/manifest 摘要根由根在后续独立结果文档记录；本包不写自身摘要，避免循环。
- 新直接批准前不读真实 Dify、不创建任务/App/Key/资源、不发送任何外部请求。

## 唯一包与旧批

- live 只认 canonical `work/autonomous-dual366`；不得覆盖、force、reset、续阶段或重放 337/任何旧批。
- 旧 337 批准已消费，不能自动复用、改授或借槽；新增独立资源范围须新的直接批准。
- 原 26 Task、十二数据根、733 旧封存 + 337 封存 24 + 1 索引（合计 758 文件）及旧账本保持，不改写、不退借。

## 执行前重核

- 原机快照 0.410.0-23c94dbe89553f265c3b / 298 / PID28732，执行前重核动态 PID、health/页面、源码/快照/执行文件一致。
- 专用环境/原空间/模型/FAQ 身份按原方案 ID 照录；分类/提取/回答模型 deepseek-flash、thinking=false、温度 0.2、最大输出 512、FAQ TopK3 无阈值不重排按原 fixture，不改配置。
- 批准前 0 Secret 解密；批准后只在必要进程内存复用本机加密凭据，不从聊天复制，不向开发 DS/日志/Git/ZIP 输出明文；新增运行 Key 按产品加密保存，旧 App 的 Key 按原记录加密留档。
- 独立 pending 只读核验由根执行：三条公开替身路径、无 approval/attempt 检查；未实际执行前不写“通过”。
- 15 个源码模块派生时只允许把 Git 工作区 CRLF 归一为 LF，并核对可信 Git blob pin；根按此口径逐字节核派生源码，除换行外内容一致。原文件、旧封存、运行快照和数据仍按原始字节 SHA 核对，换行归一不扩大到数据；仅 `BATCH_ID` 与 worker 计数字段两处元数据变化。

## 证据边界

公开检查与替身只证明本机协议和边界，不证明真实模型质量、Dify 平台或业务验收；本机结果以独立冻结记录为准，不能据本文件推导真实通过。六例七轮/两版/14 轨迹/双 ZIP 仍以真实执行结果为准；读文档不等于已测试。
