# 原生Agent跨环境草稿预览：开发者接口

后续0.220加入未确认预览的本机保存／旧版本读取API，见[进度API](environment-mapping-drafts.md)；仍无前端或实际采用入口。

0.219已部署0.219.0-3dd2e318eb39134c5809（217冻结文件）。**当前只有开发者API，没有前端入口，也不能直接采用映射。通用T110未完成。** 原11任务／密文／密钥保持，前端及七模型契约不变。

POST `/api/tasks/{id}/environment-mapping/preview`。先GET当前`dsl-merge`或显式选择后的preview，获得revision/reference_id/merge_token/document_token；全部源冲突与静态阻止项先处理。请求再提供独立目标environment_id、完整target_model_json（字符串）、逐库dataset_mapping、必要的新市场插件target_dependency和acknowledge_unverified_target=true。

目标模型JSON形状为：

```json
{"provider":"author/plugin/provider","name":"实际目标型号","mode":"chat","completion_params":{"temperature":0.4,"max_tokens":512}}
```

请求字段名为`target_environment_id`；目标连接已在Sierra存在且声明版本为1.17.1。模型温度、上限和扩展参数必须完整，不继承旧型号隐藏参数；重复JSON／不精确数字／凭据参数拒绝且不回显。`dataset_mapping`是每个源库ID到目标小写连字符UUID的对象，必须全部一一明确对应，不能按名字猜、多对一或漏库。即使两个空间ID字符串相同，也须明确给对应，仍不证明目标资源可用或语义等价。

保留源手改指令、开场、知识集分组／用途／原生ID／top_k及已声明能力。源库显示名／描述不假充目标标签，原值与置空列入变更；集的业务用途不清空。源固定插件依赖不偷偷删除；换插件须补充目标完整市场标识，未核对实际安装／价格。目标配置保留原mock条件并加目标未验证项；YAML应用说明附待验证标记，API的platform/business/target_resources_verified均false，task_modified/can_apply=false。

返回完整目标YAML、目标配置／Agent Plan建议、源／目标命名空间和连接上下文摘要、明确ID映射与参数／标签／依赖／说明差异。preview_token基于源方案／目标上下文／完整结果，重复同输入得到同结果；未来采用仍须另行实现确认流程。源来自Sierra已存保留预览，不声称源Dify此刻最新；目标版本只是本机声明，未请求目标目录或复制凭据。本接口不更新Task、环境、原文件或历史，不导入／发布／运行。

139相关15.34秒、最终映射模块35项9.15秒通过；含全部SQL objects／secrets前后一致、阻止解密凭据、确定性、手改保留、知识集分组、插件条件、同UUID显式对应、应用类型、连接变更、NoEcho和OpenAPI。未重复前端GUI或完整回归，最近完整仍217的4577项。实际部署只核对OpenAPI及已先GET确认不存在Task的两条坏请求均422且不回显输入，未进行真实成功映射／Dify／业务验收。见work/agent-mapping-219-deployed-check.json和api-guard-check.json。

下一步为可恢复的未确认本机映射草稿、前端配置与完整确认流程。更一般Workflow／Chatflow图、资源自动核对、插件真实安装、跨环境实际验收仍未覆盖，不因本接口标记全场景迁移完成。
