# 导入前读取期间的暂停保护

2026-11-21，BACKLOG355／清单23，FR36与恢复/未知结果边界。

Codex拒绝DeepSeek首次把“暂停后新的人工run/import”一概当缺陷的解释：正常页面允许用户主动再次操作作为继续，不应发明无出口的暂停锁。转而要求核同次操作自动跨暂停：已有Dify手改来源的导入先GET导出草稿，若用户此时暂停，旧代码读取完成仍会import_new。根正常API独立复现HTTP200/一次创建/新App绑定/run成功而任务仍paused。

DeepSeek仅改main.py写入前检查及特定错误映射，新增test_import_pause_preflight.py。准入快照绑定pause_generation，来源读取及内容/名称检查后、import_new前在本机锁内核当前代际/暂停，暂停已变化即已知未派发，原错误结算保存failed、outcome_unknown=false和专属code，返回409；不留pending、不冒充unknown，不绑定App，保留原任务修订/成果/来源和旧运行。锁外网络，原写入不会自动重试。

用户暂停后新发的明确人工导入仍走原门禁；写入已发出之后再暂停，实际成功/App绑定或未知回执必须保留，不能回头标未派发。检查点不能取消已送出的请求。

根最终独立82项通过、151未选：新四项和DSL往返/API/发布恢复/多轮的import、pause、restart、recover、unknown定向；前置56已过不重复累计。DeepSeek外部检查经一次新测试预期自修通过（新的主动导入成功应imported，而非仍paused）；产品和旧测试未因此放宽。全差异已核，真实产品模型/DifyHTTP0、临时数据与假导出/导入，无前端/依赖修改、不跑全量。

实现f9c18b9已保护部署0.410.0-95cb99c5a273e8ab0e6a/298/PID42604，十二根/733/337封存24/26Task密文保持，health/页面200、源码/快照/所属执行文件一致。原机work/recovery355-deployment/before/after.json为实际回执，勿覆盖。真实自然到期、重启/断网外部观察和自主售后双版仍未由本次替身证据签收，旧批/费用/预留保持。
