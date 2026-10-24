# 导出所见两次试跑对照（0.282）

运行页先明确选择两条普通单轮记录并读取对照，再“下载所见对照说明（MD）”。说明包含所见输入/预期/输出、来源修订/App/环境及条件差异和全部限制。只导出保存记录，不重新评价、重跑或宣称质量提升，旧通过不继承。

导出同时绑定可见snapshot_token和完整所选来源的export_token。后者将原记录和当前任务类型/环境/App纳入有界原始指纹（最多8MB），即使敏感字段被隐藏、可见对照没变化，来源实际变化也会409。导出期间再次核对来源，不返回混合说明。无法完整标记来源时仍可查看对照，但不能导出；报告最多200KB，不截断部分返回。

原对照中缺失、超限、无效或需脱敏字段保持“未作比较”，不在文件里展开。输出以长度匹配的Markdown代码围栏保存，业务文字不能关闭围栏成为文档指令。指纹不是签名、历史来源或实时平台证明；文件仍可能含普通业务文字，分享前须审阅。

GET /api/tasks/{id}/run-comparison/report，查询revision/before_run_id/after_run_id/snapshot_token/export_token。只读Store，响应text/markdown和no-store及X-Sierra-Revision/Comparison-Token/Export-Token，文件名run-comparison-rN.md。旧修订/观察/来源变化拒绝，不解密、不写任务预算、不触发模型/Dify。页面离开或作用域变化会取消迟到下载，响应标识不符不下载。

新增13/相关32后端检查、隔离实际界面5、两个实际Markdown下载与来源变化409/错标识/迟到拒绝通过，TypeScript/构建及按钮截图通过，未全量。首次截图滚动绘制未完成，等待绘制后确认按钮正常，无产品布局修改。临时Store清理，原16对象/密文/主Key/旧回执/unknown预留精确保持，真实模型/Dify0；不是最终业务验收。Claude网关此前超时，本批未为形式重试或声称完成审查。

[验证结果](run-comparison-report-result-20261025.json)
