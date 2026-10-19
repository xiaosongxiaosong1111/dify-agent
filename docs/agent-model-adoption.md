# 明确采用合并预览模型配置

0.217已部署0.217.0-72517ecfefe057bfc31e（215文件），原11任务／密文／密钥和七模型契约保持。目标Dify1.17.1／DSL0.7.0。

构建页分析原生Agent手改保留后，模型不同且完整参数能表达时，先核对合并预览与当前已选的差异，再勾选“确认采用预览模型并稍后核对资源费用”，点击“采用预览模型配置并创建新修订”。这是明确的本机Task配置更新，不自动调用模型、Dify、发布或创建资源，也不等于保留方案／配置／资源已确认。

若存在冲突，须全部明确选择；改变的选择先保存为本机合并草稿，防止采用时丢失进度。新修订后旧草稿仍显示为历史，原文可读但不沿用审批；须重新分析，并按原流程确认保留、需求及配置后构建。无法完整表达的模型参数不提供部分配置，不能重复采用相同模型制造修订。

API POST /api/tasks/{id}/dsl-merge/model-configuration，严格绑定revision/reference_id/merge_token/document_token/draft_revision/choices和acknowledge_pending_resource_review。最终参数由服务器重新计算，不接受客户端configuration覆盖；整个model_parameters替换，不继承旧型号隐藏扩展。配置中的助手服务、资料范围、资源说明与凭据不变，仍需用户复核目标模型可用性和费用。其他未适配能力仍在完整来源内并阻止保留确认，不因修正模型而删除或通过。

修改前保存原版本；推进修订、清除旧artifact/dify_app_id、使旧overlay/配置确认及运行证据不适用于当前修订。保留源引用、旧文件／版本及合并草稿，新增local_configuration_only采用审计。源环境改变、旧token、活跃Task、过期计划或并发草稿版本不匹配均拒绝。

139相关20.51秒、6组件、13源及13生产GUI／截图/build过；完整4577项通过569.61秒、372冻结输入保持、1条既有Starlette警告。主538.74KB体积提示保留。部署检查work/agent-model-adoption-217-deployed-check.json；所有行为验证在临时Store／合成界面，不是实际Dify或业务验收。Claude第9展示组件由根改标签／采用说明，关键API和绑定／参数逻辑根实现。
