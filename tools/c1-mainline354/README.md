# C1新空任务同一用户流程：新独立执行包

实际live仅允许原work/c1-mainline354目录、固定全文件哈希与新的直接批准；缺批准不构造生产Store。attempt及worker-started各一次，不能重放或阶段重试。源目录不能live。

`worker.py`通过同版产品API和前端创建新Task，保护17旧Task及全部账本/密文资产；源码受限工作区只列本批Task与所选资源。五次实际内容需根代理按源摘要明确复核；`submit_review.py`的agent_delegated不是人类批准或资源许可，拒绝/额度不足写stop标记，运输前再次检查。

本机预检：先有已冻结work副本，再执行根tools/check_c1_rehearsals354.py，指定新的work输出和固定绝对Playwright路径；正常/6停止检查来源和精确计数。源码目录的gates_check.py另核62门禁，与冻结字节相同；其“源目录不能live”测试故意只在源码目录调用。不运行生产live或生成实际批准。synthetic.py只在非live分支作SDK末端替身，实际live严格使用原HTTPX运输；fixture中的完整图只供替身，不能放入真实Task绕模型生成。

精确配置及扩展参数由普通修订API保存，轨迹用普通诊断API；其余关键用户操作和主动候选采纳用界面，不声称全流程只有鼠标操作。完整独立范围、费用及旧账本保留见docs/c1-blank-task-plan-20261027.md；冻结plan内生产快照只保存在work，禁止提交。
