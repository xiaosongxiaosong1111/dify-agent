# Dify 1.17.1 DSL 适配范围

适配器目标是 Dify **1.17.1**，App DSL 版本为 **0.7.0**。版本值来自官方 tag 的 [`api/constants/dsl_version.py`](https://github.com/langgenius/dify/blob/1.17.1/api/constants/dsl_version.py)。官方导入服务 [`api/services/app_dsl_service.py`](https://github.com/langgenius/dify/blob/1.17.1/api/services/app_dsl_service.py) 将 `workflow` 和 `advanced-chat` 初始化为 workflow graph，并对 `agent` 使用单独的 Agent package 导入路径；因此本适配器只接受 `workflow` 与 `advanced-chat`，对 Agent 明确报错。

适配器读取官方源码副本位于 `work/dify-source/`，包括 `api_constants_dsl_version.py`、`api_services_app_dsl_service.py`、`api_core_workflow_nodes_knowledge_retrieval_entities.py`、`api_tests_unit_tests_services_test_app_dsl_service.py` 和 `api_core_workflow_generator_builder_prompts.py`。其中官方 1.17.1 检索节点实体 [`entities.py`](https://github.com/langgenius/dify/blob/1.17.1/api/core/workflow/nodes/knowledge_retrieval/entities.py) 将 `dataset_ids` 与 `retrieval_mode` 定义为必填字段；多路检索配置使用 `top_k`，并支持 `score_threshold`、`reranking_enable`、`reranking_mode` 等字段。官方同 tag 的 workflow builder schema prompt [`builder_prompts.py`](https://github.com/langgenius/dify/blob/1.17.1/api/core/workflow/generator/prompts/builder_prompts.py) 展示了 LLM、开始、结束、回复及检索节点字段。官方 `test_app_dsl_service.py` 覆盖导入、版本和依赖处理行为，没有提供可复用的完整 workflow/chatflow DSL fixture；因此这里只按同 tag 的服务实现及节点 schema 建立线性图，没有声称官方 fixture 验证或真实导入验证。

`workflow` 图包含必填字符串输入 `start.variables.query`，节点路径为开始、可选知识检索、LLM、结束；`advanced-chat` 保留开始节点但不声明自定义输入，LLM 通过 `{{#sys.query#}}` 使用 Dify 系统输入，终点为 answer。知识检索使用真实配置 `dataset_ids`、`query_variable_selector` 和 `retrieval_mode: multiple`，并将检索结果交给 LLM context。未提供 dataset ID 时不创建检索节点，不生成资源 ID。

导出只使用 `dify_model_provider`、`dify_model` 和确认过的采样参数，不写入凭据。App DSL 的 `dependencies` 保持空数组：官方 [`PluginDependency`](https://github.com/langgenius/dify/blob/1.17.1/api/core/plugin/entities/plugin.py) 结构需要安装来源和实际 marketplace/package plugin unique identifier；锁定模型 provider 插件需要目标环境中的实际版本与唯一标识，离线 compiler 没有这些信息，不能编造版本或哈希。validation 会提醒部署环境需具备指定 provider。`mock_dependencies` 会同时写入 app 描述并产生模拟警告。

初始简单 DSL 适配器 (`backend/app/dsl.py`) 只把八项需求文本合并进一个 system prompt，并生成单条直线流程；多节点能力由下文独立的 Workflow Plan 编译器提供。即使使用计划编译器，复杂业务语义是否正确也需人工审核。静态 YAML/图校验不能证明 Dify 成功导入、模型可用或运行结果正确。

## 多节点 Workflow Plan v1 编译器

`backend/app/workflow_plan.py` 根据 [`docs/workflow-plan-contract.md`](workflow-plan-contract.md) 编译显式节点图。支持 `start`、`llm`、`knowledge-retrieval`、`if-else`、`code`、`template-transform`、`http-request`、`end` 和 `answer`。它使用 Dify 1.17.1 控制台节点默认配置与类型定义构造原生 node data 和 ReactFlow edges；if-else 分支 handle 使用 case id 与 `false`，HTTP 使用 `authorization: {type: no-auth, config: null}` 及 Dify 的 `body: {type, data}` 结构。DSL 外层版本仍是 0.7.0，dependencies 留空，因为没有可验证的插件依赖唯一标识和版本。

计划校验和 DSL 编译分开：人工保存计划时，可在尚未确定模型的阶段检查图结构并给出警告；生成含 LLM 的 DSL 时，必须从 task configuration 取得非空的真实 `dify_model_provider` 与 `dify_model`，缺失时返回错误且不输出 YAML。不会猜模型、provider、dataset id 或 HTTP URL。HTTP 节点目前仅允许 Dify tag 定义的 GET/POST/HEAD/PATCH/PUT/DELETE 方法，认证只支持 no-auth；不接受 URL 凭据、secret query 参数、Authorization/Bearer 等凭据字段或文档占位域名。

该支持范围是经过结构、图及变量静态检查的编译器切片，不代表对任意 Dify workflow 的完整兼容。计划必须是无环图；所有节点需能从 start 到达且通向终点；条件节点的每个 case 与 false 出口都需要边。变量引用必须来自当前节点所有执行路径的上游（跨分支引用会拒绝）。Code 只做语法解析，永不在后端主机执行，运行环境必须是 Dify 沙箱；HTTP 远端行为、插件依赖安装、真实 Dify 导入和实际运行均未验证。Agent、循环、迭代、人工输入等未在支持集合中的类型会明确报错，不会被降级替换。


## 2026-10-09 本机真实验证补充

技术 Workflow 的 DSL 已由本机 1.17.1 实际导入、发布，并在 Dify Sandbox 运行两个文本清理样例通过。未覆盖所有节点和应用类型，不能据此宣布通用兼容。官方实际导出样例保存在 work/dify-actual-export.yaml（include_secret=false）。

Docker 配置中的 CODE_EXECUTION_API_KEY 必须与 SANDBOX_API_KEY 对应的 Sandbox API_KEY 保持一致，不能独立随机生成；本机首次代码执行 401 已因此修正。只修改运行服务配置，未绕过沙箱认证或将生成代码移至主机执行。详见 dify-live-validation.md。


## 模型、检索与队列补充

官方 DeepSeek 插件实际包 0.0.24、deepseek-flash、经济关键词库和六节点 Chatflow 的命中／无结果／人工提示三项样例真实通过。开场白、建议问题、thinking=false 和 max_tokens 在实际导出中保留。Console 模型规则／目录真实读取；限定单库 Key 对全局目录的 403 依官方权限处理。

随机化 REDIS_PASSWORD 后，CELERY_BROKER_URL 中的认证必须同步，且须验证 URL 非空有效；仅容器 running 不证明索引队列可用。本机已修复并真实 Ping、完成一份虚构文档索引。详见 rag-live-validation.md。未宣称全量节点／插件或检索策略已兼容。
