# 公开批量平台执行器（第179）

这是已验证冻结包的公开源码副本，不含授权、生产数据、密文摘要清单或消费回执。源码与 `work/batch-platform342/manifest.json` 逐文件相同，供审查和版本保存。

唯一真实入口为项目根的 `.venv\Scripts\python.exe work\batch-platform342\execute.py live`，仅收到绑定冻结方案的新直接用户批准、完成批准记录后才可调用。公开副本的 `execute.py live` 会因目录不符拒绝，不能复制批准到其他目录重放。`plan.json`、`manifest.json`、`approval.json`、`attempt.json` 和日志留本机，均不提交。

执行器从正常新Task、人工intake受托核对和确认门禁构建，只允许新App/发布/Key/运行各一次。所有HTTP先检查边界并落消费计数，任何异常停止；原16任务、原配置/账本/密文及任务文件保持，仅专用连接的批准续接/运行Key配对及新回执允许变化。根服务日志是运维追加日志，不作为冻结业务文件。

`local_rehearsal.py`、`rehearse_platform.py` 和 `gates_check.py` 是隔离验证程序；实际临时Store与替身HTTP，不能据此宣称真实Sandbox通过。先读[冻结方案](../../docs/public-batch-platform-plan-20261027.md)。
