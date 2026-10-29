# Chatflow阻塞结果的节点诊断定位

现有诊断依靠保存结果里的workflow_run_id。Dify1.17.1普通非暂停Chatflow阻塞结果返回id/message_id、conversation_id等字段，不能将其中task_id或消息ID当作原生运行ID；原路径因此只能报告缺少来源。第222补上目标消息只读映射，沿用现有诊断按钮，不重新执行对话。

只在明确read_remote=true、运行类型快照为advanced-chat、原环境绑定一致且登记版本1.17.1、原生运行ID缺失时启用。先核保存的消息别名：存在的id/message_id须为合法且相同的UUID，会话ID须合法；连续案例须与该案例保存会话一致，所选失败轮或pending轮不替换为其它轮。原生ID已存在却无效时拒绝，不以查消息掩盖冲突；未知版本/类型/身份不发映射请求。损坏的pending/轮次结果不再导致诊断崩溃或借前一轮来源。

正常路径增加一次`GET /console/api/apps/{原App}/messages/{保存message_id}`，使用原管理凭据。消息回复id和conversation_id须与所选来源一致；如出现app_id也须匹配，workflow_run_id须合法。仅保存规范化身份映射，不持久化返回的query/answer/message等正文。随后沿用原原生运行详情、节点、已发布图读取和本地成果对照；消息身份不代表节点/图或业务通过。原Workflow及已有合法workflow_run_id路径不新增消息读取。

任何身份不符、缺运行ID、HTTP/格式失败都不猜其它来源，不查消息或运行列表、不用task_id，不追加诊断层重试；原DifyClient的认证续接仍受原批准边界约束。来源在采集中变化时不保存混合诊断。原运行输入/结果/状态、验收、配置、预算及重跑保护保持，只可新增本机诊断记录。页面明确说明消息映射与节点/发布图验证分别核对。

依据固定版本的[响应转换](https://raw.githubusercontent.com/langgenius/dify/1.17.1/api/core/app/apps/advanced_chat/generate_response_converter.py)、[消息ID构造](https://raw.githubusercontent.com/langgenius/dify/1.17.1/api/core/app/apps/advanced_chat/generate_task_pipeline.py)、[按App过滤的消息读取控制器](https://raw.githubusercontent.com/langgenius/dify/1.17.1/api/controllers/console/app/message.py)及[MessageDetail字段](https://raw.githubusercontent.com/langgenius/dify/1.17.1/api/fields/conversation_fields.py)。普通阻塞与包含原生ID的暂停响应分开处理，没有将持续变化的main分支当契约。

76项定向后端检查通过，覆盖标准响应/别名/坏原生ID/错类型版本/错消息会话/App/缺runID/失败不重试/原有直接ID路径/选失败及pending轮/中途变源、脱敏及原Workflow诊断回归。类型检查、正式构建及四个正常界面场景通过：正常映射、错会话、消息404、缺消息来源；每例先本地分析再显式远端诊断，临时Store只增加诊断。正常SDK替身为4次管理GET，错会话和404各1，缺身份0；全部真实HTTP0。最初辅助浏览器脚本漏展开保存运行详情，按钮不可见而停止；修正展开后通过，原日志保留，非产品或真实平台失败。

2026-10-29受管理部署0.354.0-b00d7d8eae337c029251，289源/快照文件一致，新PID31388；核旧353/PID29440归属后原stop/start，health和前端200。实际页面仅GET读取既有Workflow r17无命中诊断，原轨迹保持且没有误标消息映射，未发新diagnose POST。18Task/六费用/所有密文资产主Key及消费包保持，部署仅server.pid变化。

本功能尚未在真实Chatflow消息上出站验证，不升级原§11订单链或全25验收。未来新真实范围需计入这一次消息管理GET及既有后续读取/认证可能请求；不借旧预留或自动重新运行C1。本轮实际模型/Dify请求均0。

[安全回执](chatflow-message-diagnostics-result-20261029.json)。定向验证：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_chatflow_diagnostic_source.py backend/tests/test_run_diagnostics.py -q --basetemp work/NEW-CHAT-DIAG
# frontend内先tsc -b、vite build，再回项目根
.\.venv\Scripts\python.exe tools/check_chatflow_diagnostic_ui.py --output work/NEW-CHAT-DIAG-UI --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
```
