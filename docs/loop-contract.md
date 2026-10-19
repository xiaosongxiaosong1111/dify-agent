# 有明确停止与无进展保护的循环

版本 0.31.0，Workflow／Chatflow 的首批单层循环。循环反复更新状态；迭代逐项遍历数组，不能相互替换。

## 准入与配置

循环需求必须确认初始状态、每轮处理和更新、停止条件、初始即达目标的返回、最大轮数、进度字段及理由、连续无进展上限、错误和次数耗尽行为。未明确时继续追问，不能以固定默认值代替业务决定。需求页新增“循环停止与保护”主题，已存在但缺该检查的评估可能需要重新复核。

loop config 必须完整包含：

```json
{
  "loop_count": 3,
  "loop_variables": [{"label":"count","var_type":"number","value_type":"constant","value":0}],
  "nodes": [{"id":"increment","type":"code","config":{"code_language":"python3","code":"def main(count: float) -> dict:\n    return {\"next_count\": count + 1}\n","variables":[{"variable":"count","value_selector":["repeat","count"]}],"outputs":{"next_count":{"type":"number","children":null}}}}],
  "updates": [{"variable":"count","value_selector":["increment","next_count"]}],
  "break_conditions": [{"variable_selector":["repeat","count"],"varType":"number","comparison_operator":"≥","value":"3"}],
  "logical_operator":"and",
  "failure_policy":"terminate",
  "limit_policy":"fail_if_unmet",
  "no_progress_limit":2,
  "progress_variables":["count"],
  "progress_reason":"计数每轮增加，代表固定三次技术处理进度；不是客户业务验收。"
}
```

示例的节点 ID 为 repeat，count 是明确业务状态，不代表所有业务应采用这种规则。流程页样例只填草稿，需修改、保存和确认。

- loop_count 明确 1—100，为 Sierra 首批支持范围。不是 Dify 全平台统一最大值，不静默缩减更大需求。
- 1—12 个唯一状态变量，var_type 为 string／number／boolean；初始值可为严格对应常量或外部必经上游变量，未知类型须先用代码声明。数值有限且在 ±10^12，字符串至多64000字；不自动把文字转数字或布尔。保留命名／凭据字段不能使用。
- 1—12 个顺序代码／模板／文字 LLM；不支持内部条件、嵌套、HTTP、检索、人工节点或并行循环。每个状态都须通过 updates 唯一对应一个本轮内部匹配类型的声明输出；所有处理完成后统一进行原生 v2 变量赋值。
- 1—12 个停止条件，仅引用本循环状态。number 支持 =／≠／>／<／≥／≤，右值为有限数值文本；boolean 支持 is／is not，右值为 true／false；string 支持 is／is not／contains／not contains／start with／end with／empty／not empty，右值为文字。明确 and／or，不支持嵌套或变量右值。
- progress_variables 为非空唯一状态字段；progress_reason 说明它们为何反映业务进度。任何所选值变化表示本规则下有进展，连续2—10轮全部未变则失败。字段变化不证明语义改善；目标已满足时优先完成，不因进度值相同而错误拦截。
- 首批固定声明错误即终止、次数耗尽而目标未达即失败；其他返回最新／跳过／继续策略未支持，不能替用户默认接受。

## 原生适配及保护

目标 Dify 1.17.1 的 graphon LoopNodeData 初始化状态后检查条件，允许零轮完成。其 handler 达到次数时可返回成功，不能直接等同业务目标达成。Sierra 额外生成入口类型／范围检查、内部无进展保护、v2 assigner 更新、外部停止条件复核。普通 source 出口全部经过复核，停止未达抛出明确失败；不能声明特殊失败出口绕过保护。

仅公开声明的用户状态输出，不公开内部进度计数或假设初始零轮时有 native loop_round；需次数作为业务输出时，显式声明并更新相应状态。内部值不能被外部直接引用。内部模型使用独立或继承配置，不读取 Chatflow 历史。

保护代码本机只做语法检查，运行仍属于 Dify Sandbox。尚未实际验证完整循环或生成保护节点，不把实体解析、源码核对或隔离接口当整图成功。原生状态和 v2赋值的字段依据为已安装目标 loop.entities、loop_node、loop_container_handler、variable_assigner.v2.entities／node；不是猜测主分支格式。

## 费用、保留与验收

最大轮数和连续无进展限制不能当 USD 费用硬上限。每轮全部显式 LLM 节点都可能调用，代码中隐式外部行为未计入；实际价格、输入长度、平台超时和限流须核对。结果未知时仍禁止盲目重跑。

已安装 Dify 的状态初始化和 v2赋值节点另以全新内存池核对：标量初始值、false／0、返回变量更新事件及原池不被节点提前改写。此四项不是完整引擎、生成保护代码或真实模型运行证明。

循环文件可读取／保存原文，但首批手改保留未适配，会阻止采用；不删除循环或保护再算完成。资源创建与实际试跑仍须按具体方案确认，当前开发不重复旧 iteration-live.py 或使用旧一次性模型授权。

验收至少包括初始即达目标、正常停止、连续无进展、次数到但目标未达、状态类型错误、模型失败、旧修订及未保存门禁。结构、声明和语法检查不证明进度字段语义正确或真实业务已交付。

## 2026-10-12 六固定纯代码场景真实证据

原0.36包保持批准SHA与manifest冻结；用户批准六新技术应用及同实例管理连接来源，normal3正文轮、initial-goal0轮、limit-unmet2轮失败、no-progress2轮失败、invalid-update-type1轮失败、goal-priority1轮成功均实际核对通过。每项唯一一次运行，normal／其余4项各一次发布；initial-goal第一次过长版本标签422，确认未发布后经单独追加批准第二次发布，不重导入或重跑其他项。结果及App/run ID、图摘要／轮数来源见 ../work/loop-runtime-validation-report.md 和 live-result.json。这不是客户业务、任意复杂循环或整个项目通过；无模型调用，不扩展旧付费授权。
