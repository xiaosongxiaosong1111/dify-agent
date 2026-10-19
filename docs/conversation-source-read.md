# 原会话来源本机只读核对

0.136已部署。选中带自定义入口的Chatflow来源后，只读当前最终成果与本机来源绑定；不解密serviceKey、不请求Dify／模型，不改Task或保存核对记录。

GET /tasks/{id}/conversation-input-source/{run_id}绑定当前revision及已读成果source_sha256。只匹配本Task唯一来源、当前登记App、原环境地址版本、当前成果、成功自由记录、原输入／CID及运行密文版本。只返回范围与状态元数据，不返回原输入、CID、私有输入／凭据摘要。platform_checked、business_verified、runtime_inputs_checked、credentials_decrypted及network_requested均false；网络字段指未请求目标平台／模型，本机前后端仍使用localhost API。

source_binding_valid true表示本机原来源匹配，尚未检查本次新参数或确认远端会话／凭据仍有效；false明确说明当前不能复用的原因；索引暂不可读返回null／unknown，不伪装没有记录或已失效。入口／修订改变409不混用旧成果。无自定义入口不将结果当普通会话许可。

界面主动说明本次参数与原参数的差异，先恢复原参数或明确新会话，不能因来源本机匹配就发送改变的参数。可手动重新读入口／来源，不自动平台轮询；错误验证等级、另一Task／修订／Run／成果回执不采用。“改为新会话（保留本次JSON）”只清本地来源选择，当前问题和输入保持，不立即创建CID、取消或还原旧平台会话。实际试跑仍逐次重新核对。

JSON数字1和1.0按同一数值处理，但不转换发送值或改原历史；布尔、数字文本、null与省略仍不同。初始参数其它变化依旧拒绝。自动复制遇到浏览器不能无损保证的非有限值或超安全整数范围时停止说明，保持原JSON，不舍入或转null；高精度业务须明确使用合适的文本／代码方案并验证。

验证：14新增，93相关通过15.75秒；来源仅读测试禁止secret/cipher.decrypt、平台／模型和预算，Task／私有记录保持，不回显CID／原值／私有hash。覆盖已失效、未知、App／revision／hash／应用类型与数字不转换。14页面／视觉通过，7来源GET全fixture、真实写0／Task不变；构建主502.58KB既有体积提示。完整2718项通过304.26秒，idle-owned部署／runtime核对；没有真实Dify或供应商调用，不算客户业务验收。
