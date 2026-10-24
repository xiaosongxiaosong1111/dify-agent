# 历史输入载入自由试跑草稿（0.281）

修改后重新核对输入时，运行历史现在可明确“预览此记录的输入”，再“载入为自由试跑草稿”。先查看全部保存输入及来源提示，再替换当前输入文字；自动清除当前固定样例选择和会话选择，不复制旧预期、旧通过或conversation_id，不运行或保存任务。

仅当前任务中唯一、明确类型且已成功/失败结束的普通单轮记录。未知/在途/平台待处理、多轮/续聊/文件记录不能据此重试或丢弃上下文。只支持最多100字段、128KB的完整标量对象，嵌套对象/数组、会话标识、无效数字/编码及已识别凭据拒绝整份，不截字段或脱敏后冒充完整输入。

保存值由后台生成JSON文字，大整数不经浏览器解析再编码，保留精度并提示数值待核对；实际发送仍走原数值/入口/资源门禁。跨修订/App/环境只表示载入文字，不证明当前入口相容、凭据可用或已有运行授权。编辑当前输入、改变任务/修订/样例/会话、来源刷新使旧预览失效，迟到响应不能覆盖新草稿。自由草稿仅页面内存，刷新前自行保留。

GET /api/tasks/{id}/runs/{run_id}/input-copy-preview?revision=当前修订，只读Store且no-store，响应绑定task/revision/run、原修订/状态、input_text与SHA256、numeric_review_required及说明；verification=saved_scalar_input_draft_only，task_changed/network_requested/automatic_execution/business_verified/case_copied/conversation_copied/current_schema_checked均false。不解密、不写预算或任务、不请求模型/Dify。

新增22/相关41后端和实际隔离界面6通过，覆盖错源拒绝、先预览后载入、清样例与会话、输入变化/迟到失效、大整数文字保留及未知来源拒绝，TypeScript/build/截图通过，未全量。临时Store清理，原16全部对象/密文/主Key/旧回执/unknown预留保持；真实模型/Dify新增0。只补人工修改后的输入准备，不是自动重跑或完整业务验收。Claude网关此前超时，本批未为形式重试或声称完成子审查。

[验证结果](saved-run-input-result-20261025.json)
