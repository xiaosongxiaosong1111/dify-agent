# 第393项本机修复结果（2026-11-28）

DeepSeek实现新独立helper `tools/reviewed_diagnostic_redaction.py`，产品诊断脱敏逻辑、旧390六源码和已消费391包保持。它只供未来新冻结计划明确授权后使用，不是批次执行器、用户批准或真实Key许可。

## 修复行为

旧Guard默认仍拒绝所选助手服务api_key。只有新计划明确提供provider_id/用途run_diagnostic_redaction/仅内存/模型调用0/最大1—14读取时，`extend_guard`才增加这一个只读权限；`ScopedDiagnosticClient`仅在正常远端诊断POST建立精确ContextVar上下文。

Task/run/修订/App/environment及UUID、相同Workflow/Chatflow类型、当前阶段、未停止状态、所选provider和环境绑定快照全部匹配才读取。计数不返还，超限拒绝；其它secret、写提供方、模型HTTP与旧Guard/物理边界规则保持。Key仅交现有safe_text，不缓存、输出或持久化；成功/异常后上下文复位，不持锁跨TestClient线程。

## 根实际验收

- 首次DS调用540秒超时exit2，留下3文件，无最终报告；根新增10测试实际过，但源码审读发现正例混用Workflow运行和Chatflow任务，未接收为足够证据。
- 明确返工同网关，新会话2e44ab33-2571-4777-8e5e-4e5963f9de9c正常0/CLI一次过：正例改真正Chatflow保存消息/会话，不预置workflow_run_id，经消息映射、运行详情、节点三GET；补类型、合法ID和三方环境来源校验。
- 根独立11项新增unittest通过，实际TestClient诊断验证加密假Key脱敏，未启用/错来源/错阶段/停止/超限拒绝，成功和异常上下文清除，旧预算/对象/密文保持。
- 根另将所选加密假助手Key接入既有公开完整双版API链：14假Service、14原生诊断、2ZIP全部过，恰14次仅内存假Key脱敏，权限上下文清除；模型与真实网络0。此项补上此前原夹具未选助手服务导致漏掉真实兼容错误的问题。
- 本机修复后旧926封存、原390源/包、停止attempt及整个Sierra预算保持；0新真实请求、0真实provider Key读取。没有前端/后端产品代码改动，无全量/构建/Docker测试。

证据：`work/diagnostic-redaction393-root-v2.log`、`-root-full-chain.json/log`、`-protection.json`，DS原超时与返工日志保留；根私有verify-diagnostic-redaction393-full-chain.py只操作临时公开数据。11项检查命令：

```text
E:/workSpace/dify-agent/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_reviewed_diagnostic_redaction.py
```

## 下一步边界

实现源提交存在后才关闭393，再交DS制作新的独立剩余执行器并冻结：复用现有App和首例，补其原生轨迹且不重跑Service；剩余13Service/11启动与修改版资源各1、103管理读取只能由新明确改授覆盖。真实所选provider Key仅内存诊断脱敏最多14读取，以及是否新登录/新增Dify估算，也要写入具体方案并取得新的直接批准。旧391不恢复或续阶段，本机绿灯不等于真实双版/全自主质量通过。
