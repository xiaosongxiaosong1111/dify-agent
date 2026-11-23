# 规划澄清的最终一致性核对（0.412.0）

已有规划提示原本就区分业务缺失和等价实现；输入也没有丢失。377实际模型仍返回澄清，同时正文承认现有规则可实现，未形成完整图。因此本次只补充模型输出前的核对规范，不把模型能力问题说成解析器故障。

Workflow/Chatflow在输出error/needs_decision前逐项对照当前需求、配置及类型契约，已给定或能由已有事实直接得出的事项不重复索要业务确认。业务含义和已确认约束相同的中间值传递、固定文案放在受支持code/template/answer的位置，允许选择完整可验证实现；保留原输入，不添加未要求的trim、改写或默认值。

真正缺失的业务规则/资源、冲突、不同业务含义或影响费用/体验的取舍仍须澄清；不能发明状态、算法、资源、URL或删除分支。最终若没有未决必需事项，应输出完整nodes/edges，不能一边说无需澄清一边返回error。程序仍对每个模型error正常停止、保存实际用量，不忽略error、不造图、不追加调用。Agent独立提示、输出schema、确认/费用/重试与编译器不改。

DeepSeek会话b9137036-3e98-49f9-8726-eca6432ed64d调查和实现。仅backend/app/main.py初始Workflow/Chatflow提示及版本0.412.0、docs/workflow-plan-contract.md新增两段通用说明；根复核完整差异，未接手代码或新增镜像字符串测试。

根58项既有定向检查过（入口上下文、能力、澄清、当前契约、重规划API、对话状态规划），不是全量。另用隔离实际API捕获三类型上下文：Workflow/Chatflow收到新契约、Agent不继承；真实缺失的合成error都只一次调用并暂停，原需求/配置/修订保持，物理HTTP0。日志work/planning-choice379-root-tests.log及context.json/log，不提交原始工作数据。

部署前原机0.411.0-90c28f738d4306fbff75/298/PID12020，27任务空闲、十二根/874封存每SHA、Task和预算、凭据资产只读基线与preflight过；实现b1c63f4存在后按已核所属PID/venv用原stop/start部署，实际新运行0.412.0-4b3c27aad0a80a616364/298/PID34736，health/页面200，源/快照/执行文件一致；after独立核27Task、十二根/874每SHA及全部旧凭据资产与before一致。证据原机work/planning-choice379-deployment/{before,preflight,after}.json，私有audit-planning-choice379-deployment.py，不覆盖重跑其exclusive输出。真实模型是否遵循新规范尚未验证，本机检查不等于完整图或双版业务通过。
