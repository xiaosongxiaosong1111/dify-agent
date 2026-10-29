# 历史版本正文只读查看

原历史页只列变更字段、节点数量及影响，无法直接核对旧需求或提示词。现在先选择“比较与恢复”，打开“只读查看此历史版本正文”，明确选择需求、配置、完整Workflow、Agent或验收样例，再点击读取；不必恢复旧版或使当前确认、成果和App失效。当前编辑与旧运行状态保持，不把历史文本装入草稿。

每页最多4000个Unicode码点，整份所选保存值最多2MB UTF-8；上下页都绑定比较时的当前修订、Task/版本身份和完整来源摘要。来源变化、未知分区、越界页、重复版本身份、缺失旧字段均拒绝，不以当前内容补齐旧快照。历史修订无可靠正整数时显示未知。大整数保持在JSON文字中，避免浏览器对象舍入；代码/模板只显示，不执行或解析为HTML。

新端点为`GET /api/tasks/{task_id}/versions/{version_id}/content`，参数`revision, section, snapshot_token, offset=0, limit=4000`；snapshot_token来自原只读restore-preview的review_token。本接口只读取五类所选历史保存值，不读取材料原件或凭据库，不解密、不恢复，不返回模型供应商原始响应或材料文件原字节或业务通过结论；所选保存值疑似含明文凭据、非法编码、非有限数值或超过界限时整份拒绝，不泄露部分正文。查看普通历史需求和流程不调用模型或Dify。

响应含Task/当前与历史修订/类型/版本/分区、snapshot_token、全内容及本页SHA256、字符/UTF8总数、offset/next_offset/text；source_kind=historical_saved_value_json、verification=local_history_content_read_only，task_changed/network_requested/platform_checked/business_verified均false。内容是历史保存值重新序列化的JSON，不是原文件字节；摘要不作签名、来源认证或恢复批准。原恢复入口、令牌及影响确认门禁保持。

第221于2026-10-29部署0.353.0-c7c4b4aa476ce7fa1e1e，288源/快照文件匹配；旧352/PID13540归属证明后使用原stop/start，新PID29440核验。33新增/31原恢复共64项定向后端检查、类型检查/正式前端构建、9实际浏览器场景及视觉通过。浏览器覆盖显式选读而非自动读、Unicode翻页、精确大整数、代码仅文字、切换快照后晚到响应拒绝、错版本/分区/页摘要/整源/flags、409与404失败不重试。替身使用公开临时Store，原Task和账本保持，未访问生产、凭据或真实外部服务；首个辅助脚本曾因Store收到str路径在浏览器开始前失败，修正Path后完成，日志保留，不冒称首轮通过。

实际8765当前售后Task仍r17/run_completed，正常历史页读取r9完整3265字符流程一页，完整JSON与保存值相等，仍为原固定文字；未恢复到r9或触发第五次运行。生产18/六费用/全部密文资产与消费包核对保持，部署仅server.pid变化，health和前端200。不是新的Dify业务验收，固定C1既有两版四例保持，原25/Chatflow订单链缺证不升级。

[安全结果](history-content-result-20261029.json)。定向验证：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_version_content.py backend/tests/test_version_restore.py -q --basetemp work/NEW-HISTORY-TESTS
# 先在frontend目录执行tsc -b和vite build，再回项目根：
.\.venv\Scripts\python.exe tools/check_version_content_ui.py --output work/NEW-HISTORY-UI --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
```
