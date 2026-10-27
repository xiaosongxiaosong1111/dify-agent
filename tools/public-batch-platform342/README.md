# 公开批量平台执行器（第179）

这是已验证冻结包的公开源码副本，不含授权、生产数据、密文摘要清单或消费回执。源码与 `work/batch-platform342/manifest.json` 逐文件相同，供审查和版本保存。

唯一真实入口为项目根的 `.venv\Scripts\python.exe work\batch-platform342\execute.py live`，仅收到绑定冻结方案的新直接用户批准、完成批准记录后才可调用。公开副本的 `execute.py live` 会因目录不符拒绝，不能复制批准到其他目录重放。`plan.json`、`manifest.json`、`approval.json`、`attempt.json` 和日志留本机，均不提交。

执行器从正常新Task、人工intake受托核对和确认门禁构建，只允许新App/发布/Key/运行各一次。所有HTTP先检查边界并落消费计数，任何异常停止；原16任务、原配置/账本/密文及任务文件保持，仅专用连接的批准续接/运行Key配对及新回执允许变化。根服务日志是运维追加日志，不作为冻结业务文件。

`local_rehearsal.py`、`rehearse_platform.py` 和 `gates_check.py` 是隔离验证程序；实际临时Store与替身HTTP，不能据此宣称真实Sandbox通过。先读[冻结方案](../../docs/public-batch-platform-plan-20261027.md)。


2026-10-27/190：源程序dispatch已修原生HTTPX未读取响应/未绑定request时过早解析的问题；SyntheticDify现返回真实传输形态的未读取流。针对性验证backend/tests/test_batch_transport_response.py共16通过，含正常HTTPX登录及全API成功/8类停止；不改任何已消费work/batch-platform342或348，不解冻/重放旧批，源修复不是新的真实授权。

2026-10-27/193：原生1.17.1未发布GET为HTTP200/null，源Boundary现接受该严格空值并保留404兼容；已见发布或发布后缺失不重新放行，已发布图清旧absence。替身默认原生null，27项定向包含两种全API路线及8类停止通过。350真实批已停止，Task/App已创建、本机publish unknown保留，源修复不解除旧一次性锁或授权重放。
