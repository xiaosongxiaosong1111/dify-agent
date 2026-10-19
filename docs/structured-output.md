# LLM 结构化对象输出

0.130已部署。目标Dify1.17.1，配置生成应用内的大模型节点，不是Sierra自身供应商能力探测。

流程页“大模型提示词与知识上下文”卡可明确开启 structured_output_enabled 并填写完整 structured_output:{schema:...}。不存在时不默认开启或填示例，未完成JSON原文保留；关闭保留已有schema和下游引用，保存时拒绝引用不可用对象，不能暗中改成text。根以及现有单层迭代／循环正文LLM都使用同一规则，不增加嵌套容器支持。

首批schema根为object，明确properties和additionalProperties:false；支持有限嵌套object/array/string/number/integer/boolean、required、同类型标量enum、文字长度／数组数量／数值上下限。最多64000 UTF-8字节、200类型节点、8层嵌套，每对象50属性。ref、组合、pattern、default、未知关键字或矛盾范围明确拒绝，不静默删规则或转换值。禁用的空schema可作为未完成占位保留，开启时必须补全。

生成映射原生开关与schema；保留检查读实际最终文件，完整规则原文保持。只有明确启用且schema合法才声明整个structured_output为object；text仍string，不推断嵌套属性类型。可以作为代码输入／聚合／最终返回或迭代array[object]来源，支配关系和原有类型规则仍适用。依赖具体属性存在及正确类型的业务应配置明确校验。

目标版本的供应商适配可能改写schema，包括boolean类型与additionalProperties；解析器可能修复JSON，仅得到对象不证明字段遵守schema。Sierra检查的是配置与引用，不是模型真实输出Schema或业务强制保证。选用模型／插件支持、成功与失败样例仍需实际Dify／供应商验证。

依据：本机Dify1.17.1的web/app/components/workflow/nodes/llm/types.ts；api/tests/unit_tests/core/workflow/test_node_factory.py保留开关及schema的实体／构造参数测试；api/core/llm_generator/output_parser/structured_output.py原生模式选择、schema变换与JSON修复实现。此次没有调用这些外部执行链或启动Dify守护进程。

最终DSL验收语义摘要新增完整开关与schema，轻量建议出站范围升级17。旧16策略不允许直接派发，需用户在应用重新查看当前范围后确认；更改范围本身不发送数据或调用模型，不复用旧单次联调许可。

验证：25新增检查，199相关通过4.92秒，6浏览器／视觉全部fixture、真实写0／Task不变，构建通过主501.07KB既有体积提示、提示词面板8.96KB按需。完整2623项通过203.02秒，原11任务及独立资源空闲后owned部署／runtime核对；不计为客户或实际平台验收。
