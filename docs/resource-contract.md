# 真实资源发现与配置契约

工作台 0.5.0；更新日期：2026-10-09；目标 Dify 1.17.1。

## 模型目录与参数

`GET /environments/{id}/models?model_type=llm` 使用 Console 管理连接，按白名单返回实际 provider/model 标识、显示名称、目录状态、chat 模式、上下文大小和声明能力。不读取或返回供应商 Key、凭据结构、credential 列表或负载均衡凭据。

状态 active 且 chat 模式的 LLM 才可在选择器采纳；disabled、未配置、权限不足、配额超限或未知状态明确标注。目录声明可用不代表实际调用成功或所有能力已验证。缺插件／凭据返回的空目录与失败请求区分显示。

`GET /environments/{id}/model-parameters?provider=...&model=...` 先从新读目录确认模型可选，再读取官方 parameter-rules。provider 路径校验，model 通过 query 参数传递；环境配置在读取期间改变则拒绝旧响应。参数规则只返回名称、类型、范围、选项与默认值等非连接元数据。

界面读取同一模型时保留当前任务参数；“填入事实问答参考参数”才主动预填 Temperature 0.2、输出上限 2048、支持时关闭思考。数值按实际范围预填，用户可调整；复杂推理不能由这个参考方案代替确认。采纳替换任务草稿，保存／复核／确认后才可生成或导入，读取本身不修改任务。

配置 `model_parameters` 接受最多 30 项简单参数，仅布尔值、有限数值、最多 1024 字文本；连接 Key／Token／密码／端点不属于完成参数。Temperature 和 Max tokens 仍使用专用字段。两种编译入口将扩展参数写入每个 LLM 的 completion_params，不悄悄省略 thinking、response_format 等已选择项。界面校验声明范围和选项；同模型旧参数未被目录声明时阻止采纳、要求人工复核。当前尚不支持任意嵌套参数或缺少标准 temperature/max_tokens 名称的模型自动配置，离线手填也不代表已通过真实资源核验。

## 知识库目录

`GET /environments/{id}/datasets?page=1&limit=100&source=console|service`。service 为 API 兼容默认，界面明确默认选择管理连接 console。两种来源不自动切换。

console 读取当前管理账号有权限的目录；service 使用知识库 Key。Dify 1.17.1 限定指定库的 Key 无法读取全局 `/v1/datasets`，返回 403；这不代表它不能访问授权库的文档。工作台说明限制、提供管理目录或保留已知 ID 的方式，不自动扩大 Key 权限，不将失败变成成功空目录。

只返回名称、ID、描述、文档数量和索引方式等元数据。分页合并不会丢失手填 ID；默认选择与节点独立指定的 ID 仍需分别复核。0.6.0 已增加产品内方案确认、建库、全文提交和索引准备界面，经济路线真实通过；详见 knowledge-provisioning-contract.md。此前开发辅助脚本记录仍不能替代该产品流程的证据。

## Chatflow 配置

`opening_statement` 为最多 4000 字文本，`suggested_questions` 最多 6 项非空文本、每项最多 500 字。保存到任务并由基础模板和多节点编译器保留到 workflow.features。界面开场建议不等于完整多轮记忆、追问策略或需求覆盖检查。

## 已有真实证据

本机安装 Dify 官方 DeepSeek 插件 0.0.24 并用用户已提供的 Key 配置，实际目录包含可用 deepseek-flash。虚构政策经济关键词库和六节点 Chatflow 实际导入、发布、运行；命中／无资料／人工核实三项声明规则通过。实际节点轨迹证明无资料分支没有执行 LLM。详见 rag-live-validation.md。
