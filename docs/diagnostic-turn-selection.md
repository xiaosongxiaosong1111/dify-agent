# 多轮样例按已保存轮次查看诊断

运行记录展开后，“诊断轮次”默认仍为自动取失败轮或末轮；可明确选择已保存的第1—10轮。切换只展示对应轮次已有诊断；主动点击本地分析或远端读取才发起该项操作，不批量读取全部轮次。两轮订单样例可以分别核对缺号追问和补号查询的轨迹，效果仍须实际平台验证。

原355固定快照已复现：selected_result固定取末轮/失败轮，接口拒绝turn_index，首轮无法主动选择。原POST `/api/tasks/{task_id}/runs/{run_id}/diagnose`增加可选`turn_index`（严格整数1—10，null/省略保持旧自动选择）。只从当前已保存多轮样例、已派发轮次的唯一索引取结果；缺失、重复、布尔索引、超出样例或非多轮记录拒绝，不回退到另一轮。非法来源在解密及远端读取前拒绝。

每轮诊断仍绑定整个源运行摘要、修订、原App/环境及当前成果；途中任一源结果变化拒绝保存。原阻塞Chatflow消息映射仅核该轮消息/会话，原生ID路径和版本边界保持；每轮读取分别计入管理请求。Agent只能本地分析。没有新模型、运行或资源创建，不能用当前功能扩大旧批准。

整体状态与所选轮状态同时展示；显式选择完成首轮时不借用后续轮的错误、HTTP拒绝或整批验收失败。首轮自己的规则失败继续提示不匹配；未知/在途轮诊断不会清除整体unknown或重跑保护。切回旧轮能看已存报告，成功轮与非最新报告不自动准备修复，既有后端修复门禁保持。原始结果、用量、费用和验收记录不改写，正常保存仅增加诊断及Task更新时间/存储序号。

124项新增及直接相关定向后端、类型检查/正式构建、5个公开临时Store实际界面场景通过：双轮分别读取/切换无请求/回看、首轮不借后续错误、未知轮保持、重复轮无选项、途中来源变化拒绝。正常两轮场景4次本地诊断保存、8次替身管理GET；其它场景的精确保存/替身读取次数也已核对，所有真实模型/Dify HTTP0，自动修复读取0。视觉核对节点摘要，未实际验证Chatflow订单理解。

辅助验证的初次节点定位未展开摘要且标题含状态，已按真实界面修正；数据比对先后未计正常updated_at和state_sequence，已严格改为验证预期保存次数而非忽略业务字段。原失败日志保留，不冒称首次全绿或真实平台失败。前端构建初次未找到全局tsc，改用项目已有node_modules内命令，无新安装。

2026-10-29原355服务未运行，已按原start.ps1恢复355/PID35660、health200；源289及原18保护核对通过。功能随后经归属核验原stop/start部署0.356.0-5476d30269eac2811387/PID35272，289文件匹配、health/前端200。实际r17 Workflow仅GET核四运行/两样例保持且无多轮选择器；原18/账本密文资产及全部消费包保持。未向真实Chatflow读取新轨迹、不升级原25/原订单完整链结论。

[安全结果](diagnostic-turn-selection-result-20261029.json)。定向复核（新输出目录）：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_diagnostic_turn_selection.py backend/tests/test_chatflow_diagnostic_source.py backend/tests/test_run_diagnostics.py backend/tests/test_success_diagnostic_view.py -q --basetemp work/NEW-TURN-TEST
# frontend内 .\node_modules\.bin\tsc.cmd -b 及 .\node_modules\.bin\vite.cmd build
.\.venv\Scripts\python.exe tools/check_diagnostic_turns_ui.py --output work/NEW-TURN-UI --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
```
