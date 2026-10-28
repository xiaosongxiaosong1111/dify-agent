# C1原空需求任务的独立357执行器

复用指定18中空需求Task，保留旧失败/消息/版本/费用；不新Task。源自已修复的199代码，源目录不能live。只有固定work/c1-existing357全18文件、独立新直接授权及明确改授/新增边界均满足后，才能唯一执行live；本次只冻结并隔离验证，没有approval/attempt或新真实HTTP。

源码freeze.py依赖本轮只读恢复后的work/c1-existing357-check/post-start-data-snapshot.json；不能复用旧17任务基线。reuse_policy.py固定空需求/配置/两例/4次20分钟及原settled，guard.py保护旧17及所选Task历史前缀。预算允许旧1条加新最多5条，不修改旧费用，不扩大运行策略。正常及6停止/HTTP200拒绝复现由外部tools/check_c1_existing357.py和check_c1_rejected_intake357.py检查，源码和冻结门禁逐字匹配；不运行全量。

具体范围/成本/双摘要见docs/c1-existing-task-plan-20261028.md，旧354永久消费不变。结构替身复核不是语义通过；五处真实内容需根代理逐项阅读source并显式登记agent_delegated。
