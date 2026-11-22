# 自主双版371执行器（本机准备，2026-11-22）

> 状态：**未批准、未真实派发**。本目录不是批准回执，不恢复真实范围，不重放 337/366/369/370；真实模型、Dify、登录、新 Task、资源与外部写入在明确新直接批准前均为 0。本机结果以独立冻结记录为准，不能据本文件推导真实通过。

方案见 [`../../docs/autonomous-dual371-plan-20261122.md`](../../docs/autonomous-dual371-plan-20261122.md)；冻结包内另有 `approved_scope.md`，本文件只说明使用边界，不替代方案或批准。

## 范围与改授

- 371 是唯一新批；拟明确改授 366 **完全未派发**的 Task1、产品模型 6 上界（成功序列 5、无第 6 阶段/JSON 修复）、管理 GET128、App/首次发布/Key 各 2、Service14/12 启动、模型 0.600＋Dify 0.100 USD 估算包；仅新增 1 次加密登录，登录保守 48→49。
- 不新增模型或读预算，不把开发 DeepSeek 委派计为产品费用；旧 settled/unknown/预留不自动退借或改授。没有用户新直接批准，366 的零派发槽仍是 366，不得自动派发。
- 60 分钟整批、Task12 启动/45 分钟；每次模型最多 6000 输出 tokens、120 秒、估算预留 0.100 USD；模型估算账本 3.355473652 不增。非账单硬限，宿主费用未知。

## 固定 CLI

使用项目 `.\.venv\Scripts\python.exe` 或原机绝对 venv；动作与参数固定：

- `prepare.py sources --output <当前项目 work 下直接子目录>`：只核/复制已 pin 源码与 profile，不读真实 DB、Secret 或 Dify；输出 root 只准新目录。
- `prepare.py pending --project-root E:/workSpace/dify-agent`：只读本机 DB 摘要/存在信息、固定快照、本机 runtime 与 CIM，派生待批 plan/manifest；不创建批准/attempt/worker-started。
- 冻结包内 `execute.py validate-pending`：只读核验待批包，不解密 Secret、不发模型或 Dify。
- 冻结包内 `execute.py approve --authorization <仓库外真实直接批准记录 JSON>`：仅在收到实际新直接答复后，exclusive 追加绑定精确 plan/manifest 的 approval。
- 冻结包内 `execute.py validate`：有批准后的准入只读校验。
- 冻结包内 `execute.py live`：只对唯一 canonical 包执行一次；禁止覆盖、force、reset、重签或旧批重放。

`prepare.py` 只放在 `tools/autonomous-dual371`；冻结时复制为 `freeze.py`。公共 sources 为 19 个代码/配置文件，冻结 manifest 为 21 项，加自身共 22 文件。

## 批准与冻结

- `approve` literal reply 必须为“允许改授366未派发范围并新增1次登录，执行独立371批”，scope 为 `autonomous-dual371`；question_ref 必须是新的 opaque `call_ID/q0`。
- 明确拒绝旧 337/366/369/370 的 ref、旧回执或代理决定冒充的答复；approval 只 exclusive 追加，不改 plan/manifest，不覆盖已有记录。
- pending 只读已有本机信息；源码、配置或数据变化必须拒绝，不得 refresh 新包沿用旧批准。没有批准时 `live` 必须拒绝；即使有 approval，也不允许重放任何旧 attempt/worker-started 标记。

## 唯一包与旧批保护

- live 只认原机 canonical `work/autonomous-dual371`；非原机、源目录、克隆同名路径和旧 337 目录均在读 Secret/外部/写 approval 或 attempt 前拒绝。
- 旧 337/366/369/370 已消费，不能自动复用、改授或借槽；366 本地封存事实为 stopped、model0/reads0/login1/import0/publish0/key0/run0、physical_http1、无 task_id，仅由封存索引绑定，不自动归还预留。
- 十二数据根与 795 保护文件保持：旧 733 + 337 封存 24 + 1 索引 = 758，加 366 封存 26+1、369 封存 2+1、370 封存 6+1；不读 Secret、不改旧封存或旧包字节。

## 执行前重核与边界

- 原机快照 0.410.0-23c94dbe89553f265c3b / 298；执行前动态核当前 PID、CIM/执行文件、health/页面与源快照一致，不固定旧 PID 做准入。
- 专用环境/原空间/模型/FAQ 身份照录；deepseek-flash、thinking=false、温度 0.2、最大输出 512、FAQ TopK3 无阈值不重排，不改全局配置。
- 六例七轮/两版/14 原生轨迹/双 ZIP 仍以真实执行结果为准；原版两处无答案文案与改版同步替换，其余图/业务/资料引用保持。
- 公开检查与替身只证明本机协议和边界，不证明真实模型质量、Dify 平台或业务验收；读文档不等于已测试。
