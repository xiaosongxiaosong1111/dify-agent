# 节点级知识检索配置

版本 0.28.0，Workflow／Chatflow 顶层知识检索节点。原生 Agent 的知识集配置继续走独立契约，迭代内部检索未纳入本批。

流程页按节点列出选库来源、Top K、分数阈值和模型重排。可以读取已有知识库目录／实际 rerank 模型目录，主动选择后填写本地流程草稿；目录读取及草稿编辑不检索、不保存、不导入、不运行，也不会新增资源。保存后需要重新核对并确认配置。

## 生成契约

- dataset_source 可为 task 或 node。task 继承任务默认选库且不得携带未生效的 dataset_ids；node 必须明确非空、唯一的 dataset_ids，空列表不能回退。没有 dataset_source 的旧计划保留已有兼容行为：非空节点 IDs 优先，空或缺省使用任务默认，不能把此旧路径称为独立选库。
- top_k 是正整数，未指定时使用任务 retrieval_top_k。
- score_threshold 为 null 或未提供时关闭；启用时须明确 0—1 有限数值。界面启用后不猜数值，未填写不能保存。分数在不同知识库／模型之间不能直接类比，可能过滤全部结果，必须确认无命中行为并纳入试跑。
- reranking_enable 缺省 false。明确 true 时必须完整提供 reranking_model={provider,model}，采用 Dify 的模型重排策略 reranking_mode=reranking_model；与 LLM 的型号和参数分开，不自动继承。false 时不得携带未生效的重排模型，界面明确关闭会移除该模型字段。
- 不支持节点权重重排、单库模型路由、元数据过滤、附件／视觉检索或修改库自身检索方式。未知配置字段阻止保存，不静默忽略。

模型重排可能增加延迟、限流、插件依赖与费用，不计入 Sierra 助手预算。目录声明可用、静态参数和 IDs 不证明真实重排／库权限／索引状态可用。Dify 的多个库采用不同索引策略时可能需要模型重排；高质量库的 Embedding 与跨库兼容性仍需实际核对，不由静态图保证。

## 人工修改保留

支持实际 multiple 检索模式、阈值及明确模型重排的原生参数，原文件字段保持不变。单库／备用 single 配置、权重或未知策略、元数据条件、附件／视觉会阻止采用，保留完整原文并说明具体限制；不通过删除这些配置后宣称完成。未声明重排开关的原生节点采用 Dify 的默认 true 语义核对，因此缺少所需模型不能冒充已明确关闭。

目标源码依据：Dify 1.17.1 api/core/workflow/nodes/knowledge_retrieval/entities.py、knowledge_retrieval_node.py、api/core/rag/entities/retrieval_settings.py、api/core/rag/retrieval/dataset_retrieval.py。本机原生实体解析只证明结构兼容，不是实际知识检索或供应商调用。

backend/tests/test_retrieval_settings.py 覆盖来源、不回退、阈值边界、参数／凭据拒绝、重排影响、保留限制和隔离最终文件保留。实际全量与页面证据以 development-status.md 为准。
