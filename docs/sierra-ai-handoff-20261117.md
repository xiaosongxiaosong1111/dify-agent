# Sierra 售后 Chatflow 接手说明

交接日期为 2026-11-17。仓库为 [xiaosongxiaosong1111/dify-agent](https://github.com/xiaosongxiaosong1111/dify-agent)，请从最新 `main` 接续。Sierra 是本机运行的 Dify 搭建工作台，当前适配目标为 Dify 1.17.1、App DSL 0.7.0。产品目标见 [需求 §11](requirements-v1.0.md#11-首条端到端验证案例)。

用户目前无法接入模型服务和 Dify。本次交接只做离线开发、验证和 Git 同步，真实调用为零。在当前接手机上，新克隆曾启动 Sierra，`/api/health` 返回正常，模型和 Dify 环境列表均为空。交接记录中的原机项目目录 `E:\workSpace\dify-agent` 在该机器不可用。仓库和旧源码交接包不带原机任务、加密凭据或解密主密钥。

## 已有证据与范围

| 证据 | 观察到的结果 | 验收范围 |
| --- | --- | --- |
| [本机回归 #319–325](BACKLOG.md) | 从空任务追问、确认需求、出图、自然语言改版、保留原版和两份 ZIP。仅静态路径走 r4/r6，替身运行路径走 r5/r7。运行路径中，两版各三例四轮，改版首次试跑前通过数为 0/3，报告和验收摘要按当前修订及 App 对应。 | 证明本机入口与状态绑定、资源和运行保护。模型回复及平台回执均为替身。 |
| [386 人工双版真实结果](stateful-chatflow-live-result-20261029.md) | 人工准备的原版和改版各有六例七轮、双 ZIP、14 轮原生轨迹。两版缺号后补号沿用同一实际会话。 | 固定人工图在当时目标环境中的规则通过。历史批次已消费。 |
| [410 模型候选单版真实结果](complete-answer-platform-live-result-20261102.md) | 受限文案修改的候选经复核与同值采纳后，单版六例七轮和原生轨迹通过。资料不足发生在已检索到片段的路径。 | 单版平台链证据。空检索分支和模糊目标起步的自主双版仍待实证。 |
| [420 原版规划实际结果](reviewed-spec-planning-live-result-20261102.md) | 手工准入通过，模型随后返回澄清问题，流程停在 `needs_decision`。 | 未取得图或 ZIP。原版提示和案例只传当前需求，避免混入后续改版计划。 |

最近的分项验证记录在 [CHANGELOG](../CHANGELOG.md) 和 [HANDOFF](../HANDOFF.md)。本机重点入口是 [空任务双版回归](../backend/tests/test_after_sales_intake_to_graph.py)。当前没有普通 `pending` 项，历史 #288 的单版冻结方案与本次自主双版范围不同。接手时按最新 BACKLOG 核对，取最早的 `pending`，旧批次和旧额度预留不继承。

第326项补齐了新机安装所需的 `jsonschema`，并对齐 Python 和 Node.js 预检。Python 3.11.15 隔离目录执行正式安装和前端构建后，50 项重点测试通过。Python 3.12 锁文件环境中，结构化输入、售后双版、会话、交付和启动快照共 142 项定向测试通过。

## 在另一台机器启动

Windows 安装需要 Python 3.11+、Node.js 20.19+（限 20.x）或 22.12+，以及 npm。首次用下面的命令克隆。已有正确克隆时从 `git status` 开始，先保留既有修改，再切换到 `main` 并快进同步。

```powershell
git clone https://github.com/xiaosongxiaosong1111/dify-agent.git
Set-Location .\dify-agent
git status --short --branch
git switch main
git pull --ff-only origin main
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
Invoke-RestMethod http://127.0.0.1:8765/api/health
Invoke-RestMethod http://127.0.0.1:8765/api/runtime
```

本机入口为 [Sierra](http://127.0.0.1:8765/)，安装和运行细节见 [README](../README.md#快速启动)。`setup.ps1` 优先使用 `backend/requirements-lock.txt`。健康接口只证明本机服务启动，目标连接要分别核对。运行使用启动时的固定快照，源码更新后按项目原有停止及启动脚本重建运行快照。

离线回归使用独立的临时数据目录与替身模型及 Dify。可从以下最小入口确认源码链路。

```powershell
$sierraTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("sierra-handoff-" + [guid]::NewGuid())
$sierraPriorDataDir = $env:FLOWCRAFT_DATA_DIR
try {
    $env:FLOWCRAFT_DATA_DIR = Join-Path $sierraTestRoot "data"
    .\.venv\Scripts\python.exe -m pytest --basetemp (Join-Path $sierraTestRoot "pytest") backend/tests/test_after_sales_intake_to_graph.py backend/tests/test_delivery_bundle.py -q
} finally {
    $env:FLOWCRAFT_DATA_DIR = $sierraPriorDataDir
}
```

## 接通后的真实验收顺序

1. 先向用户核实当前可用的目标和约定范围。可使用原主机的加密配置，或由用户在当前 Sierra 的「Dify 环境」「模型接入」登记。凭据只通过该主机的安全入口保存。确认实际 Dify 版本、工作空间、公开 FAQ 知识库、搭建模型和 Dify 应用运行模型及相应权限。只连通模型时，可先做真实访谈和规划，DSL 标记待验证。
2. 新建空 Chatflow，输入「我想做一个售后问答助手」。让模型追问，保留对话和用户确认，明确资料范围、无答案行为、订单模拟、模型参数和资源操作。使用公开合成案例。原版只提供当前版要求和当前样例，改版要求留到下一版。
3. 收到模型完整图后从正常入口检查、保存和确认。先完成原版的新 App 导入、发布、运行 Key 配对及样例试跑，随后导出原版 ZIP。交付入口只接受当前修订，切版前保存原版包。
4. 让用户以自然语言提出改动，保留原版。复核完整候选的变化范围，明确采纳，重新确认受影响的需求与配置。使用单独的新 App 发布新版，完成该版试跑、原生轨迹及 ZIP。旧 App 和历史通过记录保留。
5. 两版分别使用已确认的六例七轮。六例为 FAQ 政策命中、资料无法回答、范围外澄清、模拟订单存在、模拟订单不存在、同会话缺号后补号。每轮核对实际输出和对应原生节点轨迹，核实命中规则及补号续接的实际会话。核对环境、App、当前发布图、成果摘要与报告修订。验收样例权威参考为 [现有公开合成样例](../tools/complete-answer410/fixture.json) 的 `cases`，目录内历史脚本仅供查阅。
6. 每版交付 DSL、清单及摘要、需求和配置说明、样例预期与实际、轨迹证据、模拟依赖及真实订单接入待办。在交付包报告里用样例 ID 和试跑 ID 对照「当前修订的样例汇总」和「当前 Chatflow 样例实际回复」。报告只摘出已绑定的保存回复，疑似凭据及超限项标为省略。原生载荷缺少不可变发布版本关联时需明确记录证据边界。两版都经真实验证后，再按需求 §6 标记本次范围。运行证据与 ZIP 的静态校验标记按实际记录。异常或未知回执先留证并停止重发，保留原样例和历史记录，定位后按当前许可续接。

每次推送前更新根 `CHANGELOG.md`，写明改动、实际验证和剩余边界。启动或用法变化同步更新 README，交接状态更新 HANDOFF 和 BACKLOG。仅提交审阅过的源码、测试和文档。将 `data/`、`work/`、凭据、运行日志、未经脱敏的响应和交付 ZIP 保存在仓库外。

## 可直接发给接手 AI

> 请接手 Sierra。同步 https://github.com/xiaosongxiaosong1111/dify-agent.git 的 main，先读 docs/sierra-ai-handoff-20261117.md、HANDOFF.md、docs/BACKLOG.md 和需求 §11。按最早 pending 继续。目前连接不可用，先做有明确复现和验收命令的本机工作，已有离线回归不用反复重做。等我提供可访问的已登记连接及当前授权范围后，先核对工作空间、知识库和模型，从空 Chatflow 输入「我想做一个售后问答助手」，完成实际模型追问、出图、自然语言改版，两版分别通过六例七轮真实试跑、原生轨迹核对及同修订交付。订单保持明确标记的模拟依赖。旧批次不要重放。每次推送前更新 CHANGELOG，验收事实写进 HANDOFF 和 BACKLOG。
