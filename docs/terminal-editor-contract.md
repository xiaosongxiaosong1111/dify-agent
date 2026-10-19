# 最终回答与返回字段

0.52.0 在流程页直接编辑 Workflow end 返回字段，以及 Chatflow answer 最终回答。只改选择的终点草稿，不改其他节点或连线；保存后重新确认、构建与按样例验证。可信当前终点诊断可等待编辑器加载并定位，不自动修复或重跑。

end 逐项填写返回名称和实际两段 value_selector，可主动添加或删除；新增项先留空待填写，不自动命名或选第一个候选。候选仅列所有路径上游变量，部分分支结果不列；已有手填引用不删除，保存由后台检查。LLM 候选仅列当前文字适配的 text、usage、finish_reason，不把未启用的结构化／视觉输出当作已经可用。

完整 outputs JSON 可独立编辑；非法 JSON 保留原文，未适配结构不能被简化或丢字段。可选 value_type 原文保持，只通过 JSON 明确调整，不随选择变量自动转换。Dify End 原样收集上游值，value_type=secret 也不提供自动脱敏，配置该类型时后台明确提醒先确认敏感数据处理规则。

answer 的完整文字和变量引用直接编辑，数组／对象的展示方式须明确，不因引用存在就算回答正确。完整视觉、工具、复杂流式输出模式仍未适配，不能放入 config 后静默忽略。

后台新增约束：end config 仅 outputs，answer config 仅 answer；end 每项仅 variable、value_selector、可选 value_type。最多 64 个返回项、名称非空且最多 128 字符；同名结果会在原生节点字典中覆盖，因此生成前拒绝，不静默删项或改名。value_type 按固定 Dify 1.17.1 OutputVariableEntity 枚举核对，保留兼容 Array[...] 原文。额外常量／模式字段拒绝。来源存在、完整两段和全路径支配检查沿用原规则。

验证：30 新增后台检查，最新完整 **1427 项通过**，既有 Starlette 提示 1；前端构建、10 项受控终点／回答／诊断定位检查及视觉核对通过。真实任务前后相同，全部写请求禁止；实际 Dify、模型、知识检索或 HTTP 执行 0。固定 Dify 原生实体与 End 收集代码已只读核对；这不是客户业务真实运行证明。记录见 work/terminal-editor-ui-result.json／png。
