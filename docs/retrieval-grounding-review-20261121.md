# 检索证据与基于资料回答的有界复核

2026-11-21，BACKLOG352／清单14，FR23/30/33、AT13。

DeepSeek只读核retrieval_observations.py、相关诊断/资料库检查及售后回答路径，Codex抽查直接代码/用例，并独立执行：

- test_retrieval_observations.py、test_retrieval_query_source.py、test_dataset_configuration_check.py：90项通过。
- test_after_sales_intake_to_graph.py：4项通过，正常空任务到完整双版、逐轮诊断和交付替身链路。

当前原生result完整空列表、返回片段、技术失败、缺失/截断/不兼容证据分别标记empty/returned/technical_failure/unknown。仅保存受限来源ID/有限分数，片段数量/分数不等于相关性或答案正确；诊断追加到原运行并核源修订/环境/App/图，不修改运行结论或自动重跑。查询变量有类型和来源依据，不编造默认问题。

售后双版测试固定无命中文字、资料不足提示与各版回复/逐轮证据/交付绑定。它使用受控候选和模型/Dify替身，不能证明真实模型理解、实际片段相关性、资料不足分支质量或自主双版完成。片段是否足够回答仍须模型和实际内容核对，不添加机械关键词正确性判断。

DeepSeek与根有界复核未发现新的正常入口可复现实质缺口。沿用当前实现，不新增等价测试、不重写提示/编译器、不重复部署，运行保持351的d5348d954c69e689f59a。生产资料/真实产品模型及Dify请求0，旧费用和消费批不改。
