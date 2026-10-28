# 修改版零模型收尾准备（第216，未完成）

216已补零模型收尾所需的严格话术范围核对：只接受已知LLM资料不足提示及无命中模板两处同字面替换，其余完整JSON严格一致；额外节点/边/模型参数/数据源/第三文本、缺失或歧义目标均拒绝，不改候选、不授资源权限。23定向通过，实际当前r13与213已保存模型来源及原版两例/六费用条目/全部旧消费包只读审计通过，原18保持，模型Dify0。完整平台执行器、隔离全链及最终冻结/直接改授尚未完成，216仍doing，不称可真实执行。

这里只修正未来执行包“一项业务改动只能一个字段”的过窄假设，精确允许已观察的两处同话术，不是任意忽略图差异。已消费365及其严格旧检查/拒绝/费用不修改，也不继续旧批。新核对模块只返回局部内容比较，resource_authorized=false；它不是语义验证、真实发布许可或平台通过。

源tools/c1-model-free368/literal_scope.py与audit.py。审计只读SQLite和已有回执，验证当前r13保存图等于第二模型原候选、原版图与213来源摘要一致，六settled/原版两例及18Task和所有旧消费保持；不构造生产Store、不解密、不调用模型或Dify。[当前证据](model-free-closeout-preparation-20261028.json)。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_closeout_literal_scope.py -q -p no:cacheprovider --basetemp work/pytest-model-free368
.\.venv\Scripts\python.exe tools/c1-model-free368/audit.py --output work/model-free368/audit-proof.json
```

下一仍须完成最小独立执行器：当前r13图及静态成果来源强绑定，0新模型/Task/库；拟明确改授365剩28管理读取/新App首次发布Key各1/两运行与原生轨迹，原运行上限4/20分钟不变。为避免等待授权后过期，拟仅新增1加密登录36→37；模型/读取/资源/运行及旧费用边界不增，Dify估0.01 USD非账单硬限。全部副作用需新具体直接批准；当前未批准、未冻结、无attempt，不能执行。实现后先正常/拒绝/异常停止/历史保护隔离，再一次提交可审查整批方案。
