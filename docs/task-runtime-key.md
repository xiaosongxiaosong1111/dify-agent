# 运行页登记当前App的运行Key（0.250）

运行页直接展示当前导入App、目标环境、当前Key是否与App配对及共享环境任务数。用户填写Dify应用运行Key，明确确认后，只在本机加密保存并绑定当前App；不用手工复制App ID去环境设置。DeepSeek模型服务Key用途不同，仍在模型服务设置管理。

- 只接受同修订/环境/App的成功导入记录及存在的当前成果。状态摘要绑定任务、修订、成果字节、暂停代数、环境地址/版本/连接修订/空间、当前运行Key指纹与共享环境任务集合。
- 明确确认时持锁重新核对。状态、共享任务集合或旧Key变化后旧令牌失效；任务/环境有在途操作或当前任务暂停则拒绝。
- 仅原子更新service_app_id、加密service_api_key、连接修订和runtime登记未核验状态。需求/配置确认、成果、App、模型服务、Console登录、知识库Key及归档Key保持。相同绑定和Key提交是无操作，不抖动密文或连接修订。
- 请求JSON严格限制字段/类型/体积/重复键；手工验证错误不回显Key。响应只有存在/配对标记及元数据，UI密码框提交即清空，刷新不恢复，不写浏览器存储。
- 本版不创建Dify Key、不访问Dify或模型、不自动试跑；本机配对不证明Key属于目标App或仍有效。用户仍须在Dify取得该App的运行Key，再按获批范围试跑确认。

定向验收：`.venv\Scripts\python.exe -m pytest backend/tests/test_task_runtime_key.py -q` 26 passed；`node work\task-runtime-key-ui.cjs "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"` 8项拦截UI通过；前端构建通过。使用临时存储/合成Key/禁止传输，无真实写入/模型/Dify调用。首次UI脚本因按钮正则转义丢失超时，修正后通过。未重跑全量。

Claude Code现有网关的新契约核对触发error_max_budget_usd，无可用结果且未重试。设置上限0.05USD，CLI返回估价0.08331USD，证明该字段不是派发前账单硬上限；不把它当真实供应商账单或Codex账户额度，不声称审查完成。

用户补充DeepSeek之后，本机两条DeepSeek服务均有已保存Key；当前售后任务原主模型仍有Key，未修改选择、未发送模型测试。模型设置编辑框按设计不回显旧Key，列表“密钥已存”及“留空继续使用”才是保存状态；空密码框不等于密钥丢失。
