# 当前类型与版本的节点规则查询

0.299在“流程 → 当前生成能力与边界 → 查看节点规则与合成示例”增加只读查询。首批为知识检索、条件分支、Python代码和文字LLM；可按节点选择查看规则、限制、完整合成Workflow Plan、占位配置和来源。示例可复制核对，不会载入或覆盖任务，也不代表任何确认、发布或运行授权。

`GET /api/node-guidance?app_type=workflow&dify_version=1.17.1&node_types=code`只读本机内置条目，不访问Dify、模型或网络。`node_types`省略时列首批全部条目，最多查询16项/每项80字符，重复项去重；暂无条目与“不支持此节点”分别表述。仅固定目标Dify1.17.1/DSL0.7.0，版本不符拒绝，不回退其它版本。Workflow用start.query/end；Chatflow用sys.query/answer。原生Agent不接受这些Workflow示例，仍使用独立Agent Plan。

条目包含固定类型/版本ID、内容SHA256、适配依据、规则和限制。代码的调用约定来自[Dify1.17.1 Python调用器](https://github.com/langgenius/dify/blob/1.17.1/api/core/helper/code_executor/python3/python3_transformer.py)，检索问题类型与结果形状参照[固定版本检索节点](https://github.com/langgenius/dify/blob/1.17.1/api/core/workflow/nodes/knowledge_retrieval/knowledge_retrieval_node.py)。Sierra的额外限制分别来自`code_entry_contract.py`、`retrieval_settings.py`、`condition_settings.py`和`workflow_plan.py`；条件/LLM条目明确标为本机适配依据，没有把本机约束伪称完整上游能力。页面读取时不重新获取或校验上游源码，也不宣称当前连接的实际版本就是1.17.1。

实际规划入口按本任务当前保存的计划节点（含已适配单层容器正文）和需求关键词选取专项条目；不检索其它任务、旧消息或供应商资料，未匹配保持空结果，不猜业务方案。模型仍收到完整契约与能力清单，必须保留已确认需求和现有图；示例EXAMPLE模型/知识库是明确占位值，不能拿来替代真实资源。规则只帮助规划，不自动修图或改变配置。新规划回执保存所选条目ID/摘要及类型版本，便于追溯构造依据；这是当时传入内容的摘要，不是业务正确性证明。新增上下文也由原有费用估算与预算门禁核算，没有扩大调用次数或旧真实批的范围。

18项新检查与相关163项定向通过；四类×两种类型共八个完整示例使用自身占位配置静态编译，未执行代码。实际界面8项检查覆盖按需加载、类型切换、来源/示例、暂无条目、服务失败/错类型结果拒绝及Agent隔离，构建与截图核对通过。相关检查发现旧数字迭代条件夹具声明index却没绑定，已补齐夹具，不放宽生产入口校验。未跑全量或真实模型/Dify。T063/T064仅补首批专项查询证据，不是完整节点专业知识库、全部工具注册或模型生成质量验收；T078独立受限代码样例执行仍未完成。

实现提交0950113。本机部署0.299.0-bc728747737959febd32，260源码/快照一致，health/前端200；原stop/start脚本在管理员权限核实原PID与命令行归属后完成受管理重启，PID登记及新版本核验通过。新接口生产只读核对Workflow4/Chatflow4/Agent0及版本不符422通过，原16任务/设置能力/账本/凭据密文主Key及第124冻结证据保持。工作证明见`work/node-guidance299`，旧失败回执不改写。
